---
phase: 05-memory-safety
plan: 05
subsystem: memory
tags: [cython, valgrind, memory-leak, calloc, free]

# Dependency graph
requires:
  - phase: 05-01
    provides: Valgrind suppression file, preprocessing leak fixes
provides:
  - Leak-free Cython layer with explicit memory management
  - Cython memory tests for regression detection
  - Updated Valgrind suppressions for Python 3.13
  - pyproject.toml for proper build dependencies
affects: [future-cython-development, ci-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "free(ptr) immediately after C function copies calloc'd data"
    - "Cleanup char** arrays with loop to free each string then free array"

key-files:
  created:
    - tests/test_cython_memory.py
    - pyproject.toml
  modified:
    - cbqs/branching.pyx
    - cbqs/state.pyx
    - tests/valgrind-python.supp

key-decisions:
  - "Add free() immediately after set_*_dependence() since C function copies data"
  - "Free char** in reverse order: strings first, then array"
  - "Suppress Python 3.13 internal allocations in Valgrind (debug symbols stripped)"

patterns-established:
  - "Cython calloc pattern: allocate, use, free immediately"
  - "Memory test pattern: iterate 50-100x to amplify leaks for Valgrind detection"

# Metrics
duration: 12min
completed: 2026-02-05
---

# Phase 05 Plan 05: Cython Layer Memory Audit Summary

**Fixed 2 memory leaks in Cython wrappers (branching.pyx, state.pyx) with tests proving zero Valgrind-detected leaks**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-05T17:27:53Z
- **Completed:** 2026-02-05T17:40:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Audited all 7 .pyx files in cbqs/ with documented findings
- Fixed memory leaks in branching.pyx (2 calloc without free)
- Fixed memory leak in state.pyx (char** allocation not freed after read_states)
- Created comprehensive Cython memory tests (8 tests across 5 classes)
- Valgrind with PYTHONMALLOC=malloc confirms 0 definitely lost bytes

## Cython Audit Results

| File | Lines Checked | Allocation Patterns | Status | Action |
|------|---------------|---------------------|--------|--------|
| branching.pyx | 12-26 | calloc at lines 14, 22 | LEAK | Added free(ptr) |
| state.pyx | 89-119 | calloc char** at lines 103, 108 | LEAK | Added free loop |
| state_sampler.pyx | 5-22 | ctx (line 10), state (line 11) | CLEAN | None |
| SearchLib.pyx | 17-265 | ctx (lines 155, 239), states | CLEAN | None |
| Expression.pyx | 100-145 | expr (line 102) | CLEAN | None |
| Constraint.pyx | 24-45 | con (line 26) | CLEAN | None |
| Model.pyx | 28-181 | mod (line 30), ptr (line 161) | CLEAN | None |

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix Cython memory leaks** - `6071277` (fix)
2. **Deviation: Missing numpy import** - `d106bba` (fix)
3. **Task 2: Add memory tests** - `78e29e9` (test)
4. **Task 3: Valgrind suppressions** - `c9b2c57` (chore)
5. **Build config: pyproject.toml** - `3feab42` (chore)

## Files Created/Modified
- `cbqs/branching.pyx` - Added free(ptr) after set_*_dependence calls, added numpy import
- `cbqs/state.pyx` - Added char** cleanup after read_states
- `tests/test_cython_memory.py` - New: 8 memory tests across all Cython modules
- `tests/valgrind-python.supp` - Added Python 3.13/NumPy suppressions
- `pyproject.toml` - New: build dependencies for pip

## Decisions Made
- Add free(ptr) immediately after set_obj_dependence/set_constraint_dependence because C functions copy the data
- Use reverse-order cleanup for char**: free each string, then free the array
- Suppress Python 3.13 internal allocations (debug symbols not available)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing numpy import in branching.pyx**
- **Found during:** Task 2 (running memory tests)
- **Issue:** set_*_dependence_wrapper uses np.array() but numpy was only imported in .pxd, not .pyx
- **Fix:** Added `import numpy as np` to branching.pyx
- **Files modified:** cbqs/branching.pyx
- **Verification:** Tests pass after rebuild
- **Committed in:** d106bba

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Pre-existing bug discovered during testing. Fix was essential for tests to run.

## Issues Encountered
- GCC 15 LTO internal compiler error during build - worked around by using venv pip
- Python 3.13 internal allocations show as leaks in Valgrind - added suppressions

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Cython layer memory management verified clean
- All 7 .pyx files audited with documented findings
- Memory regression tests available in test_cython_memory.py
- Ready for integration with CI pipeline

---
*Phase: 05-memory-safety*
*Completed: 2026-02-05*
