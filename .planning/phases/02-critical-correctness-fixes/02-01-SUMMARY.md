---
phase: 02
plan: 01
subsystem: core-kernel
tags: [memory-safety, threading, performance, c, pthread]
dependency-graph:
  requires: [01]
  provides: [thread-safe-local-search, efficient-preprocessing]
  affects: [06, 07]
tech-stack:
  added: []
  patterns: [pthread-join-before-cleanup, batch-reallocation]
key-files:
  created:
    - tests/test_local_search.c
  modified:
    - cbqs/src/local_search.c
    - cbqs/src/constraint.c
    - tests/CMakeLists.txt
decisions:
  - id: 02-01-01
    summary: "Thread cleanup after pthread_join, not pthread_create"
    rationale: "Thread data must remain valid while threads execute"
  - id: 02-01-02
    summary: "Realloc condition uses == 0 && counter > 0"
    rationale: "Trigger at multiples of size_steps, skip first iteration"
metrics:
  duration: ~8m
  completed: 2026-02-05
---

# Phase 2 Plan 01: Critical C Memory Safety Fixes Summary

**One-liner:** Fixed use-after-free in accept_best_routine by moving cleanup after pthread_join; fixed inverted realloc condition reducing ~16000x unnecessary reallocations.

## What Was Done

### Bug 1: Use-After-Free in accept_best_routine (local_search.c)

**Root cause:** Thread data (`remainings`, `ful_con`, `ful`) was freed immediately after `pthread_create`, before threads had a chance to consume it.

**Fix:** Moved cleanup operations from the pthread_create loop to after each `pthread_join` completes:

```c
// BEFORE (buggy): cleanup in pthread_create loop
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *)&data[i]);
    free(data[i].remainings);      // BUG: freed before thread uses
    sw_clear(data[i].ful_con);
    sw_clear(data[i].ful);
}

// AFTER (fixed): cleanup after pthread_join
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *)&data[i]);
}
for (int i = 0; i < NUMThreads; ++i) {
    pthread_join(threads[i], NULL);
    free(data[i].remainings);      // NOW safe: thread completed
    sw_clear(data[i].ful_con);
    sw_clear(data[i].ful);
    // ... process results
}
```

**Impact:** Prevents heap corruption and silent data corruption during parallel local search.

### Bug 2: Inverted Realloc Condition in preprocessing functions (constraint.c)

**Root cause:** The bitmask condition `counter & (size_steps - 1)` is true for 16383 out of 16384 values (all non-multiples). This triggered reallocation on nearly every iteration instead of every 16384 iterations.

**Fix:** Changed condition to `(counter & (size_steps - 1)) == 0 && counter > 0`:

```c
// BEFORE (buggy): triggers ~16383/16384 times
if (counter_negative & (size_steps - 1))
    con->negative_indices = realloc(...);

// AFTER (fixed): triggers only at multiples of 16384
if ((counter_negative & (size_steps - 1)) == 0 && counter_negative > 0)
    con->negative_indices = realloc(...);
```

**Fixed 6 locations:**
- `preprocessing()`: counter_negative (line 185), counter_positive (line 192)
- `preprocessing_sparse()`: counter_negative (line 300), counter_positive (line 307), nnz_neg (line 318), nnz_pos (line 332)

**Impact:** Eliminates ~16000x performance regression from excessive heap allocations during constraint preprocessing.

### Regression Test Added (test_local_search.c)

Created CMocka tests for `local_search()` that exercise the multi-threaded accept_best_routine:

- `test_local_search_thread_data_lifetime`: Basic test that would catch use-after-free under ASan
- `test_local_search_multiple_iterations`: Extended test with multiple iterations to catch intermittent issues

**Test coverage:** 188 lines, verifies thread data lifetime and solution feasibility after local search.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| bac31ae | fix | Fix use-after-free in accept_best_routine |
| 22d5f19 | fix | Fix inverted realloc condition in preprocessing |
| b900e61 | test | Add regression test for thread data lifetime |

## Verification

1. **Build succeeds:** `python3 setup.py build_ext --inplace` - PASSED
2. **Phase 1 tests pass:** All 9 existing tests pass - PASSED
3. **New test passes:** `test_local_search` - PASSED (2 test cases)
4. **ASan build passes:** All 10 tests pass with ASan (leaks disabled) - PASSED

## Deviations from Plan

None - plan executed exactly as written.

## Must-Haves Verification

| Requirement | Status |
|-------------|--------|
| Thread data valid while threads run | VERIFIED: cleanup after pthread_join |
| Realloc triggers only every size_steps | VERIFIED: 6 conditions use `== 0 && counter > 0` |
| Existing Phase 1 tests pass | VERIFIED: 9/9 tests pass |
| test_local_search.c exists (min 30 lines) | VERIFIED: 188 lines |
| pthread_join before free pattern | VERIFIED: line 313 join, line 316 free |

## Next Phase Readiness

- **Phase 2 Plan 02:** Can proceed with Expression mutation/ownership fixes
- **Phase 6 dependency:** These fixes are prerequisite for performance optimization work
