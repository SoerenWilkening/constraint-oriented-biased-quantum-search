---
phase: 05-memory-safety
plan: 02
subsystem: memory
tags: [VLA, heap-allocation, thread-safety, valgrind, memory-leak]

# Dependency graph
requires:
  - phase: 05-01
    provides: preprocessing leak fixes, Valgrind suppressions
  - phase: 03
    provides: solver_ctx_t thread context
  - phase: 04
    provides: prng.c for thread-local PRNG
provides:
  - VLA-free local_search.c with heap-allocated per-thread buffers
  - Complete allocation audit for explore_neighbourhood and accept_best_routine
  - Zero Valgrind leaks for local_search tests
affects: [05-03, 05-04, 05-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Per-thread scratch buffers in struct (thread_totals, thread_bits)
    - Malloc before pthread_create, free after pthread_join pattern
    - Early return cleanup pattern

key-files:
  created: []
  modified:
    - cbqs/src/local_search.h
    - cbqs/src/local_search.c
    - tests/CMakeLists.txt
    - tests/test_local_search.c

key-decisions:
  - "Per-thread buffers stored in local_search_data_t struct for cache-friendly access"
  - "Allocation failure returns -1 with full cleanup before return"
  - "Early return path at max_worse_acceptances now includes cleanup"

patterns-established:
  - "VLA replacement: malloc before use, free after use in same scope OR struct fields for thread data"
  - "All code paths (normal return, early return, error) must have cleanup"

# Metrics
duration: 50min
completed: 2026-02-05
---

# Phase 5 Plan 2: VLA Replacement in local_search.c Summary

**Replaced all VLAs in local_search.c with heap-allocated per-thread buffers, fixed 3 memory leaks including missing cur_best_tabu free**

## Performance

- **Duration:** 50 min
- **Started:** 2026-02-05T17:26:26Z
- **Completed:** 2026-02-05T18:16:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Eliminated VLAs (`bits[d]`, `totals[C]`, `remainings[C]`) that risked stack overflow with large constraint counts
- Added thread_totals and thread_bits fields to local_search_data_t for per-thread scratch buffers
- Fixed 3 memory leaks found during allocation audit (cur_best_tabu, early return cleanup, tabu_list.moves)
- Valgrind now reports "All heap blocks were freed -- no leaks are possible" for test_local_search

## Task Commits

Each task was committed atomically:

1. **Task 1: Add per-thread scratch buffer fields** - `1c7a59e` (feat)
2. **Task 2: Replace VLAs and audit allocations** - `d229d9d` (fix)

## Files Created/Modified
- `cbqs/src/local_search.h` - Added thread_totals, thread_bits, num_constraints fields to local_search_data_t
- `cbqs/src/local_search.c` - VLA replacement and memory leak fixes
- `tests/CMakeLists.txt` - Added prng.c and solver_ctx.c dependencies for test_local_search
- `tests/test_local_search.c` - Updated to use solver_ctx_t API

## Decisions Made
- Per-thread scratch buffers stored in local_search_data_t for locality with other thread data
- Allocation failure in accept_best_routine returns -1 with full cleanup
- Early return at max_worse_acceptances now frees all resources (was missing)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing free_state(cur_best_tabu) in accept_best_routine**
- **Found during:** Task 2 (allocation audit)
- **Issue:** cur_best_tabu allocated at line 277 but never freed at function end
- **Fix:** Added free_state(cur_best_tabu, 1) after free_state(cur_best, 1) at line 414
- **Files modified:** cbqs/src/local_search.c
- **Verification:** Valgrind shows 0 definitely lost
- **Committed in:** d229d9d

**2. [Rule 1 - Bug] Missing cleanup on early return at max_worse_acceptances**
- **Found during:** Task 2 (allocation audit)
- **Issue:** Line 399 `return 0` without freeing cur_best, cur_best_tabu, ful, ful_con
- **Fix:** Added full cleanup block before early return
- **Files modified:** cbqs/src/local_search.c
- **Verification:** Valgrind shows 0 definitely lost
- **Committed in:** d229d9d

**3. [Rule 1 - Bug] Missing free(tabu_list.moves) in local_search**
- **Found during:** Task 2 (allocation audit)
- **Issue:** tabu_list.moves malloc'd at line 459 but never freed
- **Fix:** Added free(tabu_list.moves) before return
- **Files modified:** cbqs/src/local_search.c
- **Verification:** Valgrind shows 0 definitely lost
- **Committed in:** d229d9d

**4. [Rule 3 - Blocking] test_local_search missing dependencies**
- **Found during:** Task 2 (build verification)
- **Issue:** test_local_search CMake target missing prng.c and solver_ctx.c
- **Fix:** Added ${CBQS_SRC_DIR}/prng.c and ${CBQS_SRC_DIR}/solver_ctx.c to CMake target
- **Files modified:** tests/CMakeLists.txt
- **Verification:** Build succeeds
- **Committed in:** d229d9d

**5. [Rule 3 - Blocking] test_local_search using old local_search API**
- **Found during:** Task 2 (build verification)
- **Issue:** Test calling local_search(cur_sol, mod, NULL) but API now requires solver_ctx_t
- **Fix:** Updated tests to create/free solver_ctx_t and pass as first argument
- **Files modified:** tests/test_local_search.c
- **Verification:** Tests pass
- **Committed in:** d229d9d

---

**Total deviations:** 5 auto-fixed (3 bugs, 2 blocking)
**Impact on plan:** All auto-fixes necessary for memory safety and correct operation. Bug fixes were part of the allocation audit requirement.

## Allocation Audit Table

### explore_neighbourhood() allocations

| Allocation | Line | Free Location | Status |
|------------|------|---------------|--------|
| `bits` (via thread_bits) | 162 | N/A (struct field) | OK - freed in accept_best_routine |
| `cur_best = copy_state()` | 163 | 263 (assigned to dat->cur_best) | OK - freed by caller |
| `cur_best_tabu = copy_state()` | 164 | 264 (assigned to dat->cur_best_tabu) | OK - freed by caller |
| `new_sol = copy_state()` | 168 | 264: free_state(new_sol, 1) | OK |
| `totals` (via thread_totals) | 189 | N/A (struct field) | OK - freed in accept_best_routine |
| `inv = sw_init()` | 190 | 208: sw_clear(inv) | OK |
| `changed_con = calloc()` | 191 | 205: free(changed_con) | OK |
| `changes = calloc()` | 238 | 249: free(changes) | OK |

### accept_best_routine() allocations

| Allocation | Line | Free Location | Status |
|------------|------|---------------|--------|
| `cur_best = copy_state()` | 276 | 413 + early return | OK - FIXED early return |
| `cur_best_tabu = copy_state()` | 277 | 414 + early return | OK - FIXED (was missing) |
| `ful = sw_init()` | 281 | 415 + early return | OK - FIXED early return |
| `ful_con = sw_init()` | 282 | 416 + early return | OK - FIXED early return |
| `prog_data.progress = malloc()` | 293 | 392: free() | OK |
| `data = malloc()` | 301 | 390: free(data) | OK |
| `threads = malloc()` | 302 | 391: free(threads) | OK |
| `data[i].remainings = malloc()` | 308 | 365: free() | OK |
| `data[i].thread_totals = malloc()` | 330 | 366: free() | OK - NEW |
| `data[i].thread_bits = malloc()` | 331 | 367: free() | OK - NEW |
| `data[i].ful_con = sw_set()` | 311 | 366: sw_clear() | OK |
| `data[i].ful = sw_set()` | 312 | 367: sw_clear() | OK |
| `data[i].cur_best` (from thread) | thread | 373: free_state() | OK |
| `data[i].cur_best_tabu` (from thread) | thread | 381: free_state() | OK |

### local_search() allocations

| Allocation | Line | Free Location | Status |
|------------|------|---------------|--------|
| `ful = sw_init()` | 428 | 496: sw_clear(ful) | OK |
| `ful_con = sw_init()` | 436 | 495: sw_clear(ful_con) | OK |
| `moves = move_list()` | 447 | 493: free_move_list() | OK |
| `tabu_list.moves = malloc()` | 459 | 494: free() | OK - FIXED (was missing) |

## Issues Encountered
- GCC 15 internal compiler error when building Python extension with LTO - workaround: build C tests separately with CMake
- Python extension build intermittently failed due to GCC ICE - verification done via C tests and Valgrind

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- local_search.c is now VLA-free and Valgrind-clean
- Per-thread buffer pattern established for future thread-related memory work
- Ready for Phase 5 Plan 3 (SearchLib.c VLA fixes) and beyond

---
*Phase: 05-memory-safety*
*Completed: 2026-02-05*
