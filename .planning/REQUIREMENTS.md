# Requirements: CBQS Stabilization & Optimization

**Defined:** 2026-02-04
**Core Value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## v1 Requirements

### Correctness

- [ ] **CORR-01**: C unit test suite using CMocka covering core functions (constraint evaluation, move generation, branching, state management)
- [x] **CORR-02**: Fix use-after-free in `accept_best_routine` — thread data freed before threads consume it (`local_search.c:307-311`)
- [x] **CORR-03**: Fix inverted realloc condition in preprocessing — triggers on nearly every iteration instead of every `size_steps` iterations
- [x] **CORR-04**: Fix Expression mutation — operations must return new expressions, not mutate in-place; integer variable reuse must work without manual copying

### Thread Safety

- [ ] **THRD-01**: Introduce `solver_ctx_t` struct encapsulating BranchingStats, stop flag, and callback — eliminate global mutable state
- [ ] **THRD-02**: Replace `signal.raise_signal(signal.SIGINT)` with atomic boolean stop flag checked by all threads
- [ ] **THRD-03**: Replace global `rand()` with per-thread PRNG (e.g., `rand_r()` or xoshiro256**)
- [ ] **THRD-04**: Make thread count configurable — remove hardcoded `NUMThreads=6`, derive from model or user parameter

### Memory & Data Structures

- [ ] **MEM-01**: Fix memory leak in move list generation — ensure all allocations in `explore_neighbourhood` are freed
- [ ] **MEM-02**: Replace fixed-size expression arrays (MAXCLAUSESIZE) with dynamically allocated variable-length storage
- [ ] **MEM-03**: Implement arena/pool allocator for hot-path allocations in `explore_neighbourhood` inner loop
- [ ] **MEM-04**: Replace VLAs sized by problem input with heap allocation to prevent stack overflow on large instances

### Robustness

- [ ] **RBST-01**: Add input validation at API boundary — validate coefficients, bounds, sense values, variable indices
- [ ] **RBST-02**: Add post-solve solution validation — verify returned solution satisfies all constraints and objective value is correct
- [ ] **RBST-03**: Return structured result object with solve diagnostics — timing breakdown, constraint violations, improvement history, oracle call counts

## v2 Requirements

### Branching Extensions

- **BRCH-01**: Additional branching bias factors beyond objective/constraint/lookahead/base
- **BRCH-02**: Problem-specific branching rules (e.g., knapsack, MaxClique)
- **BRCH-03**: Adaptive branching that learns during search from incumbent history
- **BRCH-04**: ML-based branching strategy selection based on problem/instance features

### Solver Extensions

- **SOLV-01**: Automatic multi-heuristic solver combining sampling and local search
- **SOLV-02**: Branch-and-bound extension
- **SOLV-03**: Warm-start/hot-start support — provide initial solution hint to solver

## Out of Scope

| Feature | Reason |
|---------|--------|
| Circuit backend / quantum hardware execution | Exists as submodule but not active; stabilize classical solver first |
| GUI or web interface | CLI/API sufficient for research use |
| Python free-threading (nogil) | Cython support is experimental; wait for Cython 3.3+ |
| Metal/GPU acceleration | macOS-only; not relevant to core solver stabilization |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORR-01 | Phase 1: Test Foundation | Complete |
| CORR-02 | Phase 2: Critical Correctness Fixes | Complete |
| CORR-03 | Phase 2: Critical Correctness Fixes | Complete |
| CORR-04 | Phase 2: Critical Correctness Fixes | Complete |
| THRD-01 | Phase 3: Solver Context Architecture | Pending |
| THRD-02 | Phase 3: Solver Context Architecture | Pending |
| THRD-03 | Phase 4: Thread Isolation | Pending |
| THRD-04 | Phase 4: Thread Isolation | Pending |
| MEM-01 | Phase 5: Memory Safety | Pending |
| MEM-04 | Phase 5: Memory Safety | Pending |
| MEM-02 | Phase 6: Memory Optimization | Pending |
| MEM-03 | Phase 6: Memory Optimization | Pending |
| RBST-01 | Phase 7: API Robustness | Pending |
| RBST-02 | Phase 7: API Robustness | Pending |
| RBST-03 | Phase 8: Solve Diagnostics | Pending |

**Coverage:**
- v1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-02-04*
*Last updated: 2026-02-05 after Phase 2 completion*
