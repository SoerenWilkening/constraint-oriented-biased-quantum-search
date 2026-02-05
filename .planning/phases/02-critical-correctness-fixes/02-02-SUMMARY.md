---
phase: 02-critical-correctness-fixes
plan: 02
subsystem: core
tags: [c, memory, deep-copy, expression]

# Dependency graph
requires:
  - phase: 01-test-foundation
    provides: CMocka test infrastructure for C unit tests
provides:
  - copy_expression_contents() C helper function for deep copying expression data
  - Unit test verifying copy creates independent arrays without aliasing
affects:
  - 02-03 (Expression immutability fix will use this helper)
  - Any future Cython code needing independent Expression copies

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deep copy pattern: allocate fresh arrays, memcpy data, initialize padding"
    - "Allocation size uses min_size chunks matching init_expression"

key-files:
  created: []
  modified:
    - cbqs/src/Expression.c
    - cbqs/src/Expression.h
    - tests/test_expression.c

key-decisions:
  - "copy_expression_contents frees existing dest arrays before allocating (handles reuse)"
  - "Copies only actual data (expr_size), not full allocation size"
  - "Initializes padding to -1 matching init_expression pattern"

patterns-established:
  - "Expression deep copy: use copy_expression_contents() for independent copies"

# Metrics
duration: 8min
completed: 2026-02-05
---

# Phase 02 Plan 02: Expression Copy Helper Summary

**C helper function copy_expression_contents() for deep copying expression data with independent arrays and no aliasing**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-05T00:00:00Z
- **Completed:** 2026-02-05T00:08:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Implemented copy_expression_contents() in Expression.c that creates fully independent copies
- Added function declaration to Expression.h for Cython visibility
- Added comprehensive unit test verifying deep copy semantics (no aliasing, independent modification)

## Task Commits

Each task was committed atomically:

1. **Task 1 & 2: Add copy_expression_contents function and header declaration** - `e0e7fe4` (feat)
2. **Task 3: Add unit test for copy_expression_contents** - `1a36820` (test)

## Files Created/Modified

- `cbqs/src/Expression.c` - Added copy_expression_contents() function after free_expression()
- `cbqs/src/Expression.h` - Added function declaration for Cython access
- `tests/test_expression.c` - Added test_copy_expression_contents() verifying deep copy semantics

## Decisions Made

- **Frees existing dest arrays:** The function handles reuse cases by freeing any existing arrays in the destination expression before allocating fresh ones
- **Allocation strategy:** Uses same min_size chunk allocation as init_expression() for consistency
- **Padding initialization:** Initializes new array memory to -1 matching existing padding pattern
- **Copy scope:** Only copies actual data (using expr_size), not the full allocated buffer

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **LTO build race condition:** Initial build attempt failed due to temporary directory race condition during LTO compilation. Resolved by cleaning build directory and rebuilding.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- copy_expression_contents() is ready for use in 02-03 (Expression immutability fix)
- Function is exported in the compiled .so library (verified via nm)
- All 10 C unit tests pass including the new copy test
- Python build succeeds with the new function

---
*Phase: 02-critical-correctness-fixes*
*Completed: 2026-02-05*
