---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - cbqs/src/solver_ctx.c
autonomous: true
must_haves:
  truths:
    - "solver_ctx.c compiles without _SC_NPROCESSORS_ONLN undeclared identifier error on Linux glibc"
    - "clock_gettime and CLOCK_MONOTONIC remain available (used in solver_ctx_create, solver_ctx_should_stop, solver_ctx_debug_stats)"
    - "All existing C tests pass (test_branching, test_searchlib, test_local_search, test_thread_safety)"
    - "prng.c is unaffected (does not use _SC_NPROCESSORS_ONLN, keeps its own _POSIX_C_SOURCE)"
  artifacts:
    - path: "cbqs/src/solver_ctx.c"
      provides: "Feature test macro enabling both clock_gettime and _SC_NPROCESSORS_ONLN"
      contains: "_GNU_SOURCE"
  key_links:
    - from: "cbqs/src/solver_ctx.c"
      to: "sysconf(_SC_NPROCESSORS_ONLN)"
      via: "_GNU_SOURCE feature test macro"
      pattern: "_GNU_SOURCE"
---

<objective>
Fix `_SC_NPROCESSORS_ONLN` undeclared identifier error in `solver_ctx.c` by replacing the `_POSIX_C_SOURCE 199309L` feature test macro with `_GNU_SOURCE`.

Purpose: `_SC_NPROCESSORS_ONLN` is a glibc extension not exposed under strict `_POSIX_C_SOURCE`. The current macro restricts visible symbols to POSIX 1993, which excludes processor count queries. `_GNU_SOURCE` is a superset that includes POSIX (>= 200809L, covering `clock_gettime`/`CLOCK_MONOTONIC`) plus GNU/BSD extensions (covering `_SC_NPROCESSORS_ONLN`). On macOS, `_SC_NPROCESSORS_ONLN` is available regardless of feature test macros. Note: this file previously used `_GNU_SOURCE` (phase 03) and was narrowed to `_POSIX_C_SOURCE` in phase 10 when the `u_int64_t` dependency was removed -- but that narrowing overlooked the `_SC_NPROCESSORS_ONLN` usage added in phase 04.

Output: Fixed `solver_ctx.c` that compiles cleanly on both Linux and macOS.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@cbqs/src/solver_ctx.c
@cbqs/src/prng.c (uses _POSIX_C_SOURCE but NOT _SC_NPROCESSORS_ONLN -- leave untouched)
@tests/CMakeLists.txt (test targets that compile solver_ctx.c: test_branching, test_searchlib, test_local_search, test_thread_safety)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace _POSIX_C_SOURCE with _GNU_SOURCE in solver_ctx.c and verify build</name>
  <files>cbqs/src/solver_ctx.c</files>
  <action>
In `cbqs/src/solver_ctx.c`, replace line 9:
```c
#define _POSIX_C_SOURCE 199309L
```
with:
```c
#define _GNU_SOURCE
```

Also update the comment on lines 6-8 to reflect the new macro:
```c
/* Feature test macro for GNU/POSIX extensions.
 * Enables clock_gettime, CLOCK_MONOTONIC, and _SC_NPROCESSORS_ONLN.
 * Must be defined before any includes to take effect.
 */
```

Do NOT modify `cbqs/src/prng.c` -- it only needs `clock_gettime`/`CLOCK_MONOTONIC` and `_POSIX_C_SOURCE 199309L` is correct and sufficient for that file.

After modifying the file, verify by:
1. Clean-building the CMocka test suite (which compiles solver_ctx.c in 4 test targets)
2. Running all tests to confirm no regressions
  </action>
  <verify>
Build and run all C tests:
```bash
cd tests && rm -rf build && mkdir build && cd build && cmake .. -DWERROR=ON && make -j$(nproc) && ctest --output-on-failure
```

All tests must pass, including the 4 targets that compile solver_ctx.c:
- test_branching
- test_searchlib
- test_local_search
- test_thread_safety

Additionally confirm the fix with a standalone compile check:
```bash
gcc -c cbqs/src/solver_ctx.c -o /dev/null -I cbqs/src -std=c17 -Wall -Wextra -Wpedantic -Werror
```
  </verify>
  <done>
- `solver_ctx.c` line 9 reads `#define _GNU_SOURCE` (not `_POSIX_C_SOURCE`)
- Comment above it documents the three features it enables
- `prng.c` still reads `#define _POSIX_C_SOURCE 199309L` (unchanged)
- All CMocka tests pass with `-DWERROR=ON`
- Standalone compile of solver_ctx.c succeeds with `-Werror`
  </done>
</task>

</tasks>

<verification>
- `grep -n '_GNU_SOURCE' cbqs/src/solver_ctx.c` shows line 9 match
- `grep -n '_POSIX_C_SOURCE' cbqs/src/solver_ctx.c` returns no matches
- `grep -n '_POSIX_C_SOURCE' cbqs/src/prng.c` still shows line 12 match (unchanged)
- All C tests pass: `cd tests/build && ctest --output-on-failure` returns 0
</verification>

<success_criteria>
- The `_SC_NPROCESSORS_ONLN` undeclared identifier error is resolved
- `clock_gettime` and `CLOCK_MONOTONIC` remain functional (timeout and debug stats work)
- No regressions in any existing test
- Only `solver_ctx.c` is modified; `prng.c` is untouched
</success_criteria>

<output>
After completion, create `.planning/quick/2-fix-sc-nprocessors-onln-undeclared-ident/2-SUMMARY.md`
</output>
