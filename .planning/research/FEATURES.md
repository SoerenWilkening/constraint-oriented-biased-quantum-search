# Feature Landscape: v1.1 Bug Fixes and Code Polish

**Domain:** Bug fixes, tech debt cleanup, and code polish for C/Cython/Python solver
**Researched:** 2026-02-06
**Confidence:** HIGH (based on direct codebase analysis of every affected file + solver library patterns)

## Context

v1.0 shipped a stable, thread-safe solver with comprehensive testing. v1.1 is a cleanup milestone:
no new features, no breaking changes. The goal is to fix known bugs, remove dead code, fix
compiler warnings, and rework internal patterns that limit correctness or future extensibility.

All items below derive from the v1.0 audit's 6 tech debt items plus additional code analysis.

---

## Table Stakes (Must Fix for v1.1)

These are bugs that cause crashes, incorrect behavior, or compiler warnings that indicate latent
correctness issues. Shipping v1.1 without these fixed provides no value.

### 1. SATISFY Mode Crash (P0 -- Crashes at Runtime)

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/SearchLib.pyx`, line 220 |
| **Bug** | `stpvl = -len(mod.mod[0].con[0].num_constraints)` calls `len()` on a `uint32_t` scalar |
| **Root cause** | `num_constraints` is a `uint32_t` field in the `new_constraints_t` struct (see `constraint.h:34`), not an array. `len()` on an int raises `TypeError: object of type 'int' has no len()` |
| **Impact** | Any model that uses `solver == SATISFY` (the default mode for models without `set_objective`) crashes immediately when `solve()` is called |
| **Expected fix** | Replace `len(mod.mod[0].con[0].num_constraints)` with `mod.mod[0].con[0].num_constraints` (the integer value directly) |
| **Complexity** | LOW -- single line change |
| **Confidence** | HIGH -- verified by reading both `SearchLib.pyx:220` and `constraint.h:34` |

**Additional SATISFY mode issue at line 236:** The SATISFY branch still uses `signal.raise_signal(signal.SIGINT)` to stop all workers when a solution is found. This was supposed to be replaced by the `solver_ctx_request_stop()` mechanism in v1.0 Phase 4. The OPTIMIZE branch correctly uses the ctx-based stop, but the SATISFY branch was apparently missed. This should be fixed alongside the crash.

**SATISFY mode semantics (from solver library patterns):**

In established solvers (SCIP, OR-Tools CP-SAT), satisfaction and optimization modes differ fundamentally:
- **Satisfaction**: Goal is finding ANY feasible solution. There is no objective function to track. The solver should return as soon as feasibility is achieved, or report infeasibility. In OR-Tools, `SearchForAllSolutions` is only valid when no objective is set. In SCIP, satisfaction problems use `SCIPsolve()` with early termination on first feasible solution.
- **Optimization**: Goal is improving objective iteratively. History tracking, incumbent solutions, and convergence are meaningful.

The CBQS SATISFY path in `ctg()` (SearchLib.c:110-194) correctly uses `CSearch_sat` which maximizes the count of satisfied constraints. The stop condition at line 194 checks `cur_sol->tot_profit == -(int64_t)mod->con->num_constraints` (all constraints satisfied). This is logically correct -- the Cython-side crash is purely a type error in the Python wrapper, not a C-level logic bug.

### 2. Remaining VLA in local_search.c (P1 -- Stack Overflow Risk)

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/src/local_search.c`, line 332 |
| **Bug** | `int64_t remainings[C]` where C is `con->num_constraints` (runtime value) |
| **Root cause** | This VLA was missed during the v1.0 VLA elimination pass (Phase 5). Other VLAs in the same file were replaced with heap or per-thread buffers |
| **Impact** | Stack overflow for large constraint counts. C23 removes VLA entirely. GCC 15 may warn with `-Wvla` |
| **Expected fix** | Replace with `int64_t *remainings = malloc(C * sizeof(int64_t))` plus NULL check and corresponding `free()` before all return paths |
| **Complexity** | LOW -- follows the exact pattern already used elsewhere in the same file (e.g., lines 572-576) |
| **Confidence** | HIGH -- verified at `local_search.c:332` |

### 3. GCC 15 Type Mismatch Warnings (P1 -- Compiler Correctness)

| Attribute | Detail |
|-----------|--------|
| **Files** | Multiple C source files |
| **Bug** | Type mismatches between `int`, `size_t`, `uint32_t`, and `int64_t` in function calls and comparisons |
| **Root cause** | The constraint struct uses `uint32_t` for counts and offsets, but many functions use `int` or `size_t` for the same values. GCC 15 is stricter about implicit narrowing conversions |
| **Impact** | Clean compilation is a prerequisite for CI trust. Warnings may hide real truncation bugs (e.g., constraint counts exceeding INT_MAX on 32-bit) |
| **Expected fix** | Audit all warning sites, use consistent types, add explicit casts where narrowing is intentional and safe |
| **Complexity** | MEDIUM -- requires systematic review, but each individual fix is trivial |
| **Confidence** | MEDIUM -- exact warning list needs a GCC 15 build to enumerate |

### 4. Incomplete local_search() API Migration (P1 -- Incorrect Behavior)

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/Model.pyx`, `local_search()` method (line 371-417) |
| **Bug** | The method signature and parameter passing were updated in v1.0 to match `solve()`, but the internal wiring may be incomplete |
| **Root cause** | `local_search()` was updated to return `OptimizeResult` but some parameters (seed, num_threads) may not flow correctly through to the C layer since the `run_local_search` call pattern differs from `run_sampling` |
| **Impact** | `local_search()` results may not reflect configured seed/threads correctly |
| **Expected fix** | Verify parameter flow: seed -> ctx, num_threads -> ctx for local_search path. Ensure `model.seed` and `model.num_threads` are honored |
| **Complexity** | LOW -- mostly verification and small wiring fixes |
| **Confidence** | MEDIUM -- needs testing to confirm whether behavior is actually wrong |

---

## Nice-to-Have (Could Defer to v1.2)

These improve code quality and maintainability but do not fix user-facing bugs. Ideally done in v1.1
for cleanliness, but deferrable without harm.

### 5. Dead Code Removal -- Commented-Out VLA/Debug Code

| Attribute | Detail |
|-----------|--------|
| **Files** | `local_search.c` (lines 47, 53-66, 179, 231-238, 252-256, 496-498, 506-511, 541-544, etc.), `Branching.c` (lines 48-97, 101, 113-132), `SearchLib.c` (lines 91, 159, etc.), `solver.c` (scattered printf), `Model.pyx` (lines 86, 105, 109, 245-248), `Expression.pyx` (line 197) |
| **Issue** | Dozens of commented-out code blocks: old VLA declarations, debug printf statements, abandoned algorithm variants, commented-out aspiration criteria |
| **Impact** | Reduces readability, confuses maintainers about what is active, makes grep/search noisy |
| **Expected approach** | Remove all `//` and `#`-commented code blocks that are clearly dead (old implementations, debug prints). Preserve comments that document WHY something is done a certain way. Git history preserves the deleted code |
| **Complexity** | LOW -- mechanical, but needs care to not remove meaningful comments |
| **Confidence** | HIGH -- verified by reading every source file |

### 6. Module-Level cdef History Callback Rework

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/SearchLib.pyx`, lines 137-159 |
| **Bug** | Four module-level `cdef` variables (`_history_list`, `_history_prev_best`, `_history_original_callback`, `_history_mod`) store per-solve history state at module scope |
| **Root cause** | Cython `cpdef` functions cannot capture closures, and regular Python classes cannot access `cdef` attributes. The module-level state was a pragmatic workaround |
| **Impact** | If two `solve()` calls run concurrently in the same process (e.g., from different threads or async contexts), they overwrite each other's history state. The current joblib-based parallelism in `solve()` is safe because all workers share the same `_history_mod` object, but any future multi-model concurrent solving would break |
| **Constraint** | No breaking changes in v1.1 |

**How established solvers handle this:**

- **SCIP**: Uses per-solve event handler objects. Event handlers are registered per SCIP instance. Each handler has its own data pointer (`SCIPeventhdlrGetData`). History tracking is done via `SCIP_EVENTTYPE_BESTSOLFOUND` events, with history stored in the handler's private data.
- **OR-Tools CP-SAT**: Uses `CpSolverSolutionCallback` subclasses. Each callback instance has its own state. The solver guarantees that "at most one thread executes solution_callback at a time" but callbacks are per-solve-call, not global. The `SharedResponseManager` class handles cross-thread history with explicit thread safety.
- **Pattern**: The universal pattern is **per-solve callback state**, not module-level state. The callback object/struct carries its own history buffer.

**Expected approach for CBQS:**

Move the four module-level `cdef` variables into the `Model` object's `cdef` attributes (which are accessible from `cdef`/`cpdef` functions). Pass the Model instance through the callback chain. This keeps the callback mechanism working identically but scopes state to the solve call. Since `_history_mod` is already set to the Model instance, the refactor is straightforward.

**Alternative**: Use a Python `dict` keyed by `id(mod)` as module-level state, with cleanup in a `finally` block. Less clean but lower risk.

| Complexity | MEDIUM -- requires understanding the Cython cdef/cpdef closure limitation |
|------------|---------|
| **Confidence** | HIGH -- verified the pattern and the limitation |

### 7. Bare Except Clause in Model.pyx

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/Model.pyx` |
| **Bug** | Bare `except:` clauses that catch `BaseException` including `KeyboardInterrupt` and `SystemExit` |
| **Impact** | Can mask bugs, prevent clean shutdown, and swallow keyboard interrupts during debugging |
| **Expected fix** | Replace `except:` with `except Exception:` throughout |
| **Complexity** | LOW |
| **Confidence** | MEDIUM -- the grep for `except:` returned no matches, which may mean the issue was already partially addressed or the pattern uses `except Exception` with too broad a scope. Need to verify during implementation |

**Note:** My grep for `bare except|except:` in the cbqs directory found zero matches. This item may have been fixed during v1.0 or the issue may manifest differently (e.g., `try/except` in `__init__.py` catching `ImportError` broadly). Verify during implementation.

### 8. Deprecated Global BranchingStats Cleanup

| Attribute | Detail |
|-----------|--------|
| **Files** | `cbqs/src/Branching.c` (lines 6-21), `cbqs/src/Branching.h` (line 30) |
| **Current state** | Global `BranchingStats` variable still exists alongside the per-context `ctx->branching_stats`. The global functions `set_bias()`, `set_factors()`, `set_obj_dependence()`, `set_constraint_dependence()` modify the global. The Python-side `branching.pyx` calls these global setters |
| **Issue** | Two parallel state systems (global and per-ctx) must stay in sync. The global is marked `DEPRECATED` in the header but is still actively used by `branching.pyx` |
| **v1.1 approach** | Keep the API (`set_bias_wrapper()` etc.) but have the global setters ALSO propagate to any active solver context. Or, have `branching.pyx` wrappers call the ctx-based setters when a ctx is available. Do NOT remove the global API -- that's a breaking change for v2.0 |
| **Complexity** | MEDIUM -- needs careful thought about the sync mechanism |
| **Confidence** | HIGH -- verified both code paths |

### 9. signal.raise_signal in SATISFY Branch

| Attribute | Detail |
|-----------|--------|
| **File** | `cbqs/SearchLib.pyx`, line 236 |
| **Bug** | `signal.raise_signal(signal.SIGINT)` is still used in the SATISFY mode branch to stop parallel workers |
| **Root cause** | The v1.0 Phase 4 refactoring to `solver_ctx_request_stop()` covered the OPTIMIZE path but missed the SATISFY path |
| **Impact** | Sends SIGINT to the entire process when a satisfying solution is found, which can interfere with Jupyter notebooks, debuggers, and calling applications |
| **Expected fix** | Replace with `solver_ctx_request_stop(ctx)` and check `not_stop[0] = 0` for the Python-level loop, matching the OPTIMIZE branch pattern |
| **Complexity** | LOW |
| **Confidence** | HIGH -- verified at SearchLib.pyx:236 |

---

## Anti-Features (Do NOT Do During v1.1 Cleanup)

Over-engineering risks during cleanup milestones. Each of these is a real temptation during
"while we're in there" refactoring.

### A1. Refactoring the Solver Architecture While Fixing Bugs

| Why tempting | "The OPTIMIZE and SATISFY paths share so much code, we should unify them" |
|-------------|---------|
| **Why avoid** | The `ctg()` function in SearchLib.c is the core solver loop. It has complex state transitions between stages (satisfaction -> constraint tightening -> optimization). Refactoring this while fixing the SATISFY crash risks breaking the working OPTIMIZE path. The function is ~130 lines and well-understood; it does not need structural changes |
| **What to do instead** | Fix the specific Cython-side crash (line 220) and the signal.raise_signal (line 236). Leave the C-level `ctg()` function untouched |

### A2. Adding New Test Infrastructure Beyond What Bugs Require

| Why tempting | "We should add property-based testing, mutation testing, fuzz testing for the cleanup" |
|-------------|---------|
| **Why avoid** | v1.0 already established 58+ C tests and 200+ Python tests with ASan/Valgrind/TSan in CI. Adding new testing infrastructure is a feature, not a bug fix. The existing test suite is sufficient to validate v1.1 fixes |
| **What to do instead** | Write targeted regression tests for each bug fix (SATISFY mode test, VLA boundary test, concurrent history test). Use existing pytest + CMocka frameworks |

### A3. Reworking the Expression System

| Why tempting | "While cleaning up dead code in Expression.pyx, we should fix the __eq__ method returning self" |
|-------------|---------|
| **Why avoid** | The Expression `__eq__` returning `self` (line 367-380) is intentional -- it converts the expression into a constraint with EQUAL sense. This is the API's constraint-building DSL. "Fixing" it to return a boolean would break every model that uses `expr == value`. Similarly, `__le__` and `__ge__` return self with sense metadata. This is correct by design |
| **What to do instead** | Remove commented-out code in Expression.pyx. Do not change operator semantics |

### A4. Making BranchingStats Fully Context-Only

| Why tempting | "The global BranchingStats is deprecated, just remove it now" |
|-------------|---------|
| **Why avoid** | Removing `extern BranchingStats_t BranchingStats` and the global setter functions is a breaking change. Downstream code (including the project's own `branching.pyx` and potentially user scripts) calls `set_bias_wrapper()` which calls the global `set_bias()`. Removing it requires migrating all callers to pass a solver context |
| **What to do instead** | Clean the internals (ensure ctx and global stay in sync). Mark the global API with deprecation warnings. Plan removal for v2.0 |

### A5. Optimizing Hot Paths During Cleanup

| Why tempting | "The commented-out incremental constraint evaluation in local_search.c should be re-enabled" |
|-------------|---------|
| **Why avoid** | The incremental path (`adjusted_constraint_violation` calls at lines 231-238) was commented out and replaced with full evaluation (`constraint_violation` at line 229). This was a deliberate choice -- the incremental path had correctness issues. Re-enabling it is a performance optimization, not a bug fix. Mixing optimization work with cleanup increases risk |
| **What to do instead** | Remove the commented-out incremental code as dead code. If performance optimization is needed, do it in a dedicated future milestone with proper benchmarking |

### A6. Migrating to Python Free-Threading (nogil)

| Why tempting | "Cython 3 has experimental free-threading support, we should adopt it" |
|-------------|---------|
| **Why avoid** | Cython's free-threading support (documented in `cython.readthedocs.io`) is explicitly described as not yet ensuring "any significant level of thread safety" for extension modules. The `critical_section` primitive exists but the ecosystem is immature. Adopting it during a bug-fix milestone would introduce new, poorly-understood failure modes |
| **What to do instead** | The existing GIL-based callback mechanism works. The C-level parallelism (pthreads) is already GIL-free. Leave the threading model as-is |

---

## Feature Dependencies for v1.1

```
[SATISFY Mode Crash Fix (#1)]
    |
    +-- includes --> [signal.raise_signal fix (#9)]
    |
    +-- regression test needed

[Remaining VLA (#2)]
    |
    +-- follows v1.0 VLA elimination pattern exactly
    |
    +-- regression test: large constraint count

[GCC 15 Warnings (#3)]
    |
    +-- independent, can be done in parallel with all others
    |
    +-- requires GCC 15 build to enumerate warnings

[local_search() API Migration (#4)]
    |
    +-- depends on understanding ctx flow from run_local_search
    |
    +-- test: verify seed_used populated after local_search()

[Dead Code Removal (#5)]
    |
    +-- independent, but do AFTER bug fixes (avoid merge conflicts)

[History Callback Rework (#6)]
    |
    +-- depends on understanding Cython cdef attribute access rules
    |
    +-- test: concurrent model solves produce correct history

[BranchingStats Cleanup (#8)]
    |
    +-- depends on understanding global/ctx sync requirements
    |
    +-- test: global setters still work, ctx-based setters still work
```

## Comparable Solver Cleanup Patterns

How established solvers handle the same categories of cleanup:

| Category | SCIP Pattern | OR-Tools Pattern | CBQS v1.1 Approach |
|----------|-------------|-----------------|-------------------|
| **Callback state** | Per-instance event handler data pointer | Per-call callback class instances | Move from module-level to Model-level cdef attributes |
| **Deprecated API** | `SCIP_DEPRECATED` macro, kept for 2 major versions | Proto field deprecation with `deprecated = true` | Keep API, mark DEPRECATED in header, plan removal for v2.0 |
| **Dead code** | Aggressive removal in minor versions | Removed in release branches | Remove all commented-out code, git preserves history |
| **Compiler warnings** | Zero-warning policy (`-Werror` in CI) | Zero-warning policy | Fix all GCC 15 warnings, consider adding `-Wvla` flag |
| **VLA elimination** | Never used VLAs (C89 compatibility) | C++ does not have VLAs | Replace remaining VLA with malloc + error handling |
| **Signal handling** | Per-instance interrupt handler via `SCIPinterruptSolve()` | No signals, uses atomic stop flags | Replace `signal.raise_signal` with `solver_ctx_request_stop()` |

## MVP Recommendation for v1.1

**Must ship (P0/P1):**
1. SATISFY mode crash fix (line 220 type error + line 236 signal)
2. Remaining VLA replacement (local_search.c:332)
3. GCC 15 type mismatch warnings
4. local_search() API migration completion

**Should ship (P2):**
5. Dead code removal (commented-out blocks across all C/Cython files)
6. History callback rework (module-level to Model-level)
7. Bare except clause fix (if still present)
8. BranchingStats cleanup (sync global and ctx)

**Defer to v1.2:**
- Any performance optimization
- Any new test infrastructure beyond regression tests
- Any API redesign
- Free-threading adoption

## Sources

- Direct codebase analysis (HIGH confidence) -- all line references verified against source
- [SCIP Event Handler documentation](https://www.scipopt.org/doc/html/EVENT.php) -- HIGH confidence, official docs
- [SCIP Concurrent Solving](https://www.scipopt.org/doc/html/CONCSCIP.php) -- HIGH confidence, official docs
- [OR-Tools CP-SAT Callback documentation](https://developers.google.com/optimization/reference/python/sat/python/cp_model) -- HIGH confidence, official docs
- [OR-Tools SharedResponseManager](https://developers.google.com/optimization/reference/sat/synchronization/SharedResponseManager) -- HIGH confidence, official docs
- [OR-Tools log callback thread safety issue](https://groups.google.com/g/or-tools-discuss/c/5FHrIjHBstc) -- MEDIUM confidence, community discussion
- [Cython free-threading documentation](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) -- HIGH confidence, official docs
- [Cython cdef globals should be module state](https://github.com/cython/cython/issues/5425) -- MEDIUM confidence, open issue
- [VLA pitfalls in C](https://jorenar.com/blog/vla-pitfalls) -- MEDIUM confidence, technical blog
- [C23 VLA removal](https://www.codegenes.net/blog/in-which-versions-of-the-c-standard-are-variable-length-arrays-not-part-of-the-language-required-or-optional/) -- MEDIUM confidence, technical reference

---
*Feature research for: CBQS v1.1 Bug Fixes and Code Polish*
*Researched: 2026-02-06*
*Supersedes: v1.0 FEATURES.md (2026-02-04)*
