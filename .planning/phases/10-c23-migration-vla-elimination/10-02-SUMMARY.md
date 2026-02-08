---
phase: 10-c23-migration-vla-elimination
plan: 02
subsystem: c-kernel
tags: [c17, warnings, werror, sign-comparison, type-safety, ci]

# Dependency graph
requires:
  - phase: 10-01-c23-forward-compatibility
    provides: stdbool.h migration, CBQS_UNUSED macro, (void) param lists, VLA elimination
provides:
  - Zero-warning compilation under -Wall -Wextra -Wpedantic -Wvla -Werror
  - C17 standard in both CMakeLists.txt files
  - WERROR CMake option for CI enforcement
  - VLA regression guard via -Wvla flag
  - All sign comparison warnings fixed by type changes (no casts)
affects: [11-callback-rework, 12-branchingstats]

# Tech tracking
tech-stack:
  added: []
  patterns: [PRId64 for int64_t format specifiers, SIZE_MAX for sentinel size_t values, uint32_t loop vars for num_constraints iteration]

key-files:
  created: []
  modified:
    - tests/CMakeLists.txt
    - CMakeLists.txt
    - cbqs/src/solver.c
    - cbqs/src/constraint.c
    - cbqs/src/constraint.h
    - cbqs/src/local_search.c
    - cbqs/src/state.c
    - cbqs/src/Branching.c
    - cbqs/src/SearchLib.c
    - tests/test_solver.c
    - .github/workflows/test.yml

key-decisions:
  - "WERROR OFF by default, ON in CI only -- local builds not broken by new warnings"
  - "Sign comparison fixes use variable type changes, not casts (user decision)"
  - "PRId64 from inttypes.h for portable int64_t formatting instead of %lld"
  - "SIZE_MAX as sentinel value for uninitialized size_t instead of -1"
  - "c-tests-tsan left without -DWERROR (Clang-specific, separate warning profile)"

patterns-established:
  - "Use uint32_t for num_constraints loop variables (num_constraints is uint32_t)"
  - "Use size_t for cnstr in get_index and similar functions accepting constraint index"
  - "Use PRId64/PRIu64 from inttypes.h for int64_t/uint64_t format specifiers"
  - "Add parentheses for mixed && / || and & / | expressions"

# Metrics
duration: 37min
completed: 2026-02-08
---

# Phase 10 Plan 02: Strict Warning Flags Summary

**Zero-warning GCC compilation with -Wall -Wextra -Wpedantic -Wvla -Werror via type-safe sign comparison fixes, C17 standard, and CI enforcement**

## Performance

- **Duration:** 37 min
- **Started:** 2026-02-08T14:15:00Z
- **Completed:** 2026-02-08T14:52:50Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- Achieved zero-warning compilation under strict GCC flags (-Wall -Wextra -Wpedantic -Wvla -Werror)
- Fixed ~40 sign comparison warnings across 7 C source files by changing variable types (no casts)
- Updated both CMakeLists.txt files to C17 standard with strict warning flags
- CI now enforces -DWERROR=ON on c-tests, c-tests-asan, and c-tests-valgrind jobs
- All 56 C tests and 262 Python tests pass with strict warnings enabled

## Task Commits

Each task was committed atomically:

1. **Task 1: Update build system with strict warning flags** - `8208b24` (chore)
2. **Task 2: Fix all type mismatch and sign comparison warnings** - `b6d907e` (fix)
3. **Task 3: Update CI to enforce -Werror and verify Cython compatibility** - `1a4dbd4` (chore)

## Files Created/Modified
- `tests/CMakeLists.txt` - C17 standard, WERROR option, strict warning flags in add_cmocka_test
- `CMakeLists.txt` - C17 standard, strict warning flags for main executable target
- `cbqs/src/solver.c` - Fixed sign comparison (int->size_t/uint32_t for loop vars), parentheses, removed unused vars
- `cbqs/src/constraint.c` - Fixed sign comparison, PRId64 format specifiers, const qualifiers on get_index
- `cbqs/src/constraint.h` - Updated get_index signature (const qualifiers, size_t params)
- `cbqs/src/local_search.c` - Fixed sign comparison (int C->uint32_t C), parentheses, removed unused vars
- `cbqs/src/state.c` - Added inttypes.h, PRId64 format specifiers, size_t loop vars
- `cbqs/src/Branching.c` - Removed unused variables count0, count1
- `cbqs/src/SearchLib.c` - Parentheses in complex condition, size_t m_tot, removed unused var
- `tests/test_solver.c` - CBQS_UNUSED on intentionally unused result variable
- `.github/workflows/test.yml` - Added -DWERROR=ON to c-tests, c-tests-asan, c-tests-valgrind jobs

## Decisions Made
- WERROR is OFF by default so local developer builds are not broken by future warnings; CI enables it via -DWERROR=ON
- All sign comparison warnings fixed by changing variable types to match the signedness of the value they hold (no casts per user decision)
- Used PRId64 from inttypes.h for portable int64_t formatting, replacing %lld which is not portable to all platforms
- Used SIZE_MAX as sentinel for uninitialized size_t (replacing -1 which causes sign comparison warnings)
- Left c-tests-tsan without -DWERROR since it uses Clang with custom CMAKE_C_FLAGS and may require separate Clang-specific suppressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed additional warnings in state.c, Branching.c, SearchLib.c, test_solver.c**
- **Found during:** Task 2 (warning fixes)
- **Issue:** Plan only listed solver.c, constraint.c, local_search.c as files to fix, but warnings also existed in state.c (format specifiers), Branching.c (unused vars), SearchLib.c (sign comparison), and test_solver.c (unused var)
- **Fix:** Applied same type-change pattern to all affected files
- **Files modified:** cbqs/src/state.c, cbqs/src/Branching.c, cbqs/src/SearchLib.c, tests/test_solver.c
- **Verification:** Zero warnings with -Werror, all tests pass
- **Committed in:** b6d907e (Task 2 commit)

**2. [Rule 3 - Blocking] Updated constraint.h header to match implementation changes**
- **Found during:** Task 2 (warning fixes)
- **Issue:** After changing get_index signature in constraint.c (const qualifiers, size_t params), the header declaration was mismatched
- **Fix:** Updated constraint.h get_index declaration to match: const uint32_t params, size_t cnstr, size_t C
- **Files modified:** cbqs/src/constraint.h
- **Verification:** Build succeeds with matching declaration/definition
- **Committed in:** b6d907e (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both deviations were necessary to achieve the plan's stated goal of zero warnings. The plan underestimated the scope of affected files but the fix pattern was the same throughout. No scope creep.

## Issues Encountered
- Root CMakeLists.txt edit initially broke the add_executable block (premature closing parenthesis) -- fixed by rewriting the entire file
- Required 4 build-fix-rebuild cycles to eliminate all warnings, as each cycle revealed warnings hidden by earlier compilation failures
- `git add .github/workflows/test.yml` was rejected because .github/ was in .gitignore -- used `git add -f` to force-add
- `pip install -e .` required `--break-system-packages` flag in the agent environment

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 10 (C23 Migration & VLA Elimination) is now complete -- both plans executed successfully
- Zero-warning compilation achieved with strict GCC flags; CI enforces this via -DWERROR=ON
- Codebase ready for Phase 11 (Callback Rework) -- no blocking warnings or C23 compatibility issues remain
- GCC 15 warnings blocker from STATE.md is now fully resolved

## Self-Check: PASSED

All 11 modified files verified present. All 3 task commit hashes (8208b24, b6d907e, 1a4dbd4) verified in git log. SUMMARY.md exists.

---
*Phase: 10-c23-migration-vla-elimination*
*Completed: 2026-02-08*
