---
phase: 07-api-robustness
plan: 03
subsystem: api
tags: [cython, verification, post-solve, eval-con, eval-obj, warnings]

# Dependency graph
requires:
  - phase: 01-test-foundation
    provides: pytest infrastructure and Model test patterns
  - phase: 02-correctness
    provides: Expression immutability and operator semantics
  - phase: 07-02-api-robustness
    provides: Model input validation and validate=False parameter
provides:
  - verify_solution() method for post-solve constraint and objective checking
  - verify=True parameter on solve() and local_search() for automatic verification
  - _verified attribute tracking verification state (None/True/False)
affects: [future-phases-using-solver-results, documentation, researcher-workflows]

# Tech tracking
tech-stack:
  added: []
  patterns: [post-solve-verification, c-state-reconstruction, sense-aware-comparison]

key-files:
  created:
    - tests/test_verification_py.py
  modified:
    - cbqs/Model.pyx
    - cbqs/Model.pxd

key-decisions:
  - "Reconstruct state_py from C-level mod.global_opt bits for eval_con/eval_obj compatibility"
  - "Apply sense multiplication to eval_obj output for correct user-facing comparison"
  - "Use NULL check on mod.global_opt (C pointer) rather than Python global_opt attribute"
  - "verify=False default on solve() and local_search() for opt-in behavior"

patterns-established:
  - "C state reconstruction: sw_tstbit loop to extract bits from state_t, create state_py for Python-level evaluation"
  - "Sense-aware comparison: eval_obj returns raw (possibly negated) value, multiply by self.sense for user-facing"

# Metrics
duration: 8min
completed: 2026-02-06
---

# Phase 7 Plan 3: Post-Solve Verification Summary

**verify_solution() method using C eval_con/eval_obj with sense-aware objective comparison and _verified flag tracking**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-06T11:20:44Z
- **Completed:** 2026-02-06T11:29:16Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added verify_solution() method that checks constraint satisfaction via eval_con and objective value correctness via eval_obj, using existing C evaluation functions
- Added _verified attribute (None/True/False) tracking verification state across the model lifecycle
- Added verify=False parameter to solve() and local_search() for automatic post-solve verification
- Discovered and fixed sense multiplication issue: eval_obj returns raw (negated for MAXIMIZE) value, requiring `* self.sense` for correct comparison with objective_value property
- 15 new tests across 3 classes covering all verification scenarios

## Task Commits

Each task was committed atomically:

1. **Task 1: Add verify_solution() method and verify=True parameter to Model.pyx** - `4edfdac` (feat)
2. **Task 2: Create post-solve verification tests** - `c675fb6` (test)

**Plan metadata:** (pending)

## Files Created/Modified
- `cbqs/Model.pyx` - Added verify_solution() method, verify=False on solve()/local_search(), sw_tstbit cimport, _verified init
- `cbqs/Model.pxd` - Added _verified cdef public object declaration
- `tests/test_verification_py.py` - 15 tests across 3 classes: TestVerifySolution (9), TestVerifyWarnings (2), TestVerifyOnSolve (4)

## Decisions Made
- **C state reconstruction over Python attribute:** The Python-level `self.global_opt` remains None after solve(); the real solution is in `self.mod[0].global_opt` (C state_t pointer). verify_solution() reconstructs a state_py from the C bits using sw_tstbit for compatibility with eval_con/eval_obj.
- **Sense-aware objective comparison:** The C `objective_value()` function and `eval_obj()` return the raw internal value (negated for MAXIMIZE). The comparison multiplies by `self.sense` to match the user-facing `objective_value` property (`tot_profit * sense`).
- **NULL pointer check for unsolved detection:** Uses `self.mod[0].global_opt is NULL` (C-level check) rather than checking the Python attribute, since the C global_opt is initialized by manual_initial() but starts as NULL in init_model().

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed sense multiplication in objective comparison**
- **Found during:** Task 1 (verify_solution() implementation)
- **Issue:** Initial implementation compared eval_obj raw output directly with self.objective_value, but eval_obj returns negated values for MAXIMIZE (because the objective expression is internally negated via `expr >= 0`). This caused false verification failures.
- **Fix:** Applied `* self.sense` to eval_obj output before comparison: `recomputed_obj = self.objective.eval_obj(st) * self.sense`
- **Files modified:** cbqs/Model.pyx
- **Verification:** Quick test confirms verify_solution() returns True for valid solved knapsack with MAXIMIZE
- **Committed in:** 4edfdac (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential fix for correct objective comparison. Without sense multiplication, MAXIMIZE models always fail verification.

## Issues Encountered
None beyond the sense multiplication deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 7 (API Robustness) is now complete: all 3 plans (Expression validation, Model validation, Post-solve verification) delivered
- Ready for Phase 8 (final phase)
- No blockers

## Self-Check: PASSED

---
*Phase: 07-api-robustness*
*Completed: 2026-02-06*
