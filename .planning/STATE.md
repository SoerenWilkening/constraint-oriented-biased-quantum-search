# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v1.1 Bug Fixes & Polish -- Phase 12 (BranchingStats)

## Current Position

Phase: 12 of 13 (BranchingStats & Local Search Cleanup) -- IN PROGRESS
Plan: 1 of 2 in current phase
Status: Plan 12-01 complete, Plan 12-02 pending
Last activity: 2026-02-08 -- Completed 12-01-PLAN.md (branching param API + mutex protection)

Progress: [v1.0 ########] [v1.1 ########..] Phase 12 in progress (1/2 plans)

## Performance Metrics

**Velocity (v1.0 baseline):**
- Total plans completed: 35 (v1.0)
- v1.1 plans completed: 7
- Total execution time: ~3 days (v1.0)

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 9. SATISFY Crash Fixes | 2/2 | 11m 01s | 5m 31s |
| 10. C23 & VLA | 2/2 | 45m 28s | 22m 44s |
| 11. Callback Rework | 2/2 | 12m 13s | 6m 07s |
| 12. BranchingStats | 1/2 | 9m 01s | 9m 01s |
| 13. Dead Code Cleanup | 0/TBD | - | - |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.
- v1.1 constraint: No breaking changes (keep deprecated APIs working)
- Module-level cdef callback to be replaced with threading.get_ident()-keyed dict
- VLA replacement uses arena allocation (matching v1.0 pattern)
- objective_value returns None (not 0) in SATISFY mode
- History callback records one entry in SATISFY mode (first callback only)
- SATISFY feasibility: use tot_profit == -num_constraints (not global_opt.feasible C flag)
- CBQS_THREAD_LOCAL macro: MSVC->__declspec(thread), GCC/Clang->__thread, fallback->_Thread_local
- CBQS_UNUSED macro: GCC/Clang->__attribute__((unused)), other->empty
- Replaced _GNU_SOURCE with _POSIX_C_SOURCE 199309L in solver_ctx.c (u_int64_t removed)
- WERROR OFF by default, ON in CI only (local builds not broken by new warnings)
- Sign comparison fixes use variable type changes, not casts
- PRId64 from inttypes.h for portable int64_t formatting instead of %lld
- c-tests-tsan left without -DWERROR (Clang-specific warning profile)
- Per-thread state dict keyed by threading.get_ident() for callback isolation
- track_history defaults to True for backward compatibility
- SATISFY mode history records satisfaction count (num_constraints + tot_profit)
- Shared solve_start_time computed before Parallel() for consistent elapsed times
- Concurrent tests build fresh Model per thread (copy() doesn't preserve variable count)
- History tests validate structure not count (solver may find optimal in greedy pass)
- set_param/get_param validates against _KNOWN_PARAMS set, raises ValueError for unknowns
- _params values take precedence over solve() kwargs over defaults for branching config
- Deprecated branching setters remain functional but emit DeprecationWarning
- pthread_mutex_trylock for non-blocking global_opt protection (contended lock skips update)

### Pending Todos

None.

### Blockers/Concerns

- GCC 15 warnings: FULLY RESOLVED (all format/sign comparison warnings fixed in Plan 02)
- Callback rework (Phase 11): FULLY RESOLVED -- all concurrency tests pass, no GIL contention issues

## Session Continuity

Last session: 2026-02-08
Stopped at: Completed 12-01-PLAN.md (branching param API + mutex protection)
Resume file: .planning/phases/12-branchingstats-local-search-cleanup/12-01-SUMMARY.md
Next action: Execute 12-02-PLAN.md (branching stats test suite)
