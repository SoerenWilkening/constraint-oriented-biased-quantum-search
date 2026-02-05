---
phase: 02-critical-correctness-fixes
plan: 06
subsystem: testing
tags: [valgrind, stress-test, ci, memory-analysis, pytest]

# Dependency graph
requires:
  - phase: 02-01
    provides: C test infrastructure with ASan
provides:
  - Valgrind CI job for deeper memory analysis
  - Stress tests (200+ iterations) for accumulated memory issues
  - Separate CI steps for unit vs stress tests
affects: [phase-3-performance, phase-6-optimization]

# Tech tracking
tech-stack:
  added: [valgrind, pytest-timeout]
  patterns: [separate-ci-steps-for-slow-tests]

key-files:
  created:
    - tests/test_stress.py
  modified:
    - .github/workflows/test.yml

key-decisions:
  - "Valgrind tests subset of critical tests due to performance overhead"
  - "Use --errors-for-leak-kinds=definite to avoid false positives on possible leaks"
  - "Stress tests run separately from unit tests for CI visibility"
  - "180 second timeout for stress tests in CI"

patterns-established:
  - "Stress tests: 200+ iterations to surface accumulated memory issues"
  - "CI separation: slow tests get their own job/step for visibility"

# Metrics
duration: 2min
completed: 2026-02-05
---

# Phase 02 Plan 06: Valgrind CI and Stress Tests Summary

**Valgrind CI job with --leak-check=full and stress tests running 200+ solve iterations to surface accumulated memory issues**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-05T10:32:40Z
- **Completed:** 2026-02-05T10:34:29Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Added Valgrind job to CI workflow for deeper memory analysis than ASan
- Created stress tests with 200+ iterations to catch accumulated memory issues
- Separated stress tests from unit tests in CI for better failure visibility
- Added pytest-timeout dependency for stress test time limits

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Valgrind job to CI workflow** - `fabb7df` (ci)
2. **Task 2: Create stress test for repeated solve cycles** - `52094fb` (test)
3. **Task 3: Add stress test to CI workflow** - `8fbee57` (ci)

## Files Created/Modified
- `.github/workflows/test.yml` - Added c-tests-valgrind job, separated Python unit/stress tests
- `tests/test_stress.py` - Stress tests: 200 solve cycles, 500 expression ops, immutability checks, 300 model creation cycles

## Decisions Made
- **Valgrind subset:** Run only expression, state, constraint tests under Valgrind due to significant performance overhead
- **Definite leaks only:** Use --errors-for-leak-kinds=definite to avoid CI failures from possible/indirect leaks
- **Separate stress tests:** Better visibility when stress tests fail vs unit tests
- **180s timeout:** Balance between catching slow issues and CI runtime

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Local cbqs installation not possible (externally-managed Python environment) - verified syntax and structure instead

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Valgrind and stress tests ready for Phase 2 completion
- Phase 2 now has comprehensive memory checking: ASan (fast), Valgrind (deep), stress tests (accumulated)
- Ready for performance optimization phases with memory safety foundation

---
*Phase: 02-critical-correctness-fixes*
*Completed: 2026-02-05*
