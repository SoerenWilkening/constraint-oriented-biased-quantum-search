# Roadmap: CBQS Stabilization & Optimization

## Overview

This roadmap takes the CBQS solver from its current state -- functional but with critical correctness bugs, thread safety violations, memory leaks, and missing validation -- to a stable, performant engine that researchers can trust for benchmarking and publishing. The work proceeds in strict dependency order: tests first, then correctness fixes, then thread architecture, then memory optimization, then robustness. Every phase builds on verified foundations from the previous phase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Test Foundation** - CMocka test suite establishing correctness baseline
- [x] **Phase 2: Critical Correctness Fixes** - Fix bugs that produce silently wrong results
- [x] **Phase 3: Solver Context Architecture** - Introduce solver_ctx_t and eliminate global mutable state
- [x] **Phase 4: Thread Isolation** - Per-thread PRNG and configurable parallelism
- [x] **Phase 5: Memory Safety** - Fix leaks and eliminate unsafe stack allocations
- [x] **Phase 6: Memory Optimization** - Dynamic arrays and arena allocator for hot paths
- [ ] **Phase 7: API Robustness** - Input validation and solution verification
- [ ] **Phase 8: Solve Diagnostics** - Structured result object with timing and history

## Phase Details

### Phase 1: Test Foundation
**Goal**: Researchers can run an automated test suite that validates core solver correctness, providing a safety net for all subsequent changes
**Depends on**: Nothing (first phase)
**Requirements**: CORR-01
**Success Criteria** (what must be TRUE):
  1. Running `make test` (or equivalent) executes a CMocka test suite that passes on a clean build
  2. Tests cover constraint evaluation, move generation, branching logic, and state management functions in the C kernel
  3. At least one integration test solves a small known-optimal problem and verifies the returned solution satisfies all constraints with the correct objective value
  4. Tests run under AddressSanitizer without triggering any warnings (establishing a clean ASan baseline)
**Plans**: 5 plans

Plans:
- [x] 01-01-PLAN.md — CMake test infrastructure + intarray/Expression/state C tests
- [x] 01-02-PLAN.md — constraint/model/Branching C tests
- [x] 01-03-PLAN.md — solver/SearchLib C tests + integration test
- [x] 01-04-PLAN.md — Python pytest suite (Expression, Constraint, Model API)
- [x] 01-05-PLAN.md — GitHub Actions CI + ASan + local validation

### Phase 2: Critical Correctness Fixes
**Goal**: The solver produces correct results -- no use-after-free, no excessive reallocation, and integer variable expressions behave like normal Python objects
**Depends on**: Phase 1
**Requirements**: CORR-02, CORR-03, CORR-04
**Success Criteria** (what must be TRUE):
  1. Local search with multiple threads completes without ASan/Valgrind heap errors (use-after-free in accept_best_routine is fixed)
  2. Sparse preprocessing reallocation triggers only every `size_steps` iterations, not on nearly every iteration
  3. Reusing an integer variable in multiple expressions does not corrupt earlier expressions -- `expr1 = x + 3; expr2 = x + 5` leaves expr1 unchanged
  4. All Expression operators (__add__, __mul__, etc.) return new Expression objects rather than mutating self
  5. Existing Phase 1 test suite still passes after all fixes (no regressions)
**Plans**: 6 plans

Plans:
- [x] 02-01-PLAN.md — Fix C-level memory bugs (use-after-free, realloc condition)
- [x] 02-02-PLAN.md — Add C helper for Expression deep copy
- [x] 02-03-PLAN.md — Implement Expression immutability (standard operators)
- [x] 02-04-PLAN.md — Implement in-place operators (__iadd__, __imul__, etc.)
- [x] 02-05-PLAN.md — Deprecation warning + Variable operator fixes + regression tests
- [x] 02-06-PLAN.md — Valgrind CI + stress tests

### Phase 3: Solver Context Architecture
**Goal**: All per-solve mutable state lives in an explicit solver_ctx_t struct passed through call chains, eliminating global variables that cause data races
**Depends on**: Phase 2
**Requirements**: THRD-01, THRD-02
**Success Criteria** (what must be TRUE):
  1. BranchingStats is no longer a global variable -- it lives inside solver_ctx_t and is passed explicitly to all functions that need it
  2. The global stop flag (signal.raise_signal pattern) is replaced with an atomic boolean in solver_ctx_t, checked by all worker threads
  3. Two independent Model instances can solve concurrently in separate threads without interfering with each other's branching statistics or stop conditions
  4. ThreadSanitizer reports zero data races on a multi-threaded solve
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — Create solver_ctx.h/c foundation with ctx struct and lifecycle
- [x] 03-02-PLAN.md — Migrate solver functions (CSearch_*, monte carlo samplers) to use ctx
- [x] 03-03-PLAN.md — Migrate entry points (ctg, local_search) and stop flag to ctx
- [x] 03-04-PLAN.md — Update Cython layer and C tests for ctx lifecycle
- [x] 03-05-PLAN.md — ThreadSanitizer verification and debug output testing

### Phase 4: Thread Isolation
**Goal**: Each worker thread operates with fully isolated random state and the user controls parallelism at runtime
**Depends on**: Phase 3
**Requirements**: THRD-03, THRD-04
**Success Criteria** (what must be TRUE):
  1. Each worker thread uses its own PRNG instance (no calls to global rand()); seeding each thread with a known seed produces deterministic results
  2. Thread count is a runtime parameter (not compile-time NUMThreads=6) -- user can specify via Model API or solver call
  3. Solving the same problem with the same seed and same thread count produces identical results across runs
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — Create PRNG module (prng.h/c) with xoshiro256**, SplitMix64 seeding, jump functions
- [x] 04-02-PLAN.md — Extend solver_ctx, replace all rand() calls, remove NUMThreads constant
- [x] 04-03-PLAN.md — Update Cython layer, expose seed/num_threads API, add determinism tests

### Phase 5: Memory Safety
**Goal**: No memory leaks under normal operation and no risk of stack overflow on large problem instances
**Depends on**: Phase 3
**Requirements**: MEM-01, MEM-04
**Success Criteria** (what must be TRUE):
  1. Valgrind/ASan reports zero memory leaks after a complete solve-and-exit cycle (all allocations in explore_neighbourhood are freed)
  2. VLAs sized by problem input (e.g., totals[C], remainings[C]) are replaced with heap or pre-allocated buffers
  3. Solving a problem with 10,000+ constraints does not segfault due to stack overflow from large VLAs
**Plans**: 5 plans

Plans:
- [x] 05-01-PLAN.md — Fix preprocessing leaks + create Valgrind suppression file
- [x] 05-02-PLAN.md — Replace VLAs in local_search.c with per-thread heap buffers
- [x] 05-03-PLAN.md — Replace VLAs in solver.c, SearchLib.c, approximate_state_sampler.c
- [x] 05-04-PLAN.md — Enable ASan leak detection + add memory stress tests
- [x] 05-05-PLAN.md — Audit Cython layer for memory management (Py_INCREF/DECREF, calloc/free)

### Phase 6: Memory Optimization
**Goal**: Hot-path allocations are eliminated through pre-allocation and arena allocation, and expression storage scales with actual term count
**Depends on**: Phase 3, Phase 5
**Requirements**: MEM-02, MEM-03
**Success Criteria** (what must be TRUE):
  1. Expression storage uses dynamically allocated variable-length arrays instead of fixed MAXCLAUSESIZE -- a 2-term expression uses less memory than a 20-term expression
  2. The explore_neighbourhood inner loop contains zero malloc/calloc/free calls -- all scratch memory comes from a pre-allocated arena
  3. Arena memory is correctly reset between iterations and freed after solve completes (no leaks)
  4. Benchmark on a representative problem shows measurable improvement in solve time compared to Phase 5 baseline
**Plans**: 5 plans

Plans:
- [x] 06-01-PLAN.md — Create arena allocator module (arena.h/c) with bump allocation and chained overflow
- [x] 06-02-PLAN.md — Create dynamic expression with small-object optimization (dyn_expr.h/c)
- [x] 06-03-PLAN.md — Integrate arena into solver_ctx, replace hot-path allocations in local_search.c
- [x] 06-04-PLAN.md — Create benchmark suite with pytest-benchmark, CI integration
- [x] 06-05-PLAN.md — (Gap closure) Integrate dyn_expr into Expression.c, remove fixed MAXCLAUSESIZE allocation

### Phase 7: API Robustness
**Goal**: The solver rejects invalid inputs with clear error messages and verifies that returned solutions are actually correct
**Depends on**: Phase 2
**Requirements**: RBST-01, RBST-02
**Success Criteria** (what must be TRUE):
  1. Passing an out-of-range variable index, invalid constraint sense, or NaN coefficient raises a clear Python exception before solve begins
  2. Negative variable bounds, zero-length constraint arrays, and duplicate variable indices in a constraint are caught and reported
  3. After every solve, the solver automatically checks that the returned solution satisfies all constraints and the reported objective matches recomputation
  4. If post-solve validation detects a violation, the result is flagged with a warning (not silently returned as feasible)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

### Phase 8: Solve Diagnostics
**Goal**: Researchers get a structured result object containing everything needed to analyze solver behavior without manual instrumentation
**Depends on**: Phase 7
**Requirements**: RBST-03
**Success Criteria** (what must be TRUE):
  1. Solve returns a result object (not just a solution array) containing: solution, objective value, feasibility status, solve time, iteration count, and oracle call count
  2. The result object includes an improvement history showing objective value progression over iterations
  3. Timing breakdown distinguishes preprocessing time from solve time
**Plans**: TBD

Plans:
- [ ] 08-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8
Note: Phases 4, 5, and 7 can proceed independently after their dependencies complete.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Foundation | 5/5 | Complete | 2026-02-04 |
| 2. Critical Correctness Fixes | 6/6 | Complete | 2026-02-05 |
| 3. Solver Context Architecture | 5/5 | Complete | 2026-02-05 |
| 4. Thread Isolation | 3/3 | Complete | 2026-02-05 |
| 5. Memory Safety | 5/5 | Complete | 2026-02-05 |
| 6. Memory Optimization | 5/5 | Complete | 2026-02-06 |
| 7. API Robustness | 0/TBD | Not started | - |
| 8. Solve Diagnostics | 0/TBD | Not started | - |
