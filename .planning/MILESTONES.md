# Project Milestones: CBQS

## v1.1 Bug Fixes & Polish (Shipped: 2026-02-08)

**Delivered:** Fixed all known bugs, eliminated tech debt, and cleaned up code quality issues from v1.0 with zero breaking changes.

**Phases completed:** 9-13 (10 plans total)

**Key accomplishments:**

- Fixed all SATISFY mode crashes — solve completes without TypeError, history tracks satisfaction count, objective_value returns None
- Migrated C kernel to C23-compatible patterns — stdbool.h, portability macros, zero VLAs, zero GCC 15 warnings with -Werror in CI
- Reworked callback system to per-thread state — concurrent solves produce independent history, new 2-tuple (value, elapsed) format
- Added set_param/get_param API with strict validation — branching parameters propagate to both solvers, deprecated setters emit warnings
- Cleaned ~400 lines of dead code — removed unused functions, commented-out code, unguarded printfs; added field annotations to major solver functions
- Hardened local_search with pthread_mutex_trylock for non-blocking global_opt write protection

**Stats:**

- 84 files modified, 10,946 insertions, 1,858 deletions
- 15,143 lines of C/Python/Cython (tracked)
- 5 phases, 10 plans
- 3 days from v1.0 to v1.1 ship (2026-02-06 -> 2026-02-08)
- 304 tests passing (51 new), 56 C tests, CI with ASan/Valgrind/ThreadSanitizer/-Werror

**Git range:** `docs(09)` -> `docs(13)`

**Audit:** 21/21 requirements satisfied, 0 gaps, 3 tech debt items (0 blockers)

**What's next:** v1.2 or v2.0 — Remove deprecated BranchingStats API (breaking), extract local_search_params_t, or new feature work

---

## v1.0 Stabilization & Optimization (Shipped: 2026-02-06)

**Delivered:** Took the CBQS solver from a functional but buggy state to a stable, memory-safe, thread-safe engine with comprehensive testing, input validation, and structured diagnostics.

**Phases completed:** 1-8 (35 plans total)

**Key accomplishments:**

- Established CMocka + pytest test suite with CI (ASan, Valgrind, ThreadSanitizer) providing correctness baseline for all changes
- Fixed critical correctness bugs: use-after-free, realloc condition, Expression mutation — solver now produces reliable results
- Introduced solver_ctx_t architecture eliminating global mutable state; ThreadSanitizer reports zero data races
- Per-thread xoshiro256** PRNG with deterministic reproducibility via seed/num_threads API
- Eliminated all memory leaks and replaced VLAs with heap buffers; arena allocator and dynamic expressions optimize hot paths
- Added comprehensive input validation and post-solve verification with structured OptimizeResult diagnostics

**Stats:**

- 176 files created/modified, 29,622 insertions
- 15,211 lines of C/Python/Cython (tracked)
- 8 phases, 35 plans
- 3 days from start to ship (2026-02-04 → 2026-02-06)
- 58+ C tests, 200+ Python tests, 7 benchmarks

**Git range:** `docs(01)` → `docs(08-02)`

**Audit:** 15/15 requirements satisfied, 0 gaps, 6 tech debt items (0 blockers)

**What's next:** v2.0 — Branching extensions, solver extensions, or user experience improvements

---

## v2.0 API Cleanup (Shipped: 2026-02-14)

**Delivered:** First breaking release — unified the branching model into a single-array design, removed all solve() keyword arguments in favor of set_param(), and eliminated all deprecated global state.

**Phases completed:** 14-17 (8 plans, 19 tasks)

**Key accomplishments:**

- Unified branching model — replaced dual obj_dependent/constraint_dependent arrays with single `branching_weights` array and 3-term formula with L1 normalization
- Zero-arg solve() — removed all 14 solve() keyword arguments; all configuration now flows through set_param()/get_param() with type coercion and validation
- Global state elimination — deleted global BranchingStats_t, deprecated C setters, and entire branching.pyx module
- Parameter registry — _PARAM_DEFS registry with 20 params, strict coercion, defaults, and _get_effective() helper
- Full test coverage — 446 tests (390 Python + 56 C) with new branching_weights edge case, determinism, and lifecycle tests
- Valgrind-verified memory safety — zero leaks for branching_weights allocation, deallocation, and reallocation across solve lifecycles

**Stats:**

- 54 files modified, 5,908 insertions, 716 deletions
- 4 phases, 8 plans, ~56 minutes execution time
- 446 tests passing (390 Python + 56 C), 100% pass rate
- 1 day (2026-02-14)

**Git range:** `feat(14-01)` → `feat(17-02)`

**Audit:** 17/17 requirements satisfied, 0 gaps, 2 tech debt items (0 blockers)

**What's next:** Next milestone TBD — ML-based branching, adaptive branching, or solver extensions

---


## v2.1 Code Audit & Optimization (Shipped: 2026-02-26)

**Delivered:** Comprehensive codebase cleanup — eliminated all dead code, unified API naming across C/Cython/Python, adopted incremental evaluation, modernized build system, and filled all documentation gaps.

**Phases completed:** 18-24 (14 plans total)

**Key accomplishments:**

- Removed all 4 orphaned model_t fields and dead/commented-out code across C, Cython, and Python layers
- Adopted incremental constraint evaluation in local_search using adjusted_constraint_violation() with benchmark infrastructure
- Unified look_ahead_factor naming across all C/Cython/Python layers, audited _PARAM_DEFS, aligned Cython types
- Deduplicated C sources via build_clib static library, removed pandas dependency, bumped to v2.1.0
- Added NumPy-style docstrings to all public Python methods and algorithm block comments to C kernel
- Created VERIFICATION.md for all phases with 18/18 requirements confirmed

**Stats:**

- 81 files modified, 8,109 insertions, 674 deletions
- 7 phases, 14 plans
- 2 days (2026-02-25 → 2026-02-26), 48 commits
- 446 tests passing (390 Python + 56 C), 100% pass rate

**Git range:** `feat(18)` → `docs(v2.1)`

**Audit:** 18/18 requirements satisfied, 0 gaps, 5 tech debt items (0 blockers, all cosmetic)

**What's next:** Next milestone TBD — ML-based branching, adaptive branching, multi-heuristic solver, or solver extensions

---

