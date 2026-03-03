---
phase: quick
plan: 4
subsystem: docs
tags: [readme, ml, training, weight-prediction, adaptive-solve]

# Dependency graph
requires:
  - phase: 25-ml-foundation
    provides: cbqs.ml subpackage (FeatureExtractor, WeightPredictor)
  - phase: 26-adaptive-solve
    provides: adaptive_solve online adaptation
  - phase: 27-evaluation-framework
    provides: evaluate_weights with convergence metrics
  - phase: 28-transfer-learning
    provides: validate_transfer pipeline
provides:
  - User-facing training guide documentation in README.md
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Documentation-as-code: code examples mirror actual API signatures"

key-files:
  created: []
  modified:
    - README.md

key-decisions:
  - "Used knapsack as running example throughout, consistent with existing README"
  - "All imports from cbqs.ml (public API), not from submodules directly"
  - "Structured as five subsections: Installation, Offline Training, Online Adaptation, Evaluation, Transfer Learning"

patterns-established:
  - "Training guide follows code-focused minimal formatting style matching existing README"

requirements-completed: [quick-4]

# Metrics
duration: 1min
completed: 2026-03-03
---

# Quick Task 4: Extend README with Training Guide Summary

**Comprehensive ML training guide covering offline weight prediction, online adaptation, evaluation, and transfer learning with working cbqs.ml code examples**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-03T11:08:26Z
- **Completed:** 2026-03-03T11:09:26Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added full Training Guide section to README.md with 5 subsections
- Documented complete ML workflow: install, collect data, fit, predict, save/load
- Covered online adaptation with adaptive_solve including offline-to-online chaining
- Included evaluation comparison framework and transfer learning pipeline
- All code examples use real cbqs.ml API signatures verified against source

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ML training guide section to README** - `66851b4` (feat)

**Plan metadata:** (pending)

## Files Created/Modified
- `README.md` - Added 167 lines: Training Guide with Installation, Offline Training (WeightPredictor), Online Adaptation (adaptive_solve), Evaluation (evaluate_weights), and Transfer Learning (validate_transfer) subsections

## Decisions Made
- Used knapsack as the running example throughout the guide, consistent with existing README content
- All imports use `from cbqs.ml import ...` (the public API), never importing from submodules like `cbqs.ml.training`
- Structured the guide to follow the natural workflow progression: install -> collect data -> train -> predict -> adapt -> evaluate -> transfer
- Included parameter documentation inline with code examples rather than as separate reference tables

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- README documentation complete for v3.0 ML capabilities
- No further documentation tasks pending

---
*Quick Task: 4*
*Completed: 2026-03-03*
