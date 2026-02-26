# Pitfalls Research: ML-Based Adaptive Branching for CBQS v3.0

**Domain:** Adding ML-based branching weight learning to an existing combinatorial optimization solver
**Researched:** 2026-02-26
**Confidence:** HIGH (based on codebase analysis, domain literature, and architecture understanding)

**Key principle:** The existing solver is stable with 446 tests, deterministic reproducibility, and thread-safe parallel solving. Every pitfall below threatens one of these properties. The challenge is not building ML -- it is integrating ML without breaking what works.

---

## Critical Pitfalls

Mistakes that break the existing solver, produce silently wrong results, or require architectural rework.

---

### Pitfall 1: Online Weight Updates That Break Deterministic Reproducibility

**What goes wrong:**
The solver guarantees that `seed=42, num_workers=1` produces identical results across runs. Online adaptation -- updating `branching_weights` during solve based on feedback -- introduces a timing dependency. If weight updates depend on wall-clock time, thread scheduling order, or callback execution timing, the same seed produces different results.

Specifically in this codebase: `BranchingFunction()` in `Branching.h` reads `ctx->branching_stats.branching_weights[index]` on every branching decision (called 7 times across `solver.c` CSearch functions). If those weights change mid-solve, the sequence of branching decisions changes. If the change is triggered by timing-dependent events (e.g., "update weights after 10 seconds"), determinism is destroyed.

**Why it happens:**
Developers think "I'll just update weights in the callback." The callback (`_history_callback_fn` in `SearchLib.pyx`) is triggered after each global_opt update, which happens at non-deterministic wall-clock times in multi-worker mode. Even in single-worker mode, callbacks are invoked from a `with gil:` block at unpredictable points relative to the C search loop.

**How to avoid:**
- Tie weight updates to deterministic solver events, not wall-clock time. Use iteration count, improvement count, or sampling round number as the update trigger.
- In multi-worker mode: do NOT share adapted weights between workers. Each worker gets its own copy of weights at solve start. Only aggregate learned weights after solve completes.
- Make the adaptation schedule depend only on quantities derivable from `seed` and solver state (iteration count, objective value), never from `time.time()` or `time.monotonic()`.
- Add a regression test: run the same model with `seed=42, num_workers=1` twice with online adaptation enabled. Assert `result1.solution == result2.solution`.

**Warning signs:**
- Determinism tests start failing intermittently (not always -- timing-dependent).
- `test_same_seed_same_result` in `tests/test_determinism.py` passes locally but fails in CI (different CPU speeds change timing).
- Results vary between runs with the same seed when `num_workers > 1`.

**Phase to address:**
Online adaptation design phase. Must be resolved before any adaptation code is written -- the adaptation trigger contract must be deterministic by design, not patched afterward.

---

### Pitfall 2: Mutating branching_weights While C Threads Are Reading Them

**What goes wrong:**
The `BranchingFunction()` in `Branching.h` reads `stats->branching_weights[index]` without any lock -- it is a static inline function called in the inner loop of every CSearch variant. If Python-level online adaptation writes to the same `branching_weights` array while C threads are reading it, this is a data race. Even without crashes, torn reads of `double` values produce garbage branching probabilities.

The existing architecture creates one `solver_ctx_t` per worker thread (see `run_sampling` in `SearchLib.pyx` line 215: `cdef solver_ctx_t *ctx = solver_ctx_create()`). Each worker gets its OWN copy of branching_weights (copied via `solver_ctx_set_branching_weights` which does `memcpy`). This is safe for the current static-weights design. But if online adaptation tries to update a shared weight array across workers, this safety breaks.

**Why it happens:**
The temptation: "We want all workers to benefit from learned weights immediately." So developers add a shared weight array that all workers read from and a single updater writes to. This works in Python (GIL), but the actual branching decisions happen in `with nogil:` C code where the GIL is released.

**How to avoid:**
- NEVER share a mutable weight array between workers during solve. The existing per-ctx copy pattern is correct -- preserve it.
- If online adaptation needs to propagate weights, do it at a well-defined synchronization point: between sampling rounds (when the C code returns to Cython), not during `with nogil:` execution.
- If implementing cross-worker weight sharing, use a snapshot pattern: writer updates a separate buffer, readers swap pointers at a synchronization point. This mirrors how `solver_ctx_set_branching_weights` already works (copy + normalize).
- Run ThreadSanitizer (`-fsanitize=thread`) on every CI run -- the existing CI already does this. Any shared-weight bug will be caught immediately.

**Warning signs:**
- ThreadSanitizer reports data races on `branching_weights` reads.
- Non-deterministic crashes in `BranchingFunction()` -- SIGSEGV on `stats->branching_weights[index]` with a NULL or freed pointer.
- Sporadically wrong branching probabilities (0.0 or NaN) appearing in debug output.

**Phase to address:**
Online adaptation implementation phase. The architecture decision (per-worker isolation vs. shared state) must be made before coding. Per-worker isolation is strongly recommended.

---

### Pitfall 3: L1 Normalization Drift During Incremental Weight Updates

**What goes wrong:**
The existing `solver_ctx_set_branching_weights()` in `solver_ctx.c` copies the full array and L1-normalizes it so weights sum to 1.0. If online adaptation incrementally adjusts individual weights (e.g., `weights[i] += delta`), the L1 normalization invariant breaks. The `BranchingFunction()` formula assumes normalized weights. Unnormalized weights cause the branching probability to exceed [0, 1], producing invalid state probabilities that accumulate multiplicatively in `StateProbability()`.

Concrete failure mode: if `weights[5]` is increased but others are not renormalized, the branching_factor * w[5] term in `BranchingFunction()` dominates, producing `value > 1.0`. After the `bit_T` logic, `total_bias` can become negative (via `1.0 - value`). `StateProbability()` multiplies these across all variables -- one negative factor makes the entire state probability negative, which downstream code does not handle.

**Why it happens:**
Full-array renormalization after every single weight update is expensive (O(n) per update, and updates happen in the hot loop). Developers skip it "for now" or batch updates without re-normalizing between batches.

**How to avoid:**
- Never update individual weights. Always set the full array via `solver_ctx_set_branching_weights()`, which normalizes atomically. Build the updated weight vector in Python/numpy, then pass the complete array down.
- If per-element updates are needed for performance, maintain a running L1 sum: `sum += new_weight - old_weight`. Re-normalize only when the sum drifts beyond a tolerance (e.g., `abs(sum - 1.0) > 1e-10`).
- Add a debug assertion in `BranchingFunction()` (behind `#ifndef NDEBUG`): `assert(value >= 0.0 && value <= 1.0)`.
- Add a test that runs online adaptation for 1000 iterations and verifies all branching probabilities remain in [0, 1].

**Warning signs:**
- `StateProbability()` returns negative or > 1.0 values.
- Solver finds no improving solutions (all state probabilities are effectively 0 or garbage).
- Valgrind reports no errors but solve quality degrades mysteriously over time.

**Phase to address:**
Online adaptation implementation phase. The weight-update API must enforce normalization. This is a hard requirement, not a "nice to have."

---

### Pitfall 4: Overfitting Branching Weights to Training Instance Structure

**What goes wrong:**
The trained ML model learns branching weights that are optimal for the training instances but fail on structurally different problems. Research confirms this is the primary failure mode of ML-based branching: "methods inherit biases from expert demonstrations and generalize poorly to unseen instances" and "success is rooted in the ability of learning within the distribution of specific classes of MILP instances, though generalizing outside of a specific class has proven difficult."

For this solver specifically: if training only uses knapsack-style problems (single capacity constraint, all <= constraints), the model learns that high-value variables should have high branching weight. When applied to set-cover problems (many equality constraints, different structure), these weights actively harm performance -- worse than uniform weights.

**Why it happens:**
The training pipeline naturally uses available benchmark instances. If all benchmarks are from one problem family, overfitting is invisible during evaluation. The model looks great on test instances that are i.i.d. with training, then fails in production on different problem types.

**How to avoid:**
- Always include a "uniform weights" baseline in evaluation. If the ML model ever performs worse than uniform weights on any test set, the model is overfitting.
- Train on heterogeneous instance sets: mix knapsack, set cover, graph coloring, scheduling instances.
- Use problem-independent features (constraint density, variable-constraint ratio, coefficient statistics) rather than problem-specific features. The CBQS model exposes these through `model_t`: `con->num_constraints`, `con->num_clauses`, variable count `n`.
- Implement a "confidence gate": if the model's predicted weights are too far from uniform (high entropy), fall back to uniform weights. This prevents catastrophic failure on out-of-distribution instances.
- Evaluate on instances deliberately larger than training instances (the v3.0 goal explicitly mentions "train on small/medium, generalize to larger").

**Warning signs:**
- ML-adapted solve is consistently faster than uniform on training-like instances but slower on different problem types.
- Feature importance analysis shows the model relies on problem-size features (n, m) rather than structural features.
- Performance degrades sharply when instance size crosses the training range.

**Phase to address:**
Offline training pipeline phase. Feature design and training data diversity must be addressed from the start -- retrofitting generalization is much harder than designing for it.

---

### Pitfall 5: Feature Extraction That Couples to Instance Size

**What goes wrong:**
The feature vector used to predict branching weights has a dimension that depends on the number of variables or constraints. A model trained on 20-variable instances cannot predict weights for 100-variable instances because the input/output dimensions differ.

For CBQS specifically: `branching_weights` is an array of length `n` (number of variables). A naive approach trains a model that takes instance features and outputs `n` weights directly. This model has a fixed output dimension and cannot handle variable-size instances.

**Why it happens:**
The simplest ML pipeline is `features -> model -> weights`, where the model is a standard sklearn regressor/classifier with fixed input/output dimensions. This works perfectly for instances of the same size, which is what testing uses.

**How to avoid:**
- Design the ML model to predict PER-VARIABLE features, not a full weight vector. Input: features of variable `i` (its coefficient in the objective, number of constraints it appears in, constraint tightness statistics). Output: weight for variable `i`. This makes the model instance-size-independent.
- Alternative: predict a small set of weight "parameters" (e.g., "how much to weight objective coefficients vs. constraint participation") and compute per-variable weights from these parameters and the instance structure. This reduces the ML model to a fixed-dimension input/output regardless of instance size.
- Test generalization by training on n=20 instances and evaluating on n=100, n=500 instances. If the pipeline crashes or produces nonsensical weights, the feature design is wrong.

**Warning signs:**
- Pipeline crashes with dimension mismatch when instance size changes.
- Model accuracy is perfect on same-size instances but random on different sizes.
- The sklearn model has `n_features_in_` that matches a specific instance size.

**Phase to address:**
Feature engineering phase (early in offline training pipeline). This is an architectural decision that affects all downstream work.

---

## Moderate Pitfalls

### Pitfall 6: Training Pipeline That Is Too Slow to Be Practical

**What goes wrong:**
Collecting training data requires running the solver many times on many instances. If each solve takes 5 minutes and training needs 1000 solves across 50 instances, the training pipeline takes 3.5 days. This makes iteration on the ML model impractical.

**Why it happens:**
Using production solver settings (stopping_time=300, num_workers=12) for training data collection. Each data point is a full solve, not a partial one.

**How to avoid:**
- Use short solves for training data: `stopping_time=5-10`, not 300. The branching weight quality signal is visible within the first few seconds.
- Use small instances for training (n=10-30), large instances only for evaluation.
- Collect training signal from solve checkpoints (callback history), not just final results. Each solve yields multiple data points (one per improvement event).
- Pre-compute instance features once and cache them. Feature extraction should be O(n*m), not O(solve_time).
- Target: full training pipeline should complete in under 30 minutes on a single machine.

**Warning signs:**
- Training takes hours, discouraging experimentation.
- Feature extraction is the bottleneck (not model training).
- Each data collection run produces only one label per solve.

**Phase to address:**
Training pipeline design phase. Set time budget constraints before building the pipeline.

---

### Pitfall 7: sklearn Version/API Instability Breaking the Pipeline

**What goes wrong:**
sklearn is an optional dependency. If the ML pipeline hard-codes a specific sklearn API (e.g., `model.predict()` return shape, `Pipeline` steps interface, preprocessing transformer API), a sklearn version upgrade breaks the entire training/inference pipeline without touching any solver code.

Recent sklearn releases (1.6-1.8) have changed the testing infrastructure and tag system. While the core estimator API has been stable, edge cases around `Pipeline`, `ColumnTransformer`, and serialization (`pickle`/`joblib.dump`) can break across versions.

**Why it happens:**
The ML pipeline is tested against one sklearn version during development. CI pins that version. A year later, users install a different version and the pipeline silently produces different results (or crashes).

**How to avoid:**
- Pin sklearn version range in optional dependencies: `scikit-learn>=1.5,<2.0`.
- Wrap sklearn interactions in a thin adapter layer. Never import sklearn in the core solver -- only in `cbqs.ml` or similar optional module.
- Use only the core sklearn API: `fit()`, `predict()`, `score()`. Avoid internal APIs (`_validate_data`, `_check_feature_names`).
- Serialize trained models with explicit version metadata. On load, check sklearn version and warn if different from training version.
- Add a CI job that tests with the minimum and maximum supported sklearn versions.

**Warning signs:**
- `ImportError` or `AttributeError` from sklearn on import.
- Trained model produces different predictions after sklearn upgrade.
- `pickle.load()` fails on serialized model with version mismatch.

**Phase to address:**
Dependency setup phase (first phase of v3.0). The sklearn integration boundary must be defined before any ML code is written.

---

### Pitfall 8: The Global `python_callback` Variable Race Condition

**What goes wrong:**
`SearchLib.pyx` has a module-level `cdef object python_callback = None` that is set by every worker thread in `run_sampling()` (line 268: `python_callback = _history_callback_fn`). This is a data race: multiple joblib worker threads write to the same global variable. The `_SolveState` dict per-thread isolation only works because the callback function itself is the same object for all threads. But if online adaptation needs a PER-WORKER callback (to update weights differently per worker), this global variable pattern breaks.

This is an existing limitation, not a new bug. But v3.0 online adaptation is very likely to need per-worker callback customization, which will expose this race.

**Why it happens:**
The original callback design assumed all workers use the same callback function and differ only in thread-local state (via `_SolveState[tid]`). Online adaptation may need different behavior per worker (e.g., different learning rates, different update schedules).

**How to avoid:**
- If online adaptation uses the callback mechanism: keep the same global function, put all per-worker state in `_SolveState[tid]`. Do NOT try to set different `python_callback` per thread.
- Better: do NOT use the existing callback mechanism for weight updates. Instead, add a dedicated "adaptation hook" that runs at a well-defined C-level synchronization point (between sampling rounds), not at the unpredictable callback invocation point.
- If refactoring the callback system: make it per-ctx rather than global. Store the callback pointer in `solver_ctx_t` instead of a module-level global.

**Warning signs:**
- Callbacks invoke the wrong function intermittently.
- History tracking produces garbled results in multi-worker mode.
- ThreadSanitizer reports a race on `python_callback`.

**Phase to address:**
Online adaptation architecture phase. Decide early whether to extend the callback mechanism or build a separate adaptation hook.

---

### Pitfall 9: Reward Signal Design That Conflates Objectives

**What goes wrong:**
The v3.0 design calls for a "combined reward signal: objective improvement rate + constraint satisfaction rate." If these are naively combined (e.g., `reward = alpha * obj_improvement + beta * constraint_satisfaction`), the model cannot distinguish between weights that are good for feasibility and weights that are good for optimality. In practice, the solver goes through phases: first find feasibility (constraint satisfaction), then optimize (objective improvement). Weights that are optimal for phase 1 are often wrong for phase 2.

In the CBQS solver, this phase transition is explicit in `ctg()` (SearchLib.c lines 126-138): `stage=1` is constraint satisfaction, `stage=2` is tightening, `stage=3` is optimization. Using the same branching weights across all stages is suboptimal.

**Why it happens:**
Combining multiple objectives into a single scalar reward is the default approach. It is easy to implement and works for simple cases. But the solver's multi-phase structure means the optimal weighting changes during solve.

**How to avoid:**
- Track objective improvement and constraint satisfaction as separate signals, not combined.
- Allow different branching weights per solver stage. The `search_stage` field in `incumbents_t` already tracks which stage produced each incumbent -- use this to split training data by stage.
- Start simple: train one model for all stages with the combined reward. But design the architecture so per-stage models can be swapped in later without refactoring.
- Evaluate each stage's contribution independently: "Did ML weights improve time-to-feasibility? Did ML weights improve optimization after feasibility?"

**Warning signs:**
- ML-adapted solver finds feasible solutions faster but finds worse optima (or vice versa).
- Reward signal is noisy and model does not converge during training.
- Feature importance shows model relying on stage-correlated features rather than structural features.

**Phase to address:**
Reward signal design phase (part of training pipeline). Must be addressed before collecting training data.

---

### Pitfall 10: Integration Testing Gaps Between ML and Solver

**What goes wrong:**
Unit tests pass for the ML pipeline (correct features, correct predictions) and unit tests pass for the solver (correct branching with given weights). But the integration -- ML predicts weights, weights are set on the model, model is solved -- is never tested end-to-end. Bugs in the glue code (wrong array ordering, off-by-one in feature indexing, weights not applied due to parameter precedence) cause silent quality degradation.

The existing test suite (`test_branching_propagation.py`) verifies that static weights propagate correctly. But it does NOT verify that dynamically-generated weights from an ML model are correct. The "generate weights from features, set them, solve, compare against baseline" flow has zero test coverage.

**Why it happens:**
The ML team builds the pipeline, the solver team builds the integration point, and nobody writes the test that exercises both together. Each side assumes the other is correct.

**How to avoid:**
- Write integration tests from day one. A test that:
  1. Creates a known problem instance.
  2. Extracts features.
  3. Runs the ML model to predict weights.
  4. Sets weights on the solver via `set_param('branching_weights', predicted)`.
  5. Solves and verifies the result is at least as good as uniform weights on this instance.
- Add a "round-trip" test: extract features, predict weights, verify weights have correct length (`n`), correct dtype (`float64`), non-negative, and sum to approximately 1.0 after normalization.
- Test with sklearn unavailable (import guarded) to verify graceful degradation -- solver should work fine without ML, just using default weights.

**Warning signs:**
- ML pipeline tests pass, solver tests pass, but solved quality is worse with ML weights than without.
- Features have correct values but wrong ordering relative to variable indices.
- `set_param('branching_weights', predicted)` silently uses default weights because `predicted` is the wrong shape.

**Phase to address:**
Every phase that touches the ML-solver boundary. Integration tests should be written alongside implementation, not deferred.

---

## Minor Pitfalls

### Pitfall 11: Forgetting That branching_weights Must Match Variable Count

**What goes wrong:**
The ML model predicts a weight vector. If the model was trained on instances with `n=20` and is applied to an instance with `n=25`, the predicted vector has length 20. `set_param('branching_weights', ...)` in `Model.pyx` validates: `if self.n > 0 and len(arr) != self.n: raise ValueError`. The solve crashes before starting.

**How to avoid:**
Per-variable prediction model (Pitfall 5 solution) avoids this entirely. If using a fixed-output model, add a wrapper that pads/truncates and warns.

**Phase to address:** Feature engineering and ML model design.

---

### Pitfall 12: Numpy dtype Mismatch at the Cython Boundary

**What goes wrong:**
`SearchLib.pyx` converts branching_weights to C doubles: `arr_bw = np.array(param_weights, dtype=np.double)`. If the ML pipeline returns `float32` predictions (common with sklearn when input data is float32), the conversion is implicit but correct. However, if it returns integer predictions or object arrays, the conversion may lose precision or raise errors.

**How to avoid:**
Always cast ML predictions to `np.float64` before passing to `set_param()`. Add a type assertion in the ML pipeline output.

**Phase to address:** ML pipeline output stage.

---

### Pitfall 13: Assuming Improvement Signal Is Always Available

**What goes wrong:**
Online adaptation expects to learn from objective improvements during solve. But on hard instances, the solver may run for minutes without finding any improvement. If the adaptation system requires frequent feedback, it will either (a) make no updates (wasting the opportunity to adapt) or (b) make updates based on noise (no-improvement rounds treated as negative signal, driving weights to degenerate values).

**How to avoid:**
- Use constraint satisfaction progress as an alternative signal in early solve stages (before feasibility is found).
- Handle the "no improvement" case explicitly: either hold weights steady or apply a small exploration perturbation.
- Set a minimum number of improvements before triggering the first adaptation (e.g., wait for 5 improvements before updating weights).

**Phase to address:** Online adaptation reward signal design.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing trained model as pickle in the repo | Easy to version and distribute | Pickle is fragile across sklearn versions, security risk from untrusted pickles | Never in production; OK for development prototyping |
| Hardcoding feature list in the training script | Fast to implement | Adding a new feature requires touching training, inference, and tests | Only in initial prototype; must be config-driven before v3.0 ships |
| Using `stopping_time` as adaptation trigger | Simple to implement | Breaks determinism (wall-clock dependent) | Never -- use iteration count instead |
| Combining all solver stages into one reward | Simpler model, more training data per instance | Cannot optimize per-stage performance | Acceptable for MVP if architecture allows per-stage extension later |
| Skipping integration tests for "simple glue code" | Faster development | Silent bugs in feature ordering, weight application, dtype conversion | Never -- integration tests are the highest-value tests for this milestone |

## Integration Gotchas

Common mistakes when connecting ML components to the existing solver.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| sklearn -> set_param('branching_weights') | Passing sklearn output directly (may be 2D array, wrong dtype, wrong length) | Flatten, cast to float64, verify length == n, then pass |
| Feature extraction -> model input | Computing features in a different order than training used | Use an ordered dict or named feature vector; verify feature names match at predict time |
| Model serialization -> model loading | Pickling with one sklearn version, loading with another | Store sklearn version in metadata, warn on mismatch, use joblib.dump not pickle.dump |
| Online adaptation -> solver ctx | Updating weights while C code is in `with nogil:` block | Only update weights between sampling rounds, when control returns to Cython |
| Training data collection -> labeling | Using wall-clock solve time as the label | Use iteration count to first feasible solution, or objective improvement per 100 iterations |
| Per-worker adaptation -> global state | Writing adapted weights to a shared array | Each worker maintains independent adapted weights; merge after solve |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full L1 renormalization after every weight update | Solve slows down linearly with n | Maintain running sum, normalize lazily | n > 500 variables with frequent updates |
| Feature extraction that re-evaluates all constraints | Feature computation dominates solve time | Cache constraint statistics at close() time | n > 100, m > 200 (constraint count) |
| Training on full solve results (5+ min each) | Training pipeline takes days | Use short solves (5-10s) for training, evaluate on full solves | > 50 training instances |
| Per-iteration Python callback for adaptation | GIL acquisition overhead in hot loop | Batch updates every K iterations, minimize Python-C boundary crossings | > 10,000 iterations/second |
| Storing full solve history for every training run | Memory grows with instance count * solve length | Store only summary statistics (improvement count, time-to-feasibility, final objective) | > 100 training instances |

## UX Pitfalls

Common user experience mistakes when exposing ML-based branching.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Requiring sklearn just to import cbqs | `ImportError` on `from cbqs import Model` if sklearn not installed | Make sklearn a lazy import; only fail when ML features are actually used |
| No way to inspect learned weights | Users cannot debug why ML-adapted solve is slow | Expose `get_param('branching_weights')` returning the current weights, add a `model.explain_weights()` method |
| Silent fallback to uniform weights | User thinks ML is active but sklearn import failed silently | Warn explicitly: "sklearn not found, using uniform branching weights" |
| ML adaptation ON by default | Solver behavior changes unpredictably for existing users | ML adaptation must be opt-in via `set_param('adaptation', True)` or similar |
| No way to disable adaptation mid-solve | User cannot stop adaptation if it is making things worse | Provide a callback-based kill switch or a "max_adaptations" parameter |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Offline training pipeline:** Often missing cross-validation across instance families -- verify model is evaluated on held-out instance TYPES (not just held-out instances of the same type)
- [ ] **Feature extraction:** Often missing variable-index alignment -- verify that feature[i] corresponds to variable[i] in the solver, not feature[i] corresponds to the i-th constraint
- [ ] **Online adaptation:** Often missing the "no improvement" path -- verify that adaptation does not crash or degenerate when the solver finds zero improvements for 1000+ iterations
- [ ] **Weight normalization:** Often missing the all-zeros edge case -- verify that predicted all-zero weights trigger the existing division-by-zero guard in `solver_ctx_set_branching_weights` (it does: sum=0 means no normalization, all weights stay 0, BranchingFunction returns 0.5)
- [ ] **sklearn optional dependency:** Often missing the import guard -- verify that `from cbqs import Model` works without sklearn installed
- [ ] **Determinism with adaptation:** Often missing the multi-worker case -- verify determinism with `num_workers=4`, not just `num_workers=1`
- [ ] **Integration tests:** Often missing the "worse than baseline" check -- verify that ML weights produce results at least as good as uniform weights on a known instance

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Determinism broken by online adaptation | MEDIUM | Revert to per-round (not per-time) update triggers; re-run determinism tests; may require redesigning the adaptation schedule |
| Thread safety violation in weight updates | LOW | Revert to per-ctx weight copies (existing pattern); the current architecture already isolates per-worker state correctly |
| L1 normalization drift | LOW | Add full renormalization call after each adaptation round; no architecture change needed |
| Overfitting to training instances | HIGH | Requires redesigning training data (heterogeneous instances), feature engineering (problem-independent features), and re-training. Cannot be patched post-hoc. |
| Feature-size coupling | HIGH | Requires redesigning the ML model architecture to per-variable prediction. Cannot be retrofitted onto a fixed-dimension model. |
| Training pipeline too slow | MEDIUM | Switch to short solves for training data, cache features, use partial solve histories. Requires re-collecting training data but no architecture change. |
| sklearn API breakage | LOW | Pin sklearn version, add compatibility layer. Existing models still work if sklearn version is pinned. |
| Global callback race | MEDIUM | Move to per-ctx callback storage or use `_SolveState` pattern consistently. Requires touching SearchLib.pyx but changes are localized. |
| Reward signal conflation | MEDIUM | Split training data by solver stage, retrain per-stage models. Requires re-collecting data with stage labels. |
| Integration test gaps | LOW | Write the missing tests. No code changes needed -- only test additions. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| P1: Determinism break | Online adaptation design | Determinism regression test passes with adaptation enabled, seed=42, workers=1 AND workers=4 |
| P2: Thread-unsafe weight mutation | Online adaptation architecture | ThreadSanitizer CI passes with adaptation enabled and num_workers=4 |
| P3: L1 normalization drift | Weight update API design | Assert all branching probabilities in [0,1] after 1000 adaptation rounds |
| P4: Overfitting to training instances | Training pipeline design | ML weights beat uniform weights on held-out instance TYPES (not just sizes) |
| P5: Feature-size coupling | Feature engineering | Pipeline works on n=20, n=100, n=500 without code changes |
| P6: Slow training pipeline | Training pipeline design | Full pipeline completes in < 30 minutes on single machine |
| P7: sklearn version instability | Dependency setup (first phase) | CI tests with minimum and maximum supported sklearn versions |
| P8: Global callback race | Adaptation hook design | ThreadSanitizer clean with adaptation callbacks and num_workers=4 |
| P9: Reward signal conflation | Reward signal design | Per-stage evaluation shows ML improves both feasibility time and optimization quality |
| P10: Integration testing gaps | Every phase (continuous) | End-to-end test: extract features -> predict weights -> solve -> verify >= baseline |
| P11: Weight length mismatch | ML model output validation | Test with instances of 3 different sizes |
| P12: Numpy dtype mismatch | ML pipeline output | Explicit float64 cast in pipeline output, test with float32 sklearn predictions |
| P13: No-improvement adaptation | Online adaptation edge cases | Test adaptation on hard instance where solver finds zero improvements for 60 seconds |

## Sources

- Codebase analysis: `cbqs/src/Branching.h` (BranchingFunction, L1 normalization), `cbqs/src/solver_ctx.c` (weight copy + normalize), `cbqs/SearchLib.pyx` (per-worker ctx creation, global callback, GIL handling), `cbqs/Model.pyx` (set_param validation, joblib threading), `cbqs/src/SearchLib.c` (ctg search loop, mutex-protected global_opt updates, solver stages)
- Test suite analysis: `tests/test_determinism.py`, `tests/test_branching_propagation.py` (existing determinism and weight propagation tests)
- [A Comprehensive Evaluation of Contemporary ML-Based Solvers for Combinatorial Optimization](https://arxiv.org/abs/2505.16952) -- generalization pitfalls in ML-based CO solvers
- [Learning Branching Policies for MILPs with Proximal Policy Optimization](https://arxiv.org/html/2511.12986) -- overfitting in imitation learning for branching
- [Machine learning augmented branch and bound for MIP](https://link.springer.com/article/10.1007/s10107-024-02130-y) -- training/inference cost limitations
- [scikit-learn Release History](https://scikit-learn.org/stable/whats_new.html) -- sklearn API stability across versions
- [sklearn-compat PyPI](https://pypi.org/project/sklearn-compat/) -- sklearn version compatibility tooling
- [Solving Reproducibility Challenges in Deep Learning](https://www.ingonyama.com/post/solving-reproducibility-challenges-in-deep-learning-and-llms-our-journey) -- floating-point non-determinism in ML systems

---
*Pitfalls research for: ML-based adaptive branching in CBQS v3.0*
*Researched: 2026-02-26*
