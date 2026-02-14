# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v2.0 API Cleanup — BranchingStats, solve() args, unified branching weights

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-02-14 — Milestone v2.0 started

Progress: [v1.0 ########] [v1.1 ##########] [v2.0 ░░░░░░░░░░]

## Performance Metrics

**Cumulative:**
- v1.0: 8 phases, 35 plans
- v1.1: 5 phases, 10 plans
- v2.0: 0 phases, 0 plans (in progress)
- Total: 13 phases, 45 plans

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.

- v2.0: Hard breaking change — remove all solve() kwargs, set_param() only
- v2.0: Merge obj_dependent + constraint_dependent into single unified array
- v2.0: 3-term BranchingFunction (unified_array + assignment_bias + look_ahead)
- v2.0: Array input via set_param('branching_weights', [...])

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-14
Stopped at: Defining v2.0 requirements
Next action: Complete requirements and roadmap
