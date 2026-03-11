# Implementation Plan: CBQS ML Pipeline & Solver Enhancements

**Approach**: Modular, test-driven. Each new module ≤ 400–500 lines. Tests written before implementation.

---

## Module Map

```
Phase 1: C Foundation
  ├── M1: solver_ctx phase-specific stats     (C, ~80 lines changed)
  ├── M2: ctg() stage switching               (C, ~50 lines changed)
  └── M3: branching_bias validation           (Cython, ~20 lines changed)

Phase 2: Variable Ordering
  ├── M4: variable_order in BranchingStats_t  (C, ~60 lines changed)
  └── M5: CSearch ordering iteration          (C, ~80 lines changed)

Phase 3: Python Parameter Layer
  ├── M6: ml/phase_params.py        (NEW, ~250 lines)
  └── M7: Model.pyx phase params    (Cython, ~120 lines changed)

Phase 4: ML Infrastructure
  ├── M8:  ml/signals.py            (NEW, ~150 lines)
  ├── M9:  ml/regressors.py         (NEW, ~350 lines)
  ├── M10: ml/training_log.py       (NEW, ~450 lines)
  └── M11: ml/data_collection.py    (NEW, ~400 lines)

Phase 5: Trainers
  ├── M12: ml/sat_trainer.py        (NEW, ~350 lines)
  └── M13: ml/opt_trainer.py        (NEW, ~450 lines)

Phase 6: Integration
  ├── M14: ml/adaptation.py update  (~100 lines changed)
  └── M15: End-to-end wiring        (SearchLib.pyx, ~80 lines changed)
```

---

## Phase 1: C Foundation

### M1 — Phase-Specific BranchingStats in solver_ctx_t

**Files changed**: `cbqs/src/solver_ctx.h`, `cbqs/src/solver_ctx.c`

**Tests first** (`tests/test_solver_ctx_phases.c`, ~150 lines):
```
test_three_stats_initialized_with_defaults
test_set_sat_bias_independent_of_opt
test_set_opt_sat_weights_independent_of_sat
test_set_opt_bias_independent_of_opt_sat
test_free_releases_all_three_stats
test_default_values_match_current_defaults
```

**Changes to `solver_ctx.h`** (~30 lines added):
- Replace `BranchingStats_t branching_stats` with:
  ```c
  BranchingStats_t branching_stats_sat;
  BranchingStats_t branching_stats_opt_sat;
  BranchingStats_t branching_stats_opt;
  BranchingStats_t *active_stats;  // pointer to currently active phase
  ```
- Keep `branching_stats` as an alias macro for backwards compat during transition:
  ```c
  #define branching_stats branching_stats_opt  // temporary compat
  ```

**Changes to `solver_ctx.c`** (~50 lines added):
- `solver_ctx_create()`: Initialize all three stats with same defaults (bias=5.0, branching_factor=1.0, bias_factor=1.0, look_ahead_factor=0.0). Set `active_stats = &ctx->branching_stats_opt_sat`.
- Add phase-specific setters:
  ```c
  void solver_ctx_set_sat_bias(solver_ctx_t *ctx, double bias);
  void solver_ctx_set_opt_sat_bias(solver_ctx_t *ctx, double bias);
  void solver_ctx_set_opt_bias(solver_ctx_t *ctx, double bias);
  // Same pattern for: _weights, _branching_factor, _bias_factor, _look_ahead_factor
  ```
- `solver_ctx_free()`: Free weights for all three stats.
- Existing unprefixed setters (`solver_ctx_set_bias`, etc.) set ALL three stats (backwards compat).

**Done when**: All 6 tests pass. Existing tests still pass (compat macro).

---

### M2 — ctg() Stage Switching

**Files changed**: `cbqs/src/SearchLib.c`

**Tests first** (`tests/test_stage_switching.c`, ~200 lines):
```
test_satisfy_mode_uses_sat_stats
test_optimize_infeasible_uses_opt_sat_stats
test_stage2_constraint_tightening_uses_opt_sat_stats
test_stage3_optimization_uses_opt_stats
test_transition_1_to_2_switches_stats_pointer
test_transition_2_to_3_switches_stats_pointer
test_different_bias_per_stage_applied_correctly
```

**Changes to `SearchLib.c`** (~50 lines changed):
- At stage initialization (line ~126-139):
  ```c
  // Stage 1, SATISFY mode
  ctx->active_stats = &ctx->branching_stats_sat;

  // Stage 1, OPTIMIZE infeasible
  ctx->active_stats = &ctx->branching_stats_opt_sat;
  ```
- At stage 1→2 transition (line ~182):
  ```c
  ctx->active_stats = &ctx->branching_stats_opt_sat;  // stays opt_sat
  ```
- At stage 2→3 transition (line ~213):
  ```c
  ctx->active_stats = &ctx->branching_stats_opt;
  ```
- CSearch functions already receive `ctx`; change `&ctx->branching_stats` references to `ctx->active_stats`.

**Done when**: 7 tests pass. Verify stage transitions use correct stats by setting distinct bias values per phase and checking which value is active.

---

### M3 — branching_bias Validation

**Files changed**: `cbqs/Model.pyx`

**Tests first** (`tests/test_bias_validation.py`, ~60 lines):
```python
test_bias_minus_one_rejected()          # set_param('branching_bias', -1) raises ValueError
test_bias_below_minus_one_rejected()    # set_param('branching_bias', -5) raises ValueError
test_bias_just_above_minus_one_ok()     # set_param('branching_bias', -0.99) works
test_bias_positive_ok()                 # set_param('branching_bias', 5.0) works
test_bias_zero_ok()                     # set_param('branching_bias', 0) works
test_bias_none_resets_to_default()      # set_param('branching_bias', None) works
```

**Changes to `Model.pyx`** (~10 lines changed):
- Update `_PARAM_DEFS['branching_bias']` to add validation:
  ```python
  'branching_bias': {
      'default': None,
      'coerce': float,
      'validate': lambda v: v > -1,
      'validate_msg': 'branching_bias must be greater than -1',
      ...
  }
  ```

**Done when**: 6 tests pass. Existing tests still pass.

---

## Phase 2: Variable Ordering

### M4 — variable_order Array in BranchingStats_t

**Files changed**: `cbqs/src/Branching.h`, `cbqs/src/solver_ctx.h`, `cbqs/src/solver_ctx.c`

**Tests first** (`tests/test_variable_ordering.c`, ~200 lines):
```
test_default_ordering_is_identity           // [0,1,2,...,n-1] when no priorities
test_set_priorities_produces_sorted_order   // priorities [3,1,2] → order [0,2,1]
test_equal_priorities_stable_order          // ties broken by index
test_ordering_independent_per_phase         // sat order ≠ opt order
test_null_priorities_uses_default           // NULL priorities → identity order
test_set_variable_order_from_degrees        // degree-based default ordering
test_free_releases_ordering_arrays
```

**Changes to `Branching.h`** (~10 lines added):
```c
typedef struct {
    double *branching_weights;
    int num_weights;
    double branching_factor;
    double bias_factor;
    double bias;
    double look_ahead_factor;
    int *variable_order;     // NEW: iteration order, length = num_vars
    int num_vars;            // NEW: number of variables
} BranchingStats_t;
```

**Changes to `solver_ctx.c`** (~50 lines added):
- `solver_ctx_set_variable_order(BranchingStats_t *stats, double *priorities, int n)`:
  - Allocate `int[n]`, argsort priorities descending, store in `stats->variable_order`.
- `solver_ctx_set_default_order(BranchingStats_t *stats, int n)`:
  - Identity ordering `[0, 1, ..., n-1]`.
- `solver_ctx_set_degree_order(BranchingStats_t *stats, int *degrees, int n)`:
  - Sort by degree descending (most-constrained-first).
- Free ordering arrays in `solver_ctx_free()`.

**Done when**: 7 tests pass.

---

### M5 — CSearch Ordering Iteration

**Files changed**: `cbqs/src/solver.c`

**Tests first** (`tests/test_csearch_ordering.c`, ~250 lines):
```
test_csearch_sat_respects_ordering          // custom order changes sampling behavior
test_csearch_opt_sat_respects_ordering
test_csearch_opt_respects_ordering
test_identity_ordering_matches_original     // regression: same results as before
test_reverse_ordering_differs_from_forward  // ordering actually matters
test_ordering_with_weights_combined         // ordering + weights interact correctly
```

**Changes to `solver.c`** (~80 lines changed):
- In each CSearch function (`CSearch_opt_monte_carlo_sampler`, `CSearch_opt_sat_monte_carlo_sampler`, `CSearch_sat_monte_carlo_sampler`):
  - Replace:
    ```c
    for (i = 0; i < n; i++) {
    ```
  - With:
    ```c
    int *var_order = ctx->active_stats->variable_order;
    for (k = 0; k < n; k++) {
        i = var_order ? var_order[k] : k;
    ```
  - All existing references to `i` inside the loop remain unchanged.

**Done when**: 6 tests pass. All existing solver tests still pass (identity ordering = old behavior).

---

## Phase 3: Python Parameter Layer

### M6 — `ml/phase_params.py` (NEW, ~250 lines)

Phase-specific parameter definitions, resolution logic, and serialization helpers.

**Tests first** (`tests/test_phase_params.py`, ~300 lines):
```python
# Parameter definitions
test_all_phase_params_defined()                  # 15 phase-specific params exist
test_phase_param_names_follow_convention()        # sat_*, opt_sat_*, opt_*
test_each_phase_has_5_params()                    # weights, factor, bias_factor, bias, priorities

# Resolution logic
test_phase_specific_overrides_unprefixed()        # sat_bias=3 + bias=5 → sat gets 3
test_unprefixed_fallback_when_no_phase_param()    # bias=5, no sat_bias → sat gets 5
test_default_when_nothing_set()                   # no bias, no sat_bias → default
test_resolve_all_phases()                         # resolve returns dict with sat/opt_sat/opt keys
test_partial_phase_override()                     # only sat_bias set, others use unprefixed

# Validation
test_phase_bias_validates_gt_minus_one()
test_phase_weights_validates_array()
test_phase_priorities_validates_array()

# Serialization
test_params_to_ctx_dict()                         # flatten resolved params for C layer
test_round_trip_save_load()
```

**Implementation**:
```python
# cbqs/ml/phase_params.py (~250 lines)

PHASES = ('sat', 'opt_sat', 'opt')
PHASE_PARAM_SUFFIXES = ('branching_weights', 'branching_factor', 'bias_factor',
                        'branching_bias', 'variable_priorities')

class PhaseParamResolver:
    """Resolves phase-specific parameters with fallback to unprefixed defaults."""

    def __init__(self, param_store: dict, defaults: dict):
        ...

    def resolve(self, phase: str, param_suffix: str) -> any:
        """Resolution order: phase_param > unprefixed > default."""
        ...

    def resolve_all(self) -> dict:
        """Returns {phase: {suffix: value}} for all phases."""
        ...

    def to_ctx_kwargs(self) -> dict:
        """Flatten to kwargs for solver_ctx setters."""
        ...

# Parameter definition helpers
def make_phase_param_defs() -> dict:
    """Generate _PARAM_DEFS entries for all 15 phase-specific params."""
    ...

def validate_weights(value, n_vars):
    ...

def validate_priorities(value, n_vars):
    ...
```

**Done when**: 13 tests pass.

---

### M7 — Model.pyx Phase-Specific Parameters

**Files changed**: `cbqs/Model.pyx`

**Tests first** (`tests/test_model_phase_params.py`, ~250 lines):
```python
# Setting phase-specific params
test_set_sat_branching_weights()
test_set_opt_sat_branching_bias()
test_set_opt_variable_priorities()
test_set_phase_param_validates()
test_set_phase_param_none_resets()

# Resolution in solve context
test_solve_uses_phase_specific_when_set()
test_solve_falls_back_to_unprefixed()
test_solve_uses_default_when_nothing_set()

# Backwards compatibility
test_unprefixed_params_still_work()
test_existing_solve_unchanged()
```

**Changes to `Model.pyx`** (~120 lines added):
- Import `make_phase_param_defs` from `ml.phase_params`.
- Merge generated phase param defs into `_PARAM_DEFS`.
- In `set_param()`: No changes needed — generic validation handles new params.
- Add helper `_resolve_phase_params()` that uses `PhaseParamResolver`.

**Done when**: 10 tests pass. All existing Model tests still pass.

---

## Phase 4: ML Infrastructure

### M8 — `ml/signals.py` (NEW, ~150 lines)

Training signal computation: AUC and weighted combination.

**Tests first** (`tests/test_signals.py`, ~200 lines):
```python
# AUC computation
test_auc_single_point()                    # one incumbent → area = value * total_time
test_auc_two_points()                      # trapezoidal integration
test_auc_monotone_improving()              # increasing objective over time
test_auc_empty_history()                   # returns 0
test_auc_normalized_by_time()              # AUC / total_time gives average quality
test_auc_negative_objectives()             # works with negative values

# Weighted combination
test_weighted_basic()                      # score = obj - lambda * time
test_weighted_lambda_zero_equals_obj()     # lambda=0 → pure objective
test_weighted_high_lambda_penalizes_slow() # slow solutions scored lower
test_weighted_infeasible_penalty()         # infeasible gets large negative score

# Signal factory
test_signal_factory_auc()
test_signal_factory_weighted()
test_signal_factory_unknown_raises()

# Edge cases
test_auc_with_one_history_entry()
test_weighted_with_zero_time()
```

**Implementation**:
```python
# cbqs/ml/signals.py (~150 lines)

def compute_auc(history: list[tuple[float, float]], total_time: float) -> float:
    """Area under incumbent curve via trapezoidal rule.

    Args:
        history: [(objective_value, elapsed_seconds), ...] sorted by time
        total_time: total solve time for right boundary
    Returns:
        Integrated area (higher = better for maximization)
    """
    ...

def compute_weighted(objective: float, time_to_best: float,
                     lam: float, feasible: bool,
                     infeasible_penalty: float = -1e6) -> float:
    """Weighted combination: objective - lambda * time_to_best."""
    ...

def make_signal(name: str, **kwargs) -> callable:
    """Factory returning a scoring function from result objects.

    Args:
        name: 'auc' or 'weighted'
        kwargs: signal-specific parameters (e.g., lam for weighted)
    Returns:
        Callable(result) -> float
    """
    ...
```

**Done when**: 15 tests pass.

---

### M9 — `ml/regressors.py` (NEW, ~350 lines)

Wraps per-variable and instance regressors with warm-start, post-processing, and save/load.

**Tests first** (`tests/test_regressors.py`, ~350 lines):
```python
# VariableRegressor
test_var_regressor_fit_predict_shape()       # (n_samples*n_vars, 20) → (n_vars, k) per instance
test_var_regressor_weights_nonnegative()     # post-processing clips weights
test_var_regressor_warm_start_adds_trees()   # tree count increases
test_var_regressor_multi_output_sat()        # k=2: [weight, priority]
test_var_regressor_multi_output_opt()        # k=4: [opt_sat_w, opt_sat_p, opt_w, opt_p]

# InstanceRegressor
test_inst_regressor_fit_predict_shape()      # (n_samples, 11) → (k,) per instance
test_inst_regressor_bias_clipped()           # bias > -1 post-processing
test_inst_regressor_factors_nonneg()         # factors >= 0
test_inst_regressor_warm_start_adds_trees()
test_inst_regressor_sat_output()             # k=3: [bias, branching_factor, bias_factor]
test_inst_regressor_opt_output()             # k=6: [opt_sat_*, opt_*]

# PhasePredictor (composite)
test_phase_predictor_sat_predict()           # returns dict with weights, priorities, bias, factors
test_phase_predictor_opt_predict()           # returns dict with opt_sat_* and opt_*
test_phase_predictor_save_load_roundtrip()
test_phase_predictor_warm_start()
test_phase_predictor_initial_fit_tree_count()
test_phase_predictor_incremental_tree_count()
```

**Implementation**:
```python
# cbqs/ml/regressors.py (~350 lines)

class VariableRegressor:
    """Per-variable multi-output regressor with warm-start."""

    def __init__(self, n_outputs: int, n_estimators: int = 100, ...):
        self.model = ExtraTreesRegressor(
            n_estimators=n_estimators, warm_start=True, ...)
        self.n_outputs = n_outputs  # 2 for SAT, 4 for OPT

    def fit(self, X_list: list[np.ndarray], y_list: list[np.ndarray]):
        """Fit on list of per-instance feature matrices and target arrays."""
        # Stack all instances: (sum(n_vars_i), 20) → (sum(n_vars_i), n_outputs)
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict for single instance. Returns (n_vars, n_outputs)."""
        ...

    def add_trees(self, n_new: int):
        """Increase n_estimators for next warm-start fit."""
        ...

    @staticmethod
    def postprocess_weights(raw: np.ndarray) -> np.ndarray:
        """Clip to non-negative."""
        ...

    @staticmethod
    def postprocess_priorities(raw: np.ndarray) -> np.ndarray:
        """Return argsort order (descending priority)."""
        ...


class InstanceRegressor:
    """Instance-level regressor for global parameters."""

    def __init__(self, n_outputs: int, n_estimators: int = 100, ...):
        ...

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Fit on (n_instances, 11) → (n_instances, n_outputs)."""
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict for single instance. Returns (n_outputs,)."""
        ...

    @staticmethod
    def postprocess_globals(raw: np.ndarray, mode: str) -> dict:
        """Clip bias > -1, factors >= 0. Unpack into named dict."""
        ...


class PhasePredictor:
    """Composite predictor: variable + instance regressors for one trainer type."""

    def __init__(self, mode: str = 'sat', ...):
        # mode='sat': var(2 outputs) + inst(3 outputs)
        # mode='opt': var(4 outputs) + inst(6 outputs)
        ...

    def fit(self, features_list, targets_list):
        ...

    def predict(self, var_features, inst_features) -> dict:
        """Returns phase-keyed parameter dict ready for set_param."""
        ...

    def warm_start_fit(self, new_features, new_targets, n_new_trees=50):
        ...

    def save(self, path): ...
    def load(self, path): ...
```

**Done when**: 17 tests pass.

---

### M10 — `ml/training_log.py` (NEW, ~450 lines)

Structured JSON logging at three granularity levels with query and display interface.

**Tests first** (`tests/test_training_log.py`, ~350 lines):
```python
# Writing events
test_log_strategy_event()
test_log_model_event()
test_log_refit_event()
test_log_retrain_event()
test_log_preserves_order()

# Reading/querying
test_summary_returns_learning_curve()
test_model_details_returns_strategies()
test_strategies_filters_by_phase()
test_refit_history()

# File I/O
test_save_creates_json_file()
test_load_reads_back_events()
test_append_to_existing_file()
test_empty_log_summary()

# Display
test_summary_as_dataframe()
test_compare_two_logs()
test_plot_learning_curve_returns_figure()   # matplotlib figure object

# Edge cases
test_model_details_invalid_idx()
test_strategies_no_matching_phase()
test_log_with_numpy_arrays_serialized()
```

**Implementation**:
```python
# cbqs/ml/training_log.py (~450 lines)

import json
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class StrategyEvent:
    model_idx: int
    phase: str
    strategy_idx: int
    parameters: dict
    result: dict    # objective, feasible, time, auc, history

@dataclass
class ModelEvent:
    model_idx: int
    n_strategies_tried: int
    best_signal: float
    best_parameters: dict
    trivially_feasible: bool

@dataclass
class RefitEvent:
    n_training_models: int
    validation_score: float
    timestamp: str

@dataclass
class RetrainEvent:
    episode: int
    new_instances: list
    total_instances: int
    trees_before: int
    trees_after: int
    score_before: float
    score_after: float
    timestamp: str


class TrainingLog:
    """Structured training log with three granularity levels."""

    def __init__(self, path: str | Path | None = None):
        self._events = []
        self._path = Path(path) if path else None

    # --- Writing ---
    def log_strategy(self, **kwargs): ...
    def log_model(self, **kwargs): ...
    def log_refit(self, **kwargs): ...
    def log_retrain(self, **kwargs): ...
    def flush(self): ...   # write to disk

    # --- Querying ---
    def summary(self) -> list[dict]:
        """Learning curve: refit events with quality over time."""
        ...

    def model_details(self, model_idx: int) -> dict:
        """All strategies and summary for a model."""
        ...

    def strategies(self, model_idx: int, phase: str = None) -> list[dict]:
        """Per-strategy results, optionally filtered by phase."""
        ...

    def refit_history(self) -> list[dict]: ...

    # --- Display ---
    def plot_learning_curve(self, ax=None):
        """Plot validation score vs n_training_models."""
        ...

    def compare(self, other: 'TrainingLog') -> dict:
        """Side-by-side comparison of two training runs."""
        ...

    def to_dataframe(self, level: str = 'model'):
        """Convert events at given level to pandas DataFrame."""
        ...

    # --- I/O ---
    def save(self, path: str | Path | None = None): ...
    def load(self, path: str | Path): ...

    @staticmethod
    def _serialize_event(event) -> dict:
        """Handle numpy arrays and other non-JSON-serializable types."""
        ...
```

**Done when**: 18 tests pass.

---

### M11 — `ml/data_collection.py` (NEW, ~400 lines)

Random parameter sampling, feasibility screening, and Option C data collection.

**Tests first** (`tests/test_data_collection.py`, ~350 lines):
```python
# Random parameter generation
test_random_sat_params_shape()             # 2n+3 values in correct ranges
test_random_opt_params_shape()             # 4n+6 values
test_random_weights_nonneg()
test_random_bias_gt_minus_one()
test_random_params_diverse()               # N samples are not identical

# SAT data collection
test_collect_sat_data_returns_best()       # best by constraint count
test_collect_sat_data_tries_n_strategies()
test_collect_sat_data_with_timeout()

# OPT data collection (Option C)
test_trivially_feasible_detection()
test_feasibility_screening_selects_top_k()
test_full_solve_pairs_top_k_times_m()
test_option_c_returns_best_pair()
test_option_c_trivially_feasible_skips_opt_sat()
test_option_c_respects_time_budget()

# Signal integration
test_collect_with_auc_signal()
test_collect_with_weighted_signal()

# Edge cases
test_all_infeasible_strategies()
test_single_strategy()
```

**Implementation**:
```python
# cbqs/ml/data_collection.py (~400 lines)

import numpy as np

def random_sat_params(n_vars: int, rng: np.random.Generator) -> dict:
    """Sample random SAT parameters: weights(n), priorities(n), bias, bf, bif."""
    ...

def random_opt_params(n_vars: int, rng: np.random.Generator) -> dict:
    """Sample random OPT parameters: opt_sat(2n+3) + opt(2n+3)."""
    ...

def _evaluate_strategy(model, params: dict, phase: str,
                       time_budget: float) -> dict:
    """Run solver with given params, return result dict."""
    ...


class SATDataCollector:
    """Collect training data for SAT trainer."""

    def __init__(self, n_strategies: int = 10, time_budget: float = 30.0,
                 signal_fn: callable = None):
        ...

    def collect(self, model) -> dict:
        """Returns {features, best_params, best_signal, all_results}."""
        ...


class OPTDataCollector:
    """Collect training data for OPT trainer using Option C."""

    def __init__(self, n_opt_sat: int = 10, top_k: int = 3,
                 n_opt_per_candidate: int = 5,
                 screening_budget: float = None,
                 full_budget: float = None,
                 signal_fn: callable = None):
        ...

    def collect(self, model) -> dict:
        """Option C: screen opt_sat, then pair with opt, return best.

        Returns {features, best_opt_sat_params, best_opt_params,
                 best_signal, trivially_feasible, all_results}.
        """
        ...

    def _is_trivially_feasible(self, model) -> bool:
        ...

    def _screen_opt_sat(self, model) -> list[dict]:
        """Sample N opt_sat param vectors, quick feasibility eval, return top K."""
        ...

    def _evaluate_pairs(self, model, opt_sat_candidates: list) -> list[dict]:
        """For each opt_sat candidate, sample M opt params, full solve."""
        ...
```

**Done when**: 17 tests pass.

---

## Phase 5: Trainers

### M12 — `ml/sat_trainer.py` (NEW, ~350 lines)

End-to-end SAT training: data collection → feature extraction → regressor training → prediction.

**Tests first** (`tests/test_sat_trainer.py`, ~300 lines):
```python
# Core training
test_fit_single_model()
test_fit_multiple_models()
test_predict_returns_complete_params()      # weights, priorities, bias, bf, bif
test_predict_weights_nonneg()
test_predict_bias_gt_minus_one()

# Incremental training
test_warm_start_increases_trees()
test_warm_start_improves_or_maintains()
test_refit_frequency_default_5()
test_refit_frequency_custom()

# Logging integration
test_fit_logs_strategies()
test_fit_logs_model_summaries()
test_fit_logs_refits()
test_warm_start_logs_retrain()

# Save/load
test_save_creates_joblib_and_json()
test_load_restores_predictor()
test_load_restores_log()

# Signal selection
test_default_signal_constraint_count()
test_custom_signal_auc()
```

**Implementation**:
```python
# cbqs/ml/sat_trainer.py (~350 lines)

from .regressors import PhasePredictor
from .data_collection import SATDataCollector
from .training_log import TrainingLog
from .signals import make_signal
from .features import FeatureExtractor

class SATTrainer:
    """Train SAT-phase branching parameters from problem instances."""

    def __init__(self, n_estimators: int = 100,
                 n_strategies: int = 10,
                 time_budget: float = 30.0,
                 signal: str = 'constraint_count',
                 refit_every: int = 5,
                 log_path: str = None,
                 random_state: int = None):
        self.predictor = PhasePredictor(mode='sat', n_estimators=n_estimators)
        self.collector = SATDataCollector(n_strategies=n_strategies,
                                          time_budget=time_budget,
                                          signal_fn=make_signal(signal))
        self.extractor = FeatureExtractor()
        self.log = TrainingLog(path=log_path)
        self.refit_every = refit_every
        self._collected = []  # accumulated (features, targets) pairs

    def fit(self, models: list, validation_models: list = None):
        """Train on a list of Model instances.

        For each model:
          1. Collect training data (N random strategies → best)
          2. Extract features
          3. Log strategy and model events
          4. Every refit_every models: refit predictor, log refit event
        """
        ...

    def predict(self, model) -> dict:
        """Predict SAT parameters for a new model.

        Returns dict with keys:
          sat_branching_weights, sat_variable_priorities,
          sat_branching_bias, sat_branching_factor, sat_bias_factor
        """
        ...

    def warm_start(self, new_models: list, n_new_trees: int = 50):
        """Incrementally train on new models without full refit."""
        ...

    def validate(self, models: list) -> float:
        """Evaluate predictor quality on validation set."""
        ...

    def save(self, dir_path: str):
        """Save predictor.joblib + training_log.json."""
        ...

    @classmethod
    def load(cls, dir_path: str) -> 'SATTrainer':
        ...
```

**Done when**: 17 tests pass.

---

### M13 — `ml/opt_trainer.py` (NEW, ~450 lines)

End-to-end OPT training with Option C joint optimization.

**Tests first** (`tests/test_opt_trainer.py`, ~350 lines):
```python
# Core training
test_fit_single_model()
test_fit_multiple_models()
test_predict_returns_opt_sat_and_opt_params()   # all 4n+6 parameters
test_predict_params_valid()

# Option C data collection integration
test_trivially_feasible_excluded_from_opt_sat()
test_non_trivially_feasible_trains_both()
test_screening_budget_respected()
test_full_budget_respected()

# Joint training
test_opt_sat_and_opt_regressors_independent()
test_joint_prediction_coherent()

# Incremental training
test_warm_start()
test_refit_frequency()

# Signal options
test_auc_signal()
test_weighted_signal()

# Logging
test_fit_logs_all_levels()
test_log_includes_trivially_feasible_flag()
test_log_captures_screening_phase()

# Save/load
test_save_load_roundtrip()
```

**Implementation**:
```python
# cbqs/ml/opt_trainer.py (~450 lines)

from .regressors import PhasePredictor
from .data_collection import OPTDataCollector
from .training_log import TrainingLog
from .signals import make_signal
from .features import FeatureExtractor

class OPTTrainer:
    """Train OPT-phase branching parameters using Option C data collection."""

    def __init__(self, n_estimators: int = 100,
                 n_opt_sat_strategies: int = 10,
                 top_k: int = 3,
                 n_opt_per_candidate: int = 5,
                 screening_budget: float = None,
                 full_budget: float = None,
                 signal: str = 'auc',
                 signal_kwargs: dict = None,
                 refit_every: int = 5,
                 log_path: str = None,
                 random_state: int = None):
        self.predictor = PhasePredictor(mode='opt', n_estimators=n_estimators)
        self.collector = OPTDataCollector(...)
        self.extractor = FeatureExtractor()
        self.log = TrainingLog(path=log_path)
        ...

    def fit(self, models: list, validation_models: list = None):
        """Train on models using Option C strategy.

        For each model:
          1. Check trivially feasible
          2. Option C data collection (screen opt_sat → pair with opt)
          3. Extract features
          4. Log all events
          5. Periodic refit
        """
        ...

    def predict(self, model) -> dict:
        """Predict OPT parameters for a new model.

        Returns dict with keys:
          opt_sat_branching_weights, opt_sat_variable_priorities,
          opt_sat_branching_bias, opt_sat_branching_factor, opt_sat_bias_factor,
          opt_branching_weights, opt_variable_priorities,
          opt_branching_bias, opt_branching_factor, opt_bias_factor
        """
        ...

    def warm_start(self, new_models, n_new_trees=50): ...
    def validate(self, models) -> float: ...
    def save(self, dir_path): ...

    @classmethod
    def load(cls, dir_path) -> 'OPTTrainer': ...
```

**Done when**: 17 tests pass.

---

## Phase 6: Integration

### M14 — Phase-Aware `adaptive_solve()` Update

**Files changed**: `cbqs/ml/adaptation.py`

**Tests first** (`tests/test_phase_adaptive.py`, ~200 lines):
```python
test_adaptive_with_sat_params()
test_adaptive_with_opt_params()
test_ema_updates_per_phase()
test_history_records_active_phase()
test_backwards_compat_unprefixed_weights()
test_phase_predictor_as_initial_weights()
```

**Changes to `adaptation.py`** (~100 lines changed/added):
- `adaptive_solve()` accepts optional `initial_phase_params: dict` (from SATTrainer or OPTTrainer).
- EMA updates operate on the phase that was active when the result was produced.
- `AdaptiveResult.history` extended with a `phase` field per round.

**Done when**: 6 tests pass. Existing adaptation tests still pass.

---

### M15 — SearchLib.pyx Phase Parameter Propagation

**Files changed**: `cbqs/SearchLib.pyx`

**Tests first** (`tests/test_phase_propagation.py`, ~250 lines):
```python
test_propagate_sat_params_to_ctx()
test_propagate_opt_sat_params_to_ctx()
test_propagate_opt_params_to_ctx()
test_fallback_unprefixed_to_all_phases()
test_priorities_set_variable_order()
test_no_priorities_uses_default_order()
test_end_to_end_solve_with_phase_params()
test_end_to_end_solve_backwards_compat()
```

**Changes to `SearchLib.pyx`** (~80 lines changed):
- In `run_sampling()`, after context creation:
  ```python
  resolver = PhaseParamResolver(mod._params, _PARAM_DEFS)
  resolved = resolver.resolve_all()

  for phase in ('sat', 'opt_sat', 'opt'):
      p = resolved[phase]
      # Set bias, weights, factors for each phase
      solver_ctx_set_{phase}_bias(ctx, p['branching_bias'])
      if p['branching_weights'] is not None:
          solver_ctx_set_{phase}_weights(ctx, ...)
      if p['variable_priorities'] is not None:
          solver_ctx_set_variable_order(&ctx->branching_stats_{phase}, ...)
      else:
          solver_ctx_set_degree_order(&ctx->branching_stats_{phase}, ...)
  ```

**Done when**: 8 tests pass. Full regression suite passes.

---

## Dependency Graph

```
M1 (ctx stats)
├──→ M2 (ctg switching)  ──→ M15 (SearchLib propagation)
├──→ M4 (var order field) ──→ M5 (CSearch iteration) ──→ M15
└──→ M3 (bias validation)

M6 (phase_params.py) ──→ M7 (Model.pyx params) ──→ M15

M8  (signals.py)        ─┐
M9  (regressors.py)      ├──→ M11 (data_collection.py) ──→ M12 (sat_trainer)
M10 (training_log.py)   ─┘                             ──→ M13 (opt_trainer)
                                                              │
                                                              v
                                                        M14 (adaptation update)
```

**Parallelizable work**:
- M1 + M3 + M6 (no dependencies between them)
- M8 + M9 + M10 (no dependencies between them)
- M12 + M13 (independent trainers, both depend on M8-M11)

---

## Refactoring: Existing `training.py` (592 lines)

The existing `WeightPredictor` class in `training.py` will be **kept as-is** for backwards compatibility during development. Once M12 (SATTrainer) is validated:

1. Mark `WeightPredictor` as deprecated (docstring warning)
2. Add thin wrapper: `WeightPredictor.predict()` delegates to `SATTrainer.predict()` internally
3. Remove `WeightPredictor` in a later cleanup pass

This avoids breaking existing users while the new pipeline is built.

---

## Line Count Budget

| Module | Type | Est. Lines | Test Lines |
|--------|------|-----------|------------|
| M1: solver_ctx phases | C change | +80 | 150 |
| M2: ctg switching | C change | +50 | 200 |
| M3: bias validation | Cython change | +10 | 60 |
| M4: var order field | C change | +60 | 200 |
| M5: CSearch ordering | C change | +80 | 250 |
| M6: phase_params.py | **New Python** | **250** | 300 |
| M7: Model.pyx params | Cython change | +120 | 250 |
| M8: signals.py | **New Python** | **150** | 200 |
| M9: regressors.py | **New Python** | **350** | 350 |
| M10: training_log.py | **New Python** | **450** | 350 |
| M11: data_collection.py | **New Python** | **400** | 350 |
| M12: sat_trainer.py | **New Python** | **350** | 300 |
| M13: opt_trainer.py | **New Python** | **450** | 350 |
| M14: adaptation update | Python change | +100 | 200 |
| M15: SearchLib propagation | Cython change | +80 | 250 |
| **Totals** | | **~3030** | **~3760** |

All new Python modules are within the 400–500 line limit. Total test code exceeds implementation code (~1.2:1 ratio).

---

## Execution Order (Suggested Sprint Plan)

**Sprint 1** (Foundation): M1 → M2 → M3 → M4 → M5
- All C/Cython changes. Solver works with phase-specific stats and variable ordering.
- Existing behavior unchanged (identity ordering, all-phase setters).

**Sprint 2** (Python params + ML infra): M6 + M7 (parallel with) M8 + M9 + M10
- Parameter layer and ML building blocks. No training yet.

**Sprint 3** (Data collection + Trainers): M11 → M12 + M13
- Full training pipelines operational.

**Sprint 4** (Integration): M14 + M15
- Wire everything together. End-to-end validation.

**Sprint 5** (Cleanup): Deprecate old WeightPredictor, remove compat macro.
