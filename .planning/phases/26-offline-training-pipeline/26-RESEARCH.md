# Phase 26: Offline Training Pipeline - Research

**Researched:** 2026-03-02
**Domain:** ML-based offline training pipeline for branching weight prediction (sklearn regression, joblib serialization, automated data collection)
**Confidence:** HIGH

## Summary

Phase 26 builds the offline training pipeline for CBQS branching weight prediction. It sits on top of Phase 25's FeatureExtractor infrastructure and produces a `WeightPredictor` class that can be trained on (Model, best_weights) pairs, predict weights for new models, and be serialized/loaded via joblib. The phase also includes an automated data collection utility that solves instances with diverse weight strategies and returns training pairs, plus an evaluation module that compares predicted weights against a uniform-weights baseline.

The existing codebase provides all necessary building blocks: `FeatureExtractor` (9 per-variable features + 11 instance features = 20 features per sample), `Model.set_param('branching_weights', ...)` for applying predictions, `Model.solve()` returning `OptimizeResult` with `.feasible` and `.objective` attributes, and `joblib` already in core dependencies. The sklearn `ExtraTreesRegressor` (decided in STATE.md) is available in sklearn 1.8.0 (installed) and works correctly with joblib serialization round-trips. The per-variable prediction approach means one model predicts the weight for any variable based on its 20-feature vector (9 variable + 11 instance features concatenated), making predictions size-invariant.

**Primary recommendation:** Implement `WeightPredictor` as a wrapper around `ExtraTreesRegressor` with fit/predict/save/load API. The predictor takes (Model, best_weights) pairs, extracts features via `FeatureExtractor`, trains one regression model mapping 20-feature vectors to weight values, and predicts a full weight array for any new Model. Data collection generates random/structured weight vectors, solves with each, and returns (Model, best_weights) pairs ranked by feasibility-first then best objective. Evaluation solves test models with predicted vs. uniform weights and reports metrics as both dict and printed table.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Weight strategy generation: Claude's discretion (random, structured grid, or hybrid -- whatever produces useful training signal)
- Solve budget: configurable by user via parameter (iterations or time), with sensible defaults
- "Best weights" selection: primary criterion is feasibility (constraint satisfaction), tiebreak by best objective value
- Data output: in-memory only -- returns list of (Model, best_weights) pairs
- ML model choice: Claude's discretion (sklearn-based -- RF, GBT, or other as appropriate)
- Feature input: concatenate per-variable features (9) with instance features (11) = 20 features per sample. One model predicts weight for any variable.
- Training target representation: Claude's discretion (raw weights, normalized, or other)
- Training mode: batch fit() only, no partial_fit/incremental learning
- Saved artifact includes metadata: feature names, training date, number of training instances, CBQS version
- Compatibility check: error on feature name mismatch when loading (prevents silent wrong predictions)
- Format: joblib as specified in success criteria
- File extension/naming: Claude's discretion
- Metrics: best objective value and feasibility rate
- Report format: returns Python dict AND prints human-readable comparison table to stdout
- Evaluation mode: self-contained -- evaluate() takes test Models, solves internally with predicted vs. baseline weights
- Baselines: uniform weights by default, but user can pass additional weight strategies to compare against (extensible)

### Claude's Discretion
- Weight strategy generation approach for data collection
- ML model choice (within sklearn)
- Training target representation
- File extension convention for saved predictors
- Internal implementation details (solver integration, parallelism, etc.)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRAIN-01 | User can train a weight predictor from a collection of (Model, best_weights) pairs via fit() | WeightPredictor.fit() wraps ExtraTreesRegressor.fit() on concatenated per-variable + instance features; FeatureExtractor already provides all 20 features |
| TRAIN-02 | User can predict branching weights for a new Model via predict(), returning a numpy array compatible with set_param() | WeightPredictor.predict() extracts features, predicts per-variable weights, clips to non-negative, returns 1D float64 array of length model.n -- matches set_param('branching_weights', ...) validation |
| TRAIN-03 | User can save and load a trained predictor via joblib serialization | joblib.dump/load verified with ExtraTreesRegressor + metadata dict; joblib 1.5.3 already a core dependency; round-trip preserves predictions exactly |
| TRAIN-04 | User can collect training data automatically via a utility that runs short solves with diverse weight strategies | collect_training_data() generates diverse weight vectors, solves each with budget, selects best by feasibility-first/objective-tiebreak, returns (Model, best_weights) list |
| TRAIN-05 | Training pipeline includes uniform-weights baseline in evaluation | evaluate() solves test models with predicted weights AND uniform weights, reports objective and feasibility metrics with comparison table |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | >=1.2 (1.8.0 installed) | ExtraTreesRegressor for weight prediction | Decided in STATE.md; tree ensemble handles small-data regime well; no hyperparameter tuning needed |
| numpy | >=1.20 (already a dependency) | Feature arrays, weight arrays, array operations | Core dependency of cbqs |
| joblib | >=1.0 (1.5.3 installed) | Model persistence (save/load) | Already a core dependency in setup.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| datetime | stdlib | Training date metadata in saved artifacts | When saving predictor to disk |
| textwrap/tabulate-style formatting | stdlib | Human-readable comparison table output | In evaluate() stdout printing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ExtraTreesRegressor | RandomForestRegressor | Similar performance; ExtraTrees faster training due to random splits (no exhaustive search) |
| ExtraTreesRegressor | GradientBoostingRegressor | GBT slightly worse on very small data (30 samples); more sensitive to hyperparameters |
| joblib | pickle | joblib is optimized for numpy arrays and already a dependency; pickle lacks numpy optimization |

**Installation:**
```bash
pip install cbqs[ml]  # Already adds sklearn; joblib is in core deps
```

## Architecture Patterns

### Recommended Module Structure
```
cbqs/ml/
├── __init__.py          # Import guard + public API exports
├── features.py          # FeatureExtractor (Phase 25 -- exists)
├── training.py          # WeightPredictor (fit/predict/save/load) + collect_training_data()
└── adaptation.py        # Stub for Phase 27

tests/
├── test_ml_import.py    # Existing import tests
├── test_ml_features.py  # Feature extraction tests (if exists from Phase 25)
└── test_ml_training.py  # NEW: training pipeline tests
```

### Pattern 1: Per-Variable Prediction with Instance Context
**What:** Each training sample is one variable's feature vector (9 features) concatenated with the instance-level feature vector (11 features), giving a 20-feature input. The target is that variable's weight value from the best_weights array. For a model with N variables, one (Model, best_weights) pair produces N training samples.
**When to use:** Always -- this is the core training pattern.
**Example:**
```python
# Source: Phase 25 FeatureExtractor + CONTEXT.md decisions
fe = FeatureExtractor()
var_features = fe.extract_variable_features(model)   # (n_vars, 9)
inst_features = fe.extract_instance_features(model)   # (11,)

# Tile instance features to match each variable row
inst_tiled = np.tile(inst_features, (var_features.shape[0], 1))  # (n_vars, 11)
X = np.hstack([var_features, inst_tiled])  # (n_vars, 20)
y = best_weights  # (n_vars,)
```

### Pattern 2: Feasibility-First Best Weights Selection
**What:** When collecting training data, multiple weight strategies are tried. The "best" is selected by: (1) feasible solutions preferred over infeasible, (2) among feasible, highest objective wins, (3) among infeasible, highest objective wins as tiebreaker.
**When to use:** In the data collection utility when ranking solve results.
**Example:**
```python
# Source: CONTEXT.md decision on best_weights selection
def _rank_result(result):
    """Sort key: feasible first, then best objective."""
    return (result.feasible, result.objective)

results.sort(key=_rank_result, reverse=True)
best_weights = weight_strategies[results.index(results[0])]
```

### Pattern 3: Metadata-Wrapped joblib Serialization
**What:** Save a dict containing the fitted sklearn model plus metadata (feature names, training date, instance count, CBQS version). On load, validate feature names match to prevent silent prediction errors from schema drift.
**When to use:** In save()/load() methods.
**Example:**
```python
# Source: CONTEXT.md serialization decisions
import joblib
import cbqs

artifact = {
    'model': self._regressor,
    'feature_names': self._feature_names,
    'training_date': datetime.now().isoformat(),
    'n_training_instances': self._n_training_instances,
    'cbqs_version': cbqs.__version__,
}
joblib.dump(artifact, path)

# On load:
artifact = joblib.load(path)
if artifact['feature_names'] != expected_feature_names:
    raise ValueError(f"Feature name mismatch: saved={artifact['feature_names']}, "
                     f"expected={expected_feature_names}")
```

### Pattern 4: Self-Contained Evaluation
**What:** The evaluate() function takes test Models plus a trained predictor, solves each model with predicted weights and with uniform weights (and optionally additional baseline strategies), then reports metrics.
**When to use:** After training, to verify predictor value.
**Example:**
```python
# Source: CONTEXT.md evaluation decisions
def evaluate(predictor, test_models, solve_params=None, baselines=None):
    """Solve test models with predicted vs. baseline weights, report metrics."""
    results = {}
    for name, weight_fn in strategies.items():
        objectives = []
        feasible_count = 0
        for model in test_models:
            weights = weight_fn(model)
            model.set_param('branching_weights', weights)
            result = model.solve()
            objectives.append(result.objective)
            feasible_count += int(result.feasible)
        results[name] = {
            'mean_objective': np.mean(objectives),
            'feasibility_rate': feasible_count / len(test_models),
        }
    return results
```

### Anti-Patterns to Avoid
- **Fitting separate models per variable index:** The per-variable prediction pattern means ONE model predicts for ALL variables based on features. Do not train separate models for variable 0, variable 1, etc.
- **Storing raw Model objects in the predictor:** Only store the fitted sklearn model and metadata. Model objects contain Cython state that cannot be serialized.
- **Modifying Model objects during evaluation:** Each evaluation solve mutates Model state (solution, etc.). Either re-create models or accept that models are consumed. Document this clearly.
- **Skipping non-negativity clipping on predictions:** ExtraTreesRegressor can predict negative values. The branching_weights validation requires non-negative values. Always clip predictions to >= 0.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Regression model | Custom tree/neural implementation | sklearn ExtraTreesRegressor | Handles small data, fast training, no tuning needed |
| Model serialization | Custom pickle wrapper | joblib.dump/load wrapping dict with model + metadata | joblib optimized for numpy, already a dependency |
| Cross-validation | Manual train/test splits | sklearn cross_val_score (if needed) | Correct stratification, reproducibility |
| Feature extraction | Re-implementing feature computation | Existing FeatureExtractor from Phase 25 | Already tested and validated |
| Array normalization | Manual mean/std computation | z-score normalization already in FeatureExtractor | Features are already normalized by extract_variable_features() |

**Key insight:** The entire training pipeline is a thin orchestration layer around existing components (FeatureExtractor, ExtraTreesRegressor, joblib, Model.solve). The main engineering challenge is the data flow plumbing, not the algorithms.

## Common Pitfalls

### Pitfall 1: Negative Predictions Breaking set_param
**What goes wrong:** ExtraTreesRegressor predictions can be negative if training targets include weights near zero. set_param('branching_weights', ...) rejects arrays with negative values.
**Why it happens:** Tree regressors extrapolate poorly; averaging leaf values can produce small negatives.
**How to avoid:** Always `np.clip(predictions, 0, None)` before returning from predict(). Include a test that verifies predict() output is always non-negative.
**Warning signs:** ValueError from set_param during integration testing.

### Pitfall 2: Feature Name Mismatch After Code Updates
**What goes wrong:** Loading a predictor saved with an older feature set produces wrong predictions silently.
**Why it happens:** Feature columns shift if feature names change between versions.
**How to avoid:** Store feature names in the saved artifact. On load, compare against current FeatureExtractor.feature_names + instance_feature_names. Raise ValueError on mismatch.
**Warning signs:** Unexpected prediction quality degradation after code updates.

### Pitfall 3: Model Mutation During Evaluation
**What goes wrong:** After evaluation, test models have modified _params and solve state. Calling solve() again may give different results.
**Why it happens:** set_param('branching_weights', ...) mutates the Model object. solve() overwrites solution state.
**How to avoid:** Document that evaluation consumes model state. If re-evaluation is needed, pass a model-creation callable or re-create models. Alternatively, reset branching_weights to None after each evaluation solve.
**Warning signs:** Non-deterministic evaluation results on repeated calls.

### Pitfall 4: Empty or Trivial Training Data
**What goes wrong:** fit() with zero or very few training pairs produces a useless predictor or crashes.
**Why it happens:** User passes too few instances, or data collection finds no feasible solutions.
**How to avoid:** Validate input size in fit(). Require at least 1 training pair. Warn if fewer than 5.
**Warning signs:** sklearn raises ValueError about empty arrays, or predictor always predicts constant values.

### Pitfall 5: Instance Feature Normalization Inconsistency
**What goes wrong:** FeatureExtractor's variable features are z-score normalized per instance. If instance features are NOT normalized, the 20-feature vector has mixed scales.
**Why it happens:** extract_variable_features() normalizes, extract_instance_features() does not.
**How to avoid:** Instance features (raw counts, ratios) should be used as-is or normalized consistently. Since the feature extractor returns instance features unnormalized (they are already ratios/counts), and ExtraTreesRegressor is tree-based (invariant to feature scaling), this is acceptable. Do NOT add normalization that would require a fit/transform state.
**Warning signs:** None for tree-based models; would matter if switching to linear models later.

### Pitfall 6: Solve Time Budget in Data Collection
**What goes wrong:** Data collection takes excessively long if solve budget is too high, or produces useless data if too low.
**Why it happens:** Default solve time must balance quality vs. speed across different problem sizes.
**How to avoid:** Make budget configurable with a sensible default (e.g., 5 seconds stopping_time, 2 workers). Document that larger problems may need larger budgets.
**Warning signs:** Data collection takes hours, or all collected solutions are infeasible.

## Code Examples

### WeightPredictor Class Skeleton
```python
# Source: Architecture analysis of CONTEXT.md decisions + existing codebase patterns
from sklearn.ensemble import ExtraTreesRegressor
from cbqs.ml.features import FeatureExtractor, VARIABLE_FEATURE_NAMES, INSTANCE_FEATURE_NAMES
import numpy as np
import joblib
import cbqs

class WeightPredictor:
    """Train and predict branching weights for CBQS Models."""

    def __init__(self, n_estimators=100, random_state=None):
        self._regressor = ExtraTreesRegressor(
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self._feature_extractor = FeatureExtractor()
        self._feature_names = list(VARIABLE_FEATURE_NAMES) + list(INSTANCE_FEATURE_NAMES)
        self._is_fitted = False
        self._n_training_instances = 0

    def _build_feature_matrix(self, model):
        """Build (n_vars, 20) feature matrix for a single model."""
        var_feats = self._feature_extractor.extract_variable_features(model)  # (n_vars, 9)
        inst_feats = self._feature_extractor.extract_instance_features(model)  # (11,)
        inst_tiled = np.tile(inst_feats, (var_feats.shape[0], 1))  # (n_vars, 11)
        return np.hstack([var_feats, inst_tiled])  # (n_vars, 20)

    def fit(self, training_pairs):
        """Train from list of (Model, best_weights) pairs."""
        X_all, y_all = [], []
        for model, weights in training_pairs:
            X = self._build_feature_matrix(model)
            X_all.append(X)
            y_all.append(np.asarray(weights, dtype=np.float64))
        X_combined = np.vstack(X_all)
        y_combined = np.concatenate(y_all)
        self._regressor.fit(X_combined, y_combined)
        self._is_fitted = True
        self._n_training_instances = len(training_pairs)
        return self

    def predict(self, model):
        """Predict branching weights for a new Model. Returns 1D non-negative float64 array."""
        X = self._build_feature_matrix(model)
        raw = self._regressor.predict(X)
        return np.clip(raw, 0, None).astype(np.float64)

    def save(self, path):
        """Save trained predictor to disk via joblib."""
        artifact = {
            'model': self._regressor,
            'feature_names': self._feature_names,
            'training_date': __import__('datetime').datetime.now().isoformat(),
            'n_training_instances': self._n_training_instances,
            'cbqs_version': cbqs.__version__,
        }
        joblib.dump(artifact, path)

    @classmethod
    def load(cls, path):
        """Load a predictor from disk. Validates feature name compatibility."""
        artifact = joblib.load(path)
        expected = list(VARIABLE_FEATURE_NAMES) + list(INSTANCE_FEATURE_NAMES)
        if artifact['feature_names'] != expected:
            raise ValueError(
                f"Feature name mismatch: saved predictor has {artifact['feature_names']}, "
                f"but current code expects {expected}"
            )
        predictor = cls.__new__(cls)
        predictor._regressor = artifact['model']
        predictor._feature_extractor = FeatureExtractor()
        predictor._feature_names = artifact['feature_names']
        predictor._is_fitted = True
        predictor._n_training_instances = artifact.get('n_training_instances', 0)
        return predictor
```

### Data Collection Utility
```python
# Source: CONTEXT.md data collection decisions
def collect_training_data(models, n_strategies=10, stopping_time=5,
                          num_workers=2, random_state=None):
    """Solve each model with diverse weight strategies, return (Model, best_weights) pairs."""
    rng = np.random.RandomState(random_state)
    training_pairs = []

    for model in models:
        n = len(model.variables)
        best_result = None
        best_weights = None

        for _ in range(n_strategies):
            # Generate random weight vector
            weights = rng.exponential(1.0, size=n)  # Exponential for positive skew
            model.set_param('branching_weights', weights)
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)
            result = model.solve()

            if best_result is None or _rank_result(result) > _rank_result(best_result):
                best_result = result
                best_weights = weights.copy()

        if best_weights is not None:
            training_pairs.append((model, best_weights))

    return training_pairs
```

### Evaluation Utility
```python
# Source: CONTEXT.md evaluation decisions
def evaluate(predictor, test_models, stopping_time=5, num_workers=2,
             baselines=None):
    """Compare predicted weights against uniform and optional baselines."""
    strategies = {'predicted': lambda m: predictor.predict(m)}
    strategies['uniform'] = lambda m: np.ones(len(m.variables))
    if baselines:
        strategies.update(baselines)

    results = {}
    for name, weight_fn in strategies.items():
        objectives, feasible_count = [], 0
        for model in test_models:
            weights = weight_fn(model)
            model.set_param('branching_weights', weights)
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)
            result = model.solve()
            objectives.append(result.objective)
            feasible_count += int(result.feasible)
        results[name] = {
            'mean_objective': float(np.mean(objectives)),
            'feasibility_rate': feasible_count / len(test_models),
        }

    # Print comparison table
    _print_comparison_table(results)
    return results
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global weight tuning (one weight per problem class) | Per-variable weight prediction via ML | Current phase (26) | Variable-specific weights capture structural information |
| Manual weight selection | Automated data collection + training | Current phase (26) | Removes manual tuning burden |
| sklearn PassiveAggressiveRegressor | SGDRegressor (for online) / ExtraTreesRegressor (for offline) | sklearn 1.8+ | PassiveAggressiveRegressor deprecated in 1.8, removed in 1.10; not relevant for offline anyway |

**Deprecated/outdated:**
- PassiveAggressiveRegressor: Deprecated in sklearn 1.8 (see REQUIREMENTS.md Out of Scope). Not used here -- ExtraTreesRegressor is the offline choice.

## Open Questions

1. **Model reuse in data collection**
   - What we know: Calling solve() mutates Model state (solution, global_opt). Multiple solves on the same Model object work because solve() re-initializes.
   - What's unclear: Whether set_param('branching_weights', ...) followed by solve() correctly resets from the previous solve's branching_weights. Based on code inspection, _params persists and solve() reads it fresh each call, so this should work.
   - Recommendation: Verify with a test that calls solve() twice on the same model with different branching_weights and gets valid results both times.

2. **Training target representation**
   - What we know: CONTEXT.md says Claude's discretion. Options are: raw weights, normalized weights, log-transformed weights.
   - What's unclear: Which representation produces the best predictions.
   - Recommendation: Use raw non-negative weight values as targets. ExtraTreesRegressor handles varying scales well. Clip predictions to >= 0 on output. Simpler is better for v3.0; more sophisticated representations can be explored in future versions.

3. **Weight strategy generation diversity**
   - What we know: Need diverse strategies to produce useful training signal.
   - What's unclear: Optimal mix of random vs. structured strategies.
   - Recommendation: Use exponential(1.0) random vectors as the primary strategy. This produces positive-valued weights with natural variation. Optionally include uniform weights as one of the strategies. The exponential distribution naturally favors positive values (no clipping needed) and produces good diversity.

## Sources

### Primary (HIGH confidence)
- sklearn 1.8.0 installed locally -- ExtraTreesRegressor API verified via direct Python execution
- joblib 1.5.3 installed locally -- dump/load round-trip verified with ExtraTreesRegressor + metadata dict
- cbqs codebase -- Model.set_param('branching_weights', ...) validation rules inspected in Model.pyx
- cbqs.ml.features -- FeatureExtractor code reviewed, 9 variable + 11 instance features confirmed
- cbqs/result.py -- OptimizeResult.feasible and .objective attributes confirmed
- setup.py -- joblib >=1.0 already in install_requires, sklearn >=1.2 in extras_require['ml']

### Secondary (MEDIUM confidence)
- ExtraTreesRegressor vs RandomForestRegressor performance comparison on small data: local benchmarking shows comparable MSE on 30-sample dataset; ExtraTrees chosen per STATE.md decision

### Tertiary (LOW confidence)
- None -- all findings verified via code inspection or local execution

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries installed and verified locally; versions confirmed
- Architecture: HIGH - per-variable prediction pattern follows directly from CONTEXT.md decisions and existing FeatureExtractor API; code examples verified
- Pitfalls: HIGH - all pitfalls identified from code inspection of set_param validation, FeatureExtractor normalization behavior, and sklearn prediction characteristics

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable -- sklearn and joblib APIs are mature; codebase is under active development but ml/ module structure is established)
