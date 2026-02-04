# Project Research Summary

**Project:** CBQS Solver Stabilization and C Optimization
**Domain:** C/Cython constraint-oriented quantum search solver
**Researched:** 2026-02-04
**Confidence:** HIGH

## Executive Summary

This project is a C-based constraint optimization solver with Cython Python bindings that uses quantum-inspired local search algorithms. The codebase is currently plagued by critical thread safety issues, memory leaks, and performance bottlenecks that make it unsuitable for production use. Research reveals that the solver has a solid algorithmic foundation but requires systematic stabilization before any feature additions or optimizations.

The recommended approach is a phased refactoring that prioritizes correctness over performance initially. The first phase must establish a test suite and fix critical safety bugs (use-after-free, global state races) that produce silently incorrect results. Only after achieving a stable correctness baseline should the project proceed to performance optimization (memory pools, incremental evaluation). This mirrors the development patterns of mature C solvers like SCIP and OR-Tools, which emphasize per-solver context isolation and extensive test coverage.

Key risks center on the complexity of the multi-threaded C/Cython architecture. The global BranchingStats variable creates data races under joblib threading that are "benign" today (all workers use same values) but will silently break if per-worker differentiation is added. The use-after-free in accept_best_routine is a heap corruption time bomb. Both must be fixed before any optimization work, as performance improvements on a broken foundation will just create faster incorrect solvers. Mitigation requires discipline: comprehensive AddressSanitizer/ThreadSanitizer CI gates, golden test suite establishment before optimization, and strict separation of build-phase from solve-phase memory management.

## Key Findings

### Recommended Stack

The current stack (Python 3.13.7, Cython 3.2.x, C11, gcc/clang) is appropriate for this domain and already in place. The critical gap is not in core technologies but in tooling and development practices.

**Core technologies:**
- C11 with gcc/clang: Correct choice for low-level solver kernel; provides atomics, VLAs, and stdint.h
- Cython 3.2.x: Appropriate Python-to-C bridge; upgrade to pin 3.2.x for bug fixes and free-threading groundwork
- Python 3.13.7: Current stable line; adequate for API and joblib orchestration

**Essential additions (not currently used):**
- AddressSanitizer (ASan): Primary memory debugger; catches heap/stack overflows and use-after-free with 2-3x slowdown vs Valgrind's 20-50x
- ThreadSanitizer (TSan): Primary thread safety tool; detects data races on shared memory; directly addresses BranchingStats and stopping_criterion races
- CMocka 2.0: C unit test framework with mocking; TAP 14 output for CI integration; essential for testing constraint evaluation and solver correctness
- perf + FlameGraph: CPU sampling profiler with zero instrumentation overhead; required for identifying hot functions without distorting measurements
- Arena allocators (no external dependency): Custom pattern to eliminate malloc/free overhead in explore_neighbourhood hot loop; 50-100x speedup claim requires validation

**Build configurations needed:**
- Separate ASan, TSan, and release builds (sanitizers are mutually exclusive)
- Profiling build with -fno-omit-frame-pointer for accurate stack traces
- Valgrind runs require PYTHONMALLOC=malloc to filter interpreter noise

### Expected Features

The feature landscape is dominated by **table stakes** that must be fixed before the solver is production-ready. These are not new features but rather fundamental correctness and robustness requirements that any C solver must have.

**Must have (table stakes - currently missing):**
- Thread-safe state management: Eliminate global BranchingStats and stopping_criterion races; pass context through structs
- Memory leak elimination: Fix use-after-free in accept_best_routine (threads read freed memory); fix double copy_state leak in SearchLib
- Malloc elimination from hot loops: explore_neighbourhood calls calloc(MINSIZE) per move iteration; pre-allocate scratch buffers instead
- Input validation: No bounds checking on variable indices or constraint counts; add validation at Cython boundary
- Test suite: Zero automated tests; highest-leverage table stake; prerequisite for all other fixes
- Proper thread stopping: signal.raise_signal(SIGINT) is process-wide; replace with per-solver atomic flag
- Solution validation: No verification that returned solutions satisfy constraints; add post-solve check
- Expression immutability: Operator overloading mutates in-place, violating Python semantics; return new objects instead

**Should have (competitive advantage - after table stakes):**
- Memory pool allocator: Bump allocator per thread for scratch memory; eliminates hot-loop malloc overhead
- Incremental constraint evaluation: adjusted_constraint_violation is commented out; re-enabling avoids O(total_clauses) work per move
- Sparse preprocessing realloc fix: Inverted bitmask condition causes excessive reallocation; near-zero-risk high-value fix
- Configurable thread count: NUMThreads=6 is compile-time; should use mod->num_workers at runtime
- Solution diagnostics: Structured logging of iteration count, objective value, feasibility status

**Defer (anti-features for this milestone):**
- New solver algorithms (simulated annealing, genetic algorithms): Stabilize existing algorithms first; new algorithms on broken foundation inherit all bugs
- ML-guided branching: Adds massive complexity and new failure modes before current branching is thread-safe
- GPU/Metal acceleration: Platform-specific complexity; CPU path must be correct first
- Distributed solving: Cannot safely share state between threads on one machine; distributed requires that fixed first

### Architecture Approach

The current architecture is a three-layer stack (Python API -> Cython bindings -> C kernel) with critical architectural flaws in state management. The core issue is pervasive use of global mutable state (BranchingStats, stop_flag, python_callback) that creates data races under joblib threading.

**Major components and current issues:**
1. **model_t (model.h/c)**: Holds solver parameters and constraint pointers; currently mixes read-only config with shared mutable state (global_opt, runtime, qtg_applications need synchronization)
2. **BranchingStats (Branching.h/c)**: Process-wide global variable; data race when joblib threading spawns multiple workers; must move to per-solver context struct
3. **new_constraints_t (constraint.h/c)**: Constraint/objective storage in flattened arrays; correctly read-only after preprocessing; safe to share
4. **local_search_data_t (local_search.h)**: Per-thread work packet; reasonably isolated but references shared constraint data
5. **expression_t (Expression.h)**: Fixed MAXCLAUSESIZE=4 wastes memory for linear terms and blocks higher-order; needs dynamic variable storage

**Recommended refactoring (from ARCHITECTURE.md):**
- Introduce solver_ctx_t struct to bundle all per-solve mutable state (branching config, scratch arena, working buffers, tabu list, RNG state)
- Pass solver_ctx_t* explicitly to every function currently touching globals
- Separate shared (read-only after preprocessing) from thread-local (mutable per solver) state boundaries
- Implement arena allocator pattern for hot-loop scratch allocations
- Pre-allocate working state buffers (cur_best, cur_best_tabu, new_sol) in solver_ctx_t instead of malloc per call
- Replace fixed-stride MAXCLAUSESIZE with offset-based variable storage (deferred to later phase due to invasiveness)

**Critical pattern: Eliminate globals via context struct**
Research shows this is THE fundamental pattern for C thread safety. Every mature C solver (SCIP, Gurobi) uses per-solver contexts. The existing update_lock mutex around global_opt updates demonstrates the codebase already understands this pattern partially; it must be applied systematically to all mutable state.

### Critical Pitfalls

1. **Global BranchingStats races under joblib threading** — BranchingStats is process-wide; joblib.Parallel(backend="threading") spawns workers that all read/write the same global; produces silently wrong sampling distributions with no crash. **Prevention:** Move BranchingStats into model_t, pass through all call chains, delete the global to force compiler errors on remaining references. This MUST be the first refactoring step.

2. **Freeing thread-local data before thread completes** — accept_best_routine frees data[i].remainings immediately after pthread_create but thread hasn't started yet; use-after-free causes heap corruption or silent data corruption. **Prevention:** Move all free() calls to AFTER pthread_join loop; add Valgrind/ASan CI gate to catch this entire class of bug.

3. **Expression mutation through Python operator overloading** — Expression.__add__ mutates self and returns self, violating Python semantics; expr2 = expr1 + 5 creates aliased expressions that corrupt each other. **Prevention:** Return new Expression objects from all operators; add unit tests verifying operators don't mutate arguments.

4. **GIL/nogil callback deadlock** — my_callback_c() reacquires GIL inside nogil blocks; with 12 joblib workers all calling back into Python simultaneously via shared python_callback global, deadlock or segfault occurs. **Prevention:** Make python_callback thread-local or pass via context; minimize callback frequency; consider removing from hot path entirely.

5. **Optimizing before establishing correctness baseline** — Team may start performance work (memory pools, SIMD) before having test suite; optimizations introduce bugs that go undetected because there's no reference output. **Prevention:** Create golden test suite with known optimal solutions BEFORE any optimization; every optimization PR must pass bit-exact comparison; fix random seed for determinism testing.

## Implications for Roadmap

Based on research, the project requires a strictly ordered refactoring roadmap. Performance work CANNOT proceed before correctness is established, and correctness cannot be validated without tests. The research reveals a clear critical path.

### Phase 1: Foundation (Correctness Baseline)
**Rationale:** Tests are prerequisite for all subsequent work; without them, every fix is a gamble. The use-after-free and sparse preprocessing bugs are high-confidence fixes that establish early wins.

**Delivers:**
- CMocka test suite for expression arithmetic, constraint evaluation, small model solve-and-verify
- Critical safety bugs fixed (use-after-free in accept_best_routine, double copy_state leak)
- Sparse preprocessing realloc condition fix (inverted bitmask, near-zero-risk)

**Addresses (from FEATURES.md):**
- Test suite (highest-leverage table stake)
- Memory leak elimination (critical correctness)
- High-value performance fix (realloc bug)

**Avoids (from PITFALLS.md):**
- Pitfall 10: Optimizing before establishing correctness baseline
- Pitfall 2: Freeing thread-local data before thread completes

**Research depth:** Standard patterns, no additional research needed. CMocka is well-documented, use-after-free fix is straightforward, realloc fix is a one-line change.

---

### Phase 2: Thread Safety (Global State Elimination)
**Rationale:** All performance work requires thread architecture to be settled first. The global state races are the root cause of non-determinism and prevent any multi-threaded optimization.

**Delivers:**
- solver_ctx_t struct containing all per-solver mutable state
- BranchingStats moved into solver_ctx_t (eliminate global)
- Atomic flag for thread stopping (replace signal-based pattern)
- Per-thread PRNG (replace rand() global state)
- Thread-local python_callback context

**Addresses (from FEATURES.md):**
- Thread-safe state management (table stake)
- Proper thread stopping mechanism (table stake)
- Configurable thread count (move NUMThreads to runtime parameter)

**Avoids (from PITFALLS.md):**
- Pitfall 1: Global BranchingStats races
- Pitfall 4: GIL/nogil callback deadlock
- Pitfall 9: stop_flag global shared across instances

**Uses (from STACK.md):**
- ThreadSanitizer to verify data race elimination
- Separate TSan build configuration

**Research depth:** Standard patterns, no additional research needed. Per-context struct is universal C threading pattern. TSan usage is well-documented.

---

### Phase 3: Performance (Hot Loop Optimization)
**Rationale:** Now that thread architecture is stable and tests verify correctness, performance optimization is safe. Arena allocator and malloc elimination have highest impact.

**Delivers:**
- Arena allocator implementation (bump allocator per thread)
- Pre-allocated working buffers in solver_ctx_t
- Malloc elimination from explore_neighbourhood hot loop
- Incremental constraint evaluation re-enabled (fix commented-out adjusted_constraint_violation path)
- Benchmarking harness with perf + FlameGraph integration

**Addresses (from FEATURES.md):**
- Elimination of malloc in hot loops (table stake)
- Memory pool allocator (competitive advantage)
- Incremental constraint evaluation (competitive advantage)

**Avoids (from PITFALLS.md):**
- Pitfall 6: Premature mutex insertion on hot paths (use per-thread copies instead)
- Pitfall 7: Dynamic array reallocation breaking in-flight pointers (separate build vs solve phases)

**Uses (from STACK.md):**
- Arena allocator pattern (custom implementation, no external dependency)
- perf + FlameGraph for profiling
- Profiling build with -fno-omit-frame-pointer

**Research depth:** Arena allocator pattern needs validation of 50-100x performance claim on this specific codebase. Incremental constraint path needs correctness verification against full re-evaluation. Otherwise standard patterns.

---

### Phase 4: Robustness (Input Validation and Cleanup)
**Rationale:** With correctness and performance stable, add defensive programming practices. These are lower priority than core fixes but important for production use.

**Delivers:**
- Input validation at Cython boundary (bounds checks on indices, sizes, constraint counts)
- Solution validation (post-solve constraint satisfaction check)
- Fixed-size array elimination (replace MINARRAYSIZE/MAXCLAUSESIZE patterns)
- Expression ownership documentation and enforcement
- VLA elimination (replace stack VLAs with heap or pre-allocated buffers)
- Hardcoded constant elimination (NUMThreads, MAXCLAUSESIZE, min_size to parameters)

**Addresses (from FEATURES.md):**
- Input validation (table stake)
- Solution validation (table stake)
- Fixed-size array elimination (table stake)
- Expression immutability/copy safety (table stake)
- Hardcoded constant elimination (table stake)

**Avoids (from PITFALLS.md):**
- Pitfall 8: VLA stack overflow in constraint evaluation
- Pitfall 11: Hardcoded constants limiting scalability
- Pitfall 3: Expression mutation through operator overloading

**Research depth:** Standard defensive programming practices, no additional research needed.

---

### Phase Ordering Rationale

**Strict dependencies:**
- Phase 1 (Foundation) is prerequisite for everything: without tests, every fix risks introducing new bugs
- Phase 2 (Thread Safety) must complete before Phase 3 (Performance): memory pools must be thread-local, so thread architecture must be settled first
- Phase 3 (Performance) requires Phase 1 (Foundation): incremental constraint path needs test validation; arena allocator needs benchmarking harness
- Phase 4 (Robustness) can proceed after Phase 1 but is lower priority than Phases 2-3

**Why not parallelize Phases 2 and 4:** Expression immutability fixes (Phase 4) touch the same code paths as the context struct introduction (Phase 2). Doing both simultaneously creates merge conflicts. Thread safety is more critical than input validation, so it gets priority.

**Deferred to future milestones:**
- Dynamic variable storage (replace MAXCLAUSESIZE fixed stride): This touches the most code and is invasive; defer until core is stable
- GPU/Metal acceleration: Requires CPU path to be correct first
- New solver algorithms: Must validate on stabilized foundation

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 3 (Performance):** Arena allocator performance claims (50-100x) need validation on this codebase; incremental constraint path was abandoned for a reason (commented out) — needs investigation of why it was disabled
- **Phase 4 (Robustness):** VLA replacement strategy for large arrays (totals[C], remainings[C]) needs sizing analysis for worst-case problem instances

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Foundation):** CMocka usage, Valgrind/ASan integration, and use-after-free fixes are well-documented standard practices
- **Phase 2 (Thread Safety):** Per-context struct pattern is universal in C threading; ThreadSanitizer usage is well-documented
- **Phase 4 (Robustness):** Input validation and bounds checking are standard defensive programming

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All tools verified via official docs; current stack (C11/Cython/Python) is appropriate |
| Features | HIGH | Based on direct codebase analysis with specific line references; priorities clear from bug severity |
| Architecture | HIGH | Architectural patterns (solver context, arena allocator) verified against mature C solver designs; specific anti-patterns observed in code |
| Pitfalls | HIGH | All critical pitfalls verified by direct code inspection; use-after-free at local_search.c:307-311, global BranchingStats at Branching.c:5 |

**Overall confidence:** HIGH

The research is grounded in direct codebase analysis rather than speculation. All critical findings (use-after-free, global state races, malloc in hot loops) have specific file and line number references. The recommended stack additions (ASan, TSan, CMocka) are industry-standard tools with extensive documentation. The architectural patterns (per-solver context, arena allocator) are proven in mature C solvers.

### Gaps to Address

**Arena allocator performance:** The "50-100x speedup" claim for arena allocators comes from blog posts without benchmarks on this specific codebase. The allocation pattern in explore_neighbourhood (calloc per move iteration) is a good match for arenas, but the actual speedup needs measurement. **Mitigation:** Establish baseline benchmark in Phase 1, measure actual improvement in Phase 3.

**Incremental constraint evaluation correctness:** The adjusted_constraint_violation path is commented out in explore_neighbourhood (lines 185-191), suggesting it had correctness issues. The reason for abandonment is not documented. **Mitigation:** During Phase 3 planning, investigate git history to understand why it was disabled; implement with careful validation against full re-evaluation; use hypothesis property-based testing to verify equivalence.

**Free-threaded Python (3.13t) compatibility:** Cython 3.2.x has experimental free-threading support but extension modules are not yet thread-safe for cdef class attributes. This project currently uses regular Python 3.13, not free-threaded. **Mitigation:** Monitor Cython free-threading maturity; do not migrate to 3.13t until Cython declares it production-ready.

**macOS vs Linux tooling:** Valgrind does NOT support Apple Silicon (arm64); perf is Linux-only. The codebase has Metal backend code suggesting macOS development. **Mitigation:** Use ASan/TSan on macOS (work with Apple Clang); use Instruments.app instead of perf; Valgrind testing requires Linux CI environment.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: All specific line references verified (Branching.c:5, local_search.c:307-311, SearchLib.pyx:117, Expression.pyx:131-155)
- [Valgrind 3.26.0 release](https://valgrind.org/downloads/) — version and platform support
- [ThreadSanitizer manual](https://github.com/google/sanitizers/wiki/threadsanitizercppmanual) — compilation flags, overhead
- [Clang ThreadSanitizer docs](https://clang.llvm.org/docs/ThreadSanitizer.html) — official compiler documentation
- [CMocka 2.0 release](https://blog.cryptomilk.org/2025/12/04/cmocka-2-0-released-enhancing-unit-testing-in-c/) — TAP 14, type-safe assertions
- [Cython 3.2.4 on PyPI](https://pypi.org/project/Cython/) — current version verification
- [SEI CERT thread safety standards](https://wiki.sei.cmu.edu/confluence/display/c/POS47-C.) — authoritative C threading guidance

### Secondary (MEDIUM confidence)
- [Red Hat: Comparing Sanitizers and Valgrind](https://developers.redhat.com/blog/2021/05/05/memory-error-checking-in-c-and-c-comparing-sanitizers-and-valgrind) — ASan vs Valgrind tradeoffs
- [Ryan Fleury: Arena Allocator](https://www.rfleury.com/p/untangling-lifetimes-the-arena-allocator) — arena allocator design patterns
- [Using Valgrind with Cython](https://adrianeboyd.github.io/using-valgrind-with-cython/) — PYTHONMALLOC, suppression files
- [Brendan Gregg's perf examples](https://www.brendangregg.com/perf.html) — profiling workflow
- [Cython GIL Documentation](https://cython.readthedocs.io/en/latest/src/userguide/nogil.html) — GIL management patterns

### Tertiary (LOW confidence - needs validation)
- [Arena performance claims](https://medium.com/@ramogh2404/arena-and-memory-pool-allocators-the-50-100x-performance-secret-behind-game-engines-and-browsers-1e491cb40b49) — 50-100x speedup needs validation on this codebase
- Cython free-threading status — experimental, not production-ready yet
- py-spy compatibility with Cython 3.2 — generally works but not verified for this specific version combo

---
*Research completed: 2026-02-04*
*Ready for roadmap: yes*
