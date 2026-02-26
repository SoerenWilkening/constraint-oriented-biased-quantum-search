# Architecture Research: v3.0 ML-Based Adaptive Branching

**Domain:** ML integration into existing Python/Cython/C combinatorial optimization solver (CBQS)
**Researched:** 2026-02-26
**Confidence:** HIGH (direct codebase analysis + domain research)

---

## Executive Summary

The v3.0 milestone adds ML-based learning of branching weights to the CBQS solver. The existing architecture already has the exact hook point needed: `branching_weights` is a float array on `solver_ctx_t.branching_stats` that directly feeds `BranchingFunction()` in the C kernel. The ML system needs to (a) extract features from problem instances, (b) predict branching weights, and (c) adapt weights during solve based on feedback. This document maps each capability onto the existing codebase and recommends new components, integration points, and build order.

The key architectural decision: feature extraction and ML inference happen in Python, weight updates flow through the existing `set_param('branching_weights', ...)` API, and online adaptation hooks into the existing callback mechanism. No C-level changes are needed for the core ML integration. The C kernel remains a pure computation engine that consumes weights; the Python layer owns all learning logic.

---

## Existing Architecture (Reference)

### Current Weight Flow

```
Python (Model.set_param)
    |
    v
Model._params['branching_weights'] = np.array(...)  (validated, stored)
    |
    v
Cython (SearchLib.run_sampling)
    |  copies np.array -> C double* via calloc + memcpy
    v
C (solver_ctx_set_branching_weights)
    |  L1-normalizes, stores in ctx->branching_stats.branching_weights
    v
C (BranchingFunction, inline in Branching.h)
    |  reads ctx->branching_stats.branching_weights[index]
    |  combines with assignment_bias + look_ahead in 3-term formula
    v
Per-variable branching probability -> sampling decision
```

### Current Callback Flow

```
C (ctg main loop, SearchLib.c line 198-204)
    |  on improvement: callback() [with GIL]
    v
Cython (my_callback_c, with gil)
    |
    v
Python (_history_callback_fn via _SolveState per-thread dict)
    |  reads mod.mod[0].global_opt[0].tot_profit
    |  reads mod.mod[0].con[0].num_constraints
    |  appends (value, elapsed) to history
    v
History list returned in OptimizeResult
```

### Key Existing Integration Points

| Existing Component | What It Provides for ML | Location |
|---|---|---|
| `set_param('branching_weights', arr)` | Entry point for setting learned weights | Model.pyx line 275 |
| `solver_ctx_set_branching_weights()` | C-level weight injection with L1 normalization | solver_ctx.c line 139 |
| `BranchingFunction()` | Consumes weights per variable in 3-term formula | Branching.h line 73 |
| `_SolveState` callback dict | Per-thread callback state during solve | SearchLib.pyx line 139 |
| `callback` param in `_PARAM_DEFS` | User callback invoked on improvement | Model.pyx line 94 |
| `OptimizeResult.history` | Post-solve improvement trajectory | result.py |
| `new_constraints_t` | Constraint structure (coefficients, RHS, sparsity) | constraint.h |
| `model_t` | Objective/constraint data accessible from Cython | model.h |

---

## Recommended Architecture for v3.0

### System Overview

```
+=========================================================================+
|  New Python Layer: cbqs/ml/                                              |
|                                                                          |
|  +------------------+  +-------------------+  +----------------------+   |
|  | FeatureExtractor |  | WeightPredictor   |  | AdaptiveController   |   |
|  | (features.py)    |  | (predictor.py)    |  | (adaptive.py)        |   |
|  +--------+---------+  +---------+---------+  +----------+-----------+   |
|           |                      |                       |               |
|           | np.array features    | np.array weights      | callback      |
|           v                      v                       v               |
|  +--------------------------------------------------------------------+  |
|  | TrainingPipeline (pipeline.py)                                      |  |
|  | Orchestrates: collect data -> extract features -> train -> persist  |  |
|  +--------------------------------------------------------------------+  |
+=========================================================================+
           |                      |                       |
           | features             | set_param(weights)    | set_param(callback)
           v                      v                       v
+=========================================================================+
|  Existing Python/Cython Layer                                            |
|  Model.set_param() -> SearchLib.run_sampling() -> solver_ctx_t           |
+=========================================================================+
           |
           v (nogil)
+=========================================================================+
|  Existing C Kernel (UNCHANGED)                                           |
|  BranchingFunction() reads ctx->branching_stats.branching_weights[i]     |
+=========================================================================+
```

### New Component Responsibilities

| Component | Responsibility | Communicates With |
|---|---|---|
| `FeatureExtractor` | Extract per-variable and per-instance features from Model | Model (reads constraints, objective, structure) |
| `WeightPredictor` | Map features -> branching weights using trained ML model | FeatureExtractor (input), Model.set_param (output) |
| `AdaptiveController` | Online weight adjustment during solve via callback | Model callback mechanism, WeightPredictor |
| `TrainingPipeline` | Offline training: run instances, collect results, fit model | FeatureExtractor, WeightPredictor, Model.solve() |
| `TrainingData` | Storage/serialization of training examples | TrainingPipeline (writes), WeightPredictor (reads) |

---

## Component Design

### Component 1: FeatureExtractor (cbqs/ml/features.py)

**Purpose:** Extract numerical features from a closed Model that characterize the problem instance and individual variables. These features become the input to the ML model.

**Where extraction happens: Python, not C.** The constraint and objective data is accessible from Cython/Python via `mod.mod[0].con` and `mod.mod[0].obj`. Feature extraction runs once before solve (at close time or before solve), not during the hot loop. There is no performance benefit to doing this in C -- it runs once per instance.

**Feature categories:**

| Category | Features | Source | Per-Variable? |
|---|---|---|---|
| **Instance-level** | num_variables, num_constraints, constraint density, avg_clause_length | `model_t`, `new_constraints_t` | No |
| **Variable-constraint** | num_constraints_containing_var, avg_coefficient_magnitude, constraint_tightness | `new_constraints_t.variables`, `factors`, `rhs` | Yes |
| **Objective** | coefficient_in_objective, relative_obj_coefficient | `new_constraints_t` (obj) | Yes |
| **Structural** | variable_degree (in constraint graph), constraint_degree_of_neighbors | Derived from constraint matrix | Yes |

**Interface:**

```python
class FeatureExtractor:
    """Extract features from a closed CBQS Model for ML-based weight prediction."""

    def extract(self, model: Model) -> np.ndarray:
        """Extract per-variable feature matrix from a closed model.

        Parameters
        ----------
        model : Model
            A closed model (close() has been called).

        Returns
        -------
        np.ndarray
            Feature matrix of shape (n_variables, n_features).
        """
        ...

    def extract_instance_features(self, model: Model) -> np.ndarray:
        """Extract instance-level features (for transfer learning).

        Returns
        -------
        np.ndarray
            Feature vector of shape (n_instance_features,).
        """
        ...

    @property
    def feature_names(self) -> list[str]:
        """Names of per-variable features for interpretability."""
        ...
```

**Data access pattern:** The FeatureExtractor needs to iterate over `model.con_expr` (Python list of constraint expressions) and access the underlying C data via Cython. Two approaches:

- **Option A (recommended):** Build a helper Cython function in SearchLib.pyx (or a new `features.pyx`) that extracts raw constraint matrix data into numpy arrays. FeatureExtractor then works with pure numpy.
- **Option B:** Access `mod.mod[0].con[0].*` fields directly from Cython within the Python class. This is possible because Model.pyx exposes `mod` as a typed attribute.

Option A is recommended because it keeps the ML module as pure Python (easier to test, no Cython compilation for the ML layer).

### Component 2: WeightPredictor (cbqs/ml/predictor.py)

**Purpose:** Map extracted features to branching weights using a trained sklearn model.

**ML model choice: GradientBoostingRegressor with warm_start=True.** This is the recommended model because:

1. Gradient boosting handles tabular feature data well (constraint structure is inherently tabular)
2. `warm_start=True` allows incremental training -- add more trees when new data arrives
3. sklearn's GradientBoostingRegressor supports `warm_start` natively (verified in sklearn 1.8 docs)
4. It produces feature importances for interpretability
5. It handles the per-variable regression task naturally (predict one weight per variable)

**Alternative considered:** Random Forest with `warm_start=True` -- simpler but typically less accurate on structured prediction tasks. Neural networks -- overkill for this feature space, adds PyTorch dependency.

**Interface:**

```python
class WeightPredictor:
    """Predict branching weights from problem features."""

    def __init__(self, model_path: str | None = None):
        """Load a trained model or initialize a new one."""
        ...

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict branching weights for each variable.

        Parameters
        ----------
        features : np.ndarray
            Feature matrix of shape (n_variables, n_features).

        Returns
        -------
        np.ndarray
            Non-negative weight array of shape (n_variables,).
        """
        ...

    def fit(self, X: np.ndarray, y: np.ndarray, warm_start: bool = False):
        """Train or incrementally update the model.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix of shape (n_samples, n_features).
        y : np.ndarray
            Target weights of shape (n_samples,).
        warm_start : bool
            If True, add trees to existing model instead of retraining.
        """
        ...

    def save(self, path: str): ...
    def load(self, path: str): ...
```

**Weight target construction:** The target `y` for training is derived from solve performance. For a given instance, the "ideal" branching weights are those that led to the best solve performance. This is computed retrospectively from successful solve runs (see TrainingPipeline below).

### Component 3: AdaptiveController (cbqs/ml/adaptive.py)

**Purpose:** Adjust branching weights during solve based on real-time feedback from the callback mechanism.

**Where online adaptation hooks in: Python-level callback.** The existing callback mechanism (`_SolveState` per-thread dict in SearchLib.pyx) fires on every improvement. The AdaptiveController wraps the user callback and adjusts weights between solve iterations.

**Critical constraint:** Branching weights are set ONCE per solve context creation (in `run_sampling()` before the `ctg()` call). The C kernel reads `ctx->branching_stats.branching_weights` throughout the solve but there is no mechanism to update weights mid-solve without modifying C code.

**Two adaptation strategies:**

**Strategy A: Inter-solve adaptation (recommended first).** Run multiple shorter solves, adjusting weights between each based on performance feedback. This requires no C changes.

```python
class AdaptiveController:
    """Adapt branching weights across multiple solve calls."""

    def __init__(self, predictor: WeightPredictor, feature_extractor: FeatureExtractor,
                 learning_rate: float = 0.1, reward_blend: float = 0.5):
        ...

    def initial_weights(self, model: Model) -> np.ndarray:
        """Get initial weights from predictor for a model."""
        features = self.feature_extractor.extract(model)
        return self.predictor.predict(features)

    def adapt(self, model: Model, result: OptimizeResult) -> np.ndarray:
        """Compute updated weights based on solve result.

        Uses a combined reward signal:
        - Objective improvement rate: delta_obj / solve_time
        - Constraint satisfaction rate: num_feasible_improvements / total_improvements

        Returns updated weights to use for next solve call.
        """
        ...

    def run_adaptive_solve(self, model: Model, num_rounds: int = 5,
                           time_per_round: int = 60) -> OptimizeResult:
        """Run multiple solve rounds with weight adaptation between rounds.

        Parameters
        ----------
        model : Model
            Closed model ready to solve.
        num_rounds : int
            Number of adaptive solve rounds.
        time_per_round : int
            Seconds per round.

        Returns
        -------
        OptimizeResult
            Best result across all rounds.
        """
        ...
```

**Strategy B: Intra-solve adaptation (deferred).** Modify `solver_ctx_t` to support weight updates during solve via a flag or function pointer. This requires adding a C-level "weight update" hook but enables more responsive adaptation. Deferred because it requires C kernel changes and careful thread-safety analysis.

**Reward signal design:**

```
reward = alpha * objective_improvement_rate + (1 - alpha) * constraint_satisfaction_rate

where:
  objective_improvement_rate = (best_obj_start - best_obj_end) / solve_time
  constraint_satisfaction_rate = num_feasible_in_history / len(history)
  alpha = reward_blend parameter (default 0.5)
```

**Weight update rule (exponential moving average):**

```
new_weights[i] = (1 - lr) * old_weights[i] + lr * gradient_estimate[i]

where gradient_estimate is derived from:
  - Variables that appeared in improving solutions get positive gradient
  - Variables that appeared in worsening moves get negative gradient
  - Computed from the difference between current solution and best solution
```

### Component 4: TrainingPipeline (cbqs/ml/pipeline.py)

**Purpose:** Orchestrate offline training: run solver on a set of instances, collect performance data, extract features, construct training targets, and fit the WeightPredictor.

**Interface:**

```python
class TrainingPipeline:
    """Offline training pipeline for branching weight learning."""

    def __init__(self, feature_extractor: FeatureExtractor,
                 predictor: WeightPredictor):
        ...

    def collect_training_data(self, instances: list[Model],
                              solves_per_instance: int = 10,
                              time_per_solve: int = 30) -> TrainingData:
        """Run solver on instances and collect performance data.

        For each instance, runs multiple solves with different random weights
        and records which weight configurations led to better performance.
        """
        ...

    def construct_targets(self, data: TrainingData) -> tuple[np.ndarray, np.ndarray]:
        """Convert raw performance data into (X, y) training pairs.

        X: per-variable features from each instance
        y: target weights derived from best-performing solves
        """
        ...

    def train(self, instances: list[Model], **kwargs) -> WeightPredictor:
        """Full pipeline: collect data, extract features, train model."""
        data = self.collect_training_data(instances, **kwargs)
        X, y = self.construct_targets(data)
        self.predictor.fit(X, y)
        return self.predictor
```

**Training data collection strategy:**

1. For each training instance, run N solves with varied branching weights (random perturbations around uniform)
2. Record: (instance_features, branching_weights_used, solve_quality)
3. solve_quality = combined metric of time-to-best, final objective, feasibility
4. Best-performing weight configurations become positive training examples
5. Worst-performing become negative examples
6. This generates supervised regression data: features -> optimal weights

### Component 5: TrainingData (cbqs/ml/data.py)

**Purpose:** Structured storage for training examples with serialization.

```python
@dataclass
class SolveRecord:
    """Record of a single solve run for training."""
    instance_id: str
    features: np.ndarray           # (n_vars, n_features)
    weights_used: np.ndarray       # (n_vars,)
    objective: float | None
    feasible: bool
    solve_time: float
    history: list[tuple]
    quality_score: float           # derived reward metric

@dataclass
class TrainingData:
    """Collection of solve records for training."""
    records: list[SolveRecord]

    def save(self, path: str): ...

    @classmethod
    def load(cls, path: str) -> 'TrainingData': ...

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Convert to (X, y) arrays for sklearn."""
        ...
```

---

## Data Flow

### Offline Training Flow

```
Training Instances (list[Model])
    |
    v
TrainingPipeline.collect_training_data()
    |  For each instance:
    |    1. FeatureExtractor.extract(model) -> features
    |    2. Generate N random weight perturbations
    |    3. For each perturbation:
    |       a. model.set_param('branching_weights', weights)
    |       b. model.solve() -> OptimizeResult
    |       c. Record (features, weights, result)
    |
    v
TrainingData (list of SolveRecords)
    |
    v
TrainingPipeline.construct_targets()
    |  For each instance:
    |    1. Rank solves by quality_score
    |    2. Best-performing weights become targets
    |    3. Features -> target weights pairs
    |
    v
(X, y) arrays
    |
    v
WeightPredictor.fit(X, y)
    |
    v
Trained GradientBoostingRegressor
    |
    v
predictor.save('model.pkl')
```

### Online Prediction Flow (Single Solve)

```
New Instance (Model, closed)
    |
    v
FeatureExtractor.extract(model) -> features
    |
    v
WeightPredictor.predict(features) -> weights
    |
    v
model.set_param('branching_weights', weights)
    |
    v
model.solve() -> OptimizeResult
```

### Online Adaptive Flow (Multi-Round)

```
New Instance (Model, closed)
    |
    v
AdaptiveController.run_adaptive_solve(model, num_rounds=5)
    |
    +-- Round 1:
    |     features = extract(model)
    |     weights = predictor.predict(features)
    |     model.set_param('branching_weights', weights)
    |     model.set_param('stopping_time', time_per_round)
    |     result = model.solve()
    |
    +-- Round 2..N:
    |     weights = controller.adapt(model, previous_result)
    |     model.reset()
    |     model.set_param('branching_weights', weights)
    |     result = model.solve()
    |
    v
Best OptimizeResult across all rounds
```

---

## Project Structure

```
cbqs/
    ml/                        # NEW: ML module (pure Python)
        __init__.py            # Public API exports
        features.py            # FeatureExtractor
        predictor.py           # WeightPredictor (sklearn wrapper)
        adaptive.py            # AdaptiveController
        pipeline.py            # TrainingPipeline
        data.py                # TrainingData, SolveRecord
        _cython_helpers.pyx    # OPTIONAL: fast feature extraction helpers
    src/                       # EXISTING: C kernel (UNCHANGED)
        Branching.h            # BranchingFunction (reads weights, no changes)
        solver_ctx.h           # solver_ctx_t (no changes needed)
        solver_ctx.c           # Weight setter (no changes needed)
        ...
    SearchLib.pyx              # EXISTING: minor change for feature data export
    Model.pyx                  # EXISTING: no changes needed
    result.py                  # EXISTING: no changes needed
    __init__.py                # EXISTING: add ml imports

tests/
    test_ml/                   # NEW: ML-specific tests
        test_features.py       # Feature extraction tests
        test_predictor.py      # Predictor tests
        test_adaptive.py       # Adaptive controller tests
        test_pipeline.py       # Pipeline integration tests
    ...
```

### Structure Rationale

- **cbqs/ml/ as pure Python:** The ML module does not need Cython compilation. It consumes data from the existing Cython layer via the public Model API. This keeps the build simple and allows rapid iteration on the ML components without recompiling Cython/C.
- **Optional _cython_helpers.pyx:** If feature extraction on the constraint matrix proves slow in pure Python (unlikely for n < 10000), a Cython helper can provide fast iteration over the C constraint data.
- **Tests in test_ml/:** Isolates ML tests from existing solver tests. ML tests can use small synthetic instances for fast iteration.

---

## Integration Points: New vs Modified Components

### New Components (6 files)

| File | Type | Purpose |
|---|---|---|
| `cbqs/ml/__init__.py` | Python | Package init, public exports |
| `cbqs/ml/features.py` | Python | FeatureExtractor class |
| `cbqs/ml/predictor.py` | Python | WeightPredictor class (sklearn) |
| `cbqs/ml/adaptive.py` | Python | AdaptiveController class |
| `cbqs/ml/pipeline.py` | Python | TrainingPipeline class |
| `cbqs/ml/data.py` | Python | TrainingData, SolveRecord dataclasses |

### Modified Components (2 files, minimal changes)

| File | Change | Reason |
|---|---|---|
| `cbqs/__init__.py` | Add conditional import of `ml` subpackage | Make `from cbqs.ml import ...` work |
| `pyproject.toml` / `setup.py` | Add `scikit-learn` as optional dependency | sklearn needed for ML components |

### Unchanged Components (everything else)

| Component | Why Unchanged |
|---|---|
| C kernel (all .c/.h files) | ML inference happens in Python; weights flow through existing `set_param` API |
| Cython bindings (all .pyx/.pxd) | No new C functions to wrap; existing API sufficient |
| Model.pyx | `set_param('branching_weights')` already validates and stores weights |
| SearchLib.pyx | `run_sampling()` already copies weights to solver_ctx_t |
| result.py | OptimizeResult already captures all needed feedback data |

---

## Architectural Patterns

### Pattern 1: Python-Only ML Layer Above Cython Boundary

**What:** All ML logic (feature extraction, inference, training) lives in pure Python. The only interaction with the solver is through `Model.set_param()`, `Model.solve()`, and `OptimizeResult`.

**When to use:** When the ML component does not need to run in the hot loop. Feature extraction runs once per instance. Weight prediction runs once per solve (or once per adaptation round).

**Trade-offs:**
- Pro: No Cython recompilation for ML changes. Easy to test. Easy to swap ML backends.
- Pro: Clean separation -- ML team does not need to understand C kernel.
- Con: Cannot adapt weights mid-solve without C changes (deferred to Strategy B).
- Con: Feature extraction from constraint data requires traversing Python/Cython boundary.

**This is the right pattern because:** Branching weights are set before solve and remain constant during solve. The ML model only needs to make one prediction per solve call. The performance-critical path (BranchingFunction called millions of times) is already in C and unchanged.

### Pattern 2: Multi-Round Adaptive Solve

**What:** Instead of modifying the C kernel for intra-solve adaptation, run multiple shorter solves with weight updates between them.

**When to use:** When the existing callback mechanism cannot modify solver state mid-solve (which is the current case -- `solver_ctx_t.branching_stats` is not updated during `ctg()`).

**Trade-offs:**
- Pro: Zero C changes. Uses existing `Model.reset()` + `Model.solve()` cycle.
- Pro: Each round benefits from a warm start (previous best solution via `manual_initial()`).
- Con: Overhead of context creation/teardown per round.
- Con: Short rounds may not explore enough to generate useful feedback.

**Example:**

```python
controller = AdaptiveController(predictor, extractor, learning_rate=0.1)

for round_num in range(5):
    weights = controller.adapt(model, last_result) if round_num > 0 else controller.initial_weights(model)
    model.set_param('branching_weights', weights)
    model.set_param('stopping_time', 60)

    if round_num > 0:
        # Warm-start from previous best
        model.manual_initial(last_result.objective, list(last_result.solution))

    model.reset()
    last_result = model.solve()
```

### Pattern 3: sklearn as Optional Dependency

**What:** The ML module checks for sklearn at import time and provides clear error messages if missing.

**When to use:** Always -- sklearn should not be a required dependency for the core solver.

```python
# cbqs/ml/__init__.py
try:
    import sklearn
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

def _require_sklearn():
    if not _HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for cbqs.ml. "
            "Install it with: pip install scikit-learn"
        )
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Feature Extraction in C

**What people do:** Write feature extraction in C for "performance."
**Why it's wrong:** Feature extraction runs once per instance, not in the hot loop. C feature extraction would require new C functions, new Cython wrappers, and complex memory management for variable-length feature arrays. The development cost far exceeds the negligible runtime benefit.
**Do this instead:** Extract features in pure Python using the data already accessible through Model's Python attributes and Cython properties.

### Anti-Pattern 2: Modifying BranchingFunction() for ML

**What people do:** Add ML inference calls inside `BranchingFunction()` in C.
**Why it's wrong:** `BranchingFunction()` is a `static inline` function called millions of times per solve (once per variable per sample). Adding any overhead here -- even a pointer indirection to a callback -- would measurably impact performance. It already reads `branching_weights[index]` which is the correct integration point.
**Do this instead:** Compute weights before solve, store them in `branching_weights[]`. The function already uses them via the 3-term formula.

### Anti-Pattern 3: Tight Coupling Between ML and Solver State

**What people do:** Have the ML module directly access `mod.mod[0]` C-level fields.
**Why it's wrong:** Creates fragile coupling to C struct layout. Any C refactoring breaks the ML module. Violates the Python/Cython/C layer boundaries.
**Do this instead:** Access data through the Python API (`model.n`, `model.con_expr`, etc.) or create explicit Cython helper functions that export constraint data as numpy arrays.

### Anti-Pattern 4: Training on Predicted Weights

**What people do:** Use the model's own predictions as training targets (circular learning).
**Why it's wrong:** Creates a feedback loop where the model reinforces its own biases. Degenerates to a fixed point that may be far from optimal.
**Do this instead:** Generate training targets from actual solve performance: run multiple solves with varied weights, measure quality, use the best-performing configurations as targets.

---

## Scaling Considerations

| Instance Size | Feature Extraction | Prediction | Adaptation |
|---|---|---|---|
| n < 100 vars | < 1ms (negligible) | < 1ms | 5 rounds * 10s = 50s total |
| n < 1000 vars | < 10ms (constraint matrix iteration) | < 5ms | 5 rounds * 30s = 150s total |
| n < 10000 vars | < 100ms (may benefit from Cython helper) | < 10ms | 5 rounds * 60s = 300s total |
| n > 10000 vars | Consider Cython helper for constraint graph | < 50ms | Time-limited, 3-5 rounds |

**First bottleneck:** Training data collection (running many solves per instance). Mitigate with joblib parallelism across instances.

**Second bottleneck:** Feature extraction on large instances. Mitigate with optional Cython helper if needed.

**Not a bottleneck:** ML inference (single sklearn predict call), weight injection (single `set_param` call), BranchingFunction overhead (zero -- weights are pre-computed).

---

## Suggested Build Order

The build order follows dependency chains. Each phase produces a testable, standalone component.

### Phase 1: FeatureExtractor (foundation, no ML dependency)

**Build:** `cbqs/ml/features.py`, `cbqs/ml/__init__.py`, `tests/test_ml/test_features.py`

**Why first:** All other ML components depend on features. This can be tested with existing solver infrastructure (create a Model, close it, extract features, verify shape and values). Zero external dependencies beyond numpy (already required).

**Dependencies:** None (uses existing Model API).

**Testable output:** Given a Model with known constraints, verify feature values match expected calculations.

### Phase 2: WeightPredictor (core ML component)

**Build:** `cbqs/ml/predictor.py`, `cbqs/ml/data.py`, `tests/test_ml/test_predictor.py`

**Why second:** The predictor wraps sklearn and provides the predict/fit/save/load interface. Can be tested with synthetic feature data (no need for real solver runs yet).

**Dependencies:** Phase 1 (feature format), sklearn (optional dependency).

**Testable output:** Given synthetic features, predict weights, verify shape and non-negativity. Fit on synthetic data, verify loss decreases.

### Phase 3: TrainingPipeline (offline training)

**Build:** `cbqs/ml/pipeline.py`, `tests/test_ml/test_pipeline.py`

**Why third:** Connects FeatureExtractor + WeightPredictor + Model.solve() into a complete offline training workflow. This is where we validate that learned weights actually improve solve performance.

**Dependencies:** Phase 1 + Phase 2 + existing solver.

**Testable output:** Train on small benchmark instances, verify learned weights improve objective over uniform weights on held-out instances.

### Phase 4: AdaptiveController (online adaptation)

**Build:** `cbqs/ml/adaptive.py`, `tests/test_ml/test_adaptive.py`

**Why fourth:** Most complex component -- requires both a trained predictor AND the ability to interpret solve results as feedback. The multi-round adaptive loop is the culmination of all prior components.

**Dependencies:** Phase 1 + Phase 2 + Phase 3 (needs a pre-trained model to start from).

**Testable output:** Run adaptive solve on benchmark instance, verify objective improves across rounds (weights converge toward better configuration).

### Phase 5: Integration and Documentation

**Build:** Update `cbqs/__init__.py`, `pyproject.toml`, integration tests, user documentation.

**Why last:** All components are individually tested. This phase wires them together and ensures the public API is clean.

**Dependencies:** All prior phases.

**Testable output:** End-to-end: `from cbqs.ml import AdaptiveController; controller.run_adaptive_solve(model)` works and produces better results than baseline.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Pure Python ML layer | No Cython build complexity for ML. Clean layer separation. |
| GradientBoostingRegressor | Best sklearn model for tabular features. warm_start for incremental training. |
| Inter-solve adaptation (not intra-solve) | Zero C changes. Uses existing Model.reset() + solve() cycle. |
| Feature extraction in Python | Runs once per instance. C extraction adds complexity for negligible speedup. |
| sklearn as optional dependency | Core solver should not require ML libraries. |
| Per-variable features -> per-variable weights | Direct mapping matches the existing branching_weights array structure. |
| Combined reward signal | Balances objective improvement and constraint satisfaction for robust adaptation. |
| Multi-round with warm start | Previous best solution seeds next round via manual_initial(). |

---

## Deferred Architecture (Future Milestones)

### Intra-Solve Weight Updates (v3.1+)

Would require adding to `solver_ctx_t`:

```c
typedef struct solver_ctx {
    // ... existing fields ...
    int weights_dirty;                    // flag: 1 = weights updated, 0 = no change
    double *pending_weights;              // new weights to swap in
    int pending_weights_n;                // length of pending array
} solver_ctx_t;
```

And a check in the `ctg()` main loop (after the improvement check):

```c
if (ctx->weights_dirty) {
    // Swap pending_weights into branching_stats.branching_weights
    solver_ctx_set_branching_weights(ctx, ctx->pending_weights, ctx->pending_weights_n);
    ctx->weights_dirty = 0;
}
```

The Python callback would write to `ctx->pending_weights` (via a new Cython function), and the C loop would pick it up on the next iteration. This is thread-safe because the callback holds the GIL, and the C loop checks the flag after releasing the GIL.

**Why deferred:** Adds complexity to the C kernel. The multi-round approach (Strategy A) may be sufficient. Only pursue if benchmarks show inter-solve adaptation is too coarse.

---

## Sources

- Direct codebase analysis of all files listed in the architecture walkthrough (HIGH confidence)
- `Branching.h` lines 73-116: BranchingFunction inline implementation
- `solver_ctx.h` lines 31-64: solver_ctx_t struct definition
- `solver_ctx.c` lines 139-174: solver_ctx_set_branching_weights implementation
- `Model.pyx` lines 238-307: set_param/get_param with branching_weights validation
- `SearchLib.pyx` lines 185-334: run_sampling with ctx creation and weight propagation
- `SearchLib.pyx` lines 139-183: _SolveState callback mechanism
- `SearchLib.c` lines 108-230: ctg() main loop with callback invocation
- [ML for Combinatorial Optimization survey](https://github.com/Thinklab-SJTU/awesome-ml4co) (ML4CO approaches)
- [sklearn ensemble documentation](https://scikit-learn.org/stable/modules/ensemble.html) (warm_start for GradientBoosting)
- [Influence branching for online MIP solving](https://arxiv.org/html/2510.04273v1) (online adaptation approaches)
- [Learning to Branch in Combinatorial Optimization](https://arxiv.org/pdf/2307.01434) (feature extraction from constraint structure)

---

*Architecture research for: CBQS v3.0 ML-based adaptive branching*
*Researched: 2026-02-26*
