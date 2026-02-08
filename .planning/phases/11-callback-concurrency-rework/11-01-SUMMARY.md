---
phase: 11-callback-concurrency-rework
plan: 01
subsystem: api
tags: [threading, callback, concurrency, cython, history]

# Dependency graph
requires:
  - phase: 04-thread-isolation
    provides: seed/thread configuration on Model
provides:
  - Per-thread callback state via _SolveState class and _solve_states dict
  - track_history parameter on solve() and local_search()
  - 2-tuple (value, elapsed_seconds) history format
  - NULL callback pointer for zero-overhead when not tracking
  - SATISFY mode satisfaction count in history entries
affects: [11-02-PLAN, result-serialization, benchmarking]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-thread state keyed by threading.get_ident(), try/finally cleanup for thread state]

key-files:
  created: []
  modified:
    - cbqs/SearchLib.pyx
    - cbqs/Model.pyx
    - cbqs/result.py

key-decisions:
  - "Per-thread state dict keyed by threading.get_ident() instead of thread-local storage or solve-call IDs"
  - "track_history defaults to True for backward compatibility with existing code expecting history"
  - "SATISFY mode history records satisfaction count (num_constraints + tot_profit) as integer value"
  - "Shared solve_start_time computed before Parallel() for consistent elapsed times across workers"

patterns-established:
  - "_SolveState class + _solve_states dict: per-thread/per-solve callback state isolation pattern"
  - "try/finally cleanup: always pop thread state from dict in finally block"
  - "NULL callback pointer: zero overhead path when no history or user callback needed"

# Metrics
duration: 6min
completed: 2026-02-08
---

# Phase 11 Plan 01: Callback Concurrency Rework Summary

**Thread-safe history callback using per-thread _SolveState dict keyed by threading.get_ident(), with 2-tuple (value, elapsed_seconds) history format and track_history opt-in parameter**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-08T15:49:28Z
- **Completed:** 2026-02-08T15:55:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Replaced module-level cdef callback globals with per-thread _SolveState dictionary for concurrent solve isolation
- Added track_history parameter to solve() and local_search() with NULL callback optimization for zero overhead
- Updated history format from 4-tuple (iteration, obj, elapsed_ms, feasible) to 2-tuple (value, elapsed_seconds)
- SATISFY mode now records satisfaction count instead of None in history entries

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace module-level callback state with per-thread _SolveState in SearchLib.pyx** - `380747b` (feat)
2. **Task 2: Update Model.pyx solve()/local_search() and result.py history format** - `6de29ce` (feat)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `cbqs/SearchLib.pyx` - _SolveState class, _solve_states dict, thread-safe _history_callback_fn, updated run_sampling/run_local_search signatures
- `cbqs/Model.pyx` - track_history parameter on solve()/local_search(), shared solve_start_time, updated history merge sort key
- `cbqs/result.py` - Updated docstring and summary() rendering for 2-tuple (value, elapsed_seconds) history format

## Decisions Made
- Used threading.get_ident() as dict key (GIL already protects all dict operations since my_callback_c uses `with gil:`)
- track_history defaults to True for backward compatibility (existing code expects history in OptimizeResult)
- SATISFY mode computes satisfaction count as `num_constraints + tot_profit` (tot_profit is negative, so this gives satisfied count)
- solve_start_time computed once in Model.solve() before Parallel() for consistent elapsed times across all worker threads

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Core thread-safe callback infrastructure is in place
- Plan 02 tests can validate concurrent solve isolation, history format, and track_history=False optimization
- All existing API preserved (backward compatible)

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 11-callback-concurrency-rework*
*Completed: 2026-02-08*
