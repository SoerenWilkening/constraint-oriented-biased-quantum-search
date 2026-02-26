# Stack Research: v3.0 ML-Based Adaptive Branching Weights

**Domain:** ML-augmented combinatorial optimization solver
**Researched:** 2026-02-26
**Confidence:** HIGH (scikit-learn versions verified via PyPI/official docs; integration points verified via codebase inspection)

---

## Recommended Stack

### Core ML Library

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| scikit-learn | >=1.6,<2.0 | Offline training + online adaptation of branching weight vectors | Already the project's stated target (PROJECT.md). Supports Python 3.13.7. Provides both batch `fit()` and incremental `partial_fit()` on same estimator classes. No GPU dependency. Pure Python/C/Cython internals match CBQS architecture. |

**Version rationale:** scikit-learn 1.6+ supports Python 3.13. The latest stable is 1.8.0 (released 2025-12-10). Pin `>=1.6,<2.0` for forward compatibility without risking a major-version break. PassiveAggressiveRegressor was deprecated in 1.8 (removed in 1.10), so do not use it -- use SGDRegressor instead.

**Dependency pattern:** Optional, matching the existing gurobipy pattern. The solver must work without sklearn installed. ML features are additive.

### Specific Estimators

| Estimator | Module | Purpose | Why This One |
|-----------|--------|---------|--------------|
| `SGDRegressor` | `sklearn.linear_model` | Online weight adaptation during solve | Only regression estimator with `partial_fit()` that is not deprecated. Supports L2/L1/ElasticNet penalties. Single-sample updates with O(n_features) cost -- fast enough for mid-solve callback. |
| `ExtraTreesRegressor` | `sklearn.ensemble` | Offline training: problem features to weight vectors | Natively supports multi-output regression (predicts full n-dimensional weight vector in one call). Faster training than RandomForestRegressor because splits are random rather than optimized. Handles mixed feature scales without normalization. |
| `StandardScaler` | `sklearn.preprocessing` | Feature normalization for SGDRegressor | SGDRegressor is sensitive to feature scale. StandardScaler supports `partial_fit()` for incremental normalization. Required for online adaptation path; optional for tree-based offline path. |

### Supporting Libraries (Already Present -- No New Installs)

| Library | Version | Purpose | Why No Change |
|---------|---------|---------|---------------|
| numpy | >=1.20 (already required) | Feature arrays, weight vectors, L1 normalization | Already a hard dependency. scikit-learn requires numpy anyway. Feature vectors and weight vectors are numpy arrays. |
| joblib | >=1.0 (already required) | Model persistence (save/load trained models) | Already a hard dependency. scikit-learn uses joblib internally for model persistence (`joblib.dump`/`joblib.load`). No need for a separate persistence library. |

### What Is NOT Needed

| Technology | Why Not | What to Use Instead |
|------------|---------|---------------------|
| scipy | Not needed for this milestone. Feature extraction uses numpy array operations only. Constraint structure features are already accessible via the C-level `new_constraints_t` struct. | numpy for all array math |
| pandas | Was removed in v2.1 for good reason. Training data is simple (feature vectors + weight vectors), not tabular with heterogeneous types. | numpy arrays directly |
| PyTorch / TensorFlow | Massive overkill. The branching weight vector is n-dimensional (problem size), features are ~10-20 dimensional. This is a classic sklearn regression problem, not a deep learning problem. Adds 500MB+ dependency. | scikit-learn |
| XGBoost / LightGBM | Marginal accuracy gain over ExtraTreesRegressor for this problem size, but adds a binary dependency with build complexity. ExtraTrees is built into sklearn. | `sklearn.ensemble.ExtraTreesRegressor` |
| ONNX / skl2onnx | Model serialization for deployment. CBQS is a research solver, not a production service. joblib persistence is sufficient. | `joblib.dump` / `joblib.load` |
| dask-ml | Distributed training. Training data for branching weights is small (hundreds to low thousands of instances). Single-machine sklearn is sufficient. | `sklearn` directly |
| MLPRegressor | Has `partial_fit()` but neural networks are harder to tune, less interpretable, and overkill for this feature dimension. If a nonlinear online model is needed later, upgrade then. | SGDRegressor for online; ExtraTreesRegressor for offline |

---

## Integration Points with Existing System

### 1. branching_weights Array (Primary Output)

The ML model's output is a numpy array that feeds directly into the existing `set_param('branching_weights', array)` API. The array:
- Must be 1D, non-negative, length n (number of variables)
- Is L1-normalized at set-time inside `solver_ctx_set_branching_weights()` in C
- Flows through `BranchingFunction()` as `stats->branching_weights[index]`

**No C kernel changes needed for the weight vector itself.** The existing pipeline handles normalization and integration into the 3-term branching formula.

### 2. Feature Extraction (New Python Module)

Features come from problem structure accessible via the Model object:
- `model.n` -- number of variables
- `model.con_expr` -- constraint expressions (Python-level)
- `model.mod.con` -- C-level `new_constraints_t` with constraint statistics
- `model.mod.obj` -- C-level `new_constraints_t` with objective structure

Feature extraction should be a pure Python module (`cbqs/ml/features.py`) that operates on the Model after `close()` is called. No Cython or C code needed for feature extraction -- the existing Python/Cython accessors expose everything required.

### 3. Online Adaptation via Callback (Reward Signal)

The existing callback mechanism (`set_param('callback', fn)`) fires after each sampling iteration. The `_SolveState` per-thread dict in `SearchLib.pyx` already tracks:
- `mod.mod[0].global_opt[0].tot_profit` -- current best objective
- `mod.mod[0].con[0].num_constraints` -- constraint count
- Elapsed time via `time_mod.monotonic() - state.start_time`

**Online adaptation flow:**
1. Callback fires with current solve state
2. Python-level adapter computes reward signal (objective improvement rate + constraint satisfaction delta)
3. `SGDRegressor.partial_fit()` updates the model with one sample
4. New weight vector is predicted and set via `set_param('branching_weights', new_weights)`
5. Next sampling iteration uses updated weights (propagated to `solver_ctx_t` at worker creation)

**Critical constraint:** `set_param('branching_weights', ...)` currently only takes effect when a new `solver_ctx_t` is created (at the start of `run_sampling`). For mid-solve adaptation, the weights would need to be updated on the active `solver_ctx_t`. This requires a new Cython function to update weights on a live context, or restructuring the sampling loop to re-read weights periodically. This is an architectural decision, not a stack decision.

### 4. Model Persistence

Trained models are saved/loaded using joblib (already a dependency):
```python
import joblib
joblib.dump(trained_model, 'branching_model.joblib')
loaded_model = joblib.load('branching_model.joblib')
```

No new persistence library needed. The `.joblib` files should live in a user-specified directory, not bundled with the package.

---

## Installation

### Production (optional ML features)

```python
# In setup.py extras_require:
extras_require={
    "test": ["pytest>=7.0"],
    "dev": ["pytest>=7.0", "Cython>=3.0"],
    "ml": ["scikit-learn>=1.6,<2.0"],       # NEW
}
```

```bash
# User installs ML features explicitly:
pip install cbqs[ml]

# Or: pip install scikit-learn>=1.6
```

### Development

```bash
# Add to requirements-dev.txt:
scikit-learn>=1.6,<2.0
```

### Import Guard Pattern

```python
# cbqs/ml/__init__.py
try:
    import sklearn
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

def require_sklearn():
    if not HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for ML features. "
            "Install with: pip install cbqs[ml]"
        )
```

This matches the existing pattern for gurobipy:
```python
# cbqs/Model.pyx line 11-14
try:
    from .CircuitBackendBinder import circuit
except ImportError:
    circuit = None
```

---

## Estimator Selection Rationale

### Offline Training: ExtraTreesRegressor

**Problem:** Given problem features (constraint density, variable count, objective structure, etc.), predict a good initial branching weight vector (n-dimensional output).

**Why ExtraTreesRegressor:**
1. **Native multi-output:** Predicts the full weight vector in one `fit()`/`predict()` call. The criterion computation at tree splits takes into account all outputs by summing the criterion for each output. This naturally captures correlations between weight components.
2. **No feature scaling required:** Tree-based models are invariant to feature scale and monotonic transformations. Problem features (constraint count, density ratio, variable count) have very different scales.
3. **Fast training:** Faster than RandomForestRegressor because splits are chosen randomly rather than optimally. For the training set size expected (hundreds to low thousands of instances), training completes in seconds.
4. **Non-negative output:** Post-process with `np.maximum(predictions, 0)` to ensure non-negative weights before L1 normalization (done in C).

**Why not RandomForestRegressor:** Slower training with marginal accuracy gain for this problem size. ExtraTrees has slightly higher variance but the L1 normalization downstream absorbs small prediction differences.

**Why not MultiOutputRegressor wrapper:** Wrapping a single-output model in MultiOutputRegressor learns each weight independently, losing correlations. ExtraTreesRegressor handles multi-output natively and is better.

### Online Adaptation: SGDRegressor

**Problem:** During solve, update weight predictions based on observed reward signals (objective improvement, constraint satisfaction).

**Why SGDRegressor:**
1. **`partial_fit()` support:** The only non-deprecated sklearn regression estimator with true online learning. One call updates the model with O(n_features) cost.
2. **Low latency:** A `partial_fit()` call on 10-20 features takes microseconds. This is called inside the solve callback, so speed matters.
3. **Regularization control:** L2 penalty (`penalty='l2'`) prevents weight explosion during online updates. ElasticNet available if sparse solutions are needed.
4. **Learning rate scheduling:** `learning_rate='invscaling'` naturally reduces updates as more data is seen, stabilizing weights over the solve.

**Why not PassiveAggressiveRegressor:** Deprecated in sklearn 1.8, removed in 1.10. The sklearn team recommends SGDRegressor with `loss="epsilon_insensitive", penalty=None, learning_rate="pa1"` as a replacement.

**Single-output limitation:** SGDRegressor predicts one output. For multi-output online adaptation, use `sklearn.multioutput.MultiOutputRegressor(SGDRegressor(...))` which wraps n independent SGDRegressors -- each predicting one weight component. The `partial_fit()` call propagates to all sub-estimators. This is acceptable because:
- Online updates are incremental corrections, not full predictions
- The overhead of n independent models is still O(n * n_features) per update
- Correlation between weights matters less for small corrections than for initial predictions

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| ExtraTreesRegressor (offline) | RandomForestRegressor | If variance in weight predictions is too high and you need more stable predictions. RF is slightly more biased but lower variance. |
| ExtraTreesRegressor (offline) | GradientBoostingRegressor | If training data is large (>10K instances) and you need maximum accuracy. GBR with early stopping would outperform, but requires careful tuning. |
| SGDRegressor (online) | Direct weight perturbation (no ML) | If the overhead of sklearn import and partial_fit is measurable in the solve loop. A simple exponential moving average of reward-weighted perturbations would work with zero dependencies. |
| scikit-learn (whole library) | Custom numpy-only implementation | If the optional dependency is unacceptable. A basic linear regression with online SGD update is ~50 lines of numpy code. Loses cross-validation, pipelines, and model persistence convenience. |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| scikit-learn >=1.6,<2.0 | Python 3.13.7 | sklearn 1.6 supports 3.9-3.13; 1.7 supports 3.10-3.13; 1.8 supports 3.11-3.14. All work with project's Python 3.13.7. |
| scikit-learn >=1.6 | numpy >=1.20 | sklearn requires numpy. Project already pins numpy>=1.20. Compatible. |
| scikit-learn >=1.6 | joblib >=1.0 | sklearn uses joblib internally. Project already pins joblib>=1.0. No version conflict. |
| scikit-learn >=1.6 | Cython 3 | No interaction. sklearn is a pure Python dependency; Cython builds the C extensions. |

**Zero conflicts with existing dependencies.** scikit-learn's transitive dependencies (numpy, scipy, joblib, threadpoolctl) are either already present or are non-conflicting additions. Note: sklearn does pull in scipy as a transitive dependency, but this is managed by pip and does not need to be listed as a direct dependency.

---

## Stack Patterns by Variant

**If training data is very small (<50 instances):**
- Use `ExtraTreesRegressor(n_estimators=50)` with reduced forest size
- Skip cross-validation; use leave-one-out instead
- Because small data means overfitting risk is high with large forests

**If online adaptation proves too slow in the callback:**
- Replace SGDRegressor with direct numpy-based exponential moving average
- `weights = alpha * reward_weighted_features + (1 - alpha) * weights`
- Because this eliminates the sklearn import overhead and function call overhead

**If weight predictions need to be non-negative (they do):**
- Post-process: `weights = np.maximum(model.predict(features), 0.0)`
- The existing L1 normalization in `solver_ctx_set_branching_weights()` handles the rest
- Because tree regressors can predict negative values for out-of-distribution inputs

**If the project later needs per-constraint weights (not just per-variable):**
- The 3-term `BranchingFunction` formula would need extension in `Branching.h`
- ExtraTreesRegressor output dimension changes but the sklearn pipeline stays the same
- Because the stack is independent of the weight vector's semantic meaning

---

## Sources

- [scikit-learn 1.8.0 official documentation](https://scikit-learn.org/stable/) -- estimator APIs, version support
- [scikit-learn PyPI page](https://pypi.org/project/scikit-learn/) -- version 1.8.0 confirmed as latest stable
- [SGDRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDRegressor.html) -- partial_fit API, parameter details
- [ExtraTreesRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.ExtraTreesRegressor.html) -- multi-output support, native behavior
- [RandomForestRegressor multi-output comparison](https://scikit-learn.org/stable/auto_examples/ensemble/plot_random_forest_regression_multioutput.html) -- native vs wrapper multi-output
- [scikit-learn scaling strategies](https://scikit-learn.org/stable/computing/scaling_strategies.html) -- partial_fit incremental learning guide
- [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html) -- joblib.dump/load as recommended approach
- [PassiveAggressiveRegressor deprecation (1.8)](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PassiveAggressiveRegressor.html) -- deprecated, use SGDRegressor instead
- Codebase inspection: `Branching.h` (BranchingFunction formula), `solver_ctx.h` (BranchingStats_t struct), `solver_ctx.c` (L1 normalization in solver_ctx_set_branching_weights), `Model.pyx` (_PARAM_DEFS registry, set_param validation), `SearchLib.pyx` (solver_ctx creation and weight propagation, _SolveState callback mechanism)

---

## Confidence Assessment

| Item | Confidence | Source |
|------|------------|--------|
| scikit-learn version compatibility with Python 3.13.7 | HIGH | Official docs, PyPI |
| SGDRegressor as only non-deprecated online regressor | HIGH | sklearn 1.8 deprecation notice for PassiveAggressiveRegressor |
| ExtraTreesRegressor native multi-output support | HIGH | Official docs, comparison example |
| Integration with existing set_param('branching_weights') | HIGH | Direct codebase inspection of Model.pyx and solver_ctx.c |
| Online adaptation via callback mechanism | MEDIUM | Codebase inspection shows the path is feasible, but mid-solve weight update to live solver_ctx_t needs new Cython code |
| No scipy needed as direct dependency | HIGH | Feature extraction uses numpy arrays; scipy comes transitively via sklearn |
| joblib sufficient for model persistence | HIGH | Official sklearn docs recommend joblib; already a dependency |
| Feature extraction feasible from Python level | HIGH | Model.con_expr, model.n, and Cython-accessible C struct fields provide all needed data |

---
*Stack research for: CBQS v3.0 ML-based adaptive branching weight learning*
*Researched: 2026-02-26*
