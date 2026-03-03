# Phase 28: Transfer Learning & Diagnostics - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate that learned weights generalize across instance sizes (small-to-large transfer) and provide utilities for evaluating weight quality against baselines. Covers: transfer validation utility, evaluate_weights function with convergence speed metrics, and diagnostic reporting. Training pipeline (Phase 26) and adaptive solve (Phase 27) are prerequisites, not in scope.

</domain>

<decisions>
## Implementation Decisions

### Transfer validation
- New `validate_transfer()` utility function in `cbqs.ml` — self-contained, one call does everything
- Takes `train_models` (small) + `test_models` (large), trains a WeightPredictor internally via `collect_training_data()` + `fit()`
- No verification of "same problem type" — user is responsible for providing appropriate model sets
- Returns both the evaluation results AND the fitted WeightPredictor (so user can save/reuse after validation)
- Calls `evaluate_weights()` internally and passes through its output — one report format, no duplication

### evaluate_weights API
- New standalone function `evaluate_weights()` — separate from existing `evaluate()` which takes a WeightPredictor
- Accepts strategies as a dict of named callables: `{'learned': lambda model: weights_array, ...}` — handles variable-count differences naturally (each callable returns weights per model)
- Automatically adds 'uniform' baseline (same pattern as existing `evaluate()`)
- Single function covers both DIAG-02 and DIAG-03 — returns all metrics including convergence speed

### Convergence speed metric
- Defined as **time-to-best**: elapsed time until the best objective value was first found, using solve history `(value, elapsed_seconds)` tuples
- If best is found at the end or never improves, time_to_best = stopping_time (ceiling — penalizes late convergence)
- Report includes both absolute `mean_time_to_best` per strategy AND speedup ratio vs uniform baseline (e.g., "learned is 2.3x faster than uniform")

### Report & output format
- `evaluate_weights()` returns a dict AND prints a human-readable comparison table — matches existing `evaluate()` pattern from Phase 26
- Each strategy entry contains core trio: `mean_objective`, `feasibility_rate`, `mean_time_to_best`, plus `speedup_vs_uniform` ratio
- Printed table includes columns: Strategy | Mean Objective | Feasibility Rate | Time-to-Best | Speedup vs Uniform
- `validate_transfer()` reuses `evaluate_weights()` output directly — no custom transfer report

### Claude's Discretion
- Internal implementation of validate_transfer() orchestration (collect_training_data params, WeightPredictor config)
- How time-to-best is extracted from solve history (parsing logic)
- Speedup ratio calculation details (handling edge cases like uniform time = 0)
- Public API re-export pattern in `cbqs/ml/__init__.py`
- Test structure and helper utilities

</decisions>

<specifics>
## Specific Ideas

- Strategies as callables (not raw arrays) handles the transfer learning case naturally — predictor.predict() returns different-length arrays per model
- The speedup ratio makes it immediately clear whether ML weights are worth using ("2.3x faster" is more actionable than raw time numbers)
- validate_transfer() should feel like the existing collect_training_data() and evaluate() patterns — standalone function, same module, familiar signature

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evaluate()` in `training.py`: Reference pattern for strategy comparison (lines 327-390) — evaluate_weights follows same structure but with convergence metrics
- `_print_comparison_table()` in `training.py`: Reusable or extendable for the new table format with additional columns
- `_rank_result()` in `training.py`: Feasibility-first ranking helper for identifying best results
- `collect_training_data()` in `training.py`: Called internally by validate_transfer()
- `WeightPredictor.fit()` / `predict()`: Called internally by validate_transfer()
- `OptimizeResult.history`: List of `(value, elapsed_seconds)` tuples — source for time-to-best extraction

### Established Patterns
- Dict return + print table: evaluate() returns `{name: {metrics}}` AND calls `_print_comparison_table()` — evaluate_weights follows same dual output
- Strategies as callables: evaluate() already uses `lambda m: predictor.predict(m)` internally — evaluate_weights generalizes this to user-facing API
- Uniform baseline auto-included: evaluate() always adds 'uniform' — evaluate_weights does the same
- Weight cleanup: `set_param('branching_weights', None)` after each solve — from both collect_training_data and evaluate

### Integration Points
- `cbqs/ml/__init__.py`: Must export `evaluate_weights` and `validate_transfer`
- `cbqs/ml/training.py`: Most likely home for new functions (alongside existing evaluate)
- `Model.solve()` with `history` on `OptimizeResult`: Source for convergence speed data

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 28-transfer-learning-diagnostics*
*Context gathered: 2026-03-03*
