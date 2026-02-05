---
phase: 03-solver-context-architecture
plan: 02
subsystem: solver
tags: [solver_ctx, branching, leaf-functions, ctx-migration]

# Dependency graph
requires:
  - phase: 03-01
    provides: solver_ctx_t struct with embedded BranchingStats_t and lifecycle functions
provides:
  - CSearch_* functions with ctx parameter
  - Monte carlo sampler functions with ctx parameter
  - StateProbability and updated() with ctx parameter
  - Deprecated global setters marked for removal
affects: [03-03, 03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ctx-first parameter convention for leaf solver functions"
    - "Forward declaration to avoid circular includes"
    - "Deprecation comments for backward compatibility"

key-files:
  created: []
  modified:
    - cbqs/src/solver.h
    - cbqs/src/solver.c
    - cbqs/src/approximate_state_sampler.h
    - cbqs/src/approximate_state_sampler.c
    - cbqs/src/Branching.h
    - cbqs/src/Branching.c

key-decisions:
  - "Forward declaration in Branching.h to avoid circular include with solver_ctx.h"
  - "Preserve global BranchingStats and setters with DEPRECATED comments for backward compatibility"

patterns-established:
  - "ctx-first: solver_ctx_t *ctx is always first parameter in migrated functions"
  - "ctx->branching_stats: access branching state via context, not global"

# Metrics
duration: 5min
completed: 2026-02-05
---

# Phase 3 Plan 2: Leaf Function Migration Summary

**Migrated 9 leaf-level solver functions to accept solver_ctx_t* and use ctx->branching_stats instead of global BranchingStats**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-05T13:26:44Z
- **Completed:** 2026-02-05T13:31:26Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- All CSearch_* functions (6 total) now take solver_ctx_t *ctx as first parameter
- All BranchingFunction calls in solver.c use &ctx->branching_stats (6 occurrences)
- init_approximete_state and CSearch_opt_sampler migrated in approximate_state_sampler
- StateProbability and updated() in Branching.c now use ctx->branching_stats
- Global setters marked DEPRECATED for backward compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: Update solver.h with ctx parameter in function signatures** - `5617801` (feat)
2. **Task 2: Migrate solver.c functions to use ctx->branching_stats** - `f5ffcd6` (feat)
3. **Task 3: Update approximate_state_sampler and Branching.c leaf functions** - `7d2c74c` (feat)

## Files Created/Modified

- `cbqs/src/solver.h` - Added solver_ctx.h include, ctx parameter to all CSearch_* declarations
- `cbqs/src/solver.c` - Updated function definitions, replaced &BranchingStats with &ctx->branching_stats
- `cbqs/src/approximate_state_sampler.h` - Added solver_ctx.h include, ctx parameter to function signatures
- `cbqs/src/approximate_state_sampler.c` - Updated init_approximete_state and CSearch_opt_sampler to use ctx
- `cbqs/src/Branching.h` - Added forward declaration for solver_ctx_t, updated StateProbability/updated signatures, marked global setters DEPRECATED
- `cbqs/src/Branching.c` - Updated StateProbability and updated() to use ctx->branching_stats

## Decisions Made

- **Forward declaration vs include:** Used `struct solver_ctx; typedef struct solver_ctx solver_ctx_t;` in Branching.h to avoid circular include with solver_ctx.h (Branching.h is included by solver_ctx.h for BranchingStats_t)
- **Backward compatibility:** Preserved global BranchingStats variable and setter functions (set_bias, set_factors, etc.) with DEPRECATED comments, allowing gradual migration

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - migration was straightforward. All identified BranchingFunction calls were in expected locations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Leaf functions are now ctx-aware and ready for callers to be updated
- Plan 03-03 can proceed to migrate mid-level functions (ctg, local_search)
- Plan 03-04 will update entry points (quantum_local_search)
- Plan 03-05 will update Cython bindings

**Note:** Code will not compile until callers are updated to pass ctx to these functions. This is expected and will be resolved in subsequent plans.

---
*Phase: 03-solver-context-architecture*
*Completed: 2026-02-05*
