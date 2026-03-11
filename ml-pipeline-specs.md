# ML Pipeline Redesign — Specification

## 1. Motivation

The current ML framework trains a single set of branching weights for the entire solve. The solver, however, operates in distinct phases (satisfaction, constraint tightening, optimization) that may benefit from different branching parameters. Additionally, variable ordering is known to significantly impact solver performance but is currently fixed (left-to-right).

## 2. C-Level Changes

### 2.1 Three BranchingStats in solver_ctx_t

Replace the single `BranchingStats_t branching_stats` in `solver_ctx_t` with three:

```c
typedef struct solver_ctx {
    BranchingStats_t branching_stats_sat;     // Pure CSP mode (CSearch_sat)
    BranchingStats_t branching_stats_opt_sat; // Feasibility phase of optimization (CSearch_opt_sat)
    BranchingStats_t branching_stats_opt;     // Optimization phase (CSearch_opt)
    // ... rest unchanged
} solver_ctx_t;
```

Each `BranchingStats_t` contains:
- `double *branching_weights` — per-variable weights (L1-normalized)
- `int num_weights`
- `double branching_factor` — weight of the branching_weights term
- `double bias_factor` — weight of the assignment_bias term
- `double bias` — assignment bias value (must be > -1)
- `double look_ahead_factor` — weight of lookahead term

### 2.2 Stage Transitions in ctg()

In `SearchLib.c:ctg()`, the solver already tracks stages and switches search functions. Extend this to also switch which `BranchingStats_t` is active:

- Stage 1 (SATISFY mode): use `branching_stats_sat`
- Stage 1 (OPTIMIZE, infeasible): use `branching_stats_opt_sat`
- Stage 2 (constraint tightening): use `branching_stats_opt_sat`
- Stage 3 (optimization): use `branching_stats_opt`

The CSearch functions currently receive `&ctx->branching_stats` implicitly through `ctx`. This needs to change so the active stats pointer is passed explicitly or a pointer to the active stats is maintained in `ctx`.

### 2.3 Variable Ordering Support

Currently, all CSearch functions iterate variables in fixed order: `for (i = 0; i < n; i++)`.

Changes needed:
- Add `int *variable_order` array to each `BranchingStats_t` (or to `solver_ctx_t` per phase)
- Pre-compute ordering array before search loop based on priority scores
- Replace `for (i = 0; i < n; i++)` with `for (k = 0; k < n; k++) { i = variable_order[k]; ... }` in all CSearch functions
- Default ordering: most-constrained-first (by variable degree)
- Learned ordering: priority scores from ML regressor, sorted descending

Variable ordering is phase-specific — SAT, OPT-SAT, and OPT may each have different optimal orderings.

## 3. Python-Level Changes

### 3.1 Parameter Validation Fix

Add validation for `branching_bias` in `Model.pyx` `_PARAM_DEFS`:
```python
'branching_bias': {'default': None, 'coerce': float,
                   'validate': lambda v: v > -1,
                   'validate_msg': 'branching_bias must be greater than -1',
                   'description': '...'}
```

### 3.2 New set_param Entries

New parameters for the three-phase branching stats:

**SAT phase parameters:**
- `sat_branching_weights` — per-variable weights for CSP mode
- `sat_branching_factor` — factor weight for weights term
- `sat_bias_factor` — factor weight for bias term
- `sat_branching_bias` — assignment bias (> -1)
- `sat_variable_priorities` — per-variable ordering priorities

**OPT-SAT phase parameters:**
- `opt_sat_branching_weights`
- `opt_sat_branching_factor`
- `opt_sat_bias_factor`
- `opt_sat_branching_bias`
- `opt_sat_variable_priorities`

**OPT phase parameters:**
- `opt_branching_weights`
- `opt_branching_factor`
- `opt_bias_factor`
- `opt_branching_bias`
- `opt_variable_priorities`

The existing unprefixed parameters (`branching_weights`, `branching_factor`, etc.) should continue to work as defaults applied to all phases when phase-specific parameters are not set.

## 4. ML Training Pipeline

### 4.1 Two Training Pipelines

#### SAT Trainer
- **Purpose**: Train parameters for pure constraint satisfaction problems
- **Outputs (per-variable regressor)**: branching weights + ordering priorities (multi-output, 2 values per variable)
- **Outputs (instance regressor)**: branching_bias, branching_factor, bias_factor (3 scalar values)
- **Total parameters**: 2n + 3
- **Training signal**: Number of satisfied constraints (or configurable, see Section 4.3)
- **Data collection**: Try random parameter vectors, evaluate by satisfied constraint count

#### OPT Trainer
- **Purpose**: Jointly train feasibility-phase and optimization-phase parameters
- **Outputs (per-variable regressor)**: opt_sat weights + opt_sat priorities + opt weights + opt priorities (multi-output, 4 values per variable)
- **Outputs (instance regressor)**: opt_sat bias + opt_sat branching_factor + opt_sat bias_factor + opt bias + opt branching_factor + opt bias_factor (6 scalar values)
- **Total parameters**: 4n + 6
- **Training signal**: Final objective quality weighted by time (see Section 4.3)
- **Data collection**: Option C strategy (see Section 4.2)

### 4.2 Training Data Collection (Option C)

For the OPT trainer, joint optimization of opt_sat and opt parameters:

1. For each model in the training set:
   a. Check if initial state is trivially feasible
      - If yes: skip opt_sat parameter search; contribute data only for opt parameters
      - If no: proceed with full joint search
   b. Sample N random opt_sat parameter vectors
   c. Run quick feasibility evaluation for each (short time budget)
   d. Pick top K opt_sat candidates (by feasibility metric)
   e. For each of the K candidates, sample M opt parameter vectors
   f. Run full solve for each (opt_sat, opt) pair
   g. Record best pair by training signal

For the SAT trainer:
1. For each model, sample N random parameter vectors
2. Run solve with each, record satisfied constraint count
3. Pick best parameters as training target

### 4.3 Training Signal Options

Two options, selected by user at training time:

#### Option 1: Area Under Incumbent Curve (AUC)
- Compute from `result.history` list of `(value, elapsed_seconds)` entries
- Integrate objective value over time using trapezoidal rule (or similar)
- Naturally balances solution quality and speed
- No extra parameters needed

#### Option 2: Weighted Combination
- `score = objective - lambda * time_to_best`
- `lambda` is a user-provided parameter
- Allows explicit control over speed vs quality tradeoff

Both options available via a parameter in the training function. A single training run uses one signal. Users compare by running separate training sessions.

### 4.4 Regressor Architecture

Two regressors per trainer:

#### Per-Variable Regressor
- **Input**: (n_vars, 20) feature matrix (9 per-variable + 11 instance features tiled)
- **Output**: multi-output prediction
  - SAT: (n_vars, 2) — [weight, priority]
  - OPT: (n_vars, 4) — [opt_sat_weight, opt_sat_priority, opt_weight, opt_priority]
- **Model**: ExtraTreesRegressor (multi-output)
- **Post-processing**: clip weights to non-negative, priorities used for argsort

#### Instance Regressor
- **Input**: (11,) instance feature vector
- **Output**: global parameters
  - SAT: (3,) — [bias, branching_factor, bias_factor]
  - OPT: (6,) — [opt_sat_bias, opt_sat_branching_factor, opt_sat_bias_factor, opt_bias, opt_branching_factor, opt_bias_factor]
- **Model**: ExtraTreesRegressor
- **Post-processing**: bias clipped to > -1, factors clipped to >= 0

### 4.5 Branching Bias as Training Parameter

The `branching_bias` (and phase-specific variants) is now a predicted parameter rather than only auto-set. Default starting point for training initialization: `n / 4` (the current auto-default that has been empirically successful). The instance regressor learns to adjust from this baseline.

## 5. Training Logging

### 5.1 Architecture

All training events are logged to a structured JSON file, separate from the predictor artifact.

### 5.2 Logged Events (Three Granularity Levels)

#### Per-Strategy (finest grain)
For every parameter vector tried during data collection:
```json
{
    "level": "strategy",
    "model_idx": 7,
    "phase": "opt_sat",
    "strategy_idx": 3,
    "parameters": {"weights": [...], "priorities": [...], "bias": 12.5, ...},
    "result": {
        "objective": 42,
        "feasible": true,
        "satisfied_constraints": 15,
        "time_to_best": 1.3,
        "auc": 34.2,
        "history": [[10, 0.1], [30, 0.5], [42, 1.3]]
    }
}
```

#### Per-Model (medium grain)
Summary after all strategies tried for one model:
```json
{
    "level": "model",
    "model_idx": 7,
    "n_strategies_tried": 30,
    "best_training_signal": 34.2,
    "best_parameters": {"opt_sat": {...}, "opt": {...}},
    "trivially_feasible": false
}
```

#### Per-Refit (coarsest grain)
After refitting predictor on accumulated data:
```json
{
    "level": "refit",
    "n_training_models": 10,
    "validation_score": 0.85,
    "predictor_quality_metric": 42.3,
    "timestamp": "2026-03-11T14:30:00"
}
```

### 5.3 Display Interface

Query functions to view data at any granularity:
- `training_log.summary()` — learning curve (predictor quality vs training data size)
- `training_log.model_details(model_idx)` — all strategies tried for a model
- `training_log.strategies(model_idx, phase)` — every parameter vector and result
- `training_log.plot_learning_curve()` — visual plot of predictor quality over time
- `training_log.compare(other_log)` — side-by-side comparison of two training runs (e.g., AUC vs weighted signal)

### 5.4 Storage

- Format: JSON (human-readable, tool-agnostic, notebook-friendly)
- Separate file from predictor artifact (predictor.joblib + training_log.json)
- Log file is append-friendly for long-running training sessions

## 6. Online Adaptation Updates

The existing `adaptive_solve()` should be updated to work with phase-specific parameters:
- Accept initial weights/priorities for each phase
- EMA updates applied per-phase based on which phase produced the result
- History records which phase was active per round

## 7. Implementation Order

1. **Python validation fix**: `branching_bias > -1` in `_PARAM_DEFS` (quick win)
2. **C-level three BranchingStats**: Add to `solver_ctx_t`, wire up stage transitions in `ctg()`
3. **C-level variable ordering**: Modify CSearch functions to use ordering array
4. **Python-level new parameters**: Phase-specific set_param entries
5. **ML training pipeline**: Two trainers, new training signals, Option C data collection
6. **Training logging**: JSON logger with three granularity levels + display functions
7. **Online adaptation updates**: Phase-aware adaptive_solve
8. **Profiling and performance** (after ML pipeline is complete)

## 8. Resolved Design Decisions

### 8.1 Unprefixed Parameter Fallback
**Decision**: Backwards compatible. Resolution order: phase-specific parameter → unprefixed parameter → default value. Existing code using unprefixed parameters continues to work unchanged.

### 8.2 Quick Feasibility Screening Time Budget
**Decision**: Scales with instance size (number of variables). Default: `screening_time = full_training_time / 3`. Approximate guideline: ~25s for 50 variables, ~120s for 500 variables (roughly linear in n). User-configurable to support long-running training.

### 8.3 Instance Regressor Model
**Decision**: Start with ExtraTreesRegressor for consistency. Make model type configurable so alternatives (e.g., linear regression) can be swapped in. Compare empirically via training log. Both approaches must support incremental data addition.

### 8.4 Refit Frequency
**Decision**: Configurable, default every 5 models. Log captures all data regardless of refit frequency, enabling retroactive analysis at any granularity.

## 9. Incremental Training

### 9.1 Warm-Start Retraining
Both per-variable and instance regressors use `warm_start=True` on ExtraTreesRegressor. When new training instances are added:
- New trees are added to the existing ensemble (old trees preserved)
- No need to retrain from scratch
- Old trees' influence diminishes as new trees accumulate

### 9.2 Retraining Log
Each retraining episode is explicitly logged:
```json
{
    "level": "retrain",
    "episode": 3,
    "new_instances_added": [21, 22, 23, 24, 25],
    "total_instances": 25,
    "total_trees_before": 200,
    "total_trees_after": 300,
    "validation_score_before": 0.78,
    "validation_score_after": 0.82,
    "timestamp": "2026-03-12T10:15:00"
}
```

### 9.3 Future Consideration
If warm-start proves insufficient (e.g., early poor-quality trees degrade long-term performance), consider switching to a fully incremental model or periodic full retraining with accumulated data. The logging infrastructure will make this decision data-driven.
