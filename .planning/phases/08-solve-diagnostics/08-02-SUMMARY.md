---
phase: 08-solve-diagnostics
plan: 02
subsystem: api
tags: [cython, integration, timing, history, callback, diagnostics]

# Dependency graph
requires:
  - phase: 08-01
    provides: OptimizeResult pure Python class
  - phase: 07-api-robustness
    provides: verify_solution method and verify parameter
provides:
  - solve() and local_search() returning OptimizeResult with all 12 fields
  - Timing instrumentation (preprocessing + solve split) in SearchLib.pyx
  - History callback wrapper for improvement accumulation
  - Integration tests covering full diagnostics pipeline
affects: [future research workflows, benchmark analysis scripts]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level callback state for Cython cpdef function compatibility"
    - "warnings.catch_warnings(record=True) for verification violation capture"
    - "time.monotonic() for preprocessing timing in Cython layer"

key-files:
  created:
    - tests/test_diagnostics_py.py
  modified:
    - cbqs/SearchLib.pyx
    - cbqs/Model.pyx
    - cbqs/__init__.py
    - tests/test_model_py.py
    - tests/test_verification_py.py
    - tests/test_determinism.py
    - tests/test_validation_model_py.py

key-decisions:
  - "Module-level cdef state variables for history callback (Cython cpdef cannot use closures or regular class with cdef attribute access)"
  - "time.monotonic() for preprocessing timing, mod.runtime * 1000.0 for solve timing"
  - "Merged histories from parallel workers sorted by elapsed_ms for unified convergence view"
  - "seed defaults to 0 (not None) when _seed_used not populated, to satisfy int coercion in OptimizeResult"

patterns-established:
  - "solve() always returns OptimizeResult (breaking change from list)"
  - "local_search() always returns OptimizeResult (breaking change from None)"
  - "verify parameter populates result.verified and result.violations via warnings capture"

# Metrics
duration: 26min
completed: 2026-02-06
---

# Phase 8 Plan 2: Cython Integration Summary

**Wire OptimizeResult into solve pipeline: timing instrumentation, history callback wrapper, breaking return type change, full test coverage**

## Performance

- **Duration:** 26 min
- **Started:** 2026-02-06T13:42:24Z
- **Completed:** 2026-02-06T14:08:16Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Modified SearchLib.pyx with preprocessing timing and history callback wrapper using module-level state
- Modified Model.pyx to construct and return OptimizeResult from both solve() and local_search()
- Merged parallel worker histories, sorted by elapsed_ms for unified convergence analysis
- Integrated verify parameter with warnings.catch_warnings for violation capture
- Exported OptimizeResult from cbqs package
- Updated 4 existing test files for OptimizeResult return type
- Created 23 integration tests covering solve, local_search, verification, and history

## Task Commits

Each task was committed atomically:

1. **Task 1: Add timing and history to SearchLib.pyx** - `3932b4f` (feat)
2. **Task 2: Wire OptimizeResult into Model.pyx and __init__.py** - `6673e77` (feat)
3. **Task 3: Update existing tests and create integration tests** - `06ee916` (test)

## Files Created/Modified
- `cbqs/SearchLib.pyx` - _HistoryCallback module-level state, timing instrumentation, expanded return tuples
- `cbqs/Model.pyx` - solve() and local_search() return OptimizeResult, verify integration
- `cbqs/__init__.py` - Export OptimizeResult
- `tests/test_diagnostics_py.py` - 23 integration tests (227 lines)
- `tests/test_model_py.py` - Updated for OptimizeResult return type
- `tests/test_verification_py.py` - Updated verify assertions on OptimizeResult
- `tests/test_determinism.py` - Added result.objective comparison
- `tests/test_validation_model_py.py` - Fixed isinstance check for OptimizeResult

## Decisions Made
- Used module-level `cdef` state variables for the history callback instead of closures (Cython cpdef functions do not support closures) or regular Python classes (cannot access cdef attributes of cdef classes)
- Used `time.monotonic()` for preprocessing timing at the Cython boundary; `mod.runtime * 1000.0` from C for solve timing
- Merged all parallel worker histories into a single list sorted by elapsed_ms for unified convergence view
- seed defaults to 0 when `_seed_used` is None (satisfies OptimizeResult int coercion requirement)
- Removed `print(self.final_state)` debug line from local_search()

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cython cpdef closure limitation**

- **Found during:** Task 1
- **Issue:** Plan specified using closure for history callback, but Cython `cpdef` functions do not support closures ("closures inside cpdef functions not yet supported")
- **Fix:** Used module-level `cdef` state variables and a module-level `def` function instead of a class or closure
- **Files modified:** cbqs/SearchLib.pyx
- **Commit:** 3932b4f, 6673e77

**2. [Rule 3 - Blocking] Regular Python class cannot access cdef attributes**

- **Found during:** Task 2
- **Issue:** Initial approach used a `_HistoryCallback` Python class that tried to access `mod.mod[0]` (a cdef attribute), causing AttributeError at runtime
- **Fix:** Switched from class-based to module-level cdef state variables with a Cython-compiled `def` function that can access cdef attributes
- **Files modified:** cbqs/SearchLib.pyx
- **Commit:** 6673e77

**3. [Rule 1 - Bug] test_validation_model_py.py assertion mismatch**

- **Found during:** Task 3
- **Issue:** test_solve_valid_results_min asserted `isinstance(result, list)` which broke with the new OptimizeResult return type
- **Fix:** Updated assertion to check for OptimizeResult
- **Files modified:** tests/test_validation_model_py.py
- **Commit:** 06ee916

## Issues Encountered

None beyond the Cython limitations documented as deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 8 is the final phase. All 8 phases are now complete.
- All 246 tests pass (38 unit + 89 existing + 96 new/updated + 23 integration diagnostics)
- No blockers

## Self-Check: PASSED

---
*Phase: 08-solve-diagnostics*
*Completed: 2026-02-06*
