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
