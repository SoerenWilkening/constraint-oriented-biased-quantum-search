---
phase: 03-solver-context-architecture
plan: 04
subsystem: api
tags: [cython, solver-ctx, lifecycle-management, try-finally, thread-safety]

# Dependency graph
requires:
  - phase: 03-02
    provides: "Leaf functions migrated to use ctx parameter"
  - phase: 03-03
    provides: "Entry points (ctg, local_search) migrated to use ctx"
provides:
  - "Cython wrappers with ctx lifecycle management"
  - "Python-facing entry points managing ctx create/use/free"
  - "C tests using ctx pattern instead of global BranchingStats"
  - "solver_ctx.c added to setup.py build"
affects: [03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "try/finally pattern for ctx cleanup in Cython"
    - "cdef method for C-level ctx sharing"
    - "cmocka **state for ctx fixture pattern"

key-files:
  created: []
  modified:
    - "cbqs/SearchLib.pxd"
    - "cbqs/SearchLib.pyx"
    - "cbqs/branching.pxd"
    - "cbqs/state.pxd"
    - "cbqs/state.pyx"
    - "cbqs/state_sampler.pxd"
    - "cbqs/state_sampler.pyx"
    - "cbqs/src/solver_ctx.h"
    - "cbqs/src/state.h"
    - "setup.py"
    - "tests/test_branching.c"

key-decisions:
  - "Named struct 'solver_ctx' in solver_ctx.h to match forward declaration in Branching.h"
  - "cdef method _set_ctx() for sharing ctx with incumbents class (avoiding Python object conversion)"
  - "approximate_state class owns its ctx (created in __cinit__, freed in __del__)"
  - "state.pyx update() creates temporary ctx for single call"
  - "branching.pyx unchanged - uses deprecated global setters for backward compatibility"

patterns-established:
  - "try/finally in Cython for ctx cleanup: solver_ctx_create() at start, solver_ctx_free() in finally"
  - "cmocka setup allocates ctx, stores in **state; teardown frees from **state"

# Metrics
duration: 24min
completed: 2026-02-05
---

# Phase 03 Plan 04: Cython Bindings Update Summary

**Cython layer manages solver_ctx lifecycle with try/finally cleanup and C tests use ctx fixtures**

## Performance

- **Duration:** 24 min
- **Started:** 2026-02-05T13:39:05Z
- **Completed:** 2026-02-05T14:03:11Z
- **Tasks:** 3 (Task 2 verified only, no code changes)
- **Files modified:** 11

## Accomplishments
- run_sampling() creates ctx, configures it, passes to ctg(), frees in finally block
- run_local_search() creates ctx, passes to local_search(), frees in finally block
- incumbents.estimate_grover_iterations() uses ctx for monte carlo sampler calls
- state.update() creates temporary ctx for updated() call
- state_sampler.approximate_state owns ctx for its lifetime
- C tests use ctx-based setup/teardown fixture pattern
- solver_ctx.c added to setup.py sources for proper linking

## Task Commits

Each task was committed atomically:

1. **Task 1: Update SearchLib.pyx with ctx lifecycle management** - `79adc96` (feat)
2. **Task 2: Update branching.pyx if needed** - No commit (verified works as-is)
3. **Task 3: Update C tests to use ctx instead of global** - `31f9a1d` (test)

## Files Created/Modified
- `cbqs/SearchLib.pxd` - Added solver_ctx extern declarations, updated function signatures
- `cbqs/SearchLib.pyx` - Implemented ctx lifecycle in run_sampling/run_local_search
- `cbqs/branching.pxd` - Added solver_ctx forward declaration for StateProbability
- `cbqs/state.pxd` - Added solver_ctx extern declarations and updated() signature
- `cbqs/state.pyx` - Added ctx to update() method
- `cbqs/state_sampler.pxd` - Added ctx to class and updated C function signatures
- `cbqs/state_sampler.pyx` - approximate_state creates/owns ctx
- `cbqs/src/solver_ctx.h` - Changed anonymous struct to named struct 'solver_ctx'
- `cbqs/src/state.h` - Removed duplicate updated() declaration (now in Branching.h)
- `setup.py` - Added solver_ctx.c to sources list
- `tests/test_branching.c` - Converted to ctx-based fixtures and assertions

## Decisions Made
- **Named struct solver_ctx:** The forward declaration in Branching.h uses `struct solver_ctx`, so solver_ctx.h must define a named struct, not anonymous
- **cdef _set_ctx() method:** Python methods can't receive C pointers directly, so using cdef method callable from Cython
- **Temporary ctx in state.update():** Creates and immediately frees ctx since updated() is a one-off call
- **approximate_state owns ctx:** The class lifetime matches ctx needs, so ctx created in __cinit__ and freed in __del__
- **branching.pyx unchanged:** Uses deprecated global setters which still work for backward compatibility

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed solver_ctx_t type conflict**
- **Found during:** Task 1 (Cython compilation)
- **Issue:** solver_ctx.h used anonymous struct, but Branching.h forward-declared `struct solver_ctx`
- **Fix:** Changed to named struct `struct solver_ctx { ... }; typedef struct solver_ctx solver_ctx_t;`
- **Files modified:** cbqs/src/solver_ctx.h
- **Verification:** Build succeeds
- **Committed in:** 79adc96

**2. [Rule 3 - Blocking] Removed duplicate updated() declaration**
- **Found during:** Task 1 (Cython compilation)
- **Issue:** updated() declared in both state.h (old signature) and Branching.h (with ctx)
- **Fix:** Removed from state.h, kept in Branching.h
- **Files modified:** cbqs/src/state.h
- **Verification:** Build succeeds
- **Committed in:** 79adc96

**3. [Rule 3 - Blocking] Added solver_ctx.c to setup.py**
- **Found during:** Task 1 (Python import)
- **Issue:** undefined symbol: solver_ctx_request_stop on import
- **Fix:** Added cbqs/src/solver_ctx.c to sources list in setup.py
- **Files modified:** setup.py
- **Verification:** Import succeeds
- **Committed in:** 79adc96

**4. [Rule 3 - Blocking] Updated state_sampler for ctx API**
- **Found during:** Task 1 (Cython compilation)
- **Issue:** init_approximete_state() and CSearch_opt_sampler() now require ctx
- **Fix:** Updated state_sampler.pxd/pyx to create and use ctx
- **Files modified:** cbqs/state_sampler.pxd, cbqs/state_sampler.pyx
- **Verification:** Build succeeds
- **Committed in:** 79adc96

**5. [Rule 3 - Blocking] Updated state.pyx for updated() ctx**
- **Found during:** Task 1 (Cython compilation)
- **Issue:** updated() now requires ctx parameter
- **Fix:** Added solver_ctx_create/free calls in state.update() method
- **Files modified:** cbqs/state.pxd, cbqs/state.pyx
- **Verification:** Build succeeds
- **Committed in:** 79adc96

---

**Total deviations:** 5 auto-fixed (all blocking)
**Impact on plan:** All fixes necessary to complete ctx migration - the plan assumed only SearchLib.pyx needed updates, but ctx propagation affected more files.

## Issues Encountered
- Network unavailable during test execution - cmocka couldn't be fetched via FetchContent
- C test syntax verified through code review and pattern matching with existing tests
- All Cython extensions compile and import successfully

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All Cython entry points manage ctx lifecycle with try/finally
- C tests use ctx fixtures for clean test isolation
- Ready for Plan 05: Thread Safety Verification (concurrent ctx usage tests)
- Minor concern: C tests couldn't run due to network issues - should verify in CI

---
*Phase: 03-solver-context-architecture*
*Completed: 2026-02-05*
