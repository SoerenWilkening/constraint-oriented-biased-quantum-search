---
phase: 16-global-state-removal
plan: 01
subsystem: kernel
tags: [c, global-state, branching, solver-ctx, dead-code-removal]

# Dependency graph
requires:
  - phase: 14-unified-branching
    provides: "solver_ctx_t with embedded BranchingStats_t and context-aware setters"
provides:
  - "Clean C layer with no global BranchingStats symbol"
  - "GLOB-01 satisfied: no global or file-scope BranchingStats_t variable"
  - "GLOB-02 verified: no deprecated C setter functions"
affects: [16-02-global-state-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: ["All branching state exclusively in solver_ctx_t.branching_stats"]

key-files:
  created: []
  modified:
    - cbqs/src/Branching.h
    - cbqs/src/Branching.c
    - cbqs/src/solver_ctx.h
    - cbqs/src/solver_ctx.c
    - tests/test_solver.c
    - tests/test_local_search.c
    - tests/test_integration.c

key-decisions:
  - "Replace extern declaration and global initializer with comments documenting removal"
  - "Keep #include Branching.h in test files (needed for BranchingStats_t type used by solver_ctx_t)"

patterns-established:
  - "No global mutable state in C kernel: all state in solver_ctx_t"

# Metrics
duration: 3min
completed: 2026-02-14
---

# Phase 16 Plan 01: Global BranchingStats Removal Summary

**Removed dead global BranchingStats variable from C kernel and eliminated all references in 3 test files**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-14T20:45:05Z
- **Completed:** 2026-02-14T20:48:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Removed `extern BranchingStats_t BranchingStats` declaration from Branching.h
- Removed global `BranchingStats_t BranchingStats = {...}` initializer from Branching.c
- Removed `reset_branching_stats()` helper and all calls from test_local_search.c and test_integration.c
- Removed direct `BranchingStats.*` field resets from test_solver.c
- Updated solver_ctx.h/c comments to remove references to "global BranchingStats"
- All 3 C test suites (test_solver, test_local_search, test_integration) compile and pass with zero failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove global BranchingStats from C headers and sources** - `9512553` (feat)
2. **Task 2: Update C test files to remove global BranchingStats references** - `289d5ad` (fix)

## Files Created/Modified
- `cbqs/src/Branching.h` - Removed extern declaration, replaced with removal comment
- `cbqs/src/Branching.c` - Removed global initializer block, replaced with removal comment
- `cbqs/src/solver_ctx.h` - Updated @brief and branching_stats comments
- `cbqs/src/solver_ctx.c` - Updated initialization comment
- `tests/test_solver.c` - Removed 7 lines of BranchingStats field resets in build_small_model()
- `tests/test_local_search.c` - Removed reset_branching_stats() function and 4 call sites
- `tests/test_integration.c` - Removed reset_branching_stats() function and 2 call sites

## Decisions Made
- Replaced removed code with comments documenting the v2.0 removal (aids future code archaeology)
- Kept `#include "Branching.h"` in all test files since they need `BranchingStats_t` type definition (used by `solver_ctx_t`)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GLOB-01 (no global BranchingStats) is now satisfied
- GLOB-02 (no deprecated C setters) was already satisfied, verified during this plan
- Ready for 16-02 (Python/Cython layer global state cleanup)

## Self-Check: PASSED

All 7 modified files verified on disk. Both task commits (9512553, 289d5ad) verified in git log.

---
*Phase: 16-global-state-removal*
*Completed: 2026-02-14*
