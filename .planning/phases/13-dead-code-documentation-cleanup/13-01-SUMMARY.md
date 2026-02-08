---
phase: 13-dead-code-documentation-cleanup
plan: 01
subsystem: c-kernel
tags: [dead-code, cleanup, documentation, field-annotations, printf, mutex]

# Dependency graph
requires:
  - phase: 12-branchingstats-local-search-cleanup
    provides: "Per-context branching_stats, stable C kernel"
provides:
  - "Clean C kernel with no commented-out code or dead functions"
  - "Read/write field annotations on local_search(), ctg(), preprocessing(), initial_state_preparation()"
  - "No unguarded printf calls in production code paths"
affects: [13-02-dead-code-documentation-cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Field annotation comment blocks with Reads/Writes and mutex protection notes"

key-files:
  created: []
  modified:
    - "cbqs/src/local_search.c"
    - "cbqs/src/solver.c"
    - "cbqs/src/constraint.c"
    - "cbqs/src/constraint.h"
    - "cbqs/src/state.c"
    - "cbqs/src/state.h"
    - "cbqs/src/SearchLib.h"
    - "cbqs/src/SearchLib.c"
    - "cbqs/src/Branching.c"
    - "cbqs/src/Branching.h"
    - "cbqs/src/Expression.c"
    - "cbqs/src/quantum_search.c"

key-decisions:
  - "Remove all commented-out code -- it is in git history (nothing sacred rule)"
  - "Remove unguarded progress-bar printfs entirely rather than guarding behind CBQS_DEBUG (UI noise, not diagnostic)"
  - "Keep bfs() function but remove its unguarded printf (not called from Cython but declared in header)"
  - "Keep print_new_constraint, print_expression, print_incumbents diagnostic functions (explicitly called)"
  - "Replace dat_t struct with simple double* allocation after removing print_status/dat_t"

patterns-established:
  - "Field annotation format: /* function_name(params) * Reads: field1, field2 * Writes: field3 (mutex-protected via lock) */"

# Metrics
duration: 28m 31s
completed: 2026-02-08
---

# Phase 13 Plan 01: C Kernel Dead Code Removal & Field Annotations Summary

**Removed ~320 lines of dead code from 12 C files and added read/write field annotations with mutex protection notes to 4 major solver functions**

## Performance

- **Duration:** 28m 31s
- **Started:** 2026-02-08T18:14:38Z
- **Completed:** 2026-02-08T18:43:09Z
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments

- Removed all commented-out code from local_search.c, solver.c, constraint.c, state.c, Branching.c, Expression.c, SearchLib.c, quantum_search.c (~320 lines net reduction)
- Removed unused functions: compare() (state.c/state.h/SearchLib.h), objective_value_improved() (constraint.c/constraint.h), print_status()/dat_t (local_search.c)
- Removed all unguarded progress-bar printf calls from preprocessing(), add_expression_to_constraints(), merge_expression(), initial_state_preparation(), bfs()
- Added read/write field annotation comments to local_search(), ctg(), initial_state_preparation(), preprocessing() with mutex protection notes
- All 304 Python tests pass, 12/12 C tests pass with zero behavioral changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove dead code from core solver C files** - `d125dda` (refactor)
2. **Task 2: Remove dead code from remaining C files** - `98a7d71` (refactor)
3. **Task 3: Add field annotations and run full test suite** - `71022bb` (docs)

## Files Created/Modified

- `cbqs/src/local_search.c` - Removed aspiration(), print_status()/dat_t, VLA code, commented-out printfs; added local_search() annotation
- `cbqs/src/solver.c` - Removed commented-out debug printfs, ChangedTerms code, unguarded progress printf; added initial_state_preparation() annotation
- `cbqs/src/constraint.c` - Removed unguarded progress printfs, objective_value_improved(); added preprocessing() annotation
- `cbqs/src/constraint.h` - Removed objective_value_improved() declaration and commented-out parameter lines
- `cbqs/src/state.c` - Removed compare() function, commented-out calloc/printf/realloc, old updated() function
- `cbqs/src/state.h` - Removed compare() declaration
- `cbqs/src/SearchLib.h` - Removed compare() declaration
- `cbqs/src/SearchLib.c` - Removed unguarded printf from bfs(), commented-out code from ctg(); added ctg() annotation
- `cbqs/src/Branching.c` - Removed entire commented-out old BranchingFunction(), debug printfs
- `cbqs/src/Branching.h` - Removed commented-out alternative formulas, stale TODO
- `cbqs/src/Expression.c` - Removed unguarded progress printfs from merge_expression()
- `cbqs/src/quantum_search.c` - Removed commented-out printf and print loop

## Decisions Made

- **Remove vs guard printfs:** Unguarded progress-bar `printf("\r%f %%")` calls were removed entirely rather than guarded behind CBQS_DEBUG, per research recommendation that they are UI noise not diagnostic data
- **Keep diagnostic print functions:** `print_new_constraint()`, `print_expression()`, `print_incumbents()`, `print_state()` were kept as they are explicitly-called diagnostic functions
- **bfs() kept with printf removed:** The bfs() function is not called from any Cython code but is declared in SearchLib.h; kept the function but removed its unguarded printf
- **dat_t replaced with double*:** After removing print_status()/dat_t, the progress allocation in accept_best_routine was simplified to a raw `double*` calloc

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced dat_t with simple double* allocation**
- **Found during:** Task 1 (local_search.c cleanup)
- **Issue:** Removing print_status() and dat_t struct left accept_best_routine() with references to the removed type
- **Fix:** Replaced `dat_t prog_data` with `double *progress_arr = calloc(num_threads, sizeof(double))` and updated all references
- **Files modified:** cbqs/src/local_search.c
- **Verification:** Build succeeds, all tests pass
- **Committed in:** d125dda (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to maintain compilation after removing the dead dat_t type. No scope creep.

## Issues Encountered

- Virtual environment pointed to non-existent pyenv Python; created new .build_venv for compilation verification
- C test targets test_searchlib and test_local_search could not build in standalone CMake due to missing Python.h include (pre-existing issue, not caused by our changes)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- C kernel is now clean of all dead code and documented with field annotations
- Plan 02 (Cython/Python/build cleanup) can proceed on the same branch
- No blockers or concerns

## Self-Check: PASSED

- All 12 modified files exist on disk
- All 3 task commits verified in git log (d125dda, 98a7d71, 71022bb)
- All 4 field annotation blocks verified (local_search, initial_state_preparation, preprocessing, ctg)

---
*Phase: 13-dead-code-documentation-cleanup*
*Completed: 2026-02-08*
