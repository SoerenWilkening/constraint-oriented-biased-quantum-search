---
phase: 04-thread-isolation
plan: 02
subsystem: core-kernel
tags: [prng, threading, solver-ctx, rand-replacement, dynamic-allocation]

# Dependency graph
requires:
  - phase: 04-01
    provides: xoshiro256** PRNG with thread-local state and jump function
provides:
  - Extended solver_ctx_t with seed, seed_used, num_threads, num_threads_used, master_prng
  - All rand() calls replaced with PRNG (12 calls across 5 files)
  - Dynamic thread allocation in local_search (NUMThreads constant removed)
  - Thread-local PRNG initialization in worker threads
affects: [04-03-cython-integration, 04-04-python-api]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - solver_ctx owns master PRNG for deriving thread states
    - Thread workers call prng_seed_thread() at start
    - Dynamic thread allocation from ctx->num_threads_used

key-files:
  modified:
    - cbqs/src/solver_ctx.h
    - cbqs/src/solver_ctx.c
    - cbqs/src/solver.c
    - cbqs/src/quantum_search.c
    - cbqs/src/SearchLib.c
    - cbqs/src/approximate_state_sampler.c
    - cbqs/src/local_search.h
    - cbqs/src/local_search.c

key-decisions:
  - "Default to 4 threads if sysconf fails and CBQS_THREADS not set"
  - "CBQS_THREADS env var takes priority over CPU auto-detection"
  - "Use existing id field as thread_id for PRNG seeding"
  - "dat_t struct progress array dynamically allocated based on num_threads"

patterns-established:
  - "Pattern: solver_ctx_init_prng() must be called before any PRNG usage"
  - "Pattern: Worker threads initialize PRNG at start via prng_seed_thread(ctx->master_prng, thread_id)"
  - "Pattern: Thread count comes from ctx->num_threads_used after init"

# Metrics
duration: 6min
completed: 2026-02-05
---

# Phase 4 Plan 2: PRNG Integration Summary

**Extended solver_ctx with seed/thread config, replaced 12 rand() calls with xoshiro256** PRNG, converted local_search to dynamic thread allocation**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-02-05T15:12:00Z
- **Completed:** 2026-02-05T15:18:00Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- solver_ctx_t now owns all PRNG and thread configuration state
- All random number generation uses deterministic xoshiro256** PRNG
- NUMThreads compile-time constant eliminated in favor of runtime configuration
- Thread workers properly initialize independent PRNG streams via jump function

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend solver_ctx_t with seed and thread count fields** - `01fa592` (feat)
2. **Task 2: Replace rand() calls in solver.c, quantum_search.c, SearchLib.c, approximate_state_sampler.c** - `e1006cb` (feat)
3. **Task 3: Convert local_search.c to dynamic thread allocation** - `96c54a5` (feat)

## Files Created/Modified
- `cbqs/src/solver_ctx.h` - Added seed, seed_used, num_threads, num_threads_used, master_prng fields and init functions
- `cbqs/src/solver_ctx.c` - Implemented solver_ctx_init_prng() and solver_ctx_get_default_threads()
- `cbqs/src/solver.c` - 6 rand() calls replaced with prng_next_double()
- `cbqs/src/quantum_search.c` - 2 rand() calls replaced (sampling + QSearch)
- `cbqs/src/SearchLib.c` - 1 rand() call replaced with prng_next_int()
- `cbqs/src/approximate_state_sampler.c` - 1 rand() call replaced with prng_next_double()
- `cbqs/src/local_search.h` - Removed NUMThreads macro
- `cbqs/src/local_search.c` - Dynamic thread allocation, thread PRNG init, prng_next_int() for shuffle

## Decisions Made
- Default to 4 threads as fallback when neither CBQS_THREADS nor sysconf succeeds
- CBQS_THREADS environment variable takes priority over CPU auto-detection for explicit control
- Reused existing `id` field in local_search_data_t as thread_id for PRNG seeding (no struct change needed)
- dat_t progress array is now dynamically allocated to match actual thread count

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tasks completed without issues.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- C-level PRNG integration complete
- Ready for Cython wrapper updates (04-03)
- solver_ctx_init_prng() must be called from Cython before solver operations

---
*Phase: 04-thread-isolation*
*Completed: 2026-02-05*
