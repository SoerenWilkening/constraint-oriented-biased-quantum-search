---
phase: 18-dead-code-removal
plan: 01
subsystem: kernel
tags: [c, cython, dead-code, model_t, branching]

requires:
  - phase: 14
    provides: Unified branching model moved bias_factor/look_ahead_factor to solver_ctx branching_stats
provides:
  - Clean model_t struct with no orphaned fields
  - Clean solver.h with no commented-out signatures
  - Clean local_search.c with no commented-out code blocks
  - Aligned Model.pxd matching C model_t struct
affects: [api-consistency, build-packaging, documentation]

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - cbqs/src/model.h
    - cbqs/src/model.c
    - cbqs/src/solver.h
    - cbqs/src/local_search.c
    - cbqs/Model.pxd
    - tests/test_model.c

key-decisions:
  - "objective_value(obj, cur_sol) void-cast removed from quantum_local_search -- pure function with no side effects, only used to set init_val for now-removed commented-out code"
  - "calloc/free pair for unused 'changes' variable removed alongside commented-out objective_value_improved block"

patterns-established:
  - "Dead fields in model_t removed bottom-up: C struct -> C init/free -> Cython pxd -> tests"

requirements-completed: [DEAD-01, DEAD-02, DEAD-03, DEAD-04]

duration: 8min
completed: 2026-02-25
---

# Phase 18: Dead Code Removal Summary

**Removed 4 orphaned model_t fields, 1 commented-out function signature, and 3 commented-out code blocks across C kernel, Cython bindings, and tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-25
- **Completed:** 2026-02-25
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Removed manual_bias, bias_factor, manual_bias_factor, look_ahead_factor from model_t struct (model.h), init/free code (model.c), Cython declarations (Model.pxd), and test assertions (test_model.c)
- Removed commented-out initial_state_preparation signature from solver.h
- Removed 3 commented-out code blocks from local_search.c (stale constraint_violation loop, objective_value else branch, objective_value_improved block) plus dead void-cast of objective_value and unused changes allocation

## Task Commits

Each task was committed atomically:

1. **Task 1+2: Remove orphaned fields and commented-out code** - `30d9715` (feat)

## Files Created/Modified
- `cbqs/src/model.h` - Removed 4 orphaned fields from model_t struct
- `cbqs/src/model.c` - Removed init/free code for orphaned fields
- `cbqs/src/solver.h` - Removed commented-out function signature
- `cbqs/src/local_search.c` - Removed 3 commented-out code blocks + dead void-cast + unused allocation
- `cbqs/Model.pxd` - Removed 4 orphaned Cython declarations + commented-out objective_value
- `tests/test_model.c` - Removed assertions for orphaned fields

## Decisions Made
- Removed (void)objective_value(obj, cur_sol) call in quantum_local_search: objective_value is a pure function with no side effects, and the init_val it computed was only used by the now-removed commented-out objective_value_improved block
- Removed calloc/free of 'changes' variable: only used by the now-removed commented-out objective_value_improved block

## Deviations from Plan
None - plan executed as written.

## Issues Encountered
- No C compiler (gcc/clang/cmake) available in Docker environment -- compilation and test execution deferred to user's local environment. All changes verified via static analysis (grep confirms no references to removed fields/code remain).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Clean codebase ready for Phase 19 (Incremental Evaluation) and Phase 20 (API Consistency)
- User should rebuild C tests (cmake + make) and Python extension (pip install -e .) locally to verify full test suite passes
- Active bias_factor/look_ahead_factor routing through _PARAM_DEFS -> solver_ctx is untouched

---
*Phase: 18-dead-code-removal*
*Completed: 2026-02-25*
