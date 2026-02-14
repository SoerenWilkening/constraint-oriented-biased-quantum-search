---
phase: 14-unified-branching-model
plan: 02
subsystem: api
tags: [branching, cython, python-api, set-param, validation, branching-weights]

# Dependency graph
requires:
  - phase: 14-unified-branching-model
    plan: 01
    provides: Unified BranchingStats_t with branching_weights, solver_ctx setters
  - phase: 12-set-param-api
    provides: set_param/get_param infrastructure, _KNOWN_PARAMS, _params dict
provides:
  - End-to-end branching_weights flow: set_param -> Cython -> solver_ctx_set_branching_weights
  - Validated branching_weights (1D, non-negative, no NaN/Inf, length match)
  - Individual factor setters via set_param (branching_factor, bias_factor, look_ahead_factor)
  - Cleaned Cython layer with no deprecated wrappers
affects: [15-api-cleanup, 16-global-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: [validated-array-param-in-set-param, individual-factor-setters-via-set-param, calloc-copy-free-for-cython-to-c-array-passing]

key-files:
  created: []
  modified:
    - cbqs/branching.pxd
    - cbqs/branching.pyx
    - cbqs/SearchLib.pxd
    - cbqs/SearchLib.pyx
    - cbqs/Model.pyx
    - tests/test_set_param.py
    - tests/test_branching_propagation.py
    - tests/test_cython_memory.py

key-decisions:
  - "Removed old _KNOWN_PARAMS (manual_bias, manual_bias_factor, branching_factors) immediately; no deprecation shim"
  - "branching_weights length validation deferred when model has no variables (n=0), enforced when n>0"
  - "Factor setters only propagated to solver_ctx when explicitly set via set_param (defaults come from C-level BranchingStats defaults)"

patterns-established:
  - "Array param validation pattern: numpy.asarray + ndim + range + nan/inf checks in set_param"
  - "Cython array propagation pattern: calloc -> copy -> solver_ctx_set_* -> free (no ownership transfer)"

# Metrics
duration: 12min
completed: 2026-02-14
---

# Phase 14 Plan 02: Cython/Python Unified Branching Summary

**Wired branching_weights from Python set_param through Cython to C solver context with full validation, removed all deprecated wrappers, and updated all Python tests**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-14T18:42:28Z
- **Completed:** 2026-02-14T18:55:07Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Updated all Cython declarations (branching.pxd, SearchLib.pxd) to match the new C struct from Plan 14-01
- Removed 4 deprecated Python wrappers (set_factors_wrapper, set_bias_wrapper, set_obj_dependence_wrapper, set_constraint_dependence_wrapper) from branching.pyx
- Added branching_weights validation in set_param: 1D array, non-negative, no NaN/Inf, length must match num_variables
- Wired branching_weights, branching_factor, bias_factor, and look_ahead_factor propagation through both run_sampling and run_local_search
- Removed old solve() kwargs (manual_bias, bias_factor, manual_bias_factor, look_ahead_factor) from Model.pyx
- Updated _KNOWN_PARAMS: added branching_weights, branching_factor; removed manual_bias, manual_bias_factor, branching_factors
- 317 Python tests pass (35 set_param + 11 propagation + 271 others)

## Task Commits

Each task was committed atomically:

1. **Task 1: Update Cython declarations and remove deprecated wrappers** - `6243445` (feat)
2. **Task 2: Wire branching_weights propagation and update Model.pyx** - `b36c122` (feat)
3. **Task 3: Update Python tests for new API** - `6803e10` (test)

## Files Created/Modified
- `cbqs/branching.pxd` - Updated BranchingStats_t to match new C struct, removed deprecated C function declarations
- `cbqs/branching.pyx` - Removed all deprecated wrappers, only set_seed remains
- `cbqs/SearchLib.pxd` - Replaced old solver_ctx setters with new individual setters
- `cbqs/SearchLib.pyx` - New branching_weights/factor propagation in run_sampling and run_local_search
- `cbqs/Model.pyx` - Updated _KNOWN_PARAMS, added validation, removed old solve() kwargs
- `tests/test_set_param.py` - 35 tests: validation, old API removal, weights validation, factor validation
- `tests/test_branching_propagation.py` - 11 tests: bias, individual factors, weights propagation + determinism
- `tests/test_cython_memory.py` - Updated memory test to use branching_weights via solve instead of removed wrappers

## Decisions Made
- Removed old _KNOWN_PARAMS immediately (manual_bias, manual_bias_factor, branching_factors) -- these now raise ValueError as unknown params
- branching_weights length validation is deferred when model has no variables (n=0), allowing weights to be set before add_variables
- Factor setters (branching_factor, bias_factor, look_ahead_factor) are only propagated when explicitly set via set_param; C-level defaults apply otherwise

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_cython_memory.py referencing removed wrappers**
- **Found during:** Task 3 (Update Python tests)
- **Issue:** test_cython_memory.py::TestBranchingMemory tested set_obj_dependence_wrapper and set_constraint_dependence_wrapper, which no longer exist after Task 1
- **Fix:** Replaced with test_branching_weights_no_leak that tests branching_weights memory management through the new set_param/solve path
- **Files modified:** tests/test_cython_memory.py
- **Verification:** All 317 tests pass
- **Committed in:** 6803e10 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix was necessary for CI -- removed tests were testing functions that no longer exist. Replacement test covers the equivalent new code path. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 14 is now fully complete: C kernel (Plan 01) + Cython/Python layer (Plan 02)
- The end-to-end flow works: model.set_param('branching_weights', [...]) -> Cython -> solver_ctx_set_branching_weights()
- Ready for Phase 15 (API Cleanup): remove remaining solve() kwargs, model_t old fields
- Note: model_t C struct still has manual_bias/manual_bias_factor/bias_factor/look_ahead_factor fields that are no longer used by the Python layer -- cleanup deferred to Phase 15

## Self-Check: PASSED

All 8 modified files verified on disk. All 3 task commits verified in git log (6243445, b36c122, 6803e10). 317 Python tests pass.

---
*Phase: 14-unified-branching-model*
*Completed: 2026-02-14*
