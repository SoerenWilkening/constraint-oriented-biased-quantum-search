---
phase: 27
status: passed
verified: 2026-03-02
---

# Phase 27: Online Adaptive Solve - Verification

## Phase Goal
Users can run a multi-round adaptive solve where branching weights improve between rounds based on observed solver performance

## Success Criteria Verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | User can run an adaptive multi-round solve that updates branching weights between rounds using EMA | PASS | `adaptive_solve(model, n_rounds=3, seed=42)` returns AdaptiveResult with history showing weight evolution. 15 core tests pass. |
| 2 | Adaptation reward signal combines both objective improvement rate and constraint satisfaction rate | PASS | `_compute_reward()` blends `0.5 * feasibility + 0.5 * obj_improvement`. All reward values in [0,1]. Tests verify. |
| 3 | Running the same adaptive solve with the same seed and thread count produces identical results across runs | PASS | 4 determinism tests confirm identical weights, objectives, feasibility, and best_result with same seed on fresh model instances. |
| 4 | Concurrent adaptive solves on different models do not share or corrupt weight arrays between workers | PASS | 3 concurrency tests confirm independent results via threading.Thread. No shared mutable state — all weights are function-local copies. |

## Requirement Coverage

| Requirement | Plan | Status |
|-------------|------|--------|
| ADAPT-01 | 27-01 | PASS — adaptive_solve with EMA weight updates implemented and tested |
| ADAPT-02 | 27-01 | PASS — combined reward signal implemented and tested |
| ADAPT-03 | 27-02 | PASS — determinism verified with same-seed/same-result tests |
| ADAPT-04 | 27-02 | PASS — thread safety verified with concurrent execution tests |

## Must-Haves Verification

### Plan 27-01 Must-Haves
- [x] adaptive_solve returns AdaptiveResult with best_result, best_weights, history, n_rounds_completed
- [x] History entries contain round, objective, feasible, reward, weights keys
- [x] Reward signal combines objective improvement and constraint satisfaction
- [x] EMA formula: new_weights = alpha * reward_adjusted + (1 - alpha) * old_weights
- [x] Weights clipped to non-negative after each EMA update
- [x] best_weights from best-performing round, not final EMA'd weights
- [x] Model branching_weights restored after completion
- [x] initial_weights=None defaults to np.ones(n_vars)
- [x] initial_weights accepts WeightPredictor (predict called automatically)
- [x] initial_weights length mismatch raises ValueError
- [x] Input weights copied, never mutated

### Plan 27-02 Must-Haves
- [x] Same seed + num_workers=1 produces identical history weights
- [x] Same seed produces identical objectives and feasibility
- [x] Concurrent adaptive_solve calls complete without errors
- [x] Concurrent results have correct shapes for respective models
- [x] No shared mutable state between concurrent calls

## Artifacts

| File | Status | Lines |
|------|--------|-------|
| cbqs/ml/adaptation.py | Created | 222 |
| cbqs/ml/__init__.py | Modified | 19 |
| tests/test_ml_adaptation.py | Created | 419 |

## Test Results

```
22 passed in 11.78s (tests/test_ml_adaptation.py)
57 passed in 23.42s (full ML test suite)
```

## Score

**4/4 success criteria verified**
**4/4 requirements covered**
**All must-haves satisfied**

---
*Phase: 27-online-adaptive-solve*
*Verified: 2026-03-02*
