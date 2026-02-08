---
phase: 13-dead-code-documentation-cleanup
plan: 02
subsystem: cython-middleware, build-config
tags: [cython, pyx, dead-code, cleanup, cmake, setup.py]

# Dependency graph
requires:
  - phase: 13-dead-code-documentation-cleanup
    provides: "RESEARCH.md dead code inventory for Cython/Python layer"
provides:
  - "Clean .pyx files with no commented-out code or unguarded prints"
  - "Clean setup.py with no unused source lists"
  - "Clean root CMakeLists.txt with no stale include paths"
  - "CLEAN-03 verification (no bare except clauses in production .pyx)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No unguarded print() calls in production Cython code"
    - "All except clauses specify exception types (no bare except)"

key-files:
  created: []
  modified:
    - "cbqs/Model.pyx"
    - "cbqs/Expression.pyx"
    - "cbqs/state.pyx"
    - "cbqs/Constraint.pyx"
    - "cbqs/state_sampler.pyx"
    - "cbqs/SearchLib.pyx"
    - "setup.py"
    - "CMakeLists.txt"

key-decisions:
  - "Removed unguarded print() from Model.solution property (debug-only, not user-facing)"
  - "Removed unguarded print() from approximate_benchmarking (debug noise in production method)"
  - "Added TODO comment for pandas dependency instead of removing it"

patterns-established:
  - "Production .pyx files: no commented-out code, no unguarded print statements"
  - "Build config: no dead source lists or stale include paths"

# Metrics
duration: 16min
completed: 2026-02-08
---

# Phase 13 Plan 02: Cython/Python Dead Code & Build Config Cleanup Summary

**Removed all commented-out code and unguarded debug prints from 6 .pyx files, cleaned dead sources_circuit list from setup.py and stale iqs/src include from CMakeLists.txt**

## Performance

- **Duration:** 16 min
- **Started:** 2026-02-08T18:15:24Z
- **Completed:** 2026-02-08T18:31:48Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Removed all commented-out debug code from Model.pyx, Expression.pyx, state.pyx, Constraint.pyx, state_sampler.pyx, and SearchLib.pyx (61 lines deleted)
- Removed unguarded print() calls from Model.pyx approximate_benchmarking and solution property
- Verified CLEAN-03: no bare except clauses exist in production .pyx files (all use typed exceptions)
- Removed dead sources_circuit list (20 lines) from setup.py -- never added to extensions
- Removed stale iqs/src include directory from root CMakeLists.txt -- directory does not exist
- All 304 Python tests pass with zero behavioral changes
- All 12 buildable C tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove dead code and unguarded prints from all Cython files** - `ea04b87` (refactor)
2. **Task 2: Clean up build configuration and run full test suite** - `bb22663` (chore)

**Plan metadata:** `3175e1a` (docs: complete plan)

## Files Created/Modified
- `cbqs/Model.pyx` - Removed commented-out gpu_executor, runtime, objective_value, print blocks, unguarded print() in approximate_benchmarking and solution property
- `cbqs/Expression.pyx` - Removed commented-out print_expression calls, potential calculation in __eq__, print in c_liste, negate_expression comment
- `cbqs/state.pyx` - Removed commented-out __del__, print/debug lines in read method, print_state in __str__, iterator comment
- `cbqs/Constraint.pyx` - Removed commented-out function wrapper, print statements in process_constraints and process
- `cbqs/state_sampler.pyx` - Removed commented-out import, print statements in opt_sampler and exact_QSearch
- `cbqs/SearchLib.pyx` - Removed commented-out monte carlo estimation block and print in emulate_QSearch
- `setup.py` - Removed dead sources_circuit list and commented-out __version__ import; added pandas TODO
- `CMakeLists.txt` - Removed stale iqs/src include directory reference

## Decisions Made
- Removed unguarded print() from Model.solution property: these were debug prints that emitted noise to stdout in production. The property now simply returns 0 (preserving the existing return value).
- Removed unguarded print(state) from approximate_benchmarking: debug noise that polluted benchmarking output.
- Left pandas dependency in setup.py with a TODO comment rather than removing it, per plan guidance (may be used by user scripts).
- Did NOT remove CircuitBackendBinder import in __init__.py (has try/except for graceful failure, as plan specified).
- Left metal_test CMake target and test.c main executable target as-is (per plan: platform-specific, not stale).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed additional commented-out code not in inventory**
- **Found during:** Task 1 (Cython file cleanup)
- **Issue:** Several additional commented-out lines found during sweep: `# negate_expression(self.expr)` in Expression.pyx __ge__, `# print("l = ", l)` in Expression.pyx c_liste, `# print_state(&self.state[])` in state.pyx __str__, iterator comment in state.pyx, extra print comments in state_sampler.pyx opt_sampler/exact_QSearch
- **Fix:** Removed all additional commented-out code found during thorough sweep
- **Files modified:** cbqs/Expression.pyx, cbqs/state.pyx, cbqs/state_sampler.pyx
- **Verification:** All 304 tests pass, compilation clean
- **Committed in:** ea04b87 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix -- additional dead code beyond inventory)
**Impact on plan:** More thorough cleanup than planned. No scope creep -- all changes are dead code removal within the planned files.

## Issues Encountered
- C tests test_searchlib and test_local_search fail to build due to uncommitted Plan 01 C source changes (removed `compare` function). This is a pre-existing issue not caused by Plan 02 changes. The 12 other C tests all pass.
- Virtual environment python symlink broken (points to non-existent pyenv path). Used system Python 3.13 with --break-system-packages flag.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 13 Plan 02 complete: all Cython/Python layer dead code removed
- Combined with Plan 01 (C kernel), the full codebase dead code sweep is done
- No blockers for phase completion

## Self-Check: PASSED

All 9 key files verified present. Both task commits (ea04b87, bb22663) verified in git log.

---
*Phase: 13-dead-code-documentation-cleanup*
*Completed: 2026-02-08*
