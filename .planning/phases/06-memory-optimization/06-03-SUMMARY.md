---
phase: 06-memory-optimization
plan: 03
subsystem: infra
tags: [arena, allocator, hot-path, solver, performance]

# Dependency graph
requires:
  - phase: 06-01
    provides: arena allocator implementation (arena.c, arena.h)
provides:
  - solver_ctx owns arena for hot-path allocations
  - explore_neighbourhood uses arena_alloc (zero malloc/free per move)
  - arena reset between solver iterations
affects: [06-04, performance testing, memory benchmarks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Arena integration with solver context lifecycle
    - Conditional fallback (arena or malloc) for backward compatibility
    - Arena reset between iterations for bounded memory growth

key-files:
  modified:
    - cbqs/src/solver_ctx.h
    - cbqs/src/solver_ctx.c
    - cbqs/src/local_search.c
    - tests/test_local_search.c
    - tests/CMakeLists.txt

key-decisions:
  - "Arena owned by solver_ctx_t, created at ctx creation, freed at ctx destruction"
  - "Fallback to malloc/calloc when ctx or arena is NULL (backward compatibility)"
  - "Arena reset after pthread_join in accept_best_routine (between iterations)"
  - "sw_init_arena helper for arena-based array_t allocation"
  - "Alignment 8 for part_length_t, 4 for int arrays"

patterns-established:
  - "Hot-path arena pattern: arena_alloc in inner loop, arena_reset after batch"
  - "Conditional allocation: use_arena flag for arena vs malloc fallback"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 6 Plan 3: Solver Context Arena Integration Summary

**Arena integrated into solver_ctx_t eliminating malloc/calloc/free calls in explore_neighbourhood hot-path**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T19:24:14Z
- **Completed:** 2026-02-05T19:28:23Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Extended solver_ctx_t with arena field and lifecycle management
- Replaced 3 hot-path allocations (inv, changed_con, changes) with arena_alloc
- Added arena reset between solver iterations for bounded memory
- Added 2 new tests for arena integration, verified with Valgrind

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend solver_ctx with arena** - `374506e` (feat)
2. **Task 2: Replace hot-path allocations with arena** - `f651ed5` (feat)
3. **Task 3: Update tests for arena integration** - `4a26313` (test)

## Files Created/Modified
- `cbqs/src/solver_ctx.h` - Added arena_t *arena field and solver_ctx_arena_reset() declaration
- `cbqs/src/solver_ctx.c` - Arena create/free in lifecycle, solver_ctx_arena_reset() implementation
- `cbqs/src/local_search.c` - sw_init_arena helper, arena_alloc for hot-path, conditional fallback
- `tests/test_local_search.c` - test_local_search_with_arena and test_local_search_arena_reset tests
- `tests/CMakeLists.txt` - Added arena.c to test_local_search target

## Decisions Made
- Arena owned by solver_ctx_t for clear lifecycle management
- Conditional allocation pattern: `use_arena = (dat->ctx != NULL && dat->ctx->arena != NULL)`
- Fallback to malloc/calloc ensures backward compatibility with NULL context
- Arena reset placed after pthread_join loop in accept_best_routine
- Alignment 8 for part_length_t (64-bit), 4 for int arrays

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - implementation followed plan directly. Pre-existing compiler warnings in local_search.c are unrelated to arena changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Arena integration complete for explore_neighbourhood hot-path
- Ready for 06-04: Constraint evaluation arena integration (if planned)
- Memory benchmarks can now compare arena vs malloc performance
- Valgrind confirms no memory leaks with arena integration

---
*Phase: 06-memory-optimization*
*Completed: 2026-02-05*
