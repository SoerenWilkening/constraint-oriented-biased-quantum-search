---
phase: 12-branchingstats-local-search-cleanup
plan: 01
subsystem: api, solver
tags: [branching, set_param, deprecation, mutex, pthread, solver_ctx]

# Dependency graph
requires:
  - phase: 11-callback-concurrency-rework
    provides: solver_ctx_t per-solve context, thread-safe callback infrastructure
provides:
  - set_param/get_param generic parameter API on Model
  - Branching parameter propagation from _params to solver_ctx_t in run_sampling and run_local_search
  - DeprecationWarning on legacy branching setters
  - Mutex-protected global_opt writes in accept_best_routine
affects: [12-02 (branching stats test suite)]

# Tech tracking
tech-stack:
  added: []
  patterns: [set_param/get_param with _KNOWN_PARAMS validation, _params precedence over kwargs]

key-files:
  created: []
  modified:
    - cbqs/Model.pyx
    - cbqs/Model.pxd
    - cbqs/SearchLib.pyx
    - cbqs/branching.pyx
    - cbqs/src/local_search.c

key-decisions:
  - "set_param/get_param validates against _KNOWN_PARAMS set, raises ValueError for unknowns"
  - "_params values take precedence over solve() kwargs which take precedence over defaults"
  - "Deprecated setters remain functional (no breaking changes) but emit DeprecationWarning"
  - "pthread_mutex_trylock used for non-blocking mutex; contended lock skips global_opt update"
  - "exact_benchmark uses _params.setdefault instead of deprecated set_bias_wrapper"

patterns-established:
  - "Parameter precedence: _params > kwargs > defaults for branching configuration"
  - "DeprecationWarning with stacklevel=2 for all legacy branching setters"

# Metrics
duration: 9min
completed: 2026-02-08
---

# Phase 12 Plan 01: Branching Param API, Deprecation Warnings, and Mutex Protection Summary

**set_param/get_param API with strict validation, branching parameter propagation to solver_ctx_t, DeprecationWarning on legacy setters, and pthread_mutex_trylock for global_opt writes**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-08T17:15:19Z
- **Completed:** 2026-02-08T17:24:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added set_param/get_param API with strict validation against known parameter names
- Branching parameters from _params propagate to solver_ctx_t in both run_sampling and run_local_search
- All four legacy branching setters emit DeprecationWarning while remaining functional
- accept_best_routine uses pthread_mutex_trylock for non-blocking global_opt write protection
- All 272 existing tests pass without regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add mutex protection for global_opt writes in accept_best_routine** - `66fa4b2` (feat)
2. **Task 2: Add set_param/get_param API, deprecation warnings, and branching propagation** - `80876ef` (feat)

## Files Created/Modified
- `cbqs/src/local_search.c` - Added extern update_lock mutex, wrapped global_opt writes with pthread_mutex_trylock
- `cbqs/Model.pxd` - Added _params cdef declaration
- `cbqs/Model.pyx` - Added _KNOWN_PARAMS, set_param/get_param methods, _params initialization and copy, removed global setter calls
- `cbqs/SearchLib.pyx` - Added branching param propagation in run_sampling and run_local_search via solver_ctx_set_* calls
- `cbqs/branching.pyx` - Added DeprecationWarning to all four wrapper functions

## Decisions Made
- set_param/get_param validates against _KNOWN_PARAMS set; raises ValueError for unknowns
- _params values take precedence over solve() kwargs which take precedence over defaults
- Deprecated setters remain functional per v1.1 "no breaking changes" constraint
- pthread_mutex_trylock is non-blocking; if contended, skip global_opt update (solver loses one update at worst)
- exact_benchmark uses _params.setdefault instead of deprecated set_bias_wrapper to avoid test noise

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Removed unused imports from Model.pyx**
- **Found during:** Task 2 (Step H)
- **Issue:** After removing global setter calls from close()/solve()/exact_benchmark(), the imports of set_bias_wrapper, set_factors_wrapper, and set_obj_dependence_wrapper were unused
- **Fix:** Cleaned import line to only import set_seed (still needed by approximate_benchmarking)
- **Files modified:** cbqs/Model.pyx
- **Verification:** Build succeeds, no import errors
- **Committed in:** 80876ef (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking cleanup)
**Impact on plan:** Minor cleanup to remove unused imports. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- set_param/get_param API is functional and ready for test coverage in Plan 02
- Branching propagation can be verified end-to-end in Plan 02 integration tests
- Deprecated setters can be tested for DeprecationWarning emission in Plan 02

## Self-Check: PASSED

All 5 modified files exist. Both task commits (66fa4b2, 80876ef) verified in git log.

---
*Phase: 12-branchingstats-local-search-cleanup*
*Completed: 2026-02-08*
