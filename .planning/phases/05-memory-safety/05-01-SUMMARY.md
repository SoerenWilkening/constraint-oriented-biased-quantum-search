---
phase: 05-memory-safety
plan: 01
subsystem: memory
tags: [memory-safety, valgrind, asan, leak-fix, preprocessing]

# Dependency graph
requires:
  - phase: 01-test-foundation
    provides: Test infrastructure for verification
provides:
  - Fixed preprocessing() and preprocessing_sparse() memory leaks
  - Valgrind suppression file for Python/numpy/Cython runtime leaks
affects: [05-02-vla-removal, 05-03-asan-integration, 05-04-stress-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit free() for zero-length realloc instead of realloc(ptr, 0)"
    - "Use auxiliary pointer as guard in free_constraints() for grouped allocations"

key-files:
  created:
    - tests/valgrind-python.supp
  modified:
    - cbqs/src/constraint.c

key-decisions:
  - "Explicit free() is always correct for zero-length - realloc(ptr, 0) has implementation-defined behavior"
  - "Changed free_constraints() guard from positive_indices to positive_offsets - offsets always allocated if preprocessing ran"

patterns-established:
  - "Zero-length realloc pattern: check length, free+NULL if 0, realloc with temp if >0"

# Metrics
duration: 8min
completed: 2026-02-05
---

# Phase 5 Plan 1: Preprocessing Leak Fix Summary

**Fixed preprocessing() realloc-to-zero memory leak and created Valgrind suppression file for Python/numpy/Cython runtime leaks**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-05T17:20:00Z
- **Completed:** 2026-02-05T17:28:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed the pre-existing preprocessing() memory leak tracked since Phase 1
- Fixed matching leak in preprocessing_sparse() function
- Updated free_constraints() to use proper guard for grouped allocations
- Created comprehensive Valgrind suppression file for 14 leak patterns

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix preprocessing() realloc-to-zero leak** - `1e1447d` (fix)
2. **Task 2: Create Valgrind suppression file** - `2ea9834` (chore)

## Files Created/Modified
- `cbqs/src/constraint.c` - Fixed preprocessing() and preprocessing_sparse() realloc-to-zero leaks, updated free_constraints() guard
- `tests/valgrind-python.supp` - Valgrind suppression file for Python/numpy/Cython runtime leaks

## Decisions Made

1. **Explicit free() instead of realloc(ptr, 0):** The C11 standard (7.22.3.5) states realloc(ptr, 0) has implementation-defined behavior. On some platforms it returns NULL and frees; on others it returns a non-NULL pointer. Explicit free() is always correct.

2. **Changed guard from positive_indices to positive_offsets:** The fix can set positive_indices to NULL when array_length is 0, but positive_offsets is always allocated if preprocessing() ran. Using positive_offsets as the guard ensures all grouped allocations are freed.

3. **Comprehensive suppression patterns:** Included 14 suppression rules covering Python allocator (Malloc/Realloc/Calloc), GC, arena, type/module init, NumPy, Cython, thread state, and import patterns.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed free_constraints() guard condition**
- **Found during:** Task 1 (preprocessing() leak fix)
- **Issue:** After fixing realloc-to-zero by setting positive_indices to NULL, ASan reported leaks because free_constraints() used positive_indices as guard for freeing all preprocessing arrays
- **Fix:** Changed guard from `positive_indices != NULL` to `positive_offsets != NULL` since offsets are always allocated if preprocessing ran
- **Files modified:** cbqs/src/constraint.c
- **Verification:** ASan leak detection shows zero leaks
- **Committed in:** 1e1447d (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix was necessary for correctness - without updating the guard, the fix would introduce a different memory leak. No scope creep.

## Issues Encountered

- Valgrind not available in execution environment - used ASan leak detection instead for verification. The suppression file syntax follows standard Valgrind format and will be validated in CI.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Preprocessing functions now leak-free under normal operation
- Valgrind suppression file ready for CI integration
- Ready for Plan 05-02 (VLA removal) and Plan 05-03 (ASan integration)

---
*Phase: 05-memory-safety*
*Completed: 2026-02-05*
