---
phase: 01-test-foundation
plan: 01
subsystem: test-infrastructure
tags: [cmake, cmocka, unit-tests, intarray, expression, state, c]
requires: []
provides: [cmake-test-build, intarray-tests, expression-tests, state-tests]
affects: [01-02, 01-03, 01-04, 01-05]
tech-stack:
  added: [cmocka-1.1.7, cmake-fetchcontent]
  patterns: [per-target-source-deps, asan-option]
key-files:
  created: [tests/CMakeLists.txt, tests/test_intarray.c, tests/test_expression.c, tests/test_state.c]
  modified: []
key-decisions:
  - id: explicit-source-deps
    decision: "Use explicit per-target source file lists instead of globbing all cbqs/src/*.c"
    reason: "Several source files (SearchLib.c, local_search.c) have external deps (Python.h) or compilation errors that are irrelevant to the modules under test"
  - id: cmocka-unit-testing-flag
    decision: "Set UNIT_TESTING=ON cache variable for cmocka FetchContent"
    reason: "cmocka-static target only created when UNIT_TESTING is ON"
duration: ~11 minutes
completed: 2026-02-04
---

# Phase 01 Plan 01: CMake Test Infrastructure + C Unit Tests Summary

**CMocka test suite for intarray/Expression/state with CMake FetchContent infrastructure and per-target source dependency linking**

## Performance

- **Duration:** ~11 minutes
- **Started:** 2026-02-04T23:07:14Z
- **Completed:** 2026-02-04T23:18:38Z
- **Tasks:** 2/2
- **Files modified:** 4 created

## Accomplishments

1. Created CMake build system in `tests/` that fetches CMocka 1.1.7 via FetchContent, builds static library, and provides `add_cmocka_test()` helper function
2. Wrote 7 CMocka unit tests for intarray module covering init, setbit/tstbit, clrbit, flpbit, set_ui_0, copy (sw_set), and compare (sw_cmp)
3. Wrote 9 CMocka unit tests for Expression module covering init, add_constant, add_variable, add_two_variables, multiply_constant, add_expression, multiply_variable, sub_constant, and sense/rhs
4. Wrote 5 CMocka unit tests for state module covering init_state, copy_state, copy_state_inplace, free_state, and init_large_state
5. All 21 tests pass under both normal and AddressSanitizer builds

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | CMake test infrastructure with CMocka FetchContent | badf400 | tests/CMakeLists.txt |
| 2 | CMocka tests for intarray, Expression, and state | 78a1e49 | tests/test_intarray.c, tests/test_expression.c, tests/test_state.c |

## Files Created

- `tests/CMakeLists.txt` - CMake build config with FetchContent CMocka, ASan option, per-target sources
- `tests/test_intarray.c` - 7 unit tests for bit array operations
- `tests/test_expression.c` - 9 unit tests for expression building and arithmetic
- `tests/test_state.c` - 5 unit tests for state management

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Explicit per-target source deps instead of globbing all .c | SearchLib.c requires Python.h, local_search.c has type errors -- neither needed for priority-1 module tests |
| Set UNIT_TESTING=ON for cmocka | cmocka-static target only exists under this flag |
| Corrected sw_init(64) expected n from 1 to 2 | Actual implementation: n = (bits >> 6) + 1 = 2 for 64 bits |
| sub_constant tested as separate clause, not in-place subtraction | sub_constant adds a new -constant clause rather than modifying existing constants |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Excluded SearchLib.c from compilation**
- **Found during:** Task 1 build
- **Issue:** SearchLib.c includes Python.h which is not available in the test build environment
- **Fix:** Changed from globbing all .c files to explicit per-target source file lists
- **Files modified:** tests/CMakeLists.txt

**2. [Rule 3 - Blocking] Added cmocka include directory explicitly**
- **Found during:** Task 1 build
- **Issue:** cmocka 1.1.7's cmocka-static target doesn't automatically export include directories to consumers
- **Fix:** Added `${cmocka_SOURCE_DIR}/include` to target_include_directories
- **Files modified:** tests/CMakeLists.txt

**3. [Rule 3 - Blocking] Enabled UNIT_TESTING cache variable for cmocka**
- **Found during:** Task 1 link
- **Issue:** cmocka-static target only defined when UNIT_TESTING=ON
- **Fix:** Added `set(UNIT_TESTING ON CACHE BOOL "" FORCE)` before FetchContent_MakeAvailable
- **Files modified:** tests/CMakeLists.txt

**4. [Rule 1 - Bug] Corrected test expectations for sw_init(64)**
- **Found during:** Task 2 writing
- **Issue:** Plan specified A.n == 1 for 64-bit array, but actual implementation computes n = (64 >> 6) + 1 = 2
- **Fix:** Wrote test with correct expected value of 2
- **Files modified:** tests/test_intarray.c

## Issues Encountered

- CMocka 1.1.7 deprecation warnings from cmake_minimum_required < 3.10 -- cosmetic, no action needed
- Format warnings in upstream Expression.c and state.c (%lld vs %ld for int64_t) -- not addressed, these are in existing code

## Next Phase Readiness

- Test infrastructure is ready for subsequent plans (01-02 through 01-05)
- Future test files can use `add_cmocka_test()` helper with explicit source dependencies
- ASan integration verified and working for memory leak detection
