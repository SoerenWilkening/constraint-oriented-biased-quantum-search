# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v2.0 API Cleanup — Phase 16: Global State Removal

## Current Position

Phase: 16 of 17 (Global State Removal)
Plan: 1 of 2 complete
Status: Executing
Last activity: 2026-02-14 — Plan 16-01 complete (C layer global BranchingStats removal)

Progress: [v1.0 ########] [v1.1 ##########] [v2.0 #######░░░]

## Performance Metrics

**Cumulative:**
- v1.0: 8 phases, 35 plans
- v1.1: 5 phases, 10 plans
- v2.0: 3 phases, 6 plans
- Total: 16 phases, 51 plans

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 14-01 | C kernel unified branching | 6min | 3 | 9 |
| 14-02 | Cython/Python unified branching | 12min | 3 | 8 |
| 15-01 | Param infrastructure (_PARAM_DEFS) | 5min | 2 | 2 |
| 15-02 | Zero-arg solve, test migration | 11min | 2 | 13 |
| 16-01 | C layer global BranchingStats removal | 3min | 2 | 7 |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.

- v2.0: Hard breaking change — remove all solve() kwargs, set_param() only
- v2.0: Merge obj_dependent + constraint_dependent into single unified array
- v2.0: 3-term BranchingFunction (unified_array + assignment_bias + look_ahead)
- v2.0: Array input via set_param('branching_weights', [...])
- v2.0 14-01: L1 normalization for branching_weights (sum to 1.0)
- v2.0 14-01: Division-by-zero guard returns 0.5 (uniform random) when all factors are zero
- v2.0 14-01: Individual factor setters replace combined set_factors()
- v2.0 14-02: Old _KNOWN_PARAMS (manual_bias, manual_bias_factor, branching_factors) removed immediately
- v2.0 14-02: branching_weights length validation deferred when n=0
- v2.0 14-02: Factor setters only propagated when explicitly set via set_param
- v2.0 15-01: _PARAM_DEFS registry replaces flat _KNOWN_PARAMS set
- v2.0 15-01: Strict bool coercion via _coerce_bool (bool/int only, no strings)
- v2.0 15-01: get_param returns documented defaults for unset params (never None for params with defaults)
- v2.0 15-01: bias and manual_bias excluded from _PARAM_DEFS (raise ValueError as unknown)
- v2.0 15-01: monte_carlo_estimate is canonical name (typo monte_calor_estimate rejected)
- v2.0 15-02: bias parameter completely removed from solve() (branching_bias via close() is the replacement)
- v2.0 15-02: solve() is zero-arg, reads all 14 params from _params via _get_effective()
- v2.0 15-02: Float stopping_time values in tests changed to int to match set_param coercion
- v2.0 15-02: Benchmark assertions updated from list to OptimizeResult
- v2.0 16-01: Global BranchingStats removed from C layer; all state in solver_ctx_t
- v2.0 16-01: Removal comments left in Branching.h/c for code archaeology

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-14
Stopped at: Completed 16-01-PLAN.md (C layer global BranchingStats removal)
Next action: Execute 16-02-PLAN.md (Python/Cython global state cleanup)
