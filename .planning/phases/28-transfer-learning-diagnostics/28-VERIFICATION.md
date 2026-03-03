---
status: passed
phase: 28
phase_name: Transfer Learning & Diagnostics
verified: 2026-03-03
requirements_verified: [DIAG-01, DIAG-02, DIAG-03]
---

# Phase 28: Transfer Learning & Diagnostics — Verification

## Goal
Users can validate that learned weights generalize across instance sizes and evaluate weight quality against baselines.

## Success Criteria Verification

### 1. Train on small instances, apply to larger instances (DIAG-01)
**Status: PASSED**

- `validate_transfer()` accepts `train_models` (small) and `test_models` (large)
- Internally calls `collect_training_data()` -> `WeightPredictor.fit()` -> `evaluate_weights()`
- Returns `(results, predictor)` tuple where predictor can be saved and reused
- Test `test_validate_transfer_different_sizes` trains on n=3, evaluates on n=8 — passes
- Per-variable prediction model (Phase 26) is inherently size-invariant

### 2. evaluate_weights utility comparing against baselines (DIAG-02)
**Status: PASSED**

- `evaluate_weights(test_models, strategies)` accepts dict of named callables
- Uniform baseline auto-added when not present in strategies dict
- Returns dict with per-strategy metrics: `{name: {mean_objective, feasibility_rate, mean_time_to_best, speedup_vs_uniform}}`
- Test `test_evaluate_weights_returns_dict_with_metrics` verifies all four metric keys present
- Test `test_evaluate_weights_auto_adds_uniform` verifies automatic uniform baseline
- Importable via `from cbqs.ml import evaluate_weights`

### 3. Objective improvement and convergence speed in reports (DIAG-03)
**Status: PASSED**

- `mean_objective` reports objective quality per strategy
- `feasibility_rate` reports constraint satisfaction rate
- `mean_time_to_best` reports convergence speed (time to first occurrence of best value in history)
- `speedup_vs_uniform` reports speedup ratio relative to uniform baseline
- Human-readable table printed with columns: Strategy | Mean Objective | Feasibility Rate | Time-to-Best | Speedup vs Uniform
- Test `test_evaluate_weights_prints_table` verifies table output contains all column headers

## Requirements Traceability

| Requirement | Plan | Status | Evidence |
|-------------|------|--------|----------|
| DIAG-01 | 28-02 | Verified | `validate_transfer()` in `cbqs/ml/training.py`, `TestValidateTransfer` (4 tests pass) |
| DIAG-02 | 28-01 | Verified | `evaluate_weights()` in `cbqs/ml/training.py`, `TestEvaluateWeights` (7 tests pass) |
| DIAG-03 | 28-01 | Verified | Convergence metrics in `evaluate_weights()` output, `_compute_time_to_best()` helper |

## Test Results

```
tests/test_ml_training.py: 30 passed (0 failed)
  - TestWeightPredictorFitPredict: 5 passed
  - TestWeightPredictorEdgeCases: 2 passed
  - TestWeightPredictorPersistence: 3 passed
  - TestCollectTrainingData: 5 passed
  - TestEvaluate: 4 passed
  - TestEvaluateWeights: 7 passed (NEW - Phase 28)
  - TestValidateTransfer: 4 passed (NEW - Phase 28)
```

## Artifacts

| File | Purpose |
|------|---------|
| `cbqs/ml/training.py` | `evaluate_weights()`, `validate_transfer()`, `_compute_time_to_best()`, `_print_evaluation_table()` |
| `cbqs/ml/__init__.py` | Public exports for `evaluate_weights` and `validate_transfer` |
| `tests/test_ml_training.py` | 11 new tests (7 + 4) for Phase 28 functions |

## Notes

- History callback warnings (`History callback: error computing entry`) are pre-existing solver warnings from Cython layer, unrelated to Phase 28 code. They occur with very small test models using `close(validate=False)` and do not affect correctness.
- When history is empty due to these warnings, `_compute_time_to_best()` correctly returns `stopping_time` as ceiling penalty.
