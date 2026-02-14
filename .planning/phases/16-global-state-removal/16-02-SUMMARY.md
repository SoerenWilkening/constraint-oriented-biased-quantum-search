---
phase: 16-global-state-removal
plan: 02
subsystem: cython-api
tags: [cython, python, branching, global-state, module-deletion, build-system]

# Dependency graph
requires:
  - phase: 16-01-global-state-removal
    provides: "Clean C layer with no global BranchingStats symbol"
  - phase: 14-unified-branching
    provides: "solver_ctx_t with context-aware branching"
provides:
  - "GLOB-03 satisfied: branching.pyx deleted"
  - "GLOB-04 satisfied: no .pxd declarations for removed C functions"
  - "Clean Cython/Python layer with no branching module"
  - "set_seed removed from public API (breaking change for v2.0)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["Direct libc.stdlib srand() instead of branching.set_seed() wrapper", "StateProbability declared via extern from Branching.h in SearchLib.pxd"]

key-files:
  created: []
  modified:
    - cbqs/SearchLib.pxd
    - cbqs/SearchLib.pyx
    - cbqs/Model.pyx
    - cbqs/__init__.py
    - setup.py
  deleted:
    - cbqs/branching.pyx
    - cbqs/branching.pxd

key-decisions:
  - "StateProbability relocated to SearchLib.pxd via direct extern from Branching.h"
  - "srand() called directly from libc.stdlib instead of through branching.set_seed() wrapper"
  - "set_seed removed from cbqs public API (v2.0 breaking change)"

patterns-established:
  - "No Cython wrapper modules for trivial libc functions: use cimport directly"

# Metrics
duration: 5min
completed: 2026-02-14
---

# Phase 16 Plan 02: Branching Module Deletion Summary

**Deleted branching.pyx/pxd module, replaced set_seed with direct srand(), relocated StateProbability declaration to SearchLib.pxd**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-14T20:49:48Z
- **Completed:** 2026-02-14T20:54:19Z
- **Tasks:** 2
- **Files modified:** 7 (5 modified, 2 deleted)

## Accomplishments
- Removed all `from .branching import set_seed` references from SearchLib.pyx, Model.pyx
- Replaced `set_seed()` calls with direct `srand()` calls via `from libc.stdlib cimport srand`
- Relocated `StateProbability` declaration from branching.pxd to SearchLib.pxd (extern from Branching.h)
- Removed `set_seed` from `cbqs/__init__.py` public API
- Deleted `cbqs/branching.pyx` and `cbqs/branching.pxd`
- Removed `cbqs.branching` Extension from setup.py
- Package builds cleanly, all 383 Python tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Update Cython callers and declarations** - `1a365b2` (feat)
2. **Task 2: Delete branching module and update build system** - `c92ced5` (feat)

## Files Created/Modified
- `cbqs/SearchLib.pxd` - Replaced branching cimport with direct extern from Branching.h for StateProbability
- `cbqs/SearchLib.pyx` - Replaced `from .branching import set_seed` with `from libc.stdlib cimport srand`, changed set_seed() to srand()
- `cbqs/Model.pyx` - Replaced `from .branching import set_seed` with `from libc.stdlib cimport srand`, changed set_seed() to srand()
- `cbqs/__init__.py` - Removed set_seed from import and except block
- `setup.py` - Removed cbqs.branching Extension entry
- `cbqs/branching.pyx` - DELETED (GLOB-03)
- `cbqs/branching.pxd` - DELETED (GLOB-04)

## Decisions Made
- StateProbability relocated to SearchLib.pxd via `cdef extern from "src/Branching.h"` block -- this is the only consumer and avoids a new intermediate .pxd file
- Direct `srand()` from libc.stdlib replaces the thin `set_seed()` wrapper -- no functional change, eliminates unnecessary module
- set_seed removed from public API entirely -- solver context manages PRNG via `solver_ctx_init_prng()`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 GLOB objectives satisfied (GLOB-01 through GLOB-04)
- Phase 16 (Global State Removal) is now complete
- No blockers for subsequent phases

## Self-Check: PASSED

All 5 modified files verified on disk. Both deleted files (branching.pyx, branching.pxd) confirmed absent. Both task commits (1a365b2, c92ced5) verified in git log.

---
*Phase: 16-global-state-removal*
*Completed: 2026-02-14*
