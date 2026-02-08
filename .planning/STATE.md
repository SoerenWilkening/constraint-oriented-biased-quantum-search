# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v1.1 Bug Fixes & Polish -- Phase 10 (C23 & VLA Fixes)

## Current Position

Phase: 10 of 13 (C23 Migration & VLA Elimination)
Plan: 1 of 2 in current phase
Status: In progress
Last activity: 2026-02-08 -- Completed 10-01-PLAN.md (C23 forward-compatibility)

Progress: [v1.0 ########] [v1.1 ###.......] Plan 1/2 of Phase 10

## Performance Metrics

**Velocity (v1.0 baseline):**
- Total plans completed: 35 (v1.0)
- v1.1 plans completed: 3
- Total execution time: ~3 days (v1.0)

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 9. SATISFY Crash Fixes | 2/2 | 11m 01s | 5m 31s |
| 10. C23 & VLA | 1/2 | 8m 28s | 8m 28s |
| 11. Callback Rework | 0/TBD | - | - |
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

### Pending Todos

None.

### Blockers/Concerns

- GCC 15 warnings partially resolved (bool macros, VLA, empty params, u_int64_t done); format/sign warnings remain (Plan 02)
- Callback rework (Phase 11) has 20% chance of needing deeper research if TSan reveals GIL contention

## Session Continuity

Last session: 2026-02-08
Stopped at: Completed 10-01-PLAN.md (C23 forward-compatibility changes)
Resume file: .planning/phases/10-c23-migration-vla-elimination/10-02-PLAN.md
Next action: /gsd:execute-phase for Phase 10 Plan 02 (strict warning flags)
