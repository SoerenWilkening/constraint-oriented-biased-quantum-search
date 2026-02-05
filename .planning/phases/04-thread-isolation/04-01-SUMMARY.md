---
phase: 04-thread-isolation
plan: 01
subsystem: prng
tags: [xoshiro256, prng, thread-local-storage, determinism]
dependency_graph:
  requires: []
  provides: [prng.h, prng.c, test_prng.c]
  affects: [04-02, 04-03, 04-04]
tech_stack:
  added: []
  patterns: [thread-local-storage, xoshiro256**, splitmix64, jump-function]
key_files:
  created: [cbqs/src/prng.h, cbqs/src/prng.c, tests/test_prng.c]
  modified: [tests/CMakeLists.txt]
decisions:
  - id: prng-tls
    choice: __thread keyword for thread-local storage
    rationale: Simpler and faster than pthread_key_t, supported on target platforms
  - id: prng-seeding
    choice: SplitMix64 for expanding 64-bit seed to 256-bit state
    rationale: Recommended by xoshiro authors, prevents all-zero state problem
  - id: prng-parallel
    choice: Jump function (2^128 steps) for parallel stream derivation
    rationale: Mathematically proven non-overlapping sequences, better than hash-based
  - id: prng-entropy
    choice: /dev/urandom with clock+pid fallback
    rationale: /dev/urandom is portable across Unix-like systems, fallback handles edge cases
metrics:
  duration: ~5m
  completed: 2026-02-05
---

# Phase 4 Plan 1: PRNG Module Summary

xoshiro256** PRNG with thread-local state, SplitMix64 seeding, and jump function for parallel stream derivation.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 7cd18bf | prng.h header with API declarations |
| 2 | d80cfdd | prng.c implementation |
| 3 | 7914d28 | Unit tests for PRNG correctness |

## What Was Built

### prng.h - API declarations
- `prng_state_t` struct (256-bit state = 4 x uint64_t)
- Thread-local state: `extern __thread prng_state_t g_prng_state`
- Initialization: `prng_seed()`, `prng_seed_from_state()`, `prng_seed_thread()`
- Generation: `prng_next()`, `prng_next_double()`, `prng_next_int()`
- Parallel streams: `prng_jump()` (advances state by 2^128)
- Entropy: `prng_get_entropy_seed()` for non-deterministic seeding

### prng.c - Implementation (211 lines)
- xoshiro256** algorithm with `rotl()` helper
- SplitMix64 for seeding (expands 64-bit seed to 256-bit state)
- `prng_next_double()` uses upper 53 bits for IEEE 754 precision
- Jump function with standard constants: `0x180ec6d33cfd0aba, ...`
- `prng_seed_thread()` copies master state and jumps N times
- `prng_get_entropy_seed()` tries /dev/urandom, falls back to clock+pid

### test_prng.c - Unit tests (9 tests, all passing)
1. Seeding produces non-zero state
2. `prng_next_double()` in [0.0, 1.0)
3. `prng_next_int()` in [0, max)
4. Same seed produces same sequence (determinism)
5. Different seeds produce different output
6. Jump function produces distinct parallel streams
7. Entropy seed returns non-zero, varying values
8. `prng_seed_from_state()` works correctly
9. Double generation is deterministic

## Design Decisions

### Thread-Local Storage
Used `__thread` keyword rather than `pthread_key_t`:
- Zero overhead after initialization
- Simpler API (no create/setspecific/getspecific)
- Supported on GCC/Clang for Linux/macOS

### SplitMix64 Seeding
Mandatory for xoshiro256** initialization:
- Expands 64-bit user seed to 256-bit state
- Guarantees non-zero state (prevents all-zero deadlock)
- Recommended by algorithm authors

### Jump Function for Parallel Streams
Uses 2^128 jump rather than hash-based derivation:
- Mathematically proven non-overlapping sequences
- Each thread gets independent stream of 2^128 values
- `prng_seed_thread(master, N)` jumps N times from master

### prng_next_double Precision
Uses `(prng_next() >> 11) * 0x1.0p-53`:
- 53 bits matches IEEE 754 double mantissa
- Uniformly distributed in [0.0, 1.0)
- Better than `/RAND_MAX` which wastes bits

## Deviations from Plan

### [Rule 3 - Blocking] Added _POSIX_C_SOURCE feature test macro
- **Found during:** Task 2 compilation
- **Issue:** `clock_gettime()` and `CLOCK_MONOTONIC` were undeclared
- **Fix:** Added `#define _POSIX_C_SOURCE 199309L` before includes
- **Files modified:** cbqs/src/prng.c

### [Rule 1 - Bug] Fixed cmocka assertion in test
- **Found during:** Task 3 build
- **Issue:** `assert_uint_equal` doesn't exist in cmocka 1.1.7
- **Fix:** Changed to `assert_true(a == b)` comparison
- **Files modified:** tests/test_prng.c

## Next Phase Readiness

**Ready for 04-02 (rand() Replacement):**
- prng.h declares all needed functions
- prng.c exports thread-local state
- prng_next_double() is direct drop-in for `rand()` patterns
- prng_seed_thread() ready for worker thread initialization

**Integration points for 04-03 (Thread Count Configuration):**
- prng_seed_thread() accepts thread_id parameter
- Jump function handles any thread count

**Integration points for 04-04 (API & Determinism Testing):**
- prng_get_entropy_seed() provides auto-seeding
- prng_seed_from_state() initializes master PRNG in ctx
