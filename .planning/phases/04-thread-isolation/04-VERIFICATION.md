---
phase: 04-thread-isolation
verified: 2026-02-05T16:40:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 4: Thread Isolation Verification Report

**Phase Goal:** Each worker thread operates with fully isolated random state and the user controls parallelism at runtime

**Verified:** 2026-02-05T16:40:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each worker thread uses its own PRNG instance (no calls to global rand()) | ✓ VERIFIED | Zero rand() calls in cbqs/src/; 7 files include prng.h and use prng_next_double/int |
| 2 | Seeding each thread with a known seed produces deterministic results | ✓ VERIFIED | Test test_same_seed_same_result passes; test_seed_used_enables_reproduction passes |
| 3 | Thread count is a runtime parameter (not compile-time NUMThreads) | ✓ VERIFIED | NUMThreads constant removed; local_search uses ctx->num_threads_used; dynamic malloc |
| 4 | User can specify via Model API or solver call | ✓ VERIFIED | Model.seed and Model.num_threads properties exist with validation; wired to solver_ctx |
| 5 | Same problem + same seed + same thread count = identical results across runs | ✓ VERIFIED | All determinism tests pass (18/18); test suite demonstrates reproducibility |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| cbqs/src/prng.h | PRNG API declarations | ✓ VERIFIED | 146 lines, declares 8 functions (prng_seed, prng_next_double, prng_jump, etc.) |
| cbqs/src/prng.c | xoshiro256** implementation | ✓ VERIFIED | 211 lines, contains xoshiro256** algorithm, rotl(), JUMP constants, __thread storage |
| cbqs/src/solver_ctx.h | Extended with seed/num_threads | ✓ VERIFIED | Lines 46-59: seed, seed_used, num_threads, num_threads_used, master_prng fields |
| cbqs/src/solver_ctx.c | solver_ctx_init_prng() implementation | ✓ VERIFIED | Implements init_prng and get_default_threads; reads CBQS_THREADS env var |
| cbqs/src/local_search.c | Dynamic thread allocation | ✓ VERIFIED | Lines 290-302: num_threads from ctx, malloc for data/threads arrays, free at line 362-364 |
| cbqs/SearchLib.pyx | Wires seed to ctx | ✓ VERIFIED | Lines 166, 250: calls solver_ctx_init_prng(); lines 216, 259: stores seed_used back |
| cbqs/Model.pyx | Exposes seed properties | ✓ VERIFIED | Lines 360-398: seed, seed_used (read-only), num_threads properties with validation |
| tests/test_prng.c | PRNG unit tests | ✓ VERIFIED | 325 lines, 9 tests, all passing: determinism, range checks, jump function |
| tests/test_determinism.py | Determinism tests | ✓ VERIFIED | 187 lines, 18 tests, all passing: same seed = same result, seed_used tracking |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| solver.c | prng_next_double() | Function calls | ✓ WIRED | 6 calls to prng_next_double() replacing rand() |
| quantum_search.c | prng_next_double/int() | Function calls | ✓ WIRED | 2 calls (prng_next_double, prng_next_int) |
| SearchLib.c | prng_next_int() | Function call | ✓ WIRED | 1 call replacing rand() |
| local_search.c | prng_next_int() | Function call | ✓ WIRED | 1 call in move_list() shuffle |
| local_search.c | ctx->num_threads_used | Field access | ✓ WIRED | Line 290: reads num_threads_used; dynamic malloc follows |
| local_search.c (worker) | prng_seed_thread() | Thread initialization | ✓ WIRED | Line 154: each thread calls prng_seed_thread(ctx->master_prng, thread_id) |
| SearchLib.pyx | solver_ctx_init_prng() | C function call | ✓ WIRED | Called in run_sampling (line 166) and run_local_search (line 250) after ctx creation |
| SearchLib.pyx | mod._seed_used | Assignment | ✓ WIRED | Lines 216, 259: stores ctx.seed_used to model after solve |
| Model.pyx | seed/num_threads | Properties | ✓ WIRED | Properties implemented with getters/setters, validation, docstrings |

### Requirements Coverage

| Requirement | Description | Status | Blocking Issue |
|-------------|-------------|--------|----------------|
| THRD-03 | Replace global rand() with per-thread PRNG | ✓ SATISFIED | All rand() calls replaced; __thread storage verified |
| THRD-04 | Make thread count configurable | ✓ SATISFIED | NUMThreads removed; ctx->num_threads_used runtime parameter |

### Anti-Patterns Found

**None detected.** Scanned artifacts show:
- No TODO/FIXME comments in prng.c, prng.h
- No placeholder content in implementation
- No empty returns or stub patterns
- Proper memory management: malloc paired with free in local_search.c (lines 301-302, 362-364)
- All functions have substantive implementations

### Human Verification Required

**None required for goal achievement.** Automated verification sufficient:
- Determinism tests demonstrate reproducibility across runs
- Thread isolation verified via unit tests (jump function produces distinct streams)
- API integration verified via 18 passing tests

---

## Detailed Verification Results

### Level 1: Existence
All required artifacts exist:
- ✓ cbqs/src/prng.h (146 lines)
- ✓ cbqs/src/prng.c (211 lines)
- ✓ cbqs/src/solver_ctx.h (extended)
- ✓ cbqs/src/solver_ctx.c (extended)
- ✓ cbqs/src/local_search.c (modified)
- ✓ cbqs/SearchLib.pyx (modified)
- ✓ cbqs/Model.pyx (modified)
- ✓ tests/test_prng.c (325 lines)
- ✓ tests/test_determinism.py (187 lines)

### Level 2: Substantive
All artifacts have real implementations:
- ✓ prng.c: xoshiro256** algorithm correctly implemented with rotl() helper, JUMP constants (0x180ec6d33cfd0aba...), SplitMix64 seeding
- ✓ prng.h: 8 function declarations with complete Doxygen documentation
- ✓ solver_ctx.h: 5 new fields (seed, seed_used, num_threads, num_threads_used, master_prng)
- ✓ solver_ctx.c: solver_ctx_init_prng() resolves auto-values, solver_ctx_get_default_threads() reads CBQS_THREADS
- ✓ local_search.c: Dynamic allocation (malloc), runtime thread count, worker PRNG init at line 154
- ✓ SearchLib.pyx: solver_ctx_init_prng() called in both entry points, seed_used stored back
- ✓ Model.pyx: Properties with validation (seed must be int or None, num_threads >= 1)
- ✓ test_prng.c: 9 comprehensive tests (determinism, range, jump function)
- ✓ test_determinism.py: 18 tests (9 determinism, 9 validation)

### Level 3: Wired
All critical connections verified:
- ✓ rand() → prng_next_double/int: 12 replacements across 5 files (solver.c, quantum_search.c, SearchLib.c, approximate_state_sampler.c, local_search.c)
- ✓ NUMThreads → ctx->num_threads_used: Constant removed, runtime read at line 290
- ✓ Worker threads → prng_seed_thread(): Line 154 in explore_neighbourhood()
- ✓ Model properties → solver_ctx: SearchLib.pyx wires seed and num_threads to ctx before init
- ✓ solver_ctx → Model.seed_used: SearchLib.pyx stores ctx.seed_used to mod._seed_used after solve

### Test Execution Results

**C Unit Tests (test_prng):**
```
[==========] tests: Running 9 test(s).
[ RUN      ] test_prng_seed_produces_nonzero_state
[       OK ] test_prng_seed_produces_nonzero_state
[ RUN      ] test_prng_next_double_in_range
[       OK ] test_prng_next_double_in_range
[ RUN      ] test_prng_next_int_in_range
[       OK ] test_prng_next_int_in_range
[ RUN      ] test_prng_deterministic_with_same_seed
[       OK ] test_prng_deterministic_with_same_seed
[ RUN      ] test_prng_different_seeds_produce_different_output
[       OK ] test_prng_different_seeds_produce_different_output
[ RUN      ] test_prng_jump_produces_distinct_streams
[       OK ] test_prng_jump_produces_distinct_streams
[ RUN      ] test_prng_get_entropy_seed_nonzero
[       OK ] test_prng_get_entropy_seed_nonzero
[ RUN      ] test_prng_seed_from_state_works
[       OK ] test_prng_seed_from_state_works
[ RUN      ] test_prng_consistency_across_functions
[       OK ] test_prng_consistency_across_functions
[==========] tests: 9 test(s) run.
[  PASSED  ] 9 test(s).
```

**Python Integration Tests (test_determinism.py):**
```
============================== test session starts ==============================
tests/test_determinism.py::TestDeterminism::test_same_seed_same_result PASSED [  5%]
tests/test_determinism.py::TestDeterminism::test_seed_used_populated PASSED [ 11%]
tests/test_determinism.py::TestDeterminism::test_seed_used_matches_set_seed PASSED [ 16%]
tests/test_determinism.py::TestDeterminism::test_seed_used_enables_reproduction PASSED [ 22%]
tests/test_determinism.py::TestDeterminism::test_different_seeds_can_differ PASSED [ 27%]
tests/test_determinism.py::TestDeterminism::test_num_threads_property[1] PASSED [ 33%]
tests/test_determinism.py::TestDeterminism::test_num_threads_property[2] PASSED [ 38%]
tests/test_determinism.py::TestDeterminism::test_num_threads_property[4] PASSED [ 44%]
tests/test_determinism.py::TestDeterminism::test_env_var_threads PASSED  [ 50%]
tests/test_determinism.py::TestSeedValidation::test_seed_accepts_int PASSED [ 55%]
tests/test_determinism.py::TestSeedValidation::test_seed_accepts_none PASSED [ 61%]
tests/test_determinism.py::TestSeedValidation::test_seed_rejects_float PASSED [ 66%]
tests/test_determinism.py::TestSeedValidation::test_seed_rejects_string PASSED [ 72%]
tests/test_determinism.py::TestSeedValidation::test_num_threads_accepts_positive_int PASSED [ 77%]
tests/test_determinism.py::TestSeedValidation::test_num_threads_accepts_none PASSED [ 83%]
tests/test_determinism.py::TestSeedValidation::test_num_threads_rejects_zero PASSED [ 88%]
tests/test_determinism.py::TestSeedValidation::test_num_threads_rejects_negative PASSED [ 94%]
tests/test_determinism.py::TestSeedValidation::test_num_threads_rejects_float PASSED [100%]

============================== 18 passed in 1.31s
```

### Implementation Quality Checks

**Thread-Local Storage:**
- ✓ `__thread` keyword used for g_prng_state and g_prng_initialized (prng.c lines 24-25)
- ✓ Each thread has independent state via TLS
- ✓ No global mutable state for random generation

**xoshiro256** Correctness:**
- ✓ rotl() helper function present (line 38)
- ✓ State update follows reference implementation (lines 70-78)
- ✓ Scrambler: rotl(s[1] * 5, 7) * 9 (line 120)
- ✓ JUMP constants match reference (lines 157-160)

**Memory Management:**
- ✓ Dynamic allocation in local_search.c: malloc at lines 301-302
- ✓ Proper cleanup: free at lines 362-364
- ✓ No leaks detected in modified code

**API Design:**
- ✓ seed = None → auto-generate (entropy-based)
- ✓ num_threads = None → auto-detect (sysconf)
- ✓ seed_used populated for reproducibility
- ✓ CBQS_THREADS env var support

---

## Conclusion

**Status: PASSED**

All 5 observable truths verified. All required artifacts exist, are substantive, and properly wired. All tests pass (9 C unit tests, 18 Python integration tests). No anti-patterns or stub code detected.

Phase 4 goal achieved: Each worker thread operates with fully isolated random state (thread-local xoshiro256** PRNG), and the user controls parallelism at runtime (Model.seed, Model.num_threads properties). Same seed + same thread count produces identical results across runs (verified by test suite).

Requirements THRD-03 and THRD-04 satisfied.

---

_Verified: 2026-02-05T16:40:00Z_
_Verifier: Claude (gsd-verifier)_
