---
phase: 06-memory-optimization
plan: 05
subsystem: memory
tags: [dynamic-allocation, small-object-optimization, expression-api, backward-compatibility]

# Dependency graph
requires:
  - phase: 06-02
    provides: dyn_expression_t with SOO (small-object optimization)
provides:
  - Expression.c fully migrated to dyn_expr API
  - expression_t typedef to dyn_expression_t
  - MAXCLAUSESIZE removed entirely from Expression.h
  - CONSTRAINT_VARS_PER_CLAUSE for constraint-specific indexing
affects: [future-memory-optimizations, constraint-system, solver-extensions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pointer aliasing for backward compatibility (literals always points to valid storage)"
    - "Typedef migration (expression_t = dyn_expression_t)"

key-files:
  created: []
  modified:
    - cbqs/src/Expression.h
    - cbqs/src/Expression.c
    - cbqs/src/constraint.h
    - cbqs/src/constraint.c
    - cbqs/src/dyn_expr.c
    - tests/CMakeLists.txt
    - setup.py

key-decisions:
  - "literals/len_literal always point to valid storage (inline or heap) for backward compatibility"
  - "CONSTRAINT_VARS_PER_CLAUSE replaces MAXCLAUSESIZE in constraint.h for semantic clarity"
  - "Expression.c delegates to dyn_expr API rather than managing memory directly"

patterns-established:
  - "Pointer aliasing for SOO backward compatibility: expr->literals always valid"
  - "Semantic naming for constants: CONSTRAINT_VARS_PER_CLAUSE vs generic MAXCLAUSESIZE"

# Metrics
duration: 12min
completed: 2026-02-05
---

# Phase 6 Plan 5: dyn_expr Integration Summary

**expression_t now typedef to dyn_expression_t with full backward compatibility - existing code accessing expr->literals works unchanged**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-05T22:21:39Z
- **Completed:** 2026-02-05T22:33:34Z
- **Tasks:** 4 (Task 1, Task 2a/2b/2c combined, Task 3)
- **Files modified:** 7

## Accomplishments

- Expression.c fully migrated to dyn_expr API (28 dyn_expr function calls)
- expression_t is now a typedef to dyn_expression_t (no wrapper struct)
- MAXCLAUSESIZE removed entirely from Expression.h and constraint.h
- All 10 C expression tests pass unchanged
- All 28 Python expression tests pass unchanged
- Valgrind clean (0 leaks) for expression and constraint tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace expression_t with dyn_expression_t typedef** - `ccf3243` (feat)
2. **Task 2a/2b/2c: Migrate Expression.c to dyn_expr API** - `d00c888` (feat)
3. **Fix: Pointer aliasing for backward compatibility** - `76e20f4` (fix)
4. **Task 3: Complete MAXCLAUSESIZE removal and test dependencies** - `12f80c8` (fix)
5. **setup.py: Add dyn_expr.c to Cython builds** - `496b829` (chore)

## Files Created/Modified

- `cbqs/src/Expression.h` - typedef expression_t = dyn_expression_t, removed MAXCLAUSESIZE
- `cbqs/src/Expression.c` - all functions delegate to dyn_expr API
- `cbqs/src/constraint.h` - added CONSTRAINT_VARS_PER_CLAUSE constant
- `cbqs/src/constraint.c` - replaced MAXCLAUSESIZE with CONSTRAINT_VARS_PER_CLAUSE
- `cbqs/src/dyn_expr.c` - pointer aliasing fix for backward compatibility
- `tests/CMakeLists.txt` - added dyn_expr.c, arena.c, prng.c dependencies
- `setup.py` - added dyn_expr.c and arena.c to Cython extension sources

## Decisions Made

1. **Pointer aliasing for backward compatibility**: dyn_expression_t's `literals` and `len_literal` pointers now always point to valid storage (inline_literals or heap-allocated). This ensures existing code that accesses `expr->literals` directly (like tests and Cython bindings) continues to work without modification.

2. **CONSTRAINT_VARS_PER_CLAUSE naming**: Instead of keeping MAXCLAUSESIZE in constraint.h, introduced semantically clear CONSTRAINT_VARS_PER_CLAUSE (=4) to indicate this is about constraint storage, not expression storage.

3. **Test dependencies**: Added prng.c and arena.c to test targets that use solver_ctx.c, as solver context now requires arena and PRNG initialization.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pointer aliasing for backward compatibility**
- **Found during:** Task 2 execution - tests segfaulting
- **Issue:** Tests access `expr->literals` directly, but in inline mode this pointer was NULL
- **Fix:** Modified dyn_expr_init() and dyn_expr_copy() to always set literals/len_literal pointers to valid storage
- **Files modified:** cbqs/src/dyn_expr.c
- **Verification:** All 10 expression tests pass
- **Committed in:** 76e20f4

**2. [Rule 3 - Blocking] MAXCLAUSESIZE in constraint.c**
- **Found during:** Task 3 - build failure
- **Issue:** constraint.c used MAXCLAUSESIZE which was removed from Expression.h
- **Fix:** Replaced with CONSTRAINT_VARS_PER_CLAUSE
- **Files modified:** cbqs/src/constraint.c
- **Verification:** Build succeeds, tests pass
- **Committed in:** 12f80c8

**3. [Rule 3 - Blocking] Missing test dependencies**
- **Found during:** Task 3 - linker errors
- **Issue:** test_branching, test_solver, test_searchlib, test_integration, test_thread_safety missing prng.c/arena.c
- **Fix:** Added missing .c files to CMakeLists.txt
- **Files modified:** tests/CMakeLists.txt
- **Verification:** All tests build and pass
- **Committed in:** 12f80c8

**4. [Rule 3 - Blocking] Cython extension missing dyn_expr.c**
- **Found during:** Task 3 verification - Python tests fail
- **Issue:** cbqs.Expression extension didn't include dyn_expr.c
- **Fix:** Added dyn_expr.c and arena.c to setup.py sources
- **Files modified:** setup.py
- **Verification:** All 28 Python expression tests pass
- **Committed in:** 496b829

---

**Total deviations:** 4 auto-fixed (all Rule 3 - Blocking issues)
**Impact on plan:** All auto-fixes necessary for build/test success. No scope creep.

## Issues Encountered

- Initial approach assumed `expr->literals` could be NULL in inline mode, but existing code (tests, Cython bindings) access this pointer directly. Solved by pointer aliasing - always pointing to valid storage.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- dyn_expr integration complete - Phase 6 Memory Optimization is now fully implemented
- Memory efficiency verified: small expressions use inline storage (no heap allocation)
- Ready for Phase 7 or production use

---
*Phase: 06-memory-optimization*
*Completed: 2026-02-05*
