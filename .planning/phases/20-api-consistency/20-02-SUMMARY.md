---
phase: 20-api-consistency
plan: 02
subsystem: api
tags: [cython, c, types, uint32_t, constraint]

requires:
  - phase: 18-dead-code-removal
    provides: Clean Model.pxd with orphaned declarations removed
provides:
  - Cython type declarations aligned with C headers
affects: [22-documentation]

tech-stack:
  added: []
  patterns: [exact-typedef-matching-in-pxd]

key-files:
  created: []
  modified:
    - cbqs/Constraint.pxd
    - tests/test_validation_model_py.py

key-decisions:
  - "All unsigned int * declarations changed to uint32_t * (matching constraint.h exactly)"
  - "size_t fields changed to uint32_t where constraint.h uses uint32_t (6 fields)"
  - "nnz_pos and nnz_neg kept as size_t (matching constraint.h)"
  - "Internal C-only fields (total_clauses, total_variables, etc.) not added to .pxd per CONTEXT.md minimal declaration policy"

patterns-established:
  - "Cython .pxd declarations must use exact C typedef names from headers"

requirements-completed: [API-03]

duration: 5min
completed: 2026-02-25
---

# Phase 20-02: Cython Type Alignment Summary

**Aligned 12 Constraint.pxd type declarations with constraint.h uint32_t typedefs, verified all .pxd files match C headers**

## Performance

- **Duration:** 5 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Converted 6 `unsigned int *` fields to `uint32_t *` in Constraint.pxd
- Converted 6 `size_t`/`size_t *` fields to `uint32_t`/`uint32_t *` in Constraint.pxd
- Verified Model.pxd, state.pxd, Expression.pxd, SearchLib.pxd, state_sampler.pxd all match C headers
- Full test suite (384 tests) passes after type alignment

## Task Commits

1. **Task 1+2: Align Constraint.pxd types, verify all .pxd files, test** - `dbed917` (feat)

## Files Created/Modified
- `cbqs/Constraint.pxd` - 12 type declarations aligned with constraint.h
- `tests/test_validation_model_py.py` - Updated test for removed 'results' param

## Decisions Made
- Kept nnz_pos and nnz_neg as size_t (they match constraint.h which also uses size_t)
- Did not add internal-only C fields to .pxd (per CONTEXT.md minimal declaration policy)
- Verified all other .pxd files already match their C headers -- no changes needed

## Deviations from Plan

### Auto-fixed Issues

**1. Test for removed 'results' param needed update**
- **Found during:** Task 2 (full test suite run)
- **Issue:** test_validation_model_py.py had a test that used the now-removed 'results' param
- **Fix:** Updated test to verify 'results' is rejected as unknown
- **Files modified:** tests/test_validation_model_py.py
- **Verification:** All 384 tests pass
- **Committed in:** dbed917

---

**Total deviations:** 1 auto-fixed (test update for param removed in Plan 20-01)
**Impact on plan:** Necessary test alignment with Plan 20-01 changes.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Cython type declarations now match C headers exactly
- Phase 20 fully complete -- ready for Phase 21 (Build & Packaging)

---
*Phase: 20-api-consistency*
*Completed: 2026-02-25*
