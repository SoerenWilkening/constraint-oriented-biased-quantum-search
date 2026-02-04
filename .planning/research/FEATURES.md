# Feature Research: CBQS Solver Stabilization and C Optimization

**Domain:** C-based constraint/optimization solver with Cython Python bindings
**Researched:** 2026-02-04
**Confidence:** HIGH (based on direct codebase analysis + established C engineering practices)

## Feature Landscape

### Table Stakes (Must Fix -- Solver Is Unreliable Without These)

Features that any production-quality C solver must have. The CBQS solver currently lacks all of these, making it unsuitable for reliable use beyond development prototyping.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Thread-safe state management** | Current code uses global `python_callback` variable and shared `stopping_criterion` via raw pointer without atomics. Multiple `run_sampling` calls via joblib threading share mutable state. Race conditions cause silent wrong results. | HIGH | Global `python_callback` in `SearchLib.pyx` (line 117) is process-wide. `stopping_criterion` in `local_search.c` (line 163) is a shared `int*` read/written from multiple threads with no synchronization. Must replace with thread-local storage or pass context through structs. |
| **Memory leak elimination** | `accept_best_routine` frees `data[i].remainings` and clears `data[i].ful_con`/`ful` in the thread creation loop (lines 308-311) BEFORE threads finish executing -- this is use-after-free. `copy_state(copy_state(...))` in `SearchLib.pyx` line 133 leaks the inner copy. | HIGH | The thread data lifetime bug in `accept_best_routine` is critical -- threads read freed memory. The double `copy_state` leak happens every `run_sampling` call. Need systematic audit of all allocation/free pairs. |
| **Elimination of malloc in hot loops** | `explore_neighbourhood` calls `calloc(MINSIZE, sizeof(int))` (line 178) and `sw_init()` (which mallocs) inside the inner move loop, executed potentially millions of times. Also `calloc` at line 225. | MEDIUM | Pre-allocate these buffers once per thread before the loop. The `MINSIZE=2048` calloc per iteration is especially wasteful. Move to pre-allocated scratch buffers in `local_search_data_t`. |
| **Input validation** | No bounds checking on variable indices, constraint counts, or expression sizes. `sw_tstbit`/`sw_setbit` do not check if index B exceeds array bounds. `variable_index` can overflow with crafted input. | MEDIUM | Add validation at the Python-C boundary (Cython layer). Check: n > 0, all variable indices < n, expression sizes non-negative, constraint counts match allocated arrays. Fail fast with clear error messages. |
| **Solution validation** | No post-solve verification that returned solution actually satisfies constraints. The solver can return infeasible solutions silently due to bugs in `accept_move` logic or race conditions. | LOW | Add a verification pass after solve completes: re-evaluate all constraints against returned solution. `eval_constraints` already exists -- just need to call it and report/assert. |
| **Proper thread stopping mechanism** | `signal.raise_signal(signal.SIGINT)` used to stop threads in `SearchLib.pyx` line 184. Signals are process-wide and kill all threads indiscriminately. `reset_flag()` called after parallel execution suggests global flag state. | MEDIUM | Replace with per-solve cancellation token (atomic flag in model struct). Each thread checks flag cooperatively. No signals needed. |
| **Fixed-size array elimination** | `MINARRAYSIZE = 50000` in constraint.h pre-allocates fixed arrays. `MAXCLAUSESIZE = 4` hard-limits variables per clause. `copy_new_constraint` copies exactly `MINARRAYSIZE` elements regardless of actual data size. `min_size = 30000` in Expression.c is a global mutable. | MEDIUM | Replace fixed allocations with tracked-size dynamic arrays. `copy_new_constraint` should use `total_clauses`/`total_variables` for copy size, not `MINARRAYSIZE`. Make `min_size` a parameter, not a global. |
| **Expression immutability / copy safety** | `multiply_constant`, `multiply_variable` mutate expressions in-place. `add_expression`/`sub_expression` have commented-out `free_expression(expr2)` suggesting confusion about ownership. Operations like `expr <= 0` in `set_objective` may mutate the original. | MEDIUM | Document ownership model. Either make expressions immutable (return new) or make copy-on-write explicit. The commented-out frees indicate past bugs from unclear ownership. |
| **Test suite** | Zero automated tests. No unit tests for constraint evaluation, expression arithmetic, solver correctness, or memory safety. | HIGH | This is the highest-leverage table stake. Without tests, every fix risks introducing new bugs. Need at minimum: expression arithmetic tests, constraint evaluation tests, small model solve-and-verify tests, memory leak tests (valgrind). |
| **Hardcoded constant elimination** | `NUMThreads = 6` (local_search.h line 54), `tabu_list.max_moves = 10` (multiple places), `min_size = 30000` (Expression.c global). These prevent configuration and cause problems on different hardware. | LOW | Move to model_t parameters or function arguments. `NUMThreads` should come from `mod->num_workers`. Tabu list size should be configurable. |

### Differentiators (Competitive Advantage -- Not Required But Valuable)

Features that would make the solver notably better than a naive implementation. These should come AFTER table stakes are addressed.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Memory pool allocator for search loops** | Eliminates malloc/free overhead in `explore_neighbourhood` and `quantum_local_search_states`. Pre-allocate a pool per thread, bump-allocate during search, free entire pool at end. Could see 2-10x speedup in hot loops based on [arena allocator patterns](https://www.rfleury.com/p/untangling-lifetimes-the-arena-allocator). | MEDIUM | Implement a simple arena/bump allocator per thread. Reset between iterations rather than individual frees. The allocation pattern (allocate many small things, free all at once) is ideal for arenas. |
| **Incremental constraint evaluation** | The `adjusted_constraint_violation` function exists but is commented out in `explore_neighbourhood` (lines 185-191), replaced with full `constraint_violation` per constraint per move. Re-enabling incremental evaluation would avoid O(clauses) work per move. | HIGH | The incremental path was abandoned (commented out), suggesting correctness issues. Fixing and re-enabling it is high value but needs careful validation. The full evaluation at line 182 is an O(C * clauses) bottleneck. |
| **Sparse constraint preprocessing** | `preprocessing_sparse` already exists and is used. But the realloc pattern (line 300-301) reallocates on bitmask check `counter & (size_steps - 1)` which is inverted -- it reallocates when the counter is NOT a multiple of size_steps, which is almost always. This wastes enormous time in realloc. | MEDIUM | Fix the realloc condition (should be `== 0` not the current logic). This is likely a significant performance bug in preprocessing. Same bug exists in `preprocessing` (lines 185-186). |
| **Solution diagnostics and logging** | Currently uses printf scattered through code (many commented out). No structured logging, no way to track solver progress programmatically beyond the callback. | LOW | Add optional verbose mode with structured output: iteration count, objective value, feasibility status, constraint violations per iteration. Route through callback rather than printf. |
| **Bounds-aware move generation** | `move_list` generates all k-flip combinations up to distance d. For n=100, d=3, this is O(n^3) = ~160K moves. Could prune moves that are guaranteed infeasible based on constraint structure. | HIGH | Requires constraint analysis at preprocessing time. Significant algorithmic work. Defer unless profiling shows move generation as bottleneck. |
| **Configurable thread count at runtime** | `NUMThreads = 6` is compile-time. `mod->num_workers = 12` exists but is used for joblib parallelism, not for C-level threading. The C local search always uses exactly 6 threads. | LOW | Pass `mod->num_workers` to `accept_best_routine` and use it instead of `NUMThreads`. Replace fixed-size arrays `data[NUMThreads]` and `threads[NUMThreads]` with dynamic allocation. |
| **VLA elimination** | `int bits[dat->d]` (local_search.c line 152), `int64_t totals[C]` (line 175), `int64_t remainings[C]` (line 449) use variable-length arrays on the stack. Large values cause stack overflow. | LOW | Replace with malloc or thread-local pre-allocated buffers. Not urgent for small problems but prevents scaling to large instances. |

### Anti-Features (Do NOT Build in This Milestone)

Features that seem useful but would distract from stabilization, add complexity, or are premature.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **New solver algorithms** | "We could add simulated annealing / genetic algorithms / ADMM" | This milestone is about making existing algorithms reliable, not adding new ones. New algorithms on a broken foundation inherit all existing bugs. | Stabilize current sampling + local search + quantum local search first. New algorithms belong in a future feature milestone. |
| **ML-guided branching** | "ML could learn better branching heuristics" | Adds massive dependency complexity (ML runtime), training pipeline, and a completely new failure mode. The current branching works; it just needs to be thread-safe. | Optimize the existing `set_bias_wrapper` mechanism. Profile branching to see if it is actually a bottleneck before adding ML. |
| **GPU/Metal acceleration** | Metal executor code already exists (`Metal_executor.pyx`). "Finish GPU support." | GPU acceleration adds platform-specific complexity. The current code has fundamental memory safety issues that must be fixed first. GPU code would inherit and amplify these bugs. | Fix CPU path completely. GPU is a separate future milestone. |
| **Expression simplification / CSE** | "Expressions should be automatically simplified before solving" | `merge_expression` already exists but has O(n^2) complexity (nested loops at lines 40-55 of Expression.c). Making it smarter adds complexity to code that first needs to be correct. | Fix the O(n^2) merge to O(n log n) via sort+linear-scan as a differentiator, but do not add more algebraic manipulation. |
| **Distributed solving** | "Run across multiple machines" | The solver cannot even safely share state between threads on one machine. Distributed solving requires all the threading issues to be fixed first, plus networking, serialization, and fault tolerance. | Fix single-machine parallelism first. |
| **Python API redesign** | "The Python API is awkward" | API changes break downstream users. The internal C issues are invisible to users until they cause crashes. Fix internals first; API polish is a separate milestone. | Document current API limitations. Fix the dangerous patterns (double copy_state, signal-based stopping) without changing the public interface. |
| **Automatic preprocessing selection** | "Auto-detect sparse vs dense" | `process_constraints` already does this (Constraint.pyx line 14). The heuristic `10 * tot > n * num_constraints` works. Don't over-engineer the selection logic. | Keep existing heuristic. If it proves wrong in practice, adjust the threshold -- don't build an auto-tuning system. |

## Feature Dependencies

```
[Test Suite]
    |
    +-- enables safe work on --> [Thread Safety Fixes]
    |                                |
    |                                +-- enables --> [Memory Pool Allocator]
    |                                |
    |                                +-- enables --> [Configurable Thread Count]
    |
    +-- enables safe work on --> [Memory Leak Fixes]
    |                                |
    |                                +-- enables --> [Malloc-in-Hot-Loop Removal]
    |                                                    |
    |                                                    +-- enhances --> [Memory Pool Allocator]
    |
    +-- enables safe work on --> [Input Validation]
    |
    +-- enables --> [Solution Validation]
    |                   |
    |                   +-- enables --> [Incremental Constraint Re-enabling]
    |
    +-- enables --> [Expression Copy Safety]

[Fixed-Size Array Elimination] -- independent, can proceed in parallel

[Proper Thread Stopping] -- requires --> [Thread Safety Fixes]

[Hardcoded Constant Elimination] -- independent, low risk

[Sparse Preprocessing Realloc Fix] -- independent, high value
```

### Dependency Notes

- **Test Suite is prerequisite for everything else:** Without tests, each fix is a gamble. The test suite must come first or in parallel with the earliest fixes.
- **Thread Safety enables Memory Pool:** Memory pools must be thread-local, so thread architecture must be settled before implementing pools.
- **Memory Leak Fixes enable Malloc Removal:** Must understand current allocation patterns before restructuring them.
- **Solution Validation enables Incremental Re-enabling:** The commented-out incremental path needs validation infrastructure to safely re-enable.
- **Thread Safety Fixes enable Proper Stopping:** The signal-based stopping is a symptom of the threading model problem; fix the model first.

## Stabilization Priority (This Milestone)

### Phase 1: Foundation (Must Complete First)

- [x] **Test suite** -- Create tests for expression arithmetic, constraint evaluation, small model solve-and-verify. Use these to gate all subsequent changes.
- [x] **Memory leak fixes** -- Fix the use-after-free in `accept_best_routine` (critical safety bug). Fix double `copy_state` leak. Validate with valgrind.
- [x] **Sparse preprocessing realloc fix** -- Fix the inverted bitmask condition in `preprocessing` and `preprocessing_sparse`. This is a near-zero-risk high-value fix.

### Phase 2: Thread Safety (Requires Phase 1 Tests)

- [x] **Eliminate global python_callback** -- Pass callback through struct/context, not global variable.
- [x] **Replace signal-based stopping** -- Use atomic flag in model_t.
- [x] **Fix stopping_criterion race** -- Use atomic operations for the shared int.
- [x] **Make NUMThreads configurable** -- Use mod->num_workers.

### Phase 3: Performance (Requires Phase 2)

- [x] **Remove malloc from hot loops** -- Pre-allocate scratch buffers in thread data structs.
- [x] **Memory pool for search iterations** -- Arena allocator per thread.
- [x] **Re-enable incremental constraint evaluation** -- Fix and validate the commented-out fast path.

### Phase 4: Robustness (Can Proceed After Phase 1)

- [x] **Input validation at Cython boundary** -- Check all indices, sizes, and parameters.
- [x] **Solution validation** -- Verify returned solutions satisfy constraints.
- [x] **Fixed-size array elimination** -- Replace MINARRAYSIZE/MAXCLAUSESIZE patterns.
- [x] **Expression ownership clarification** -- Document and enforce copy/mutation rules.
- [x] **VLA elimination** -- Replace stack VLAs with heap allocations.
- [x] **Hardcoded constant elimination** -- Move to model parameters.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Test suite | HIGH | MEDIUM | P1 |
| Memory leak fixes (use-after-free) | HIGH | LOW | P1 |
| Realloc condition fix | HIGH | LOW | P1 |
| Thread safety (global state) | HIGH | HIGH | P1 |
| Signal-based stopping replacement | HIGH | MEDIUM | P1 |
| Malloc in hot loop removal | MEDIUM | MEDIUM | P2 |
| Input validation | MEDIUM | LOW | P2 |
| Solution validation | MEDIUM | LOW | P2 |
| Memory pool allocator | MEDIUM | MEDIUM | P2 |
| Fixed-size array elimination | MEDIUM | MEDIUM | P2 |
| Expression ownership model | MEDIUM | MEDIUM | P2 |
| Incremental constraint re-enabling | HIGH | HIGH | P2 |
| Configurable thread count | LOW | LOW | P3 |
| VLA elimination | LOW | LOW | P3 |
| Hardcoded constant elimination | LOW | LOW | P3 |
| Solution diagnostics | LOW | LOW | P3 |

**Priority key:**
- P1: Must fix -- solver produces wrong results or crashes without these
- P2: Should fix -- solver is slow or fragile without these
- P3: Nice to have -- cleanup that improves maintainability

## Comparable Solver Feature Analysis

| Feature | SCIP (C) | OR-Tools (C++) | Gurobi (C) | Our Approach |
|---------|----------|----------------|------------|--------------|
| Thread safety | Full (per-solver context) | Full (protobuf-based) | Full (env-based) | BROKEN -- must fix |
| Memory management | Custom allocators, block memory | Arena allocators | Opaque, no leaks | malloc/free everywhere, leaks present |
| Input validation | Extensive (SCIP_RETCODE) | Proto validation | Parameter checking | None -- must add |
| Solution verification | Built-in feasibility check | Solution validator | Automatic | Missing -- must add |
| Test suite | Extensive (CTest) | Extensive (GTest) | Internal | None -- must create |
| Configurable threading | Runtime parameter | Runtime parameter | Runtime parameter | Compile-time constant |

## Sources

- Direct codebase analysis (HIGH confidence) -- all specific line references verified against source files
- [Arena Allocator patterns](https://www.rfleury.com/p/untangling-lifetimes-the-arena-allocator) -- MEDIUM confidence, established pattern
- [Thread safety in C](https://peerdh.com/blogs/programming-insights/implementing-threadsafe-design-patterns-in-c) -- MEDIUM confidence
- [Memory pool allocators](https://8dcc.github.io/programming/pool-allocator.html) -- MEDIUM confidence
- [SEI CERT thread safety](https://wiki.sei.cmu.edu/confluence/display/c/POS47-C.+Do+not+use+threads+that+can+be+canceled+asynchronously) -- HIGH confidence, authoritative standard
- [Memory safety and thread safety relationship](https://www.ralfj.de/blog/2025/07/24/memory-safety.html) -- MEDIUM confidence

---
*Feature research for: CBQS Solver Stabilization and C Optimization*
*Researched: 2026-02-04*
