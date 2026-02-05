---
phase: 03-solver-context-architecture
plan: 03
subsystem: solver
tags: [solver_ctx, entry-points, ctg, local_search, stop-flag, signal-handler]

# Dependency graph
requires:
  - phase: 03-01
    provides: solver_ctx_t struct with lifecycle and stop signal API
  - phase: 03-02
    provides: CSearch_* functions with ctx parameter
provides:
  - ctg() with ctx parameter for signal-safe stop checking
  - local_search() with ctx parameter for thread-cooperative stopping
  - g_active_ctx pattern for signal handler interop
  - Global stop_flag replaced by ctx->stop atomic boolean
affects: [03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "g_active_ctx static global for signal handler access to ctx"
    - "Periodic stop check via bitmask (rounds & 255)"
    - "Thread data struct carries ctx pointer for worker threads"

key-files:
  created: []
  modified:
    - cbqs/src/SearchLib.h
    - cbqs/src/SearchLib.c
    - cbqs/src/local_search.h
    - cbqs/src/local_search.c

key-decisions:
  - "g_active_ctx pattern: static global pointer for signal handler to access ctx"
  - "Periodic stop check every 256 iterations using bitmask for low overhead"
  - "Thread workers access ctx via local_search_data_t.ctx field"
  - "NULL-safe stop checks in local_search for backward compatibility"

patterns-established:
  - "Signal handler pattern: g_active_ctx set on entry, cleared on exit"
  - "Thread data pattern: ctx pointer in thread-local data struct"
  - "Stop check pattern: if ((i & 255) == 0 && solver_ctx_should_stop(ctx)) break;"

# Metrics
duration: 3min
completed: 2026-02-05
---

# Phase 3 Plan 3: Entry Point Migration Summary

**Migrated ctg() and local_search() entry points to accept solver_ctx_t* and replaced global stop_flag with atomic ctx->stop**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-05T13:33:39Z
- **Completed:** 2026-02-05T13:36:33Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- ctg() now takes solver_ctx_t *ctx as first parameter
- local_search() now takes solver_ctx_t *ctx as first parameter
- Removed global stop_flag variable from SearchLib.c
- Removed reset_flag() declaration (replaced by solver_ctx_request_stop)
- Signal handler now uses g_active_ctx pattern to request stop via ctx
- All stop flag checks now use solver_ctx_should_stop(ctx)
- ctg() passes ctx to CSearch_* via updated function pointer type
- local_search_data_t struct now has ctx field for thread workers
- explore_neighbourhood checks stop flag every 256 moves

## Task Commits

Each task was committed atomically:

1. **Task 1: Update SearchLib.h/c with ctx parameter and atomic stop** - `6d4f0ab` (feat)
2. **Task 2: Update local_search.h/c with ctx parameter** - `01e9ae1` (feat)

## Files Created/Modified

- `cbqs/src/SearchLib.h` - Added solver_ctx.h include, updated ctg signature, removed reset_flag declaration
- `cbqs/src/SearchLib.c` - Replaced global stop_flag with g_active_ctx pattern, updated ctg() to use ctx, updated function pointer type to include ctx
- `cbqs/src/local_search.h` - Added solver_ctx.h include, added ctx to local_search_data_t struct, updated local_search signature
- `cbqs/src/local_search.c` - Added ctx parameter to local_search and accept_best_routine, periodic stop checks in loops and worker threads

## Decisions Made

- **Signal handler pattern:** Used static `g_active_ctx` pointer since signal handlers cannot receive user data. Set on entry to ctg(), cleared on exit. The handler calls `solver_ctx_request_stop(g_active_ctx)`.
- **Periodic stop checks:** Used bitmask pattern `(rounds & 255) == 0` for low-overhead periodic checking every 256 iterations.
- **Thread worker access:** Added `ctx` field to `local_search_data_t` struct so worker threads can access the solver context for cooperative stopping.
- **NULL-safe checks:** Added `ctx != NULL` guards in local_search for backward compatibility during migration.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - migration was straightforward. All identified entry points and function pointers were in expected locations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Entry points (ctg, local_search) are now ctx-aware
- Plan 03-04 can proceed to update quantum_local_search if needed
- Plan 03-05 will update Cython bindings to create/pass ctx
- All C-level infrastructure for ctx parameter passing is now complete

**Note:** Code will not compile until Cython bindings are updated to create and pass ctx. This is expected and will be resolved in Plan 03-05.

---
*Phase: 03-solver-context-architecture*
*Completed: 2026-02-05*
