---
phase: 15-solve-api-migration
plan: 02
subsystem: api
tags: [cython, solve, set_param, zero-arg, api-migration, breaking-change]

# Dependency graph
requires:
  - phase: 15-solve-api-migration
    plan: 01
    provides: "_PARAM_DEFS registry, _get_effective() helper, type coercion, set-time validation"
provides:
  - "Zero-arg solve() method reading all 14 params from _params via _get_effective()"
  - "Complete removal of bias parameter from solve() signature and body"
  - "Fixed monte_calor_estimate typo to monte_carlo_estimate"
  - "All ~80 solve() calls across 12 test/benchmark files migrated to set_param() + solve()"
  - "TestSolveRejectsKwargs test class verifying solve() is zero-arg"
affects: [api-cleanup-milestone, documentation, user-migration-guide]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "set_param() before solve() pattern for all solver configuration"
    - "Zero-arg solve() reads from _params -- single source of truth"

key-files:
  created: []
  modified:
    - cbqs/Model.pyx
    - tests/test_model_py.py
    - tests/test_set_param.py
    - tests/test_verification_py.py
    - tests/test_diagnostics_py.py
    - tests/test_concurrent_history.py
    - tests/test_determinism.py
    - tests/test_branching_propagation.py
    - tests/test_memory_stress.py
    - tests/test_cython_memory.py
    - tests/test_stress.py
    - tests/test_validation_model_py.py
    - benchmarks/test_bench_solver.py

key-decisions:
  - "bias parameter completely removed (not just renamed) -- branching_bias via close() handles this"
  - "Removed results validation from solve() body since set_param validates at set-time"
  - "Removed bias SAT warning since bias parameter no longer exists"
  - "stopping_time float values in tests (0.1, 0.2, 0.5) changed to int 1 to match set_param coercion"
  - "Benchmark assertions updated from list to OptimizeResult (solve() now returns OptimizeResult not list)"

patterns-established:
  - "Configure-then-solve: m.set_param('key', value); m.solve() -- no kwargs on solve()"
  - "Helper pattern: _configure_solve(m, stopping_time=5, num_workers=1) for test DRY"
  - "TypeError test pattern: pytest.raises(TypeError) for solve() kwarg rejection"

# Metrics
duration: 11min
completed: 2026-02-14
---

# Phase 15 Plan 02: Solve API Migration Summary

**Zero-arg solve() method with all 14 params read from _params via _get_effective(), plus ~80 test calls migrated to set_param() pattern**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-14T20:09:09Z
- **Completed:** 2026-02-14T20:19:52Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Stripped all 14 keyword arguments from solve() -- signature is now `def solve(self):`
- solve() reads M, stopping_time, stop_val, callback, max_delta, reset_delta, depth_look_ahead, num_workers, results, bfs, ignore_constraint_search, monte_carlo_estimate, verify, track_history from _params via _get_effective()
- Completely removed bias parameter (no longer in signature, body, or local variables)
- Fixed monte_calor_estimate typo to monte_carlo_estimate everywhere
- Converted all ~80 solve() calls across 12 test/benchmark files to use set_param() before solve()
- Added TestSolveRejectsKwargs class with 7 tests verifying solve() rejects all kwargs
- Full test suite: 383 tests pass, 7 benchmarks pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Strip solve() kwargs and rewrite internals to read from _params** - `67a3d81` (feat)
2. **Task 2: Update all test files to use set_param() before solve()** - `d509ed1` (test)

## Files Created/Modified
- `cbqs/Model.pyx` - Zero-arg solve(), _get_effective() reads for all params, bias removed, typo fixed
- `tests/test_model_py.py` - 10 solve() calls converted to set_param() + solve()
- `tests/test_set_param.py` - Persistence/precedence tests updated, TestSolveRejectsKwargs added (7 tests)
- `tests/test_verification_py.py` - 11 solve() calls converted
- `tests/test_diagnostics_py.py` - 17 solve() calls converted, _configure_solve helper added
- `tests/test_concurrent_history.py` - 5 solve() calls converted (thread-safe per-model set_param)
- `tests/test_determinism.py` - 8 solve() calls converted
- `tests/test_branching_propagation.py` - 8 solve() calls converted
- `tests/test_memory_stress.py` - 7 solve() calls converted, float stopping_times fixed to int
- `tests/test_cython_memory.py` - 1 solve() call converted
- `tests/test_stress.py` - 1 solve() call converted
- `tests/test_validation_model_py.py` - 3 solve() calls converted, results validation test updated to set-time
- `benchmarks/test_bench_solver.py` - 12 solve() calls converted, assertions updated to OptimizeResult

## Decisions Made
- bias parameter completely removed rather than renamed -- branching_bias (set during close()) is the replacement
- results validation check removed from solve() body since set_param validates at set-time (fail-fast principle)
- Removed the "bias will be ignored when solving SAT" warning since bias no longer exists as a parameter
- Float stopping_time values (0.1, 0.2, 0.5) in stress tests changed to int 1 to match set_param int coercion
- Benchmark tests updated to assert OptimizeResult instead of list (solve() return type was already OptimizeResult since Phase 8)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed float stopping_time in stress tests**
- **Found during:** Task 2 (test migration)
- **Issue:** test_memory_stress.py used stopping_time=0.1, 0.2, 0.5 -- these would be coerced to int 0 by set_param, which fails validation (stopping_time must be positive)
- **Fix:** Changed to stopping_time=1 (minimum positive int)
- **Files modified:** tests/test_memory_stress.py
- **Committed in:** d509ed1 (Task 2 commit)

**2. [Rule 1 - Bug] Fixed benchmark assertions expecting list instead of OptimizeResult**
- **Found during:** Task 2 (benchmark migration)
- **Issue:** Benchmarks asserted `isinstance(result, list)` but solve() has returned OptimizeResult since Phase 8
- **Fix:** Changed assertions to `isinstance(result, OptimizeResult)`
- **Files modified:** benchmarks/test_bench_solver.py
- **Committed in:** d509ed1 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both were necessary correctness fixes. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 15 Solve API Migration is complete
- API-01 (set_param/get_param): Delivered in Plan 01
- API-02 (zero-arg solve): Delivered in Plan 02
- API-03 (all tests pass with new API): 383 tests + 7 benchmarks pass
- API-04 (bias removed, typo fixed): Both done
- Ready for next milestone phase or documentation updates

## Self-Check: PASSED

- [x] cbqs/Model.pyx exists
- [x] tests/test_set_param.py exists
- [x] tests/test_model_py.py exists
- [x] 15-02-SUMMARY.md exists
- [x] Commit 67a3d81 (Task 1) found
- [x] Commit d509ed1 (Task 2) found

---
*Phase: 15-solve-api-migration*
*Completed: 2026-02-14*
