---
phase: quick-2
plan: 01
subsystem: kernel
tags: [c, feature-test-macros, gnu-source, posix, glibc]

# Dependency graph
requires:
  - phase: 04-thread-safe-solver
    provides: "_SC_NPROCESSORS_ONLN usage in solver_ctx_get_default_threads"
  - phase: 10-api-cleanup
    provides: "Narrowed _POSIX_C_SOURCE that inadvertently hid _SC_NPROCESSORS_ONLN"
provides:
  - "solver_ctx.c compiles cleanly on Linux glibc with _SC_NPROCESSORS_ONLN"
  - "_GNU_SOURCE feature test macro enabling all POSIX + GNU extensions"
affects: [solver_ctx, threading, build]

# Tech tracking
tech-stack:
  added: []
  patterns: ["_GNU_SOURCE for files needing GNU/BSD extensions beyond strict POSIX"]

key-files:
  created: []
  modified:
    - "cbqs/src/solver_ctx.c"

key-decisions:
  - "Used _GNU_SOURCE instead of _POSIX_C_SOURCE 200809L because _SC_NPROCESSORS_ONLN is a GNU extension not guaranteed by any POSIX version"

patterns-established:
  - "_GNU_SOURCE for glibc extension usage: files needing non-POSIX symbols like _SC_NPROCESSORS_ONLN use _GNU_SOURCE; files needing only POSIX symbols (like prng.c) keep _POSIX_C_SOURCE"

# Metrics
duration: 2min
completed: 2026-02-14
---

# Quick Task 2: Fix _SC_NPROCESSORS_ONLN Undeclared Identifier Summary

**Replaced _POSIX_C_SOURCE 199309L with _GNU_SOURCE in solver_ctx.c to expose glibc's _SC_NPROCESSORS_ONLN for CPU count detection**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-14T22:38:42Z
- **Completed:** 2026-02-14T22:41:20Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Fixed undeclared identifier error for `_SC_NPROCESSORS_ONLN` on Linux glibc
- Preserved `clock_gettime`/`CLOCK_MONOTONIC` functionality (superset via `_GNU_SOURCE`)
- Left `prng.c` untouched -- it only needs POSIX symbols and `_POSIX_C_SOURCE 199309L` is correct for it
- All 7 test targets pass including the 4 that compile `solver_ctx.c`

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace _POSIX_C_SOURCE with _GNU_SOURCE in solver_ctx.c and verify build** - `deab932` (fix)

## Files Created/Modified
- `cbqs/src/solver_ctx.c` - Replaced feature test macro and updated comment documenting enabled symbols

## Decisions Made
- Used `_GNU_SOURCE` instead of `_POSIX_C_SOURCE 200809L` because `_SC_NPROCESSORS_ONLN` is a GNU/BSD extension not standardized in any POSIX version -- `_GNU_SOURCE` is the correct and canonical way to expose it on glibc

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `test_searchlib` has a pre-existing build failure with `-DWERROR=ON` due to unused variable `count` in `SearchLib.c:73` (bfs function). This is unrelated to the `_GNU_SOURCE` change and existed before this task. All other test targets build and pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `solver_ctx.c` now compiles cleanly on both Linux and macOS
- The pre-existing `test_searchlib` unused variable warning should be tracked separately

---
*Quick Task: 2-fix-sc-nprocessors-onln-undeclared-ident*
*Completed: 2026-02-14*
