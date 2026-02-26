# Feature Landscape: v3.0 ML-Based Adaptive Branching Weight Learning

**Domain:** Machine learning for branching weight prediction in combinatorial optimization solver
**Researched:** 2026-02-26
**Confidence:** MEDIUM-HIGH (based on codebase analysis + academic literature + solver industry patterns)

## Context

CBQS v2.1 shipped a stable solver with a clean branching system:
- `branching_weights` array (per-variable, L1-normalized) set via `set_param('branching_weights', array)`
- 3-term `BranchingFunction`: `branching_factor * w[i] + bias_factor * assignment_bias + look_ahead_factor * lookahead`
- `solver_ctx_t` carries `BranchingStats_t` per-solve (thread-safe)
- `OptimizeResult` returns structured output with `history`, `solve_time`, `feasible`, `objective`

v3.0 adds ML-based learning to **predict and adapt** the `branching_weights` array, replacing manual tuning with data-driven weight selection.

The integration surface is narrow and well-defined: the ML system's only output is a `numpy.ndarray` passed to `set_param('branching_weights', array)`. Everything downstream (normalization, formula evaluation, solve loop) already works.

---

## Table Stakes

Features users expect when a solver claims "ML-based adaptive branching." Missing any of these makes the feature feel incomplete or unusable.

### 1. Problem Feature Extraction (`FeatureExtractor`)

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Every ML-for-optimization system extracts structural features from the problem instance. Without features, there is no basis for prediction. Users familiar with SATzilla, Khalil 2016, or Gasse 2019 expect this. |
| **What It Does** | Given a CBQS `Model` (after `close()`), compute a fixed-length numeric feature vector describing the instance structure. |
| **Complexity** | MEDIUM |
| **Dependencies** | Existing `Model` API (n, con, obj accessible after close) |

**Feature categories to extract (drawing from Khalil 2016 and SATzilla patterns):**

1. **Size features** (trivially computable):
   - `n_variables`: number of binary variables
   - `n_constraints`: number of constraints
   - `constraint_variable_ratio`: n_constraints / n_variables

2. **Constraint structure features** (require iterating constraint data):
   - `mean_constraint_length`: average number of variables per constraint
   - `std_constraint_length`: standard deviation of constraint lengths
   - `max_constraint_length`: longest constraint
   - `constraint_density`: total nonzero coefficients / (n_variables * n_constraints)

3. **Variable activity features** (require variable-constraint incidence):
   - `mean_variable_degree`: avg number of constraints each variable appears in
   - `std_variable_degree`: std of variable degree
   - `max_variable_degree`: most-constrained variable

4. **Coefficient statistics** (from constraint matrix):
   - `mean_abs_coefficient`: average |coefficient| across all terms
   - `std_abs_coefficient`: coefficient magnitude spread
   - `coefficient_sign_ratio`: fraction of positive coefficients

5. **Objective features** (from objective expression):
   - `n_objective_terms`: number of variables in objective
   - `objective_density`: objective terms / n_variables
   - `mean_abs_obj_coefficient`: average |objective coefficient|

**Why this specific set:** These features are computable in O(n * m) from the existing constraint representation (dense or sparse) with no external dependencies. They capture the structural characteristics that correlate with variable importance in the branching formula. Khalil 2016 uses 72 features, but most require LP relaxation data that CBQS does not compute. We use the subset that is available from the combinatorial structure alone.

**Confidence:** HIGH -- feature categories are well-established in the algorithm configuration literature (SATzilla, Khalil 2016, Gasse 2019).

### 2. Offline Training Pipeline (`WeightLearner.fit()`)

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The core value proposition. Users need to collect performance data from a set of training instances and learn a mapping from features to good branching weights. |
| **What It Does** | Given a list of (Model, OptimizeResult) pairs from solved instances, learn a model that predicts branching_weights from problem features. |
| **Complexity** | HIGH |
| **Dependencies** | FeatureExtractor (#1), sklearn (optional dependency), existing solve() + OptimizeResult |

**User workflow:**

```python
from cbqs import Model, MAXIMIZE
from cbqs.ml import FeatureExtractor, WeightLearner

# Step 1: Solve training instances (small/medium) with various weight settings
training_data = []
for instance in instance_set:
    model = build_model(instance)
    model.close()

    # Try several weight vectors, keep the best result
    best_result = None
    best_weights = None
    for weights in weight_candidates:
        model.reset()
        model.set_param('branching_weights', weights)
        result = model.solve()
        if best_result is None or result.objective > best_result.objective:
            best_result = result
            best_weights = weights

    training_data.append((model, best_weights))

# Step 2: Train the weight predictor
learner = WeightLearner()
learner.fit(training_data)

# Step 3: Use on new (potentially larger) instances
new_model = build_model(new_instance)
new_model.close()
predicted_weights = learner.predict(new_model)
new_model.set_param('branching_weights', predicted_weights)
result = new_model.solve()
```

**Training approach (use supervised learning, not RL):**

Use `sklearn.ensemble.GradientBoostingRegressor` (or `RandomForestRegressor`) to learn:
- Input: problem feature vector (from FeatureExtractor)
- Output: per-variable weight pattern (not the raw n-dimensional weight vector, but a mapping from per-variable features to that variable's weight)

This works because the weight prediction decomposes: for each variable, predict its importance weight from (a) the global problem features and (b) per-variable local features (degree, coefficient stats). This makes the model size-invariant -- trained on 50-variable instances, applicable to 500-variable instances.

**Why supervised over RL:** RL requires thousands of solver evaluations to converge. For a solver library (not a service), users want to train on 10-100 instances, not 10,000. Supervised learning from (features, best-known-weights) pairs is dramatically more sample-efficient. Khalil 2016 and Gasse 2019 both use supervised/imitation learning for the same reason.

**Why GradientBoosting over neural networks:** The project constraint is `sklearn` as optional dependency. GBMs handle tabular features (which is what we extract) better than small neural nets, train in seconds on small datasets, and have no GPU requirement. Random forests are the fallback for even simpler training.

**Confidence:** HIGH -- supervised learning from instance features to solver parameters is the established pattern in algorithm configuration (SATzilla, Hydra-MIP, AutoFolio).

### 3. Weight Prediction for New Instances (`WeightLearner.predict()`)

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The payoff of training. Users run `predict()` on a new model and get a branching_weights array ready to pass to `set_param()`. |
| **What It Does** | Extract features from a new Model, run the trained model, output a numpy array of branching_weights. |
| **Complexity** | LOW (after #1 and #2 are built) |
| **Dependencies** | FeatureExtractor (#1), trained WeightLearner (#2) |

The predict step must:
1. Extract global features from the model (same FeatureExtractor as training)
2. For each variable, extract local features (degree, coefficient stats)
3. Run the sklearn model on [global_features + local_features_for_variable_i] for each variable
4. Assemble into an n-length numpy array
5. The existing `set_param('branching_weights', array)` handles L1 normalization

**Output contract:** `predict()` returns a `numpy.ndarray` of shape `(model.n,)` with non-negative float64 values. This is exactly what `set_param('branching_weights', ...)` expects.

**Confidence:** HIGH -- straightforward composition of #1 and #2.

### 4. Model Serialization (Save/Load)

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users train once, deploy many times. Without save/load, the training is throwaway. |
| **What It Does** | Persist a trained WeightLearner to disk and reload it. |
| **Complexity** | LOW |
| **Dependencies** | WeightLearner (#2), joblib (already a dependency) |

Use `joblib.dump()` / `joblib.load()` -- already a project dependency, handles sklearn models natively, and is the sklearn-recommended serialization approach.

```python
# Save
learner.save('branching_model.joblib')

# Load
learner = WeightLearner.load('branching_model.joblib')
```

**Confidence:** HIGH -- joblib serialization is the standard pattern for sklearn models.

### 5. Online Weight Adaptation During Solve

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Explicitly listed as a v3.0 target feature. The offline predictor gives a starting point; online adaptation refines weights during the solve based on actual performance feedback. |
| **What It Does** | During solve iterations, adjust branching_weights based on a reward signal combining objective improvement rate and constraint satisfaction rate. |
| **Complexity** | HIGH |
| **Dependencies** | Existing callback mechanism, solver_ctx_t, branching_weights in BranchingStats_t |

**Reward signal design (combined metric):**

```
reward_i = alpha * objective_improvement_rate + (1 - alpha) * constraint_satisfaction_rate
```

Where for each variable i:
- `objective_improvement_rate`: how much the objective improved in iterations where variable i was flipped
- `constraint_satisfaction_rate`: fraction of constraints satisfied after flipping variable i
- `alpha`: mixing parameter (default 0.5, configurable via set_param)

**Adaptation mechanism (exponential moving average):**

```
w_i(t+1) = (1 - eta) * w_i(t) + eta * reward_i(t)
```

Where `eta` is the learning rate (default 0.1, configurable). This is stable, requires no external dependencies, and the EMA naturally forgets stale information.

**Implementation approach:**
- Use the existing per-iteration callback mechanism (`_history_callback_fn` pattern)
- In the callback, compute the reward for variables that changed since last callback
- Update `branching_weights` in the solver context
- The C-level `BranchingFunction` reads weights every iteration, so updates take effect immediately

**Why EMA over more complex approaches:** EMA is a single parameter (`eta`), has no memory overhead beyond the weight array itself, converges smoothly, and requires zero external dependencies. More complex approaches (bandit algorithms, RL) add complexity without clear benefit for the intra-solve timescale.

**Integration surface:** The `solver_ctx_set_branching_weights()` C function already copies and L1-normalizes. Online adaptation calls this periodically (every K iterations, configurable) rather than every iteration to amortize the copy cost.

**Confidence:** MEDIUM -- the EMA reward approach is well-understood but the specific integration with the CBQS solve loop (callback -> C context update) needs careful implementation to avoid thread-safety issues with the existing joblib parallelism.

---

## Differentiators

Features that would set CBQS apart from other solver libraries. Not expected, but high value.

### 6. Transfer Learning: Small-to-Large Instance Generalization

| Attribute | Detail |
|-----------|--------|
| **Value Proposition** | Train on 50-variable instances (fast to solve), apply to 500-variable instances. This is the key academic contribution of the v3.0 milestone. |
| **What It Does** | The WeightLearner predicts variable-level weights that generalize across instance sizes because the prediction is per-variable based on local structural features, not per-instance. |
| **Complexity** | MEDIUM (architectural, not implementation -- the per-variable prediction design in #2/#3 enables this by construction) |
| **Dependencies** | FeatureExtractor (#1), WeightLearner (#2, #3) |

**How it works:** The key insight is that the ML model predicts weights per-variable, not per-instance. Each variable's weight is predicted from:
- Global features (normalized by n_variables, so they are scale-independent)
- Local features of that variable (its degree, coefficient stats -- these are meaningful regardless of instance size)

A model trained on (global_features, local_features) -> weight for 50-variable instances can predict weights for each of the 500 variables in a large instance, because the feature space is the same.

**Validation approach:** Train on benchmark set at size N, evaluate on size 2N, 5N, 10N. Report objective quality and solve time vs. default weights.

**Why this is a differentiator:** Most solver libraries do not offer any learning-based weight prediction. Those that do (SCIP via bandit variable selection) do not offer cross-instance transfer. The ability to "train once on small instances, deploy on large instances" is genuinely useful for practitioners who have families of similar optimization problems at different scales.

**Confidence:** MEDIUM -- the per-variable prediction design is sound in theory, but generalization quality depends on whether the feature set captures the right structural invariants. Needs empirical validation.

### 7. Training Data Collection Utilities

| Attribute | Detail |
|-----------|--------|
| **Value Proposition** | Lower the barrier to using the ML features. Users need help generating good training data (weight candidates and corresponding performance). |
| **What It Does** | Provide utility functions that generate diverse weight candidates and solve instances with each, collecting (model, best_weights) training pairs automatically. |
| **Complexity** | LOW-MEDIUM |
| **Dependencies** | Existing solve() API, FeatureExtractor (#1) |

```python
from cbqs.ml import collect_training_data

# Automatically solve instances with diverse weight strategies
training_data = collect_training_data(
    models,           # list of closed Model instances
    n_candidates=20,  # number of weight vectors to try per instance
    time_budget=30,   # seconds per solve attempt
    strategy='diverse' # 'diverse', 'random', 'heuristic'
)
```

**Weight candidate strategies:**
- `'uniform'`: equal weights (baseline)
- `'random'`: random non-negative weights (diverse exploration)
- `'degree'`: weights proportional to variable constraint degree
- `'coefficient'`: weights proportional to objective coefficient magnitude
- `'heuristic'`: combines degree and coefficient strategies
- `'diverse'`: mix of all above

This utility replaces the manual loop shown in the Table Stakes workflow, making the ML pipeline accessible to users who are not ML experts.

**Confidence:** HIGH -- this is a convenience wrapper over existing functionality.

### 8. Diagnostic Reporting for Weight Quality

| Attribute | Detail |
|-----------|--------|
| **Value Proposition** | Users need to understand whether learned weights are actually helping. Without diagnostics, ML features are a black box. |
| **What It Does** | Compare solve performance with learned weights vs. default weights vs. uniform weights, report improvement metrics. |
| **Complexity** | LOW |
| **Dependencies** | WeightLearner (#2), existing solve() API |

```python
from cbqs.ml import evaluate_weights

report = evaluate_weights(
    model,
    learned_weights=learner.predict(model),
    n_trials=5,
    baseline='default'  # compare against default (no weights) and uniform
)
print(report)
# WeightEvaluation:
#   learned:  avg_obj=47.2, avg_time=1.23s, feasible=5/5
#   default:  avg_obj=42.1, avg_time=2.10s, feasible=5/5
#   uniform:  avg_obj=44.5, avg_time=1.87s, feasible=5/5
#   improvement: +12.1% objective, -41.4% time vs default
```

**Confidence:** HIGH -- straightforward benchmarking utility.

---

## Anti-Features

Features to explicitly NOT build in v3.0. Each is a real temptation.

### A1. Graph Neural Network (GNN) for Weight Prediction

| Why Tempting | GNNs are the state-of-the-art for variable selection in MILP (Gasse 2019, ICLR 2025). The bipartite variable-constraint graph representation is natural for CBQS. |
|-------------|---------|
| **Why Avoid** | GNNs require PyTorch or TensorFlow as a dependency -- massive, GPU-oriented, and completely wrong for a lightweight C/Cython solver library. The project constraint is `sklearn` as optional dependency. GNNs also need thousands of training instances to converge; CBQS users will have 10-100. GBMs on tabular features will outperform small GNNs on this data scale. |
| **What to Do Instead** | Use sklearn GradientBoostingRegressor/RandomForestRegressor on hand-engineered tabular features. If GNN support is ever desired, expose a hook for users to provide their own weight predictor function. |

### A2. Reinforcement Learning Training Loop

| Why Tempting | RL is the "correct" formulation -- branching weight selection is a sequential decision problem with delayed rewards. PPO-based branching (arxiv 2511.12986) shows strong results. |
|-------------|---------|
| **Why Avoid** | RL training requires 1000s of solver evaluations to converge. Each evaluation takes seconds-to-minutes. Total training time: hours-to-days. CBQS users want training in minutes on a laptop. RL also requires careful reward shaping, hyperparameter tuning, and is unstable on small problem sets. The online adaptation (Feature #5) captures the "learning during solve" benefit without the RL training overhead. |
| **What to Do Instead** | Use supervised learning for offline training (fast, sample-efficient). Use simple EMA-based online adaptation for in-solve learning (no training loop required). |

### A3. Full Algorithm Configuration System (SATzilla-style Portfolio)

| Why Tempting | SATzilla selects between entire solver configurations based on instance features. CBQS has both sampling and local search solvers -- a portfolio selector could choose which to run. |
|-------------|---------|
| **Why Avoid** | Algorithm selection is a different, much larger feature (PROJECT.md explicitly defers "Automatic multi-heuristic solver" to a future milestone). v3.0 is about learning branching weights, not solver selection. Bundling portfolio selection with weight learning conflates two independent research questions. |
| **What to Do Instead** | Focus v3.0 on the sampling solver's branching weights only (as stated in PROJECT.md: "Sampling solver as initial target, local search extension deferred"). |

### A4. Custom ML Model Interface / Plugin System

| Why Tempting | "Users should be able to plug in any ML model, not just sklearn." |
|-------------|---------|
| **Why Avoid** | Premature abstraction. v3.0 is the first ML milestone. Adding a plugin interface before having one working implementation adds complexity without users to validate the design. The internal API can be refactored later when the requirements are clear. |
| **What to Do Instead** | Build the sklearn-based pipeline. If users need custom models, they can call `learner.feature_extractor.extract(model)` to get features and run their own model, then pass the result to `set_param('branching_weights', array)`. The existing `set_param` API IS the plugin interface. |

### A5. Real-Time Weight Visualization / Dashboard

| Why Tempting | Seeing how weights evolve during online adaptation would be informative. |
|-------------|---------|
| **Why Avoid** | PROJECT.md explicitly says "CLI/API only -- no GUI or web interface." Visualization is a separate concern that users can build on top of the callback mechanism and history data. |
| **What to Do Instead** | Ensure OptimizeResult includes weight history if requested (via a `track_weights` parameter). Users can plot this with matplotlib themselves. |

### A6. Automatic Hyperparameter Tuning for the ML Model

| Why Tempting | "We should grid-search the GBM hyperparameters automatically." |
|-------------|---------|
| **Why Avoid** | The ML model is predicting branching weights, not solving ImageNet. Default sklearn GBM hyperparameters are fine for 10-100 training instances with 15-20 features. Adding cross-validation, grid search, or Bayesian optimization multiplies training time for negligible benefit at this data scale. |
| **What to Do Instead** | Use reasonable defaults (n_estimators=100, max_depth=5, learning_rate=0.1). Expose the sklearn model via `learner.model_` for users who want to tune. |

---

## Feature Dependencies

```
FeatureExtractor (#1)
    |
    +---> WeightLearner.fit() (#2)
    |         |
    |         +---> WeightLearner.predict() (#3)
    |         |         |
    |         |         +---> Transfer Learning (#6) [architectural, not code]
    |         |
    |         +---> Model Serialization (#4)
    |
    +---> Training Data Collection (#7)
    |
    +---> Diagnostic Reporting (#8)

Online Adaptation (#5)
    |
    +---> Independent of offline pipeline
    +---> Depends on: callback mechanism, solver_ctx_t, branching_weights
    +---> Can use offline-predicted weights as starting point
```

**Key dependency insight:** The FeatureExtractor is the foundation. Build it first, validate it, then build the offline pipeline on top. Online adaptation is architecturally independent and can be developed in parallel.

---

## MVP Recommendation

**Phase 1 (Foundation):**
1. FeatureExtractor (#1) -- the base for everything
2. Training Data Collection (#7) -- users need this to get started

**Phase 2 (Offline Learning):**
3. WeightLearner.fit() (#2) -- core training
4. WeightLearner.predict() (#3) -- core inference
5. Model Serialization (#4) -- persistence

**Phase 3 (Online Adaptation):**
6. Online Weight Adaptation (#5) -- in-solve learning

**Phase 4 (Polish):**
7. Transfer Learning validation (#6) -- empirical validation
8. Diagnostic Reporting (#8) -- quality of life

**Defer to v3.1+:**
- Local search solver weight adaptation
- GNN-based models
- Algorithm portfolio selection
- Custom ML model plugins

---

## Existing System Integration Points

| ML Feature | Existing Integration Point | How It Connects |
|------------|---------------------------|-----------------|
| Feature extraction | `Model.n`, `Model.con_expr`, `Model.obj_expr`, constraint data structures | Read problem structure after `close()` |
| Weight prediction | `set_param('branching_weights', array)` | Standard API, L1 normalization built in |
| Online adaptation | `_history_callback_fn` pattern, `solver_ctx_set_branching_weights()` | Callback updates weights in solver context |
| Training data | `solve()` -> `OptimizeResult` with history and objective | Existing result structure has everything needed |
| Serialization | `joblib` (already a dependency) | `joblib.dump()` / `joblib.load()` |
| New dependency | `sklearn` | Optional: `pip install cbqs[ml]` via `extras_require` |

**The integration is narrow:** The entire ML system communicates with the solver through exactly one channel: `set_param('branching_weights', numpy.ndarray)`. This is already validated, L1-normalized, and propagated to the C kernel. No C-level changes are needed for the offline pipeline. Online adaptation needs a callback -> C context path, which already exists.

---

## Sources

**Academic literature:**
- [Khalil et al. 2016 -- Learning to Branch in Mixed Integer Programming](https://ojs.aaai.org/index.php/AAAI/article/view/10080) -- 72 features for variable selection, supervised learning from strong branching (MEDIUM confidence, foundational paper)
- [Gasse et al. 2019 -- GNN for variable selection, bipartite MILP representation](https://proceedings.mlr.press/v176/gasse22a/gasse22a.pdf) -- GNN on bipartite graph, imitation learning (MEDIUM confidence, cited for architecture context)
- [Symb4CO -- Symbolic Discovery for Branching](https://openreview.net/forum?id=jKhNBulNMh) -- CPU-only symbolic policies matching GNN performance (MEDIUM confidence, relevant for lightweight approach validation)
- [PPO for Branching Policies](https://arxiv.org/html/2511.12986) -- RL-based branching, included to justify NOT using RL for offline training (MEDIUM confidence)
- [ICLR 2025 -- Learning to Select Nodes in Branch](https://proceedings.iclr.cc/paper_files/paper/2025/file/82f625a28d822d2748b9f5c4f9a89bb9-Paper-Conference.pdf) -- tripartite graph features (MEDIUM confidence)
- [SATzilla instance features](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27) -- Revisiting SATzilla features in 2024 (MEDIUM confidence)
- [Adaptive Operator Selection survey](https://ieeexplore.ieee.org/document/10904096/) -- AOS patterns for online adaptation (MEDIUM confidence)
- [Neural CO with Heavy Decoder -- small-to-large generalization](https://arxiv.org/abs/2310.07985) -- LEHD model for size generalization (MEDIUM confidence)

**Codebase analysis:**
- `cbqs/src/Branching.h` -- BranchingStats_t struct, BranchingFunction inline (HIGH confidence)
- `cbqs/src/solver_ctx.h` -- solver_ctx_set_branching_weights() API (HIGH confidence)
- `cbqs/Model.pyx` -- set_param/get_param, _PARAM_DEFS registry, solve() flow (HIGH confidence)
- `cbqs/SearchLib.pyx` -- branching weight propagation to C context, callback mechanism (HIGH confidence)
- `cbqs/result.py` -- OptimizeResult structure (HIGH confidence)

---
*Feature research for: CBQS v3.0 ML-Based Adaptive Branching Weight Learning*
*Researched: 2026-02-26*
*Supersedes: v1.1 FEATURES.md (2026-02-06)*
