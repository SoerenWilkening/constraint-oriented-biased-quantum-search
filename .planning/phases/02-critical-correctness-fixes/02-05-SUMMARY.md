---
phase: 02-critical-correctness-fixes
plan: 05
subsystem: api
tags: [expression, deprecation, immutability, python-api]

# Dependency graph
requires:
  - phase: 02-03
    provides: Expression standard operators return new objects
  - phase: 02-04
    provides: In-place operators mutate and return self
provides:
  - Deprecation warning infrastructure for behavior change notification
  - Comprehensive regression tests for Expression immutability
  - Optional import handling for missing dependencies
affects: [documentation, release-notes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Deprecation warning with env var suppression
    - One-time warning pattern with global flag
    - Optional imports for missing dependencies

key-files:
  created: []
  modified:
    - cbqs/Expression.pyx
    - cbqs/Model.pyx
    - cbqs/__init__.py
    - tests/test_expression_py.py

key-decisions:
  - "Deprecation warning is informational only - users don't need to change code"
  - "Warning respects CBQS_SUPPRESS_DEPRECATION env var for CI/production"
  - "Made CircuitBackendBinder and Model imports optional (missing deps)"

patterns-established:
  - "CBQS_SUPPRESS_DEPRECATION=1 suppresses transition warnings"
  - "Optional imports with try/except for missing external dependencies"

# Metrics
duration: 7min
completed: 2026-02-05
---

# Phase 02 Plan 05: Deprecation Warning and Variable Fix Summary

**Deprecation warning infrastructure for Expression immutability change, with comprehensive regression tests and optional import fixes**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-05T10:32:02Z
- **Completed:** 2026-02-05T10:38:55Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added deprecation warning function with CBQS_SUPPRESS_DEPRECATION env var control
- Added 8 new regression tests for Expression immutability (TestExpressionImmutability class)
- Fixed blocking import issues (CircuitBackendBinder, gurobipy optional)
- Verified Variable operators correctly delegate to Expression (already fixed in 02-03)

## Task Commits

Each task was committed atomically:

1. **Fix: Optional imports (blocking)** - `3166d2c` (fix)
2. **Task 1: Add deprecation warning** - `52a7234` (feat)
3. **Task 3: Add regression tests** - `d2f3090` (test)

**Note:** Task 2 (Variable operators) was already complete from 02-03 - operators delegate to Expression which returns new objects.

## Files Created/Modified
- `cbqs/Expression.pyx` - Added deprecation warning infrastructure
- `cbqs/Model.pyx` - Made CircuitBackendBinder import optional
- `cbqs/__init__.py` - Made Model import optional (gurobipy dependency)
- `tests/test_expression_py.py` - Added TestExpressionImmutability class with 8 tests

## Decisions Made
- Deprecation warning is informational only - informs users behavior changed but they don't need to update code
- Warning uses stacklevel=3 to point to user's code
- CBQS_SUPPRESS_DEPRECATION=1 allows suppression for CI/production environments
- Optional imports prevent crashes when external dependencies unavailable

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made CircuitBackendBinder import optional**
- **Found during:** Initial build/test setup
- **Issue:** Model.pyx imports CircuitBackendBinder which requires circuit_backend directory (not present)
- **Fix:** Wrapped import in try/except, set circuit = None on ImportError
- **Files modified:** cbqs/Model.pyx
- **Verification:** Build succeeds, imports work
- **Committed in:** 3166d2c

**2. [Rule 3 - Blocking] Made Model import optional in __init__.py**
- **Found during:** Initial build/test setup
- **Issue:** __init__.py imports Model which imports gurobipy (not installed)
- **Fix:** Wrapped import in try/except, set Model = None on ImportError
- **Files modified:** cbqs/__init__.py
- **Verification:** cbqs.Expression importable without gurobipy
- **Committed in:** 3166d2c

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes necessary for test execution. No scope creep.

## Issues Encountered
- Task 2 (Variable operators) was already fixed in 02-03/02-04 - Variable operators delegate to Expression operators which return new objects. No work needed.
- venv directory points to macOS pyenv path, created temp venv for Linux

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Deprecation warning ready for users updating from pre-02-03 versions
- All 28 Expression tests passing
- Ready for 02-06 (Valgrind CI and stress tests)

---
*Phase: 02-critical-correctness-fixes*
*Completed: 2026-02-05*
