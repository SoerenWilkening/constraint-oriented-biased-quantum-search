---
phase: 14-unified-branching-model
plan: 01
subsystem: api
tags: [branching, c-kernel, struct-refactor, formula, l1-normalization]

# Dependency graph
requires:
  - phase: 03-solver-context
    provides: solver_ctx_t with embedded BranchingStats_t and ctx-aware setters
provides:
  - Unified BranchingStats_t struct with branching_weights array
  - 3-term BranchingFunction (branching_weights + assignment_bias + look_ahead)
  - solver_ctx_set_branching_weights() with L1 normalization
  - Individual factor setters (branching_factor, bias_factor, look_factor)
affects: [14-02 Cython/Python layer, 15-api-cleanup, 16-global-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: [L1-normalization-at-set-time, 3-term-weighted-formula, copy-on-set-ownership]

key-files:
  created: []
  modified:
    - cbqs/src/Branching.h
    - cbqs/src/Branching.c
    - cbqs/src/solver_ctx.h
    - cbqs/src/solver_ctx.c
    - tests/test_branching.c
    - tests/test_solver.c
    - tests/test_integration.c
    - tests/test_local_search.c
    - tests/test_thread_safety.c

key-decisions:
  - "L1 normalization for branching_weights (sum of absolute values = 1.0)"
  - "Division-by-zero guard returns 0.5 (uniform random) when all factors are zero"
  - "Global BranchingStats defaults: branching_factor=1.0, bias_factor=1, bias=5, look_factor=0 (matches old behavior)"

patterns-established:
  - "Individual factor setters instead of combined set_factors(): solver_ctx_set_branching_factor, solver_ctx_set_bias_factor, solver_ctx_set_look_factor"
  - "Weights normalized once at set-time, not per BranchingFunction call (hot-path performance)"
  - "NULL weights pointer means skip branching_weights term entirely (2-term fallback)"

# Metrics
duration: 6min
completed: 2026-02-14
---

# Phase 14 Plan 01: C Kernel Unified Branching Summary

**Replaced dual-array BranchingStats_t with unified branching_weights array and 3-term formula at the C kernel layer**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-14T18:33:25Z
- **Completed:** 2026-02-14T18:39:46Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Restructured BranchingStats_t: removed 4 old fields (objective_factor, constraint_factor, obj_dependent, constraint_dependent), added 3 new fields (branching_weights, num_weights, branching_factor)
- Rewrote BranchingFunction with 3-term formula (or 2-term when weights=NULL), with division-by-zero guard
- Implemented solver_ctx_set_branching_weights() with copy, L1 normalization, and safe overwrite/clear semantics
- All 5 C test targets compile and pass with 5 new test cases (null_weights, 3term, normalization, overwrite, clear)

## Task Commits

Each task was committed atomically:

1. **Task 1: Restructure BranchingStats_t and rewrite BranchingFunction** - `8794c2c` (feat)
2. **Task 2: Update solver_ctx setters and lifecycle functions** - `ffec98f` (feat)
3. **Task 3: Update all C test files for new struct** - `404be56` (test)

## Files Created/Modified
- `cbqs/src/Branching.h` - New BranchingStats_t struct (6 fields) and rewritten BranchingFunction inline
- `cbqs/src/Branching.c` - Updated global defaults, removed 4 old setter functions
- `cbqs/src/solver_ctx.h` - New setter declarations, updated docstrings
- `cbqs/src/solver_ctx.c` - New setters with L1 normalization, updated create/free/debug_stats
- `tests/test_branching.c` - Rewritten for new API with 5 new tests (15 total)
- `tests/test_solver.c` - Updated build_small_model() field names
- `tests/test_integration.c` - Updated reset_branching_stats() field names
- `tests/test_local_search.c` - Updated reset_branching_stats() field names, added update_lock stub
- `tests/test_thread_safety.c` - Updated to use individual factor setters and new field assertions

## Decisions Made
- L1 normalization chosen for branching_weights (sum to 1.0) -- simplest, most intuitive for probability-like values, matches research recommendation
- Division-by-zero guard returns 0.5 (uniform random branching) when all factors are zero -- safe default preventing NaN propagation
- Global BranchingStats defaults (branching_factor=1.0, bias_factor=1, bias=5, look_factor=0) preserve identical behavior when no weights are set

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed pre-existing test_local_search linker error**
- **Found during:** Task 3 (Update all C test files)
- **Issue:** test_local_search.c links against local_search.c which references `extern pthread_mutex_t update_lock` (defined in SearchLib.c), but SearchLib.c is not in the test's CMake dependency list. The test could never link.
- **Fix:** Added `pthread_mutex_t update_lock = PTHREAD_MUTEX_INITIALIZER;` stub in test_local_search.c to satisfy the linker
- **Files modified:** tests/test_local_search.c
- **Verification:** test_local_search builds and passes all 4 tests
- **Committed in:** 404be56 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix was necessary for test_local_search to link. No scope creep.

## Issues Encountered
None beyond the pre-existing linker error documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- C kernel layer is complete: BranchingStats_t, BranchingFunction, and solver_ctx setters all use the new unified model
- Ready for Plan 02: Cython/Python layer updates to wire branching_weights through set_param()
- The Cython-generated .c files (cbqs/branching.c, cbqs/SearchLib.c) still reference old API -- they will be regenerated when the .pyx files are updated in Plan 02

## Self-Check: PASSED

---
*Phase: 14-unified-branching-model*
*Completed: 2026-02-14*
