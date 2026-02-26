# Project Research Summary

**Project:** CBQS v3.0 — ML-Based Adaptive Branching Weight Learning
**Domain:** ML-augmented combinatorial optimization solver
**Researched:** 2026-02-26
**Confidence:** HIGH

## Executive Summary

CBQS v3.0 adds machine-learning-based learning and adaptation of branching weights to a mature, thread-safe combinatorial optimization solver. The integration surface is unusually narrow and well-defined: the entire ML system communicates with the C kernel through exactly one existing API — `set_param('branching_weights', numpy.ndarray)`. The C kernel already L1-normalizes and propagates weights into the `BranchingFunction()` hot loop; the ML layer only needs to predict a better array than the current manual or uniform defaults. No C-level changes are required for the core offline pipeline, making this a Python-layer addition on top of a stable solver.

The recommended approach follows established algorithm configuration literature (SATzilla, Khalil 2016, Gasse 2019): extract structural features from problem instances, train a supervised regression model (ExtraTreesRegressor for offline, SGDRegressor for online) mapping features to effective branching weight vectors, and adapt weights between solve rounds using an exponential moving average of observed reward signals. The key architectural decision is keeping all ML logic in a pure-Python `cbqs/ml/` subpackage installed as an optional dependency (`pip install cbqs[ml]`), matching the existing optional-dependency pattern used for gurobipy. Online adaptation uses a multi-round solve loop — not mid-solve C-level mutation — to avoid thread-safety and determinism risks.

The primary risks cluster around two themes: solver integrity (breaking the existing 446-test deterministic, thread-safe solver through unsafe weight mutation or timing-dependent updates) and ML generalization (training models that overfit to problem structure or couple to instance size). Both risks are preventable through upfront architectural choices — per-worker weight isolation, deterministic adaptation triggers based on iteration counts rather than wall-clock time, and per-variable prediction models rather than fixed-output regressors. These decisions must be made before any adaptation code is written; retrofitting them is high-cost.

## Key Findings

### Recommended Stack

scikit-learn (>=1.6,<2.0) is the only new required dependency, installed as an optional extra (`cbqs[ml]`). It integrates cleanly with the existing Python 3.13.7 environment and has zero conflicts with current dependencies (numpy >=1.20 and joblib >=1.0 are already present). The recommended estimators are `ExtraTreesRegressor` for offline multi-output training (native per-variable prediction, no feature scaling required, seconds-to-train on 10-100 instances) and `SGDRegressor` via `MultiOutputRegressor` wrapper for online incremental adaptation. `PassiveAggressiveRegressor` must not be used — deprecated in sklearn 1.8, removed in 1.10. PyTorch, TensorFlow, XGBoost, and deep learning stacks are explicitly out of scope: overkill for the feature dimensionality (10-20 features) and training scale (hundreds of instances).

**Core technologies:**
- `scikit-learn >=1.6,<2.0`: ML training and inference — only new dependency, optional extra, zero version conflicts
- `ExtraTreesRegressor`: offline weight prediction — native multi-output, no feature scaling required, fast on small datasets
- `SGDRegressor` (via `MultiOutputRegressor`): online adaptation — the only non-deprecated sklearn online regressor
- `StandardScaler`: feature normalization for SGDRegressor — supports `partial_fit()` for incremental updates
- `numpy` (existing): feature arrays and weight vectors — already a hard dependency
- `joblib` (existing): model persistence — `joblib.dump/load` is the sklearn-recommended serialization approach, already present

### Expected Features

The ML pipeline has a clear dependency chain: `FeatureExtractor` is the foundation that all other components build on. Online adaptation is architecturally independent from the offline pipeline and can be developed in parallel, though it benefits from a pre-trained predictor for initial weights.

**Must have (table stakes):**
- `FeatureExtractor` — computes per-variable and instance-level feature vectors from a closed Model; without this there is no basis for ML prediction
- `WeightLearner.fit()` — offline supervised training from (Model, best_weights) pairs; the core value proposition of v3.0
- `WeightLearner.predict()` — runs trained model on new instances, returns numpy array for `set_param()`
- Model serialization (save/load via joblib) — train once, deploy many times; without this every training run is throwaway
- Online weight adaptation — explicitly listed as v3.0 target; EMA-based reward combining objective improvement and constraint satisfaction rates

**Should have (competitive differentiators):**
- Transfer learning validation (small-to-large generalization) — train on 50-variable instances, predict for 500-variable instances; the key academic contribution of v3.0
- Training data collection utilities (`collect_training_data`) — lowers the barrier to entry for users who are not ML experts
- Diagnostic reporting (`evaluate_weights`) — comparison against uniform and default baselines so users can verify ML is actually helping

**Defer (v3.1+):**
- GNN-based weight prediction (requires PyTorch; needs thousands of training instances to converge)
- Reinforcement learning training loop (needs 1000s of solver evaluations; impractical for laptop training budgets)
- Algorithm portfolio selection / multi-solver orchestration
- Custom ML model plugin interface (premature abstraction before one working implementation exists)
- Local search solver weight adaptation
- Real-time weight visualization or dashboard

### Architecture Approach

The v3.0 architecture introduces a pure-Python `cbqs/ml/` subpackage (6 new files) that sits entirely above the existing Python/Cython boundary. Feature extraction and ML inference happen in Python; weight updates flow through the existing `set_param('branching_weights', ...)` API; online adaptation uses a multi-round solve loop (each round: reset, set updated weights, solve, observe result, update weights via EMA). The C kernel is completely unchanged. Only 2 existing files require modification: `cbqs/__init__.py` (add conditional ml import) and `pyproject.toml`/`setup.py` (add sklearn as optional extra).

**Major components:**
1. `FeatureExtractor` (`cbqs/ml/features.py`) — extracts per-variable feature matrix (n_vars x n_features) and instance-level feature vector from a closed Model using Python-accessible constraint and objective data
2. `WeightPredictor` (`cbqs/ml/predictor.py`) — wraps sklearn model; maps per-variable feature matrix to non-negative weight array of shape (n_vars,); handles fit, predict, save, and load
3. `AdaptiveController` (`cbqs/ml/adaptive.py`) — runs multi-round solve loop with EMA weight updates between rounds; initial weights come from WeightPredictor; adaptation signal comes from OptimizeResult
4. `TrainingPipeline` (`cbqs/ml/pipeline.py`) — orchestrates offline training: generates weight candidates, runs solves, collects (features, best_weights) pairs, fits WeightPredictor
5. `TrainingData` / `SolveRecord` (`cbqs/ml/data.py`) — structured storage for training examples with joblib serialization

### Critical Pitfalls

1. **Online weight updates breaking deterministic reproducibility** — tie adaptation triggers to iteration count, not wall-clock time; never use `time.time()` or `time.monotonic()` as an update trigger; add regression test confirming same seed + same workers = same result with adaptation enabled

2. **Mutating branching_weights while C threads are reading them** — preserve the existing per-worker `solver_ctx_t` copy pattern; never share a mutable weight array across workers during solve; only update weights between sampling rounds when control returns to Cython, not during `with nogil:` C execution

3. **L1 normalization drift during incremental updates** — always rebuild the full weight vector in Python/numpy and pass the complete array to `solver_ctx_set_branching_weights()`; never increment individual elements; the C function atomically copies and L1-normalizes

4. **Overfitting to training instance structure** — use problem-independent structural features (constraint density, degree statistics, coefficient statistics) not problem-specific ones; train on heterogeneous instance sets; always include a uniform-weights baseline in evaluation; implement a confidence gate that falls back to uniform on out-of-distribution inputs

5. **Feature-size coupling preventing generalization** — design the ML model to predict per-variable weights (input: features of variable i; output: weight for variable i) rather than a fixed-output full weight vector; this architectural decision enables small-to-large transfer and cannot be retrofitted once the pipeline is built

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation — Dependency Setup and Feature Extraction

**Rationale:** `FeatureExtractor` is the dependency root for all ML components. It can be built and fully validated with zero external ML dependencies and zero changes to the existing solver. Establishing the sklearn optional-dependency import guard pattern correctly at the start prevents the critical UX pitfall of breaking existing users who do not install the `[ml]` extra.

**Delivers:** `cbqs/ml/` package skeleton with import guard, `FeatureExtractor` class, per-variable feature matrix extraction (n_vars x n_features), instance-level feature vector, unit tests verifying feature values on known problem instances with explicit variable-index alignment assertions.

**Addresses:** Table stakes feature #1 (FeatureExtractor); enables all subsequent offline and online pipeline work.

**Avoids:** P7 (sklearn version instability — dependency pinning and import guards established upfront); P5 (feature-size coupling — per-variable design validated before offline training is built); UX pitfall of requiring sklearn for basic `from cbqs import Model`.

### Phase 2: Offline Training Pipeline — WeightPredictor and TrainingPipeline

**Rationale:** With features validated, the offline supervised learning pipeline is the next dependency in the chain. This is the core value proposition of v3.0. Training data collection and model fit/predict must both be solid before online adaptation can use them for initial weights.

**Delivers:** `WeightPredictor` (ExtraTreesRegressor wrapper, fit/predict/save/load with explicit float64 output), `TrainingData` / `SolveRecord` dataclasses, `TrainingPipeline` (collect training data with diverse weight candidates using short solves, construct training targets from best-performing runs, fit predictor), `collect_training_data` utility function with heterogeneous weight strategies.

**Uses:** ExtraTreesRegressor for multi-output per-variable prediction; joblib for persistence; existing `Model.solve()` and `OptimizeResult`.

**Implements:** WeightPredictor and TrainingPipeline architecture components; offline training data flow.

**Avoids:** P4 (overfitting — heterogeneous training instances and uniform-weights baseline built into evaluation from day one); P6 (slow training — short solves for data collection, feature caching, 30-minute total pipeline target); P10 (integration testing gaps — end-to-end test from feature extraction through solve included in this phase); P12 (numpy dtype mismatch — explicit float64 cast in all pipeline outputs).

### Phase 3: Online Adaptive Solve — AdaptiveController

**Rationale:** The multi-round adaptive loop builds on a trained WeightPredictor and the validated FeatureExtractor. The inter-solve adaptation strategy (not intra-solve C mutation) eliminates all thread-safety and C-level complexity. This is the most architecturally complex component and must come after the offline pipeline proves out.

**Delivers:** `AdaptiveController` class, multi-round solve loop with EMA weight updates, combined reward signal (objective improvement rate and constraint satisfaction rate tracked separately, combined with configurable alpha), configurable learning rate and update frequency, end-to-end adaptive solve API (`controller.run_adaptive_solve(model)`).

**Uses:** Existing `Model.reset()` + `Model.solve()` cycle; `model.manual_initial()` for warm-start between rounds; reward signal from `OptimizeResult.history`.

**Implements:** AdaptiveController architecture component; multi-round adaptive solve data flow.

**Avoids:** P1 (determinism — iteration-count triggers not wall-clock); P2 (thread-unsafe mutation — per-worker isolation preserved, updates only between rounds); P3 (L1 normalization drift — full array passed to set_param each round); P8 (global callback race — adaptation hook built separately from existing callback mechanism); P9 (reward signal conflation — objective and constraint signals tracked independently, per-stage evaluation planned); P13 (no-improvement edge case — explicit hold-steady behavior when solver finds zero improvements).

### Phase 4: Transfer Learning Validation and Diagnostics

**Rationale:** The per-variable prediction design from Phases 1 and 2 enables size generalization by construction. This phase validates it empirically and adds the diagnostic tooling that makes the ML feature usable in practice without being a black box.

**Delivers:** Empirical validation of small-to-large generalization (train on n=50, evaluate on n=100, n=500); `evaluate_weights` diagnostic utility with learned/default/uniform baseline comparison; weight quality report; optional `track_weights` parameter for OptimizeResult.

**Addresses:** Differentiator features #6 (transfer learning empirical validation) and #8 (diagnostic reporting).

**Avoids:** P4 (overfitting — validated on held-out instance types not just sizes; requires beating uniform baseline on problem families not seen during training).

### Phase 5: Integration, Polish, and Documentation

**Rationale:** All components are individually tested and validated. This phase wires the public API, updates package entry points, and ensures the entire pipeline from `from cbqs.ml import AdaptiveController` to a working adaptive solve is clean, documented, and backward-compatible for existing users.

**Delivers:** Updated `cbqs/__init__.py`, `pyproject.toml` with `cbqs[ml]` optional extra in `extras_require`, integration test suite (`tests/test_ml/`), user-facing documentation and usage examples.

**Implements:** Phase 5 build order item from ARCHITECTURE.md; verifies all 13 pitfall prevention checklist items from PITFALLS.md.

### Phase Ordering Rationale

- `FeatureExtractor` must come first because it is the dependency root of all ML components and can be fully validated with zero external dependencies.
- The offline pipeline comes before online adaptation because `AdaptiveController` uses a pre-trained `WeightPredictor` for initial weights; building the offline path first also validates the feature format before the online path depends on it.
- Online adaptation is architecturally independent of offline training (per FEATURES.md dependency graph) but empirically benefits from it, making Phase 3 rather than Phase 2 the right slot.
- Transfer learning validation comes after the pipeline is proven because it is an empirical property of the design, not a new implementation — it requires running the complete offline pipeline first.
- All five critical pitfalls (P1-P5) are addressed in the first three phases because they are architectural decisions that cannot be patched post-hoc; they lock in behavior for everything that follows.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 3 (AdaptiveController):** The reward signal design (combined objective + constraint satisfaction) is well-motivated but not empirically validated for CBQS's specific three-stage solve structure (stage 1: constraint satisfaction; stage 2: tightening; stage 3: optimization). May need a short prototype spike to tune alpha, eta, and update frequency before committing to the full implementation. P9 specifically calls out this risk.
- **Phase 1 (FeatureExtractor data access):** The path from Python to the C-level `new_constraints_t` struct requires a choice between a helper `.pyx` Cython function (Option A) versus direct `mod.mod[0].con[0].*` attribute access (Option B) as described in ARCHITECTURE.md. The decision affects build complexity and test isolation. Worth a short spike before building the full extractor.

Phases with standard patterns (skip research-phase):

- **Phase 2 (Offline Training):** ExtraTreesRegressor on tabular features is a well-documented sklearn pattern. Training data collection and joblib persistence are straightforward. Standard sklearn documentation is sufficient.
- **Phase 4 (Diagnostics):** Benchmarking and reporting utilities are low-complexity wrappers over the existing `solve()` API. No novel patterns involved.
- **Phase 5 (Integration):** Python packaging with optional extras follows well-documented `extras_require` patterns. No research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | scikit-learn versions verified via PyPI and official docs; integration points verified via direct codebase inspection; zero dependency conflicts confirmed |
| Features | MEDIUM-HIGH | Table stakes features are well-established in algorithm configuration literature; online adaptation reward signal design is well-motivated but empirically unvalidated for CBQS's specific three-stage solve structure |
| Architecture | HIGH | Direct codebase analysis of all integration points; multi-round adaptation strategy avoids all identified C-level risks; component boundaries are clean and testable independently |
| Pitfalls | HIGH | Based on codebase analysis of actual code paths (not theoretical risks); cross-referenced with published literature on ML-for-CO generalization failures; specific failure modes traced to named source lines |

**Overall confidence:** HIGH

### Gaps to Address

- **Reward signal tuning for three-stage solve:** CBQS's `ctg()` has explicit stages (constraint satisfaction -> tightening -> optimization). The EMA-based reward that blends objective improvement and constraint satisfaction may need stage-aware weighting to avoid the conflation identified in P9. Design this before collecting training data — training data structure must capture stage labels from the start.

- **Cython helper vs. direct attribute access for feature extraction:** ARCHITECTURE.md identifies two approaches. Option A (helper `.pyx` function) keeps the ML module as pure Python and easier to test. Option B (direct `mod.mod[0].con[0].*` access) is simpler but couples the ML module to C struct layout. Spike this decision in Phase 1 before building the full `FeatureExtractor`.

- **Adaptation update frequency calibration:** The `AdaptiveController` needs a default for "update weights every K iterations." Too frequent causes GIL overhead in the solve loop; too infrequent misses learning opportunities. This is empirical and cannot be researched in advance. Target: establish a working default during Phase 3 and expose it as a configurable parameter.

- **Variable-index alignment:** `feature[i]` must correspond to variable `i` in the solver, not constraint `i`. This is identified in PITFALLS.md as a common "looks done but isn't" issue. Requires an explicit test in Phase 1 that verifies feature-variable correspondence on a known instance.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `Branching.h`, `solver_ctx.h`, `solver_ctx.c`, `Model.pyx`, `SearchLib.pyx`, `SearchLib.c`, `result.py` — branching function implementation, weight injection, callback mechanism, OptimizeResult structure
- Test suite analysis: `tests/test_determinism.py`, `tests/test_branching_propagation.py` — existing determinism and weight propagation test coverage
- [scikit-learn 1.8.0 official documentation](https://scikit-learn.org/stable/) — estimator APIs, version support matrix
- [scikit-learn PyPI](https://pypi.org/project/scikit-learn/) — version 1.8.0 confirmed as latest stable (2025-12-10)
- [SGDRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDRegressor.html) — partial_fit API, parameter details
- [ExtraTreesRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.ExtraTreesRegressor.html) — native multi-output support
- [sklearn model persistence](https://scikit-learn.org/stable/model_persistence.html) — joblib.dump/load as recommended approach
- [PassiveAggressiveRegressor deprecation (1.8)](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PassiveAggressiveRegressor.html) — use SGDRegressor instead

### Secondary (MEDIUM confidence)
- [Khalil et al. 2016 — Learning to Branch in MIP](https://ojs.aaai.org/index.php/AAAI/article/view/10080) — 72 features for variable selection, supervised learning from strong branching (foundational paper for feature design)
- [Gasse et al. 2019 — GNN for variable selection](https://proceedings.mlr.press/v176/gasse22a/gasse22a.pdf) — GNN on bipartite graph, imitation learning (cited for context; GNN approach excluded for v3.0)
- [A Comprehensive Evaluation of Contemporary ML-Based Solvers for CO](https://arxiv.org/abs/2505.16952) — generalization pitfalls, training/distribution mismatch failures
- [Learning Branching Policies for MILPs with PPO](https://arxiv.org/html/2511.12986) — overfitting in RL-based branching (justifies supervised approach)
- [Machine learning augmented branch and bound for MIP](https://link.springer.com/article/10.1007/s10107-024-02130-y) — training/inference cost limitations
- [SATzilla instance features (2024)](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27) — feature categories for algorithm selection
- [Adaptive Operator Selection survey](https://ieeexplore.ieee.org/document/10904096/) — EMA and AOS patterns for online adaptation
- [sklearn ensemble documentation](https://scikit-learn.org/stable/modules/ensemble.html) — warm_start for GradientBoosting
- [sklearn scaling strategies](https://scikit-learn.org/stable/computing/scaling_strategies.html) — partial_fit incremental learning guide

### Tertiary (MEDIUM confidence, cited for architecture context)
- [Symb4CO — Symbolic Discovery for Branching](https://openreview.net/forum?id=jKhNBulNMh) — CPU-only symbolic policies matching GNN performance (validates lightweight approach)
- [Neural CO with Heavy Decoder — small-to-large generalization](https://arxiv.org/abs/2310.07985) — size-invariant feature design patterns
- [ICLR 2025 — Learning to Select Nodes in Branch](https://proceedings.iclr.cc/paper_files/paper/2025/file/82f625a28d822d2748b9f5c4f9a89bb9-Paper-Conference.pdf) — tripartite graph feature sets
- [Influence branching for online MIP solving](https://arxiv.org/html/2510.04273v1) — online weight adaptation approaches
- [Learning to Branch in Combinatorial Optimization](https://arxiv.org/pdf/2307.01434) — feature extraction from constraint structure

---
*Research completed: 2026-02-26*
*Ready for roadmap: yes*
