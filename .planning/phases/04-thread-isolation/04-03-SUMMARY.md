---
phase: 04-thread-isolation
plan: 03
subsystem: api
tags: [cython, python-api, seed, num_threads, determinism, reproducibility]

# Dependency graph
requires:
  - phase: 04-02
    provides: solver_ctx with seed/num_threads fields and solver_ctx_init_prng()
provides:
  - Python API for seed configuration (Model.seed property)
  - Python API for seed_used retrieval (Model.seed_used property)
  - Python API for thread count (Model.num_threads property)
  - Determinism tests verifying same seed = same result
affects: [04-04, users, integration-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "cdef struct name {...}; ctypedef name name_t pattern in Cython for proper field access"
    - "try/except for backward-compatible attribute access in Cython"

key-files:
  created:
    - tests/test_determinism.py
  modified:
    - cbqs/SearchLib.pyx
    - cbqs/SearchLib.pxd
    - cbqs/Model.pyx
    - cbqs/Model.pxd
    - setup.py

key-decisions:
  - "Use cdef struct pattern instead of ctypedef struct for proper Cython field access"
  - "Add try/except for seed_used assignment for backward compatibility"
  - "Declare _seed, _num_threads, _seed_used in Model.pxd (cdef class requirement)"

patterns-established:
  - "Model.seed property: set before solve() for reproducibility"
  - "Model.seed_used property: read after solve() to capture auto-generated seed"
  - "Model.num_threads property: set before solve() or use CBQS_THREADS env var"

# Metrics
duration: 20min
completed: 2026-02-05
---

# Phase 4 Plan 3: Cython API Summary

**Python API for seed/thread configuration with determinism tests - Model.seed, Model.seed_used, Model.num_threads properties**

## Performance

- **Duration:** 20 min
- **Started:** 2026-02-05T16:14:32Z
- **Completed:** 2026-02-05T16:34:33Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- SearchLib.pyx wires seed and num_threads from Model to solver_ctx
- SearchLib.pyx calls solver_ctx_init_prng() and stores seed_used back to Model
- Model.pyx exposes seed, seed_used (read-only), and num_threads properties
- All 18 determinism tests pass (9 determinism, 9 validation)
- All 52 existing Python tests still pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Update SearchLib.pxd and SearchLib.pyx** - `d5a5a03` (feat)
2. **Task 2: Expose properties in Model.pyx** - `88468a1` (feat)
3. **Fix: Cython struct definition and prng.c** - `65cedcc` (fix)
4. **Task 3: Add determinism tests** - `612bf12` (test)

## Files Created/Modified
- `cbqs/SearchLib.pxd` - Added struct solver_ctx definition with seed fields, solver_ctx_init_prng declaration
- `cbqs/SearchLib.pyx` - Wires seed/num_threads from Model to ctx, calls init_prng, stores seed_used
- `cbqs/Model.pyx` - Added seed, seed_used, num_threads properties with validation
- `cbqs/Model.pxd` - Added _seed, _num_threads, _seed_used attribute declarations
- `setup.py` - Added prng.c to sources list
- `tests/test_determinism.py` - 18 tests for deterministic behavior and validation

## Decisions Made
- **cdef struct pattern:** Used `cdef struct solver_ctx:` followed by `ctypedef solver_ctx solver_ctx_t` instead of `ctypedef struct solver_ctx_t:` to properly expose struct fields to Cython. The ctypedef struct pattern doesn't allow field access.
- **Model.pxd declarations:** cdef class attributes must be declared in the .pxd file, not just in __init__. Added _seed, _num_threads, _seed_used.
- **try/except for seed_used:** Used try/except around mod._seed_used assignment for backward compatibility with older Model objects.
- **prng.c in setup.py:** Added missing prng.c to sources list (was added in 04-01 but not in setup.py).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added prng.c to setup.py sources**
- **Found during:** Task 1 (build verification)
- **Issue:** prng_next_double undefined symbol - prng.c not compiled into extensions
- **Fix:** Added prng.c to sources list in setup.py
- **Files modified:** setup.py
- **Verification:** Build succeeds, tests pass
- **Committed in:** 65cedcc (fix commit)

**2. [Rule 3 - Blocking] Fixed Cython struct definition pattern**
- **Found during:** Task 1 (build verification)
- **Issue:** "Cannot convert 'solver_ctx_t *' to Python object" when accessing struct fields
- **Fix:** Changed from `ctypedef struct solver_ctx_t:` to `cdef struct solver_ctx:` + `ctypedef`
- **Files modified:** cbqs/SearchLib.pxd
- **Verification:** Cython compiles, field access works
- **Committed in:** 65cedcc (fix commit)

**3. [Rule 3 - Blocking] Added Model.pxd attribute declarations**
- **Found during:** Task 2 (test run)
- **Issue:** "object has no attribute '_seed'" - cdef class requires pxd declarations
- **Fix:** Added cdef public object _seed, _num_threads, _seed_used to Model.pxd
- **Files modified:** cbqs/Model.pxd
- **Verification:** Tests pass
- **Committed in:** 65cedcc (fix commit)

---

**Total deviations:** 3 auto-fixed (3 blocking)
**Impact on plan:** All auto-fixes necessary for correct Cython compilation and runtime. No scope creep.

## Issues Encountered
- Cython struct field access required specific declaration pattern - resolved by using cdef struct + ctypedef pattern
- cdef class attributes need .pxd declarations - resolved by adding to Model.pxd

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full Python API for seed/thread configuration is complete
- Ready for 04-04 (full integration tests and documentation)
- Same seed + same num_threads produces deterministic results

---
*Phase: 04-thread-isolation*
*Completed: 2026-02-05*
