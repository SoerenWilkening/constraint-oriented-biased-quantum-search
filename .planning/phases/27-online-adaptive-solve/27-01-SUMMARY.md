---
phase: 27-online-adaptive-solve
plan: 01
subsystem: ml
tags: [numpy, ema, online-learning, adaptive-solve, dataclass]

requires:
  - phase: 26-offline-training-pipeline
    provides: WeightPredictor class, _rank_result helper, collect_training_data pattern
provides:
  - adaptive_solve() function for multi-round adaptive weight optimization
  - AdaptiveResult dataclass for structured result representation
  - Combined reward signal (feasibility + objective improvement)
  - _resolve_initial_weights helper for WeightPredictor duck-typing
affects: [28-transfer-learning-diagnostics]

tech-stack:
  added: []
  patterns: [online-adaptive-loop, ema-weight-update, combined-reward-signal]

key-files:
  created:
    - tests/test_ml_adaptation.py
  modified:
    - cbqs/ml/adaptation.py
    - cbqs/ml/__init__.py

key-decisions:
  - "Reward signal formula: 0.5 * feasibility + 0.5 * normalized_objective_improvement"
  - "AdaptiveResult implemented as dataclass for clean type-hinted data container"
  - "Seed propagation via model.seed property (not set_param) for per-round determinism"
  - "Import _rank_result from training.py to reuse feasibility-first ranking"

patterns-established:
  - "Online adaptation loop: resolve weights -> save state -> loop(set params, solve, reward, EMA update) -> restore state"
  - "_resolve_initial_weights: accept None/ndarray/WeightPredictor with duck-typing"

requirements-completed: [ADAPT-01, ADAPT-02]

duration: 5min
completed: 2026-03-02
---

# Phase 27-01: Online Adaptive Solve Summary

**adaptive_solve() with EMA weight updates, combined reward signal, and AdaptiveResult return type**

## Performance

- **Duration:** 5 min
- **Completed:** 2026-03-02
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented adaptive_solve() in cbqs/ml/adaptation.py with full EMA weight update loop
- Combined reward signal blending feasibility (binary) and objective improvement rate (normalized)
- AdaptiveResult dataclass with best_result, best_weights, history, n_rounds_completed
- Support for initial_weights as None (uniform), ndarray (copied), or WeightPredictor (predict called)
- Model state restoration via try/finally to prevent side effects
- 15 comprehensive tests covering all core behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: Write adaptive_solve tests (RED phase)** - `7e455dc` (test)
2. **Task 2: Implement adaptive_solve and update __init__.py (GREEN phase)** - `0115ff5` (feat)

## Files Created/Modified
- `cbqs/ml/adaptation.py` - Full adaptive_solve implementation replacing stub
- `cbqs/ml/__init__.py` - Added adaptive_solve and AdaptiveResult exports
- `tests/test_ml_adaptation.py` - 15 tests for core adaptive solve behavior

## Decisions Made
- Reward formula: equal weight (0.5) for feasibility and objective improvement signals
- Reward-adjusted weights = reward * current_weights (reinforces good, dampens bad)
- Used model.seed property (not set_param) since seed is not in _PARAM_DEFS
- Neutral reward (0.5) for first round or when previous objective is 0

## Deviations from Plan
None - plan executed exactly as written

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- adaptive_solve() ready for determinism and thread safety testing (Plan 27-02)
- All existing ML tests continue to pass (35 tests)

---
*Phase: 27-online-adaptive-solve*
*Completed: 2026-03-02*
