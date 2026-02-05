# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-04)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** Phase 2 in progress - Critical Correctness Fixes

## Current Position

Phase: 2 of 8 (Critical Correctness Fixes)
Plan: 3 of 6 in current phase
Status: In progress
Last activity: 2026-02-05 - Completed 02-03-PLAN.md

Progress: [████████░░] ~45% (9 plans of ~20 total)

## Performance Metrics

**Velocity:**
- Total plans completed: 9
- Average duration: ~8m
- Total execution time: ~1.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5/5 | ~46m | ~9m |
| 02 | 4/6 | ~30m | ~8m |

**Recent Trend:**
- Last 5 plans: 01-05 (~10m), 02-01 (~8m), 02-02 (~8m), 02-03 (~6m)
- Trend: stable/improving

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Cleanup before features: Stabilize foundation before extending branching/integer UX
- Dynamic expression arrays: Fixed-size wastes memory on small expressions, limits large ones
- Encapsulate global state: BranchingStats as global breaks thread safety in parallel solves
- Explicit per-target source deps in test CMake: SearchLib.c needs Python.h, local_search.c has type errors
- Feasibility-only solve verification: heuristic solver means tests check constraint satisfaction, not optimality
- xfail for Expression mutation bug: Expression.__add__ mutates self and returns self, Phase 2 fix - FIXED in 02-03
- Build expressions term-by-term to avoid multiply_constant pitfall (01-02)
- Setup/teardown fixtures for BranchingStats global reset (01-02)
- Python3 include discovery for SearchLib.c test compilation (01-03)
- cmocka FetchContent URL switched to gitlab.com mirror (01-03)
- free_incumbents uses num_states(0) instead of allocated(1024) -- pre-existing leak (01-03)
- Disable ASan leak detection in CI due to pre-existing preprocessing() leaks (01-05)
- Skip Metal_executor build on Linux -- requires macOS Objective-C runtime (01-05)
- Filter ctest to project tests only, exclude cmocka internal tests (01-05)
- Thread cleanup after pthread_join, not pthread_create (02-01)
- Realloc condition uses == 0 && counter > 0 pattern (02-01)
- copy_expression_contents added for deep copying (02-02)
- Standard operators return new objects, in-place operators mutate self (02-03)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 6: Arena allocator "50-100x speedup" claim needs validation on this codebase
- Phase 6: Incremental constraint evaluation (adjusted_constraint_violation) was commented out for unknown reasons -- investigate git history during planning
- GCC 15 compilation: Most type mismatches fixed, some warnings remain (non-fatal)
- SATISFY mode crashes: run_sampling in SearchLib.pyx calls len() on int when solver == SATISFY
- preprocessing() has memory leak on realloc-to-zero (pre-existing, track for Phase 2) - PARTIALLY ADDRESSED by 02-01 realloc fix

## Session Continuity

Last session: 2026-02-05T10:28:00Z
Stopped at: Completed 02-03-PLAN.md (Expression immutability)
Resume file: None
