---
phase: 05-memory-safety
plan: 03
subsystem: kernel
tags: [vla, heap-allocation, memory-safety, malloc, free, solver]

# Dependency graph
requires:
  - phase: 05-01
    provides: "Preprocessing leak fixes, Valgrind suppressions"
provides:
  - "VLA-free solver.c with heap-allocated constraint arrays"
  - "VLA-free SearchLib.c and approximate_state_sampler.c"
  - "Proper cleanup on all function exit paths"
affects: [05-04, 05-05, 06-performance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Heap allocation pattern for constraint-sized arrays"
    - "NULL check after malloc with early return on failure"
    - "Free buffers before all return statements"

key-files:
  created: []
  modified:
    - cbqs/src/solver.c
    - cbqs/src/SearchLib.c
    - cbqs/src/approximate_state_sampler.c

key-decisions:
  - "Return 0 on allocation failure in search functions (treated as no improvement found)"
  - "Return -1 on allocation failure in CSearch_opt_sampler"
  - "Use size_t C variable for constraint count consistency"

patterns-established:
  - "VLA replacement pattern: declare pointer, malloc, NULL check, use, free before returns"
  - "Use size_t C = con->num_constraints for consistency across all functions"

# Metrics
duration: 30min
completed: 2026-02-05
---

# Phase 5 Plan 03: VLA Elimination in Solver Functions Summary

**Replaced all VLAs in solver.c, SearchLib.c, and approximate_state_sampler.c with heap-allocated arrays, adding proper NULL checks and cleanup on all exit paths**

## Performance

- **Duration:** 30 min
- **Started:** 2026-02-05T17:26:50Z
- **Completed:** 2026-02-05T17:56:58Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Eliminated 24 VLAs across 9 functions in solver.c
- Eliminated 1 VLA in SearchLib.c (bfs function)
- Eliminated 3 VLAs in approximate_state_sampler.c (CSearch_opt_sampler function)
- Added proper allocation failure handling with early returns
- Ensured cleanup (free) on all function exit paths including early returns

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace VLAs in solver.c** - `978f5c1` (feat)
2. **Task 2: Replace VLAs in SearchLib.c and approximate_state_sampler.c** - `d70c89a` (feat)

## Files Created/Modified
- `cbqs/src/solver.c` - 8 functions converted: initial_state_preparation, CSearch_opt, CSearch_opt_sat, CSearch_sat, CSearch_opt_monte_carlo_sampler, CSearch_opt_sat_monte_carlo_sampler, CSearch_sat_monte_carlo_sampler
- `cbqs/src/SearchLib.c` - bfs() function converted
- `cbqs/src/approximate_state_sampler.c` - CSearch_opt_sampler() function converted

## Decisions Made
- Use `size_t C = con->num_constraints` local variable for cleaner code
- Return 0 on allocation failure in search functions (semantically means "no improvement found")
- Return -1 on allocation failure in CSearch_opt_sampler (distinguishes from 0 which is valid return)
- Free all three buffers (potentials, ret_total1, ret_total2) even if only one is NULL (safe with free(NULL))

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Build directory caching caused module import issues after edits; resolved by running `python3 setup.py build_ext --inplace` directly instead of pip editable install
- CMake test configuration failed due to network/environment issues; verified functionality through Python API tests instead

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- solver.c, SearchLib.c, and approximate_state_sampler.c are now VLA-free
- Ready for 05-04 (local_search.c VLA elimination) and 05-05 (Cython layer audit)
- All existing Python tests pass (18/18)
- Note: local_search.c still contains VLAs (int64_t totals[C], int64_t remainings[C], int bits[d]) - those are for Plan 05-04

---
*Phase: 05-memory-safety*
*Completed: 2026-02-05*
