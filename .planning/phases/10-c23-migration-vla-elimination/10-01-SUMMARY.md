---
phase: 10-c23-migration-vla-elimination
plan: 01
subsystem: c-kernel
tags: [c23, stdbool, vla, portability, thread-local, stdint]

# Dependency graph
requires:
  - phase: 05-arena-allocator
    provides: arena_alloc/arena_reset pattern used for VLA replacement
provides:
  - stdbool.h migration (no manual bool macros)
  - CBQS_UNUSED and CBQS_THREAD_LOCAL portability macros
  - (void) parameter lists on all init functions and callback_t
  - Zero VLA declarations in C kernel
  - uint64_t replacing all BSD u_int64_t usage
affects: [10-02-strict-warnings, 11-callback-rework]

# Tech tracking
tech-stack:
  added: []
  patterns: [CBQS_UNUSED for unused params, CBQS_THREAD_LOCAL for TLS portability]

key-files:
  created: []
  modified:
    - cbqs/src/definitions.h
    - cbqs/src/intarray.h
    - cbqs/src/prng.h
    - cbqs/src/prng.c
    - cbqs/src/constraint.h
    - cbqs/src/constraint.c
    - cbqs/src/Expression.h
    - cbqs/src/Expression.c
    - cbqs/src/model.h
    - cbqs/src/model.c
    - cbqs/src/local_search.c
    - cbqs/src/solver_ctx.c
    - cbqs/src/test.c

key-decisions:
  - "CBQS_THREAD_LOCAL macro: MSVC->__declspec(thread), GCC/Clang->__thread, fallback->_Thread_local"
  - "CBQS_UNUSED macro: GCC/Clang->__attribute__((unused)), other->empty (MSVC uses /wd4100)"
  - "VLA replacement uses arena when ctx->arena available, falls back to malloc"
  - "Replaced _GNU_SOURCE with _POSIX_C_SOURCE 199309L in solver_ctx.c"

patterns-established:
  - "CBQS_UNUSED: use on intentionally unused parameters in new code"
  - "CBQS_THREAD_LOCAL: use instead of raw __thread for all thread-local declarations"
  - "Arena-first allocation: check ctx->arena first, fall back to malloc"

# Metrics
duration: 8min 28s
completed: 2026-02-08
---

# Phase 10 Plan 01: C23 Forward-Compatibility Summary

**stdbool.h migration, CBQS_UNUSED/CBQS_THREAD_LOCAL portability macros, (void) parameter lists, u_int64_t elimination, and last VLA replaced with arena allocation**

## Performance

- **Duration:** 8 min 28s
- **Started:** 2026-02-08T13:57:03Z
- **Completed:** 2026-02-08T14:05:31Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments
- Replaced manual #define true/false with stdbool.h in definitions.h -- C23-forward-compatible
- Added CBQS_UNUSED and CBQS_THREAD_LOCAL portability macros covering GCC, Clang, and MSVC
- Fixed callback_t typedef and all init functions to use explicit (void) parameter lists
- Eliminated the last VLA (int64_t remainings[C]) in local_search.c using arena/malloc pattern
- Replaced BSD-only u_int64_t with standard uint64_t, removing need for _GNU_SOURCE

## Task Commits

Each task was committed atomically:

1. **Task 1: Update definitions.h with portability macros and stdbool.h** - `02f31b8` (feat)
2. **Task 2: Fix remaining headers and sources for C23 compatibility** - `1cfde68` (feat)
3. **Task 3: Eliminate remaining VLA in local_search.c** - `f073b23` (feat)

## Files Created/Modified
- `cbqs/src/definitions.h` - Added stdbool.h, removed bool macros, added CBQS_UNUSED and CBQS_THREAD_LOCAL, fixed callback_t(void)
- `cbqs/src/intarray.h` - Replaced u_int64_t with uint64_t (removed #ifdef _WIN32 guard)
- `cbqs/src/prng.h` - Replaced __thread with CBQS_THREAD_LOCAL, added definitions.h include
- `cbqs/src/prng.c` - Replaced __thread with CBQS_THREAD_LOCAL
- `cbqs/src/constraint.h` - Fixed init_new_constraint(void)
- `cbqs/src/constraint.c` - Fixed init_new_constraint(void), fixed %zu -> %u for uint32_t
- `cbqs/src/Expression.h` - Fixed init_expression(void)
- `cbqs/src/Expression.c` - Fixed init_expression(void)
- `cbqs/src/model.h` - Fixed init_model(void)
- `cbqs/src/model.c` - Fixed init_model(void)
- `cbqs/src/local_search.c` - Replaced VLA with arena/malloc allocation, added cleanup on all exit paths
- `cbqs/src/solver_ctx.c` - Replaced _GNU_SOURCE with _POSIX_C_SOURCE 199309L
- `cbqs/src/test.c` - Fixed main(void)

## Decisions Made
- Used _POSIX_C_SOURCE 199309L (not _GNU_SOURCE) in solver_ctx.c since u_int64_t dependency is removed
- CBQS_UNUSED defined as empty on non-GCC/Clang compilers (MSVC users suppress via /wd4100)
- VLA replacement includes arena allocation when solver context is available, with malloc fallback

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- First cmake build's `make -j$(nproc)` output was silent (piped to tail); re-ran `make` without `-j` flag and build completed successfully with only pre-existing format warnings (Plan 02 scope)
- All 56 tests (15 project CMocka + 41 cmocka framework) passed cleanly

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All C23-deprecated patterns eliminated from C kernel
- Ready for Plan 02: strict warning flags (-Wall -Wextra -Wpedantic -Wvla) and sign comparison fixes
- Remaining warnings visible during build are format specifier issues (%lld vs %ld for int64_t) -- Plan 02 scope

## Self-Check: PASSED

All 13 modified files verified present. All 3 task commit hashes (02f31b8, 1cfde68, f073b23) verified in git log. SUMMARY.md exists.

---
*Phase: 10-c23-migration-vla-elimination*
*Completed: 2026-02-08*
