---
phase: 06-memory-optimization
plan: 02
subsystem: memory
tags: [soo, small-object-optimization, dynamic-array, c, expression]

# Dependency graph
requires:
  - phase: 06-01
    provides: Arena allocator foundation for memory optimization
provides:
  - dyn_expression_t type with small-object optimization
  - Inline storage for <=8 terms (no heap allocation)
  - 2x capacity doubling for heap growth
  - Comprehensive unit tests for boundary cases
affects: [06-03, 06-04, constraint-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Small-object optimization (SOO) for expressions"
    - "Inline storage with capacity==0 sentinel"
    - "Transparent access via dyn_expr_literals/dyn_expr_len_literal"

key-files:
  created:
    - cbqs/src/dyn_expr.h
    - cbqs/src/dyn_expr.c
    - tests/test_dyn_expr.c
  modified:
    - tests/CMakeLists.txt

key-decisions:
  - "capacity==0 indicates inline mode, capacity>0 indicates heap mode"
  - "Initial heap capacity 32 terms when exceeding 8-term inline threshold"
  - "Zero constants skipped in dyn_expr_add_constant (matches Expression.c)"

patterns-established:
  - "SOO pattern: inline_* arrays in struct, pointers NULL when inline"
  - "Accessor functions hide storage mode: dyn_expr_literals() returns correct array"
  - "dyn_expr_ensure_capacity() handles inline-to-heap transition transparently"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 6 Plan 2: Dynamic Expression with SOO Summary

**Dynamic expression storage with small-object optimization (SOO) - inline storage for <=8 terms, 2x heap growth, comprehensive unit tests with Valgrind verification**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T19:17:10Z
- **Completed:** 2026-02-05T19:21:14Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created dyn_expression_t with inline storage for small expressions (<=8 terms)
- Implemented transparent inline-to-heap transition at 9 terms
- Added 2x capacity doubling growth strategy for heap storage
- Comprehensive test suite with 13 tests covering all boundary cases
- Valgrind verification: 0 leaks, all heap blocks freed

## Task Commits

Each task was committed atomically:

1. **Task 1: Create dynamic expression module** - `3852bee` (feat)
2. **Task 2: Create dynamic expression unit tests** - `9424c44` (test)

## Files Created/Modified
- `cbqs/src/dyn_expr.h` - Dynamic expression type definition and API
- `cbqs/src/dyn_expr.c` - Implementation with SOO and 2x growth
- `tests/test_dyn_expr.c` - 13 unit tests covering lifecycle, storage, copy
- `tests/CMakeLists.txt` - Added test_dyn_expr target

## Decisions Made
- Used `capacity==0` as sentinel for inline mode (simpler than separate flag)
- Initial heap capacity of 32 terms matches CONTEXT.md decision
- Zero constants skipped to match existing Expression.c behavior
- Accessors return correct array transparently (user code doesn't need to check mode)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - clean implementation.

## User Setup Required

None - no external service configuration required.

## Verification Results

All verification criteria met:

1. **Compilation:** `gcc -c cbqs/src/dyn_expr.c -Wall -Werror` - PASSED
2. **Unit tests:** 13/13 tests pass
3. **Valgrind:** 0 errors, 0 leaks (44 allocs, 44 frees)
4. **Memory efficiency:** Small (2-term) expressions stay inline, large (20-term) use heap
5. **Boundary test:** 8 terms stays inline, 9 terms transitions to heap

## Next Phase Readiness
- dyn_expression_t ready for integration
- API compatible with Expression.c patterns (similar function names)
- Future plans can migrate existing Expression usage to dyn_expression_t
- Arena allocator (06-01) available for combining with dyn_expr in constraint storage

---
*Phase: 06-memory-optimization*
*Completed: 2026-02-05*
