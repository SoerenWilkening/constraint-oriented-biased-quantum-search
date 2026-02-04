# Domain Pitfalls

**Domain:** C/Cython solver stabilization and optimization (CBQS)
**Researched:** 2026-02-04

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or silent correctness bugs.

### Pitfall 1: Global BranchingStats Races Under Joblib Threading

**What goes wrong:** `BranchingStats` is a global `BranchingStats_t` in `Branching.c` (line 5). The Python `Model.solve()` method launches `num_workers` threads via `joblib.Parallel(backend="threading")`, and every thread calls `set_bias_wrapper()` / `set_factors_wrapper()` which write directly to this global. Simultaneously, the hot-path `BranchingFunction()` inline reads from it. With multiple solver instances or concurrent `solve()` calls, threads stomp on each other's bias values, producing silently wrong sampling distributions.

**Why it happens:** The code was written for single-solver sequential use. Joblib threading was added later without converting global state to per-solver context.

**Consequences:** Non-deterministic solver behavior. Objective values may be subtly wrong with no crash or error message. Extremely hard to debug because the branching function still produces plausible-looking numbers -- just the wrong ones.

**Prevention:**
1. Move `BranchingStats` into `model_t` as a member field. Pass `model_t*` (or `BranchingStats_t*`) through to every function that currently reads the global.
2. Do NOT use a mutex around `BranchingStats` reads -- it is on the hot path (called per-bit per-sample). The overhead would negate all performance gains.
3. Audit every call chain from `ctg()` and `local_search()` downward to confirm they receive stats via parameter, not via global access.
4. `set_bias()`, `set_factors()`, `set_obj_dependence()`, `set_constraint_dependence()` must all become `model_t`-scoped.

**Detection:** Run two solver instances with different bias parameters simultaneously. If results are identical regardless of bias, the global is being shared. Add an assertion in debug builds: `assert(stats == &model->branching_stats)`.

**Phase mapping:** This must be the FIRST refactoring step, before any threading or performance work. Everything else depends on per-solver state being correct.

**Confidence:** HIGH -- directly observed in codebase (`Branching.c:5`, `Branching.h:26`, `Model.pyx:236`).

---

### Pitfall 2: Freeing Thread-Local Data Before Thread Completes

**What goes wrong:** In `accept_best_routine()` (local_search.c:307-311), `data[i].remainings` and bit arrays are freed immediately after `pthread_create()` returns, but the thread has not started executing yet. The thread later reads freed memory, causing use-after-free, heap corruption, or silent data corruption.

**Why it happens:** The `free()` calls are placed in the same loop as `pthread_create()` instead of after `pthread_join()`. This is a classic race: `pthread_create()` returns immediately, the thread may not have copied or used the data yet.

**Consequences:** Heap corruption, segfaults, or -- worse -- silently wrong constraint evaluations that produce incorrect solver results. Valgrind would flag this as "Invalid read of size 8."

**Prevention:**
1. Move ALL `free(data[i].remainings)`, `sw_clear(data[i].ful_con)`, and `sw_clear(data[i].ful)` calls to AFTER the `pthread_join()` loop.
2. Alternatively, have each thread own and free its own copies.
3. Add a Valgrind/ASan CI gate: `valgrind --tool=memcheck ./test` must pass with zero errors before any PR merges.

**Detection:** Run with AddressSanitizer (`-fsanitize=address`) or Valgrind. This will immediately flag the use-after-free.

**Phase mapping:** Fix this bug BEFORE any other local_search refactoring. It is a correctness bug, not a performance issue.

**Confidence:** HIGH -- directly observed at `local_search.c:307-311` where free happens inside the `pthread_create` loop rather than after `pthread_join` loop at line 314.

---

### Pitfall 3: Expression Mutation Through Python Operator Overloading

**What goes wrong:** The `Expression` class in `Expression.pyx` mutates `self` in `__add__`, `__mul__`, etc. (e.g., line 136: `add_constant(self.expr, other); return self`). When a user writes `expr2 = expr1 + 5`, both `expr1` and `expr2` point to the same mutated C expression. Later use of `expr1` in a constraint and `expr2` in an objective creates aliased, shared C memory. Any subsequent modification to either expression corrupts the other.

**Why it happens:** Python operator overloads are expected to return NEW objects. Returning `self` after mutation violates this contract. The C-level `add_constant()` and `multiply_variable()` functions mutate in place, and the Cython wrappers pass this through.

**Consequences:** Constraints and objectives silently share expression data. Model builds appear correct but produce wrong solver results. User has no way to detect this without inspecting C memory.

**Prevention:**
1. Every `__add__`, `__radd__`, `__mul__`, `__rmul__` must create a NEW `Expression`, copy `self` into it, then mutate the copy.
2. Add `__iadd__` and `__imul__` for explicit in-place operations if performance matters.
3. Write a test: `e1 = x + 5; e2 = e1 + 3; assert e1 is not e2` -- this will FAIL with current code.

**Detection:** Unit test that verifies operator overloads return distinct objects. Also test that modifying a derived expression does not change the original.

**Phase mapping:** Fix BEFORE any performance work on the expression/constraint pipeline. Immutability is a correctness prerequisite.

**Confidence:** HIGH -- directly observed in `Expression.pyx:131-155`.

---

### Pitfall 4: GIL/nogil Callback Deadlock and Segfault

**What goes wrong:** The `my_callback_c()` function in `SearchLib.pyx:112` is declared `with gil`, meaning it reacquires the GIL every time C code calls the callback. But the callback is invoked inside `with nogil` blocks (e.g., `SearchLib.pyx:159-160`). If the Python callback does anything that blocks or triggers GC, and another thread is also trying to acquire the GIL for its own callback, a deadlock or segfault occurs. Additionally, the `python_callback` global (line 117) is shared across all threads with no synchronization.

**Why it happens:** The GIL re-acquisition pattern is correct for single-threaded use. With Joblib threading (12 workers by default), multiple C threads can simultaneously try to call back into Python via `with gil`, and they all share the same `python_callback` global variable.

**Consequences:** Deadlock (all threads waiting for GIL), segfault (callback pointer changes while another thread is mid-call), or silent data corruption (callback sees wrong Python state).

**Prevention:**
1. Make `python_callback` thread-local or pass it as a parameter in a per-thread context struct.
2. Keep callbacks as simple as possible -- ideally just set a flag, do not allocate Python objects.
3. If callbacks must touch Python objects, use `PyGILState_Ensure()` / `PyGILState_Release()` pattern explicitly rather than relying on Cython's `with gil`.
4. Consider removing the callback from the hot path entirely -- accumulate results in C, report back to Python only between solver iterations.

**Detection:** Run solver with 12+ workers and a callback that does non-trivial Python work (e.g., logging, list append). Look for hangs or segfaults.

**Phase mapping:** Address during the thread-safety refactoring phase. Convert to per-solver callback context alongside BranchingStats conversion.

**Confidence:** HIGH -- `python_callback` global at `SearchLib.pyx:117`, shared across Joblib threads at `SearchLib.pyx:236`.

---

### Pitfall 5: Struct Layout Changes Breaking Cython Declarations Without Recompilation

**What goes wrong:** The C structs (`model_t`, `new_constraints_t`, `state_t`, etc.) are declared in both C headers AND duplicated in `.pxd` Cython declaration files. When you add a field to `model_t` in `model.h`, you must also update `Model.pxd`. If you forget, or if field ordering differs, the Cython-generated C code will read/write wrong offsets, producing memory corruption with no compiler error.

**Why it happens:** Cython `.pxd` files are essentially a manual copy of C struct layouts. There is no automated verification that they match the actual C headers. A field added at position 3 in the C header but missing from the `.pxd` means every field after position 3 is at the wrong offset in Cython-generated code.

**Consequences:** Silent memory corruption. Fields read garbage values. Writes overwrite adjacent fields. Extremely difficult to debug because the code compiles and links without error.

**Prevention:**
1. After ANY change to a C struct, immediately update the corresponding `.pxd` file. Treat this as an atomic operation.
2. Add a compile-time size assertion: `_Static_assert(sizeof(model_t) == EXPECTED_SIZE, "model_t layout changed");` in a test file.
3. Add a CI step that does a clean rebuild from scratch (`rm -rf build/ *.so && python setup.py build_ext --inplace`) -- stale `.so` files with old struct layouts are a common source of this bug.
4. Consider using `cdef extern from "model.h"` to declare structs directly from headers rather than manually duplicating them.

**Detection:** If solver starts producing garbage after adding struct fields, this is the first thing to check. Run `python setup.py build_ext --inplace --force` to force recompilation.

**Phase mapping:** Every phase that modifies C structs must include `.pxd` update as part of the definition of done.

**Confidence:** HIGH -- standard Cython/C interop issue, verified by the existence of separate `.pxd` and `.h` files in this codebase.

---

## Moderate Pitfalls

Mistakes that cause delays, performance regressions, or accumulated technical debt.

### Pitfall 6: Premature Mutex Insertion on Hot Paths

**What goes wrong:** When converting global state to thread-safe state, the instinct is to wrap every shared access in `pthread_mutex_lock/unlock`. For data accessed in the inner loop (like `BranchingFunction()` which is called per-bit per-sample), mutex overhead dominates computation time. A solver that was doing 100K samples/sec drops to 5K samples/sec.

**Why it happens:** Mutexes are the obvious correctness fix. The performance impact is not apparent until benchmarking.

**Prevention:**
1. Prefer per-thread/per-solver copies of hot-path data (like `BranchingStats_t`) over shared-with-mutex.
2. Reserve mutexes for infrequent operations: updating `global_opt` (already done correctly in `SearchLib.c:164`), incumbent list updates.
3. Benchmark BEFORE and AFTER every lock addition. If a function is called >10K times per solver iteration, it must not acquire a lock.
4. Use the existing pattern: `update_lock` in `SearchLib.c:9` only protects the `global_opt` update, not the sampling loop. Follow this pattern.

**Detection:** Profile with `perf stat` or `time` before and after changes. If wall-clock time increases >5% on the same benchmark, investigate.

**Phase mapping:** Thread safety phase. Establish performance baseline BEFORE starting.

**Confidence:** HIGH -- well-established performance principle, confirmed by codebase's existing `update_lock` pattern.

---

### Pitfall 7: Dynamic Array Reallocation Breaking In-Flight Pointers

**What goes wrong:** Expression arrays currently start with fixed size `min_size = 30000` (Expression.c:3) and grow via `realloc()`. When `realloc()` moves memory to a new location, any existing pointers into the old buffer become dangling. If constraint processing holds a pointer to `expr->literals` and then another expression operation triggers `realloc()`, the held pointer is invalid.

Similarly, the `new_constraints_t` struct uses fixed offsets computed during `preprocessing()`. If constraints are added after preprocessing, the offset arrays are stale.

**Why it happens:** `realloc()` may return a different address. C has no mechanism to notify holders of the old address.

**Prevention:**
1. Never hold raw pointers into realloc-able buffers across function calls. Use indices instead.
2. If moving to dynamic allocation for constraint arrays, do the allocation once (after all expressions are added, before solving). Do not grow during solving.
3. For memory pools: allocate pool at solver start, return chunks from pool, free entire pool at solver end. Never realloc the pool during solving.
4. Separate the "building" phase (expressions mutable, arrays growing) from the "solving" phase (everything frozen, no reallocation).

**Detection:** ASan will catch use-after-realloc. Also test with large expressions that force multiple reallocations.

**Phase mapping:** Memory layout refactoring phase. Establish clear build-vs-solve lifecycle.

**Confidence:** HIGH -- `realloc` at Expression.c:87-89, standard C pitfall.

---

### Pitfall 8: VLA Stack Overflow in Constraint Evaluation

**What goes wrong:** Variable-length arrays (VLAs) are used on the stack in several hot-path functions: `int bits[dat->d]` (local_search.c:152), `int64_t totals[C]` (local_search.c:175), `int64_t remainings[C]` (local_search.c:271), `int64_t potentials[C]` (solver.h/SearchLib.c). For large problem instances with many constraints, these VLAs can exceed the thread stack size (typically 2MB per pthread), causing a stack overflow with no error message -- just a segfault.

**Why it happens:** VLAs are convenient but their size is not checked at compile time. Thread stacks are much smaller than the main thread stack.

**Prevention:**
1. Replace VLAs with heap allocation (`malloc`/`free`) for any array sized by problem input (number of constraints, number of variables).
2. If allocation cost matters, use a pre-allocated scratch buffer in the per-thread data struct.
3. Set explicit thread stack sizes with `pthread_attr_setstacksize()` as a safety net.
4. As a rule: if the array size comes from user input, it MUST NOT be a VLA.

**Detection:** Test with large constraint counts (C > 10000). If segfaults appear only for large instances, suspect stack overflow.

**Phase mapping:** Memory layout refactoring phase. Convert VLAs to heap or pool allocation.

**Confidence:** HIGH -- directly observed VLAs at local_search.c:152, 175, 271, 449.

---

### Pitfall 9: stop_flag Global Shared Across Solver Instances

**What goes wrong:** `stop_flag` in `SearchLib.c:46` is a global `volatile sig_atomic_t`. When multiple solver instances run in parallel (Joblib threading), one solver's SIGINT handler sets `stop_flag = 1`, which stops ALL solver instances, not just the one that timed out. This is by design for the SAT solver's `signal.raise_signal(signal.SIGINT)` pattern in `SearchLib.pyx:184`, but it means independent solver runs cannot coexist.

**Why it happens:** Signal handling is process-global by definition. Using signals for solver control flow is a fundamentally non-thread-safe pattern.

**Prevention:**
1. Replace signal-based stopping with a per-solver flag in `model_t` (e.g., `mod->should_stop`).
2. Check `mod->should_stop` instead of `stop_flag` in the solver loop.
3. Remove `signal.raise_signal(signal.SIGINT)` from `SearchLib.pyx` -- use the per-solver flag instead.
4. Keep signal handlers only for graceful process shutdown, not for solver control flow.

**Detection:** Run two solver instances. Stop one early. Observe whether the other also stops.

**Phase mapping:** Thread safety phase. Combine with BranchingStats per-solver conversion.

**Confidence:** HIGH -- directly observed at `SearchLib.c:46-50`, `SearchLib.pyx:184`.

---

### Pitfall 10: Optimizing Before Establishing Correctness Baseline

**What goes wrong:** Team starts optimizing hot paths (memory pools, SIMD, cache-line alignment) before having a correctness test suite. Optimizations introduce subtle bugs (off-by-one in pool allocation, wrong alignment for constraint arrays) that go undetected because there is no reference output to compare against.

**Why it happens:** Performance work is more exciting than writing tests. The solver "seems to work" based on manual inspection of a few results.

**Prevention:**
1. BEFORE any optimization, create a golden test suite: 5-10 problem instances with known optimal solutions, run current (unoptimized) solver, record exact output as reference.
2. Every optimization PR must pass the golden suite with bit-exact results.
3. For stochastic solvers: fix the random seed and verify that the same seed produces the same trajectory.
4. Add a determinism test: same input + same seed = same output, across all thread counts.

**Detection:** If optimized solver produces different results from unoptimized solver on the same seed, there is a bug.

**Phase mapping:** FIRST phase, before any optimization. Creating the test harness is a prerequisite for all subsequent work.

**Confidence:** HIGH -- universal software engineering principle, especially critical for numerical/optimization code.

---

## Minor Pitfalls

Mistakes that cause annoyance or minor regressions but are recoverable.

### Pitfall 11: Hardcoded Constants Limiting Scalability

**What goes wrong:** `#define NUMThreads 6` (local_search.h:55), `#define MAXCLAUSESIZE 4` (Expression.h:11), `#define MINARRAYSIZE 50000` (constraint.h:28), `min_size = 30000` (Expression.c:3). These constants limit scalability or waste memory. Changing them requires recompilation of all C code and Cython extensions.

**Prevention:**
1. Move runtime-configurable constants into `model_t` (especially `NUMThreads`).
2. Keep compile-time constants only for truly fixed values (like `MAXCLAUSESIZE` if the math requires exactly 4).
3. Document which constants are compile-time vs runtime in a single header.

**Phase mapping:** Refactoring phase. Low priority but should be addressed when touching each file.

**Confidence:** HIGH -- directly observed in headers.

---

### Pitfall 12: Missing NULL Checks After malloc

**What goes wrong:** Throughout the C code, `malloc()` / `calloc()` / `realloc()` return values are not checked. On memory pressure, these return NULL, and subsequent pointer dereference segfaults with no diagnostic.

**Prevention:**
1. Add a wrapper macro: `#define SAFE_MALLOC(ptr, size) do { ptr = malloc(size); if (!ptr) { fprintf(stderr, "OOM at %s:%d\n", __FILE__, __LINE__); exit(1); } } while(0)`
2. Apply consistently in new code. Retrofit gradually in existing code.

**Phase mapping:** Any phase. Low effort, add as part of each file touched.

**Confidence:** HIGH -- standard C practice, observed missing throughout codebase.

---

### Pitfall 13: printf Debug Output Left in Production Code

**What goes wrong:** `merge_expression()` in Expression.c:41 has `printf("\r%f", ...)` that prints progress to stdout on every call. Other functions have commented-out printf lines that could be accidentally uncommented. This pollutes output and slows performance.

**Prevention:**
1. Use a debug logging macro gated by `#ifdef DEBUG` or a verbosity level.
2. Remove all progress-printing printf from library code.
3. Add a CI check: `grep -rn 'printf' cbqs/src/*.c` should only match intentional output.

**Phase mapping:** Cleanup phase. Quick fix, do early.

**Confidence:** HIGH -- directly observed at Expression.c:41,53.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Per-solver BranchingStats | Forgetting one call site that still reads the global | Grep for `BranchingStats` across ALL `.c` and `.h` files. Delete the global entirely so the compiler finds every reference. |
| Expression immutability | Breaking Python operator semantics (a + b should not modify a) | Write unit tests for operator algebra BEFORE refactoring. |
| Memory pool for hot paths | Pool exhaustion during large solves | Size pool based on problem instance size. Add a fallback to malloc if pool is exhausted. |
| Thread safety with mutexes | Locking in wrong order between update_lock and any new locks | Define a lock ordering document. Only one lock (update_lock) should exist for most use cases. |
| Dynamic constraint arrays | Realloc invalidating pointers during solve | Freeze all arrays before solve starts. Assert no reallocation during solving phase. |
| Cython .pxd updates | Forgetting to update .pxd when C struct changes | Make .pxd update part of PR checklist. Add sizeof assertion in test. |
| VLA to heap conversion | Performance regression from malloc in tight loops | Use per-thread scratch buffers allocated once, not malloc per iteration. |
| Callback refactoring | Deadlock from GIL reacquisition in multi-threaded context | Minimize callback frequency. Batch updates. Test with high thread counts. |
| Performance optimization | No baseline to detect regressions | Establish golden test suite and benchmark BEFORE optimizing. |

## Sources

- Codebase analysis: `Branching.c`, `Branching.h`, `local_search.c`, `local_search.h`, `SearchLib.c`, `SearchLib.pyx`, `Model.pyx`, `Expression.pyx`, `Expression.c`, `model.c`, `model.h`, `constraint.h`, `solver.h`, `definitions.h`
- [Cython GIL Documentation](https://cython.readthedocs.io/en/latest/src/userguide/nogil.html) -- GIL management patterns and pitfalls
- [Cython Free Threading](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) -- Thread safety in Cython extensions
- [Cython callback/segfault discussion](https://cython-devel.python.narkive.com/CIoEbLI0/cython-callback-segfault) -- Callback GIL reacquisition issues
- [SEI CERT CON35-C: Avoid deadlock by locking in predefined order](https://wiki.sei.cmu.edu/confluence/display/c/CON35-C.+Avoid+deadlock+by+locking+in+a+predefined+order) -- Lock ordering discipline
- [Oracle Multithreaded Programming Guide](https://docs.oracle.com/cd/E19455-01/806-5257/6je9h0342/index.html) -- Mutex pitfalls and self-deadlock
- [The Risks of Mutexes (ModernCpp)](https://www.modernescpp.com/index.php/the-risk-of-mutexes/) -- Mutex anti-patterns
- [C++ Performance Optimization Pitfalls](https://medium.com/@threehappyer/c-performance-optimization-avoiding-common-pitfalls-and-best-practices-guide-81eee8e51467) -- Hot path optimization mistakes
- [ABI Compatibility Guide](https://gist.github.com/MangaD/506a0f3273724ef3af26b8c085accdcb) -- Struct layout and binary compatibility
