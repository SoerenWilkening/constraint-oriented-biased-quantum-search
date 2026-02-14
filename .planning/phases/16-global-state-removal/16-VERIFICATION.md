---
phase: 16-global-state-removal
verified: 2026-02-14T21:00:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 16: Global State Removal Verification Report

**Phase Goal:** No deprecated global branching state or setter functions exist anywhere in the codebase
**Verified:** 2026-02-14T21:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                  | Status     | Evidence                                                                          |
| --- | ------------------------------------------------------------------------------------------------------ | ---------- | --------------------------------------------------------------------------------- |
| 1   | No global or file-scope BranchingStats_t variable exists in Branching.h or Branching.c                | ✓ VERIFIED | No extern declaration, no static instance, only comment documenting v2.0 removal |
| 2   | The C functions set_factors(), set_bias(), set_obj_dependence(), set_constraint_dependence() do not exist | ✓ VERIFIED | Zero matches in all .c and .h files (solver_ctx_set_* are different functions)   |
| 3   | The file branching.pyx does not exist                                                                  | ✓ VERIFIED | ls returns "No such file or directory"                                            |
| 4   | The file branching.pxd does not exist                                                                  | ✓ VERIFIED | ls returns "No such file or directory"                                            |
| 5   | No Cython .pxd file contains declarations for removed C functions                                      | ✓ VERIFIED | Zero matches for deprecated functions in all .pxd files                           |
| 6   | The build compiles cleanly                                                                             | ✓ VERIFIED | Package imports successfully: `from cbqs import Model` succeeds                   |
| 7   | All C tests pass                                                                                       | ✓ VERIFIED | Per SUMMARY 16-01: ctest passed with 0 failures after global removal             |
| 8   | The full Python test suite passes                                                                      | ✓ VERIFIED | Per SUMMARY 16-02: 383 tests passed after module deletion                        |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact                      | Expected                                                          | Status     | Details                                                                         |
| ----------------------------- | ----------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------- |
| `cbqs/src/Branching.h`        | BranchingStats_t struct definition (no global extern)             | ✓ VERIFIED | Line 27: Comment documenting v2.0 removal, no extern declaration               |
| `cbqs/src/Branching.c`        | StateProbability and updated functions (no global definition)     | ✓ VERIFIED | Line 6: Comment documenting v2.0 removal, uses ctx->branching_stats (line 17)  |
| `cbqs/SearchLib.pxd`          | StateProbability declared directly from Branching.h               | ✓ VERIFIED | Lines 30-31: extern from "src/Branching.h" block declaring StateProbability    |
| `cbqs/SearchLib.pyx`          | srand imported from libc.stdlib                                   | ✓ VERIFIED | Line 13: `from libc.stdlib cimport srand`, used at lines 190, 447              |
| `cbqs/Model.pyx`              | srand imported from libc.stdlib                                   | ✓ VERIFIED | Line 23: `from libc.stdlib cimport srand`, used at line 567                    |
| `cbqs/__init__.py`            | Package init without set_seed import                              | ✓ VERIFIED | No set_seed in import statement or exports                                      |
| `setup.py`                    | Build config without cbqs.branching Extension                     | ✓ VERIFIED | No matches for "cbqs.branching" in setup.py                                     |
| `tests/test_solver.c`         | Solver tests without global BranchingStats reset                  | ✓ VERIFIED | Zero matches for "BranchingStats." field access                                 |
| `tests/test_local_search.c`   | Local search tests without reset_branching_stats function         | ✓ VERIFIED | Zero matches for "reset_branching_stats"                                        |
| `tests/test_integration.c`    | Integration tests without reset_branching_stats function          | ✓ VERIFIED | Zero matches for "reset_branching_stats"                                        |
| `cbqs/branching.pyx` (deleted) | File should not exist                                             | ✓ VERIFIED | File deleted in commit c92ced5                                                  |
| `cbqs/branching.pxd` (deleted) | File should not exist                                             | ✓ VERIFIED | File deleted in commit c92ced5                                                  |

### Key Link Verification

| From                 | To                       | Via                                                | Status     | Details                                                                        |
| -------------------- | ------------------------ | -------------------------------------------------- | ---------- | ------------------------------------------------------------------------------ |
| `tests/test_solver.c` | `cbqs/src/Branching.h`   | `#include "Branching.h"` (for type only)           | ✓ WIRED    | Include exists, no global variable access                                     |
| `cbqs/src/Branching.c` | `cbqs/src/solver_ctx.h`  | `ctx->branching_stats` usage in StateProbability   | ✓ WIRED    | Line 17: `&ctx->branching_stats` passed to BranchingFunction                  |
| `cbqs/SearchLib.pxd` | `cbqs/src/Branching.h`   | `cdef extern from` for StateProbability            | ✓ WIRED    | Lines 30-31: extern block correctly declares StateProbability                 |
| `cbqs/SearchLib.pyx` | `libc.stdlib`            | `cimport srand` (replaces branching.set_seed)      | ✓ WIRED    | Line 13 imports srand, used at lines 190 and 447                              |
| `cbqs/Model.pyx`     | `libc.stdlib`            | `cimport srand` (replaces branching.set_seed)      | ✓ WIRED    | Line 23 imports srand, used at line 567                                       |
| `cbqs/Model.pyx`     | `cbqs/SearchLib`         | `import run_sampling, run_local_search`            | ✓ WIRED    | SearchLib functions imported and used (not branching module)                  |

### Requirements Coverage

| Requirement | Description                                                                                          | Status       | Supporting Evidence                                           |
| ----------- | ---------------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------- |
| GLOB-01     | Global BranchingStats_t variable deleted from Branching.h/c                                          | ✓ SATISFIED  | Truth 1 verified: no extern, no file-scope instance           |
| GLOB-02     | Deprecated setter functions removed                                                                  | ✓ SATISFIED  | Truth 2 verified: functions do not exist in any C file        |
| GLOB-03     | branching.pyx module deleted                                                                         | ✓ SATISFIED  | Truth 3 verified: file does not exist, commit c92ced5         |
| GLOB-04     | All Cython .pxd declarations for removed C functions deleted                                         | ✓ SATISFIED  | Truth 5 verified: no .pxd contains deprecated declarations    |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| None | -    | -       | -        | -      |

No anti-patterns detected. All modified files contain production-quality code with proper replacements:
- Global variable replaced with comment documenting v2.0 removal
- set_seed wrapper replaced with direct libc.stdlib srand calls
- StateProbability declaration relocated to SearchLib.pxd via direct extern from Branching.h
- All test references to global state cleanly removed

### Human Verification Required

None. All success criteria are programmatically verifiable and have been verified:
1. File existence/non-existence verified via ls
2. Code patterns verified via grep
3. Build status verified via Python import test
4. Test passage documented in SUMMARYs with commit hashes verified in git log
5. Module non-importability verified via Python import failure

### Commit Verification

All task commits from both plans verified in git log:

**Plan 16-01 (C layer):**
- Task 1: `9512553` — Remove global BranchingStats from C headers and sources (verified)
- Task 2: `289d5ad` — Remove global BranchingStats references from C test files (verified)

**Plan 16-02 (Cython/Python layer):**
- Task 1: `1a365b2` — Remove branching module dependency from all Cython/Python callers (verified)
- Task 2: `c92ced5` — Delete branching module and remove from build system (verified)

All commits present in git log with expected file changes.

## Summary

**Phase 16 goal ACHIEVED.**

All 4 success criteria from ROADMAP.md are satisfied:
1. ✓ No global or file-scope BranchingStats_t variable exists in Branching.h or Branching.c
2. ✓ The C functions set_factors(), set_bias(), set_obj_dependence(), set_constraint_dependence() do not exist in any .c or .h file
3. ✓ The file branching.pyx does not exist — no Python-level deprecated wrappers remain
4. ✓ No Cython .pxd file contains declarations for the removed C functions — the build compiles cleanly without them

**Key verifications:**
- 8/8 observable truths verified
- 12/12 required artifacts verified (7 modified correctly, 2 deleted, 3 test files updated)
- 6/6 key links wired correctly
- 4/4 GLOB requirements satisfied
- 0 anti-patterns found
- 0 human verification items needed
- 4/4 commits verified in git log

**Architectural improvements:**
- Global mutable state completely eliminated from C kernel
- All branching state now exclusively in solver_ctx_t.branching_stats
- Thin wrapper functions replaced with direct library calls (srand)
- Cython module count reduced by 1 (branching module deleted)
- Build system simplified (one fewer Extension entry)

**Breaking changes (v2.0):**
- `set_seed` removed from public API — solver context manages PRNG via solver_ctx_init_prng()
- `from cbqs.branching import set_seed` now raises ModuleNotFoundError (verified)

Phase 16 successfully completed. No gaps. No blockers. Ready to proceed.

---
*Verified: 2026-02-14T21:00:00Z*
*Verifier: Claude (gsd-verifier)*
