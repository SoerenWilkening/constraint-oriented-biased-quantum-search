# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v1.1 Bug Fixes & Polish -- Phase 11 (Callback Rework)

## Current Position

Phase: 11 of 13 (Callback Concurrency Rework)
Plan: 1 of 2 in current phase
Status: Plan 01 complete
Last activity: 2026-02-08 -- Completed 11-01-PLAN.md (thread-safe callback state)

Progress: [v1.0 ########] [v1.1 ######....] Phase 11 in progress (1/2 plans)

## Performance Metrics

**Velocity (v1.0 baseline):**
- Total plans completed: 35 (v1.0)
- v1.1 plans completed: 5
- Total execution time: ~3 days (v1.0)

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 9. SATISFY Crash Fixes | 2/2 | 11m 01s | 5m 31s |
| 10. C23 & VLA | 2/2 | 45m 28s | 22m 44s |
| 11. Callback Rework | 1/2 | 6m 13s | 6m 13s |
| 12. BranchingStats | 0/TBD | - | - |
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

### Pending Todos

None.

### Blockers/Concerns

- GCC 15 warnings: FULLY RESOLVED (all format/sign comparison warnings fixed in Plan 02)
- Callback rework (Phase 11) has 20% chance of needing deeper research if TSan reveals GIL contention

## Session Continuity

Last session: 2026-02-08
Stopped at: Completed 11-01-PLAN.md (thread-safe callback state)
Resume file: .planning/phases/11-callback-concurrency-rework/11-01-SUMMARY.md
Next action: /gsd:execute-phase for Phase 11, Plan 02 (concurrency tests)
