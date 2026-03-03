---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: Adaptive Branching
status: archived
last_updated: "2026-03-03"
progress:
  total_phases: 28
  completed_phases: 28
  total_plans: 60
  completed_plans: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v3.0 Adaptive Branching archived. Next milestone TBD.

## Current Position

Phase: 28 of 28 (Transfer Learning & Diagnostics)
Plan: 02/02 complete
Status: Milestone archived
Last activity: 2026-03-03 - Completed quick task 4: Extend README with training guide for better biasing weights

Progress: [v1.0 ##########] [v1.1 ##########] [v2.0 ##########] [v2.1 ##########] [v3.0 ##########]

## Performance Metrics

**Cumulative:**
- v1.0: 8 phases, 35 plans
- v1.1: 5 phases, 10 plans
- v2.0: 4 phases, 8 plans
- v2.1: 7 phases, 14 plans
- v3.0: 4 phases, 8 plans
- Total: 28 phases, 75 plans complete

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.

Recent decisions for v3.0:
- Pure-Python cbqs/ml/ subpackage — no C kernel changes needed for ML layer
- sklearn as only new dependency, optional extra via cbqs[ml]
- Multi-round inter-solve adaptation (not intra-solve C-level mutation) for thread safety
- Per-variable prediction model for size-invariant transfer learning
- ExtraTreesRegressor for offline, SGDRegressor for online adaptation
- Expression parsing via _parse_expression_terms() filtering list items from int sense/rhs values
- Per-column z-score normalization with zero-variance columns set to zero (not NaN)
- Model.close(validate=False) needed for testing models without constraints

### Pending Todos

None.

### Blockers/Concerns

None — milestone complete and archived.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Refactor local_search and quantum_local_search to use set_param pattern like solve | 2026-02-14 | 364a2c4 | [1-refactor-local-search-and-quantum-local-](./quick/1-refactor-local-search-and-quantum-local-/) |
| 2 | Fix _SC_NPROCESSORS_ONLN undeclared identifier in solver_ctx.c | 2026-02-14 | deab932 | [2-fix-sc-nprocessors-onln-undeclared-ident](./quick/2-fix-sc-nprocessors-onln-undeclared-ident/) |
| 3 | Update README example code to use set_param() + zero-arg solve() | 2026-02-26 | ae81337 | [3-update-example-code-in-readme-md-fix-out](./quick/3-update-example-code-in-readme-md-fix-out/) |
| 4 | Extend README with ML training guide for branching weight prediction | 2026-03-03 | 66851b4 | [4-extend-readme-with-training-guide-for-be](./quick/4-extend-readme-with-training-guide-for-be/) |

## Session Continuity

Last session: 2026-03-03
Stopped at: Completed quick task 4 (extend README with training guide)
Next action: `/gsd:new-milestone` to start next milestone cycle
