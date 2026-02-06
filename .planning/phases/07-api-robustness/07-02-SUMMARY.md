---
phase: 07-api-robustness
plan: 02
subsystem: api
tags: [cython, validation, model, validate-bypass, duplicate-merge]

# Dependency graph
requires:
  - phase: 01-test-foundation
    provides: pytest infrastructure and Model test patterns
  - phase: 02-correctness
    provides: Expression immutability and operator semantics
provides:
  - Model-level input validation for add_constraint, set_objective, close
  - validate=False bypass for performance-critical batch runs
  - Duplicate variable term merging in expressions
  - Proper ValueError in solve() replacing assert
  - add_variables n >= 1 validation
affects: [07-03-api-robustness, future-phases-using-model-api]

# Tech tracking
tech-stack:
  added: []
  patterns: [validate-parameter-bypass, eager-model-validation, duplicate-term-merging]

key-files:
  created:
    - tests/test_validation_model_py.py
  modified:
    - cbqs/Model.pyx
    - tests/test_memory_stress.py

key-decisions:
  - "validate=False skips ALL Python-level checks (not just expensive ones)"
  - "Sense validation always runs even with validate=False (critical for correctness)"
  - "Duplicate variable merging operates on C expression_t directly for efficiency"
  - "UserWarning emitted for duplicate term merging (not silent)"

patterns-established:
  - "validate=True default parameter on Model methods for input validation"
  - "_merge_duplicate_variable_terms as module-level helper operating on Expression C struct"

# Metrics
duration: 7min
completed: 2026-02-06
---

# Phase 7 Plan 2: Model Input Validation Summary

**Model.pyx validation guards with validate=False bypass, duplicate variable term merging, and solve() ValueError upgrade**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-06T11:11:03Z
- **Completed:** 2026-02-06T11:17:33Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added input validation to add_constraint (None check, sense check), set_objective (None check), close (empty model check), add_variables (n >= 1), and solve (results parameter)
- All validation methods accept validate=False to bypass Python-level checks for performance-critical batch runs
- Implemented _merge_duplicate_variable_terms that detects and merges duplicate variable terms (e.g., 3*x1 + 5*x1 -> 8*x1) directly on the C expression_t structure
- Replaced assert in solve() with proper ValueError for results parameter validation
- 26 new tests covering all validation behaviors across 6 test classes

## Task Commits

Each task was committed atomically:

1. **Task 1: Add input validation to Model.pyx methods with validate=False bypass** - `b2f0e7f` (feat)
2. **Task 2: Create Model validation tests** - `81eff91` (test)

**Plan metadata:** (pending)

## Files Created/Modified
- `cbqs/Model.pyx` - Added validation guards to add_constraint, set_objective, close, solve, add_variables; added _merge_duplicate_variable_terms helper
- `tests/test_validation_model_py.py` - 26 tests across 6 classes: TestAddConstraintValidation, TestSetObjectiveValidation, TestCloseValidation, TestSolveValidation, TestAddVariablesValidation, TestDuplicateVariableMerging
- `tests/test_memory_stress.py` - Updated test_zero_constraints to use validate=False (bypasses new validation for C-level safety test)

## Decisions Made
- validate=False skips ALL Python-level checks -- consistent "trust me" semantics for performance-critical paths
- Sense validation (MAXIMIZE/MINIMIZE) always runs even with validate=False -- critical for correctness (wrong sense corrupts solver state)
- Duplicate variable term merging operates directly on C expression_t for zero-copy efficiency rather than rebuilding expressions
- Merging emits UserWarning to alert users of likely modeling bugs while still proceeding
- close() validates both variables and constraints (empty model is always a bug per CONTEXT.md)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_memory_stress.py zero-constraint edge case test**
- **Found during:** Task 2 (test verification)
- **Issue:** test_zero_constraints deliberately creates a model with zero constraints and calls close(), which now raises ValueError from the new validation
- **Fix:** Updated test to use close(validate=False) since it tests C-level memory safety, not API validation
- **Files modified:** tests/test_memory_stress.py
- **Verification:** Full test suite passes (181/181)
- **Committed in:** 81eff91 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Auto-fix necessary to maintain test compatibility. The test was testing C-level edge cases, not API validation, so validate=False is the correct approach.

## Issues Encountered
None -- plan executed cleanly after the single test fix.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Model validation complete, ready for Plan 07-03 (post-solve verification)
- validate=False pattern established for consistent bypass across all Model methods
- No blockers

## Self-Check: PASSED

---
*Phase: 07-api-robustness*
*Completed: 2026-02-06*
