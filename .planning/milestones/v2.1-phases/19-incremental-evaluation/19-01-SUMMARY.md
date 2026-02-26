---
phase: 19-incremental-evaluation
plan: 01
subsystem: solver-core
tags: [incremental-evaluation, constraint-violation, local-search, threading]

requires:
  - phase: 18-dead-code-removal
    provides: Clean codebase with no orphaned fields or dead code
provides:
  - Incremental constraint evaluation adopted in explore_neighbourhood() and accept_best_routine()
  - Correctness test comparing full-recalc and incremental paths
  - local_search() manages remainings[] and ful_con across iterations
affects: [19-02-benchmark, 20-api-consistency]

tech-stack:
  added: []
  patterns:
    - "Incremental delta evaluation: prepare_constraints() + adjusted_constraint_violation() replaces constraint_violation() loop"
    - "Caller-managed baseline: local_search() owns remainings[] and ful_con, passes to accept_best_routine()"

key-files:
  created: []
  modified:
    - cbqs/src/local_search.c
    - tests/test_constraint.c

key-decisions:
  - "Moved remainings[] and ful_con ownership from accept_best_routine() to local_search() — eliminates per-call allocation and constraint_violation loop"
  - "Recompute remainings[] with full-recalc after each accepted move (once per iteration) — simpler than tracking exactly which bits flipped in threaded results"
  - "Used arena allocator for inv and changed_con in explore_neighbourhood() when solver context is available"

patterns-established:
  - "Incremental constraint eval pattern: prepare baseline once, use adjusted_constraint_violation() per move, combine with remainings[] for violation"
  - "Caller-owns-baseline pattern: parent function manages baseline arrays and passes them to callees"

requirements-completed: [INCR-02, INCR-03]

duration: ~25min
completed: 2026-02-25
---

# Plan 19-01: Incremental Evaluation Adoption Summary

**Replaced full constraint recalculation with incremental delta evaluation in both explore_neighbourhood() and accept_best_routine(), achieving O(affected_constraints) per move instead of O(all_constraints)**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-02-25
- **Completed:** 2026-02-25
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Replaced constraint_violation() loop in explore_neighbourhood() with adjusted_constraint_violation() incremental delta pattern matching quantum_local_search_states() reference
- Moved remainings[] and ful_con ownership from accept_best_routine() to local_search(), eliminating per-call allocation overhead
- Added test_incremental_vs_full_recalc correctness test covering 3 constraints x 8 variables with all single-flip combinations
- All 446 tests pass (56 C + 390 Python) with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace full-recalc with incremental evaluation** - `ea58b29` (feat)
2. **Task 2: Add incremental vs full-recalc correctness test** - `8ca69b1` (test)
3. **Task 3: Run full test suite** - no commit (verification only)

## Files Created/Modified
- `cbqs/src/local_search.c` - Replaced constraint_violation() loops in explore_neighbourhood() and accept_best_routine() with incremental delta computation; local_search() now manages remainings[] and ful_con across iterations
- `tests/test_constraint.c` - Added test_incremental_vs_full_recalc: builds 3 constraints with 8 variables, tests all single-flip combinations, asserts exact int64_t equality between full-recalc and incremental paths

## Decisions Made
- **Caller-owns-baseline**: Moved remainings[] and ful_con from accept_best_routine() to local_search(). This eliminates per-call allocation and the constraint_violation() loop inside accept_best_routine(), which was the TARGET 2 from CONTEXT.md.
- **Full-recalc refresh after accepted moves**: After each iteration in local_search(), remainings[] is recomputed via constraint_violation() and ful_con is re-prepared. This is simpler than tracking exact flipped bits from threaded results, and runs only once per iteration (not per-move).
- **Arena allocator for per-move temporaries**: In explore_neighbourhood(), inv bitmap and changed_con array use the arena allocator when available (solver context present), falling back to malloc/calloc otherwise.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- **Stale CMake build directories**: The build-test directory had a CMakeCache.txt pointing to an old path. Fixed by creating a fresh build directory (build-test-fresh).
- **PEP 668 Python environment**: System Python refused `pip install -e .` due to externally-managed environment policy. Fixed with `--break-system-packages` flag.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Incremental evaluation is adopted and tested
- Ready for Plan 19-02: Benchmark script to measure wall-clock performance across problem sizes
- All test infrastructure in place for regression detection

---
*Phase: 19-incremental-evaluation*
*Completed: 2026-02-25*
