# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-04)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** Phase 1 - Test Foundation

## Current Position

Phase: 1 of 8 (Test Foundation)
Plan: 2 of 5 in current phase
Status: In progress
Last activity: 2026-02-04 - Completed 01-02-PLAN.md

Progress: [███░░░░░░░] ~15% (3 plans of ~20 total)

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~9m
- Total execution time: ~0.45 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3/5 | ~27m | ~9m |

**Recent Trend:**
- Last 5 plans: 01-01 (~11m), 01-04 (10m), 01-02 (~6m)
- Trend: improving

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
- xfail for Expression mutation bug: Expression.__add__ mutates self and returns self, Phase 2 fix
- Build expressions term-by-term to avoid multiply_constant pitfall (01-02)
- Setup/teardown fixtures for BranchingStats global reset (01-02)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 6: Arena allocator "50-100x speedup" claim needs validation on this codebase
- Phase 6: Incremental constraint evaluation (adjusted_constraint_violation) was commented out for unknown reasons -- investigate git history during planning
- GCC 15 compilation: C sources have pointer type mismatches and callback signature bugs requiring -Wno-error flags
- SATISFY mode crashes: run_sampling in SearchLib.pyx calls len() on int when solver == SATISFY
- Metal_executor extension cannot build on Linux (macOS-only -ObjC flag)
- preprocessing() has memory leak on realloc-to-zero (pre-existing, track for Phase 2)

## Session Continuity

Last session: 2026-02-04T23:28:37Z
Stopped at: Completed 01-02-PLAN.md (Priority 2 C unit tests)
Resume file: None
