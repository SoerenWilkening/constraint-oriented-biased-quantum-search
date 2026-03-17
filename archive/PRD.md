# Product Requirements Document: CBQS ML Pipeline & Solver Enhancements

**Version**: 1.0
**Date**: 2026-03-11
**Status**: Draft

---

## 1. Executive Summary

The Constraint-Oriented Biased Quantum Search (CBQS) solver is a hybrid quantum-inspired sampling and local search engine for combinatorial optimization. This PRD defines enhancements to the solver's ML-based parameter learning framework and supporting infrastructure changes. The core insight is that the solver already operates in distinct phases (constraint satisfaction, constraint tightening, objective optimization) but currently uses a single set of branching parameters across all phases. Phase-specific parameters, learned variable ordering, and improved training infrastructure are expected to significantly improve solver performance.

---

## 2. Problem Statement

### 2.1 Current Limitations

1. **Single-phase branching parameters**: The solver uses one `BranchingStats_t` across all search stages, despite the stages having fundamentally different objectives (find feasibility vs. optimize objective).

2. **Fixed variable ordering**: CSearch functions iterate variables in index order (0 to n-1). Manual experiments (e.g., ratio ordering on knapsack problems) show that variable ordering significantly affects performance, but no learned ordering is supported.

3. **Limited training signal**: Training evaluates only final result quality `(feasible, objective)` without accounting for solution speed or convergence behavior.

4. **No incremental training**: The predictor must be retrained from scratch when new training data becomes available.

5. **No training progress visibility**: No logging of intermediate training quality to assess whether additional data improves the predictor.

6. **Missing input validation**: `branching_bias` parameter accepts invalid values (e.g., <= -1) that cause division-by-zero or produce values outside [0, 1] in the branching probability formula.

### 2.2 Desired Outcome

A solver that automatically selects phase-appropriate branching parameters and variable orderings, trained offline on problem instances, with observable and incrementally improvable training quality.

---

## 3. Requirements

### 3.1 Functional Requirements

#### FR-1: Phase-Specific Branching Parameters
The solver SHALL support three independent sets of branching parameters:
- **SAT**: Used during pure constraint satisfaction (`CSearch_sat`)
- **OPT-SAT**: Used during the feasibility phase of optimization problems (`CSearch_opt_sat`) and constraint tightening (Stage 2)
- **OPT**: Used during objective optimization (`CSearch_opt`, Stage 3)

Each parameter set includes: per-variable branching weights, per-variable ordering priorities, branching_bias, branching_factor, and bias_factor.

#### FR-2: Variable Ordering
The solver SHALL support per-phase variable ordering determined by learned priority scores. CSearch functions SHALL iterate variables in priority-sorted order rather than fixed index order.
- Default ordering when no priorities are set: most-constrained-first (by variable degree)
- Learned ordering: ML-predicted priority scores, sorted descending

#### FR-3: Backwards-Compatible Parameter API
Existing unprefixed parameters (`branching_weights`, `branching_factor`, etc.) SHALL continue to function as fallback defaults. Resolution order: phase-specific parameter > unprefixed parameter > built-in default.

#### FR-4: Two Training Pipelines
The system SHALL provide two independent training pipelines:

**SAT Trainer**:
- Trains parameters for pure constraint satisfaction
- Predicts: per-variable (weights, priorities) + instance-level (bias, branching_factor, bias_factor)
- Total: 2n + 3 parameters
- Training signal: number of satisfied constraints

**OPT Trainer**:
- Jointly trains feasibility-phase and optimization-phase parameters
- Predicts: per-variable (opt_sat weights, opt_sat priorities, opt weights, opt priorities) + instance-level (6 global params)
- Total: 4n + 6 parameters
- Training signal: objective quality weighted by time
- Trivially feasible instances are excluded from opt_sat parameter training

#### FR-5: Training Data Collection (Option C)
The OPT training pipeline SHALL use a staged search strategy:
1. Sample N random opt_sat parameter vectors per model
2. Quick feasibility screening (budget: full_training_time / 3, scaling linearly with number of variables)
3. Select top K opt_sat candidates by feasibility metric
4. For each of K candidates, sample M opt parameter vectors and run full solve
5. Record best (opt_sat, opt) pair by training signal

User-configurable time budgets to support long-running training sessions.

#### FR-6: Training Signal Options
Two training signal options SHALL be supported, selected at training time:
- **Area Under Incumbent Curve (AUC)**: Integrates objective value over time from the incumbent history. No extra parameters.
- **Weighted Combination**: `score = objective - lambda * time_to_best`, where lambda is user-provided.

A single training run uses one signal. Users compare approaches by running separate sessions.

#### FR-7: Regressor Architecture
Each trainer SHALL use two regressors:
- **Per-variable regressor**: Maps (n_vars, 20) feature matrix to multi-output predictions (weights + priorities per variable). Model: ExtraTreesRegressor with multi-output.
- **Instance regressor**: Maps (11,) instance feature vector to global parameters (bias, factors). Model: ExtraTreesRegressor (configurable, may be swapped for alternatives).

Post-processing: weights clipped to non-negative, bias clipped to > -1, factors clipped to >= 0. Priorities used for argsort to determine variable ordering.

#### FR-8: Branching Bias as Trained Parameter
`branching_bias` (and phase-specific variants) SHALL be a predicted parameter output from the instance regressor. Training initialization uses `n / 4` as the starting point (the empirically successful default).

#### FR-9: Incremental Training
Predictors SHALL support incremental training via `warm_start=True` on ExtraTreesRegressor. New training data adds trees to the existing ensemble without retraining from scratch. Refit frequency: configurable, default every 5 models.

#### FR-10: Training Logging
All training events SHALL be logged to a structured JSON file, separate from the predictor artifact. Three granularity levels:

**Per-Strategy** (finest): Every parameter vector tried and its result (objective, feasibility, time, AUC, full incumbent history).

**Per-Model** (medium): Summary per training model (strategies tried, best signal, best parameters, trivially feasible flag).

**Per-Refit** (coarsest): Predictor quality after each refit (n_training_models, validation score, timestamp).

**Per-Retrain**: Incremental training episodes (instances added, tree count before/after, validation score before/after).

Display interface:
- `training_log.summary()` — learning curve
- `training_log.model_details(idx)` — per-model detail
- `training_log.strategies(idx, phase)` — per-strategy detail
- `training_log.plot_learning_curve()` — visual plot
- `training_log.compare(other_log)` — side-by-side comparison of training runs

#### FR-11: Parameter Validation
`branching_bias` SHALL be validated at the Python level to enforce `> -1`. This ensures the branching probability formula `(bias + 1) / (bias + 2)` always produces a value in (0, 1).

#### FR-12: Online Adaptation Updates
`adaptive_solve()` SHALL be updated to support phase-specific parameters:
- Accept initial weights/priorities for each phase
- EMA updates applied per-phase
- History records which phase was active per round

### 3.2 Non-Functional Requirements

#### NFR-1: Performance
- Variable ordering lookup (indirection through ordering array) SHALL NOT measurably degrade solver throughput. The ordering array is precomputed once before the search loop.
- Phase-specific stats switching adds one pointer swap per stage transition — negligible overhead.

#### NFR-2: Memory
- Three `BranchingStats_t` instead of one triples the parameter memory. For n variables, this is 3 * (n * sizeof(double) * 2 + constants) — negligible relative to constraint storage.

#### NFR-3: Compatibility
- All existing solver API calls SHALL continue to work without modification.
- Existing saved predictors (`.joblib`) SHALL remain loadable (though they will only populate unprefixed parameters).

#### NFR-4: Observability
- Training progress SHALL be observable at any granularity without re-running training.
- Log files SHALL be JSON for tool-agnostic consumption (notebooks, scripts, CLI tools).

---

## 4. Architecture

### 4.1 System Context

```
User Problem Instance
        |
        v
  Python API (Model)
        |
        v
  Phase-Specific Parameter Resolution
  (phase-specific > unprefixed > default)
        |
        v
  Cython Bridge (Model.pyx, SearchLib.pyx)
        |
        v
  C Solver Core (solver.c, SearchLib.c)
  ├── ctg() stage manager
  │   ├── Stage 1/2: branching_stats_sat or branching_stats_opt_sat
  │   └── Stage 3:   branching_stats_opt
  ├── CSearch_sat()      ← variable_order_sat
  ├── CSearch_opt_sat()  ← variable_order_opt_sat
  └── CSearch_opt()      ← variable_order_opt
        |
        v
  OptimizeResult (history, objective, feasibility)
        |
        v
  ML Training Pipeline
  ├── SAT Trainer  → sat predictor + training log
  └── OPT Trainer  → opt predictor + training log
```

### 4.2 Data Flow: Training

```
Training Models
      |
      v
Feature Extraction (features.py)
├── Per-variable features (n, 9): degree, coefficients, bounds, neighbors
└── Instance features (11): counts, densities, coefficient stats
      |
      v
Data Collection (Option C for OPT)
├── Random parameter sampling
├── Quick feasibility screening (opt_sat candidates)
├── Full solve with (opt_sat, opt) pairs
└── Best pair selection by training signal
      |
      v
Regressor Training
├── Per-variable regressor: features → (weights, priorities) [warm_start]
└── Instance regressor: features → (bias, factors) [warm_start]
      |
      v
Artifacts
├── predictor.joblib (model weights)
└── training_log.json (full training history)
```

### 4.3 Data Flow: Prediction

```
New Model Instance
      |
      v
Feature Extraction
      |
      v
Per-Variable Regressor → weights[], priorities[] (per phase)
Instance Regressor     → bias, branching_factor, bias_factor (per phase)
      |
      v
Post-processing (clip, sort priorities → ordering array)
      |
      v
model.set_param('sat_branching_weights', ...)
model.set_param('sat_variable_priorities', ...)
model.set_param('sat_branching_bias', ...)
... (repeat for opt_sat, opt)
      |
      v
model.solve()
```

---

## 5. Branching Probability Formula

For reference, the core formula that all parameters feed into (per variable, per phase):

```
value = (branching_factor * w[i]
       + bias_factor * assignment_bias
       + look_ahead_factor * lookahead) / factor_sum

where:
  w[i]             = L1-normalized per-variable weight, in [0, 1]
  assignment_bias  = (bias + 1) / (bias + 2), in (0, 1) for bias > -1
  lookahead        = 0.0 or 1.0
  factor_sum       = sum of active factor weights (>= bias_factor)

Result: value in [0, 1], used as P(assign 0) or P(assign 1)
        depending on threshold bit comparison.
```

All three parameter sets (SAT, OPT-SAT, OPT) use this same formula with their respective parameter values.

---

## 6. Key Files Affected

### C Sources
| File | Changes |
|------|---------|
| `cbqs/src/solver_ctx.h` | Three `BranchingStats_t`, per-phase variable ordering arrays |
| `cbqs/src/solver_ctx.c` | Setters for phase-specific stats, ordering computation |
| `cbqs/src/SearchLib.c` | `ctg()` stage transitions swap active stats; pass ordering to CSearch |
| `cbqs/src/solver.c` | All CSearch functions iterate via ordering array |
| `cbqs/src/Branching.h` | Add `int *variable_order` to `BranchingStats_t` |

### Cython
| File | Changes |
|------|---------|
| `cbqs/Model.pyx` | `_PARAM_DEFS` for phase-specific params, `branching_bias` validation, parameter resolution logic |
| `cbqs/SearchLib.pyx` | Pass phase-specific stats to C layer |

### Python ML
| File | Changes |
|------|---------|
| `cbqs/ml/training.py` | `SATTrainer`, `OPTTrainer` classes, Option C data collection, training signal options, incremental training |
| `cbqs/ml/adaptation.py` | Phase-aware `adaptive_solve()` |
| `cbqs/ml/features.py` | No changes expected (existing features sufficient) |
| `cbqs/ml/logging.py` | **New file**: `TrainingLog` class with JSON storage and display interface |

---

## 7. Implementation Plan

### Phase 1: Foundation (no ML changes)
1. **Validation fix**: Add `branching_bias > -1` validation in `Model.pyx`
2. **Three BranchingStats**: Add to `solver_ctx_t`, wire setters
3. **Stage transition switching**: Update `ctg()` to swap active stats at phase boundaries
4. **Phase-specific Python parameters**: New `set_param` entries with fallback resolution

### Phase 2: Variable Ordering
5. **Ordering array in BranchingStats_t**: Add `int *variable_order` field
6. **CSearch iteration refactor**: Replace fixed loops with ordering-based iteration in all CSearch functions
7. **Default ordering**: Most-constrained-first when no priorities set
8. **Python parameter for priorities**: `sat_variable_priorities`, `opt_sat_variable_priorities`, `opt_variable_priorities`

### Phase 3: ML Training Pipeline
9. **Training signals**: AUC computation and weighted combination scoring
10. **SAT Trainer**: Per-variable + instance regressors, data collection, warm_start support
11. **OPT Trainer**: Option C data collection, joint opt_sat/opt training, trivially-feasible exclusion
12. **Training logging**: `TrainingLog` class with three-level JSON logging and display interface

### Phase 4: Integration & Adaptation
13. **Online adaptation**: Phase-aware `adaptive_solve()`
14. **End-to-end testing**: Full pipeline from training through prediction through solve

### Phase 5: Performance (post-ML)
15. **Profiling**: Profile solver hot paths with new infrastructure
16. **Optimization**: Address bottlenecks identified by profiling

---

## 8. Acceptance Criteria

- [ ] `branching_bias` values <= -1 are rejected with a clear error message
- [ ] Solver uses phase-specific parameters when set, falls back to unprefixed parameters, then to defaults
- [ ] Existing tests pass without modification (backwards compatibility)
- [ ] CSearch functions respect variable ordering arrays
- [ ] SAT Trainer produces a predictor that improves satisfied constraint count vs uniform weights on test instances
- [ ] OPT Trainer produces a predictor that improves objective value and/or convergence speed vs uniform weights
- [ ] Training log captures all three granularity levels and is queryable
- [ ] Incremental training (warm_start) produces comparable or better results than full retraining
- [ ] Training signals (AUC and weighted) produce distinct, comparable training runs

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Joint opt_sat/opt training (Option C) is too expensive | Training takes impractically long | Configurable time budgets; Option C limits full-solve pairs to top-K * M |
| Variable ordering indirection degrades solver speed | Core performance regression | Ordering array is cache-friendly (sequential int access); benchmark before/after |
| Warm-start accumulates stale trees | Predictor quality degrades over time | Log tracks quality per retrain episode; full retrain fallback if quality drops |
| Three parameter sets confuse users | Adoption barrier | Unprefixed fallback means users can ignore phase-specific params entirely |
| ExtraTreesRegressor not expressive enough for instance-level prediction | Poor global parameter predictions | Model type is configurable; log enables empirical comparison |

---

## 10. Future Considerations

- **Alternative regressors**: If ExtraTreesRegressor warm-start proves limiting, consider neural network fine-tuning or other incremental learners
- **Feature engineering**: Explicit ratio features (objective_coeff / constraint_coeff) if the model struggles to learn ratio-based orderings
- **Look-ahead factor training**: Currently `look_ahead_factor` is in the branching formula but not trained by the ML pipeline; could be added as another predicted parameter
- **Cross-instance transfer**: Validate that predictors trained on small instances generalize to larger instances (existing `validate_transfer` infrastructure)
- **Integer variable awareness**: ML predicts weights for binary decomposition bits independently; explicit bit-position features may help for bounded integer problems
