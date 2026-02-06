# Domain Pitfalls: v1.1 Cleanup and Polish

**Domain:** C/Cython solver bug fixes, dead code removal, and API cleanup
**Researched:** 2026-02-06
**Context:** CBQS v1.0 is stable with 58+ C tests, 200+ Python tests, CI with ASan/Valgrind/TSan. v1.1 is purely cleanup work -- no new features, no breaking changes. The test suite provides a safety net, but cleanup work introduces its own class of subtle regressions.

**Key principle:** Cleanup work feels safe. That illusion is the biggest risk. Every category below has caused real regressions in real C/Cython codebases.

---

## Critical Pitfalls

Mistakes that introduce regressions, memory corruption, or silent correctness bugs during cleanup.

---

### Pitfall 1: GCC Warning Fixes That Silently Change Behavior

**What goes wrong:** Fixing compiler warnings is not semantics-neutral. Common warning "fixes" that change behavior:

1. **Adding parentheses to `&&`/`||` chains changes evaluation.** The codebase has several instances of ambiguous operator precedence. In `solver.c:545`:
   ```c
   if (time > mod->stopping_time || (cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1)) break;
   ```
   GCC warns about `&&` inside `||` without parentheses. The current code evaluates `&&` before `||` (C precedence rules), which means: `time > stopping_time || (profit <= stop_val && stop_val != -1)`. Adding parentheses the wrong way -- `(time > stopping_time || cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1)` -- completely changes the stopping logic.

2. **Fixing signed/unsigned comparison warnings by casting.** The codebase mixes `int`, `size_t`, `uint32_t`, and `int64_t` extensively. Casting `int` to `size_t` when the int is -1 (used as a sentinel, e.g., `get_index()` in constraint.c returns -1) produces `SIZE_MAX`, which silently passes any `>= 0` check.

3. **Fixing `-Wimplicit-function-declaration` by adding missing prototypes.** If the actual function has a different return type than the compiler assumed (default `int`), adding the correct prototype changes calling convention and return value handling.

**Why it happens:** Warning fixes feel mechanical. Developers add casts or parentheses without analyzing whether the current behavior (despite the warning) is the INTENDED behavior.

**Consequences:** Solver stopping conditions change silently. Constraint evaluation produces wrong results for edge cases. No test failure if the changed code path is not covered.

**Prevention:**
1. For EVERY warning fix, write a comment documenting the INTENDED semantics: "This expression means X, parenthesized as Y."
2. Never fix `&&`/`||` precedence warnings without first confirming the current evaluation order is correct by reading surrounding context.
3. Never fix signed/unsigned warnings with a bare cast. Check if the signed value can be negative, and if -1 is a valid sentinel.
4. Run the full test suite after each individual warning fix, not after fixing all warnings at once.
5. For the specific `solver.c:545` case, add an explicit test for the stopping condition with `stop_val == -1` and `stop_val != -1`.

**Warning signs:** Test suite passes after fixing 20 warnings in one commit. This is suspicious -- at least one was probably wrong.

**Detection:** Diff the warning-fix commit. For each parenthesization or cast, ask: "Does this change the value in any case?" If unsure, add a test for that specific case.

**Phase mapping:** Compiler warning fixes must be ONE WARNING PER COMMIT with targeted test verification.

**Confidence:** HIGH -- directly observed ambiguous expressions in `solver.c:545`, `solver.c:583`, `local_search.c:662-664`. The `&&`/`||` pattern appears in at least 5 places in the solver code.

---

### Pitfall 2: Dead Code Removal That Removes Needed-But-Untested Code

**What goes wrong:** The codebase has extensive commented-out code blocks, but some "dead" code is actually:

1. **Code reachable only via code paths not covered by tests.** The `read_states()` function in `state.c` is used by `state_py.read()` which is used for file-based state loading. The tests may not exercise this path, but users do.

2. **Commented-out alternative algorithms that are toggled by uncommenting.** In `local_search.c`, the `adjusted_constraint_violation()` calls at lines 231-237 are commented out and replaced with a simpler `constraint_violation()` loop. The commented code is the OPTIMIZED version; the uncommented code is the FALLBACK. Deleting the commented code removes the only record of the optimized algorithm.

3. **Code that looks dead because it appears after a `break`/`return` but is actually reached via label or goto.** Not observed in this codebase, but a common C pitfall.

4. **Entire functions that appear unused in C but are called from Cython.** The `.pxd` files declare C functions that Cython calls directly. A function that has no C callers may still be actively used from Python.

**Why it happens:** Automated tools report "unreachable code" or "unused function" based on static analysis of the C compilation unit alone. They cannot see Cython callers. Manual inspection also misses cross-language call chains.

**Consequences:** Removing a "dead" function breaks the Cython build. Removing commented-out optimized code loses institutional knowledge. Removing a function used only in error paths causes crashes in production when errors occur.

**Prevention:**
1. Before removing ANY function, grep for its name across ALL `.pyx`, `.pxd`, `.py`, AND `.c`/`.h` files. Cython callers do not appear in C call graphs.
2. Before removing commented-out code blocks, determine: Is this an alternative implementation? A TODO? A debugging aid? Add a `// REMOVED: [reason]` comment or create a git tag before bulk removal.
3. Do not remove commented-out code and fix bugs in the same commit. Keep cleanup commits separate from behavior-changing commits so that git bisect works.
4. For each function being removed, verify it is not listed in any `.pxd` file's `cdef extern` block.

**Warning signs:** Build breaks after dead code removal ("undefined symbol"). Alternatively: no build break but a runtime `ImportError` or `AttributeError` when a previously-working feature is used.

**Detection:** Full `python setup.py build_ext --inplace && pytest` after each dead code removal. Also check: `grep -rn 'function_name' cbqs/*.pyx cbqs/*.pxd`.

**Specific codebase instances:**
- `updated()` comment in `state.c:154-178` -- an alternative implementation. The ACTIVE version is in `Branching.c:136`. The commented version in `state.c` can safely be removed, but only after verifying `Branching.h` declares the active one.
- `aspiration()` in `local_search.c:53-66` -- commented out, but the tabu aspiration logic at line 425 references it in a comment. Removing the commented function loses the algorithm documentation.
- `BranchingFunction()` in `Branching.c:48-97` -- commented-out non-inline version. The active version is the `static inline` in `Branching.h:46`. Safe to remove from `.c` but verify the `.h` inline is identical.
- `objective_value_improved()` calls commented out throughout `local_search.c` and `solver.c` -- these are the optimized constraint/objective evaluation paths. Removing them loses the algorithm.

**Phase mapping:** Dead code removal phase. One file per commit. Run full test suite between each.

**Confidence:** HIGH -- verified by examining cross-language call chains between `.pxd` declarations and C function definitions.

---

### Pitfall 3: Breaking Cython `.pxd` Declarations When Refactoring C Signatures

**What goes wrong:** Changing a C function signature (adding a parameter, changing a type, renaming) requires updating BOTH the `.h` header AND every `.pxd` file that declares it. The failure modes are:

1. **Forgetting to update the `.pxd` entirely.** Cython generates C code using the OLD signature. The generated C compiles against the NEW header. If the new parameter is a pointer, the generated code passes garbage (uninitialized stack) as the new parameter. If types changed width, truncation occurs. No compile error if types are ABI-compatible (e.g., `int` and `size_t` on 64-bit).

2. **Updating the `.pxd` but not all `.pyx` call sites.** Cython compilation fails with a clear error -- this is the BEST case.

3. **Updating the `.pxd` with a slightly different type.** For example, the C header declares `uint64_t` but the `.pxd` uses `unsigned long long`. These are the same on 64-bit Linux but NOT on all platforms. More insidiously: the C header uses `int` but the `.pxd` uses `int64_t`. The Cython-generated code may implicitly truncate.

**This pitfall is specifically relevant to v1.1** because the planned work includes:
- Cleaning the `local_search()` API (signature changes)
- Fixing the SATISFY mode crash (may require signature changes to `ctg()` or related functions)
- Reworking the callback mechanism (changes `callback_t` or adds parameters)

**Why it happens:** C and Cython are separately compiled. The `.pxd` is a MANUAL mirror of the C header. There is no automated consistency check at build time (Cython trusts whatever the `.pxd` says).

**Consequences:** Silent memory corruption. Wrong parameter values passed to C functions. Segfaults, or worse -- silently wrong solver results.

**Prevention:**
1. **Atomic rule:** Every C signature change must be a single commit containing: (a) the `.h` change, (b) the `.pxd` change, (c) all `.pyx` call site changes, (d) a test exercising the changed function.
2. Add a CI step that does a CLEAN build (`rm -rf build/ cbqs/*.so cbqs/*.c && pip install -e .`) -- stale `.so` files with old signatures are the #1 source of this class of bugs.
3. After changing any C signature, do a project-wide grep: `grep -rn 'function_name' cbqs/*.pxd cbqs/*.pyx`.
4. Prefer adding new functions over modifying existing signatures when possible. The old function can be deprecated and removed later.

**Warning signs:** Segfault or garbage output that appears only after `pip install -e .` but works fine when running from a previously-built `.so`.

**Detection:** Clean rebuild + full test suite. ASan catches the corruption in most cases.

**Specific `.pxd` files to watch:**
- `SearchLib.pxd` -- declares `ctg()`, `local_search()`, `solver_ctx_t` struct. Any C-level refactoring of these functions must update this file.
- `Model.pxd` -- declares `model_t` struct fields. Adding/removing/reordering fields in `model.h` MUST be mirrored here.
- `Constraint.pxd` -- declares `preprocessing()`, `eval_constraints()`, etc.
- `state.pxd` -- declares `state_t` struct and state functions.
- `branching.pxd` -- declares `StateProbability()`.
- `state_sampler.pxd` -- declares `approximate_state_t`, `solver_ctx_t` (duplicated from `SearchLib.pxd`).

**Phase mapping:** Every phase that touches C function signatures. Must be enforced as a checklist item.

**Confidence:** HIGH -- verified by examining the `.pxd`/`.h` pairs and confirmed by [SciPy's public Cython API documentation](https://docs.scipy.org/doc/scipy/dev/contributor/public_cython_api.html) which explicitly warns about ABI breakage from signature mismatches.

---

### Pitfall 4: Module-Level `cdef` Callback State Causing Concurrent Corruption

**What goes wrong:** The v1.1 plan includes "rework module-level cdef history callback to support concurrent tracking." The current implementation in `SearchLib.pyx` uses module-level `cdef` variables:

```python
cdef object _history_list = None
cdef object _history_prev_best = None
cdef object _history_original_callback = None
cdef Model _history_mod = None
```

These are shared across ALL concurrent workers launched by `Parallel(n_jobs=num_workers, backend="threading")`. Currently, each call to `run_sampling()` overwrites these globals (lines 201-206), which means:

1. Only the LAST worker's history callback setup is active. Earlier workers' callbacks point to stale state.
2. All workers append to the SAME `_history_list` via `_history_callback_fn()`, creating a race condition on the list object.
3. The `_history_mod` reference is shared -- if one worker finishes and the Model is modified, other workers' callbacks see corrupted state.

**The rework itself introduces new risks:**

1. **Moving to per-thread state via thread-local storage (TLS).** Cython does not natively support C11 `_Thread_local`. Using `threading.local()` requires GIL acquisition. Using `pthread_key_t` is possible but requires careful lifecycle management.

2. **Moving to per-worker callback closures.** `cpdef` functions in Cython cannot capture closures. `cdef` functions cannot be Python closures. The workaround of passing a context object through the C callback interface requires modifying the C `callback_t` typedef from `void (*)()` to `void (*)(void *user_data)`, which cascades through ALL C functions that accept callbacks.

3. **Moving to a lock-protected shared list.** Adding a mutex around `_history_list.append()` requires GIL management because `_history_list` is a Python object. The callback is called `with gil`, so the GIL is held, but Joblib threading means multiple threads contend for the GIL at each callback invocation, serializing the hot path.

**Why it happens:** The current callback architecture was designed for single-threaded use. Cython's restrictions on closures and function pointers make the "obvious" fix (per-thread state) non-trivial.

**Consequences:** Wrong history data (entries from multiple workers interleaved without synchronization). Missing history entries (lost to race conditions). Potential segfault if `_history_mod` is freed while another thread's callback is executing.

**Prevention:**
1. **Preferred approach:** Change `callback_t` from `void (*)()` to `void (*)(void *ctx)`, pass a per-worker context struct that contains the history list and model reference. This requires updating ALL C functions that accept callbacks, but is the cleanest long-term solution.
2. **Alternative:** Keep module-level state but add a Python `threading.Lock` around all accesses. This is simpler but serializes callback execution.
3. **Do NOT use `threading.local()` for `cdef` variables** -- Cython `cdef` variables are C-level and do not participate in Python's thread-local mechanism.
4. Whichever approach is chosen, add a concurrent history test: launch 4+ workers, each with a callback, verify that all workers' history entries appear in the merged list.

**Warning signs:** History entries have duplicate timestamps. History list length is less than expected. Segfault during callback execution under high worker count.

**Detection:** Run `solve()` with `num_workers=8` and `verify=True`. Check that merged history is monotonically increasing in timestamp. Run under TSan.

**Phase mapping:** Callback rework phase. This is architecturally the most complex change in v1.1. Budget extra time.

**Confidence:** HIGH -- directly observed in `SearchLib.pyx:137-159`. The module-level state pattern is a [known Cython thread-safety problem](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html).

---

### Pitfall 5: VLA Replacement Changing Stack/Heap Allocation Semantics

**What goes wrong:** The v1.1 plan includes "replace remaining VLA at local_search.c:286." The remaining VLA is:

```c
int64_t remainings[C];  // local_search.c, in accept_best_routine()
```

Where `C = con->num_constraints`. Replacing this with `malloc(C * sizeof(int64_t))` seems straightforward but introduces:

1. **A new failure mode:** `malloc` can return NULL. The VLA cannot fail (it either fits on the stack or crashes silently). Adding `malloc` requires adding error handling, which means adding a new code path that must be tested.

2. **A performance change:** VLA allocation is O(1) (stack pointer adjustment). `malloc` is O(variable) and may involve kernel calls. In a function called inside the main solver loop, this adds measurable overhead. The v1.0 work already demonstrated this pattern -- `accept_best_routine` is called once per solver iteration, so `malloc` overhead is acceptable HERE, but the pattern must not be blindly applied to inner loops.

3. **A memory leak risk:** Every `malloc` needs a matching `free`. The function has multiple return paths (line 397 for allocation failure, line 456 for early termination, line 475 for normal return). Missing `free` on ANY path leaks memory. The v1.0 work already fixed several such leaks (the `MEM-01 FIX` comments in `local_search.c`), showing this is a real pattern.

4. **Arena vs malloc decision:** The function already uses arena allocation for some buffers (`sw_init_arena`, `arena_alloc` at lines 218-225). Should the new heap buffer also use the arena? Using arena avoids the free/leak issue but ties the buffer lifetime to the arena reset cycle. If the arena is reset at the wrong time, the buffer is invalidated.

**Why it happens:** VLA replacement is treated as a simple mechanical transformation. The allocation semantics, error handling, and lifetime management are fundamentally different.

**Consequences:** Memory leak on error paths. Performance regression if done in tight loops. NULL dereference crash if error handling is missing.

**Prevention:**
1. For the specific `remainings[C]` case: use `malloc` with explicit error handling and `free` on all return paths. This matches the pattern already established in the same function for `thread_totals` and `thread_bits`.
2. Use the existing per-thread scratch buffer pattern: add `int64_t *thread_remainings` to `local_search_data_t`, allocate once in the setup loop, free after `pthread_join`. This avoids per-iteration malloc.
3. For any VLA replacement, audit ALL return paths in the containing function. Use a cleanup label pattern:
   ```c
   int result = -1;
   int64_t *buf = malloc(...);
   if (!buf) goto cleanup;
   // ... work ...
   result = 0;
   cleanup:
   free(buf);
   return result;
   ```
4. Run Valgrind after the replacement to verify zero leaks.

**Warning signs:** Valgrind reports "definitely lost" blocks originating from the function where VLA was replaced. Or: benchmark shows unexpected slowdown in local search.

**Detection:** Valgrind leak check. Performance benchmark comparing before/after.

**Phase mapping:** VLA replacement phase. One VLA per commit.

**Confidence:** HIGH -- the v1.0 `MEM-01 FIX` comments in `local_search.c` prove this exact leak pattern has already occurred in this codebase during similar refactoring.

---

## Moderate Pitfalls

Mistakes that cause delays, test instability, or technical debt accumulation.

---

### Pitfall 6: SATISFY Mode Crash Fix Affecting OPTIMIZE Mode

**What goes wrong:** The known SATISFY mode crash is in `SearchLib.pyx` where `run_sampling` calls `len()` on `mod.mod[0].con[0].num_constraints` (which is an `int`, not a sequence). The fix requires changing how `stpvl` is computed (line 220):

```python
stpvl = -len(mod.mod[0].con[0].num_constraints)  # BUG: int is not iterable
```

The fix changes this to:
```python
stpvl = -mod.mod[0].con[0].num_constraints  # or similar
```

But `stpvl` is the stopping value used to determine when a satisfying solution is found. Changing this value affects the SATISFY solver's convergence behavior. If the fix changes the sign, magnitude, or semantics of `stpvl`, it can:

1. Make the SATISFY solver never terminate (if `stpvl` becomes unreachable).
2. Make the SATISFY solver terminate too early (if `stpvl` is too easy to reach).
3. Change the quality of solutions found by the solver.

Additionally, the fix may require changes to the `ctg()` C function or to how `mod.mod[0].stop_val` is used, which affects both SATISFY and OPTIMIZE modes.

**Why it happens:** Bug fixes in one code path can have ripple effects when the fixed variable is used elsewhere. The SATISFY and OPTIMIZE paths share the `ctg()` function and `model_t` struct.

**Prevention:**
1. Before fixing, write a SATISFY mode test that captures the current intended behavior (even if the code crashes, document what the correct output should be).
2. After fixing, verify that ALL OPTIMIZE mode tests still pass with identical results (same seed, same output).
3. Verify the fix does not change `mod.mod[0].stop_val` for OPTIMIZE mode by adding an assertion.
4. The fix should be minimal: fix ONLY the `len()` call, do not refactor surrounding code in the same commit.

**Warning signs:** OPTIMIZE mode benchmark results change after the SATISFY fix.

**Detection:** Run the full test suite. Add a specific SATISFY mode test as part of the fix.

**Phase mapping:** Bug fix phase. High priority because it is a crash, but must be done carefully.

**Confidence:** HIGH -- the bug is directly observable at `SearchLib.pyx:220`.

---

### Pitfall 7: Removing Commented-Out Code That Documents Algorithm Variants

**What goes wrong:** The codebase contains extensive commented-out code that serves as DOCUMENTATION of alternative algorithms. Specifically:

1. **`adjusted_constraint_violation()` calls in `local_search.c:231-237`** -- The commented-out code is the optimized incremental constraint evaluation. The uncommented code is the brute-force fallback. Both produce the same results, but the commented version is O(changed_variables) while the uncommented version is O(all_variables). Removing the commented code loses the optimized algorithm.

2. **`objective_value_improved()` calls throughout `solver.c` and `local_search.c`** -- Same pattern. The commented code computes objective deltas incrementally. The uncommented code recomputes from scratch. The incremental version is the algorithmic contribution of the research; removing it loses the implementation.

3. **`BranchingFunction()` non-inline version in `Branching.c:48-97`** -- Documents the pre-inline algorithm with slightly different semantics.

4. **`updated()` in `state.c:154-178`** -- An earlier version of the function now in `Branching.c`.

**Why it happens:** From a code quality perspective, commented-out code is dead weight. The instinct is to remove it all. But in a RESEARCH codebase, commented-out code often represents algorithmic alternatives that may be needed later.

**Consequences:** Loss of institutional knowledge. When the next milestone wants to re-enable optimized constraint evaluation, the algorithm must be re-derived from papers rather than uncommented from code.

**Prevention:**
1. **Categorize before removing:**
   - "Debug code" (printf, commented asserts) -- safe to remove.
   - "Alternative algorithms" (commented function bodies, commented call sites) -- MOVE to a doc or `algorithms.md`, do not just delete.
   - "TODO/future work" (commented with explanation) -- keep or move to issue tracker.
2. For algorithm variants, add a block comment explaining the algorithm and why it is disabled: `/* ALGORITHM: Incremental constraint evaluation. Disabled because [reason]. See paper Section 3.2. */`
3. Create a `docs/algorithms/` directory for removed algorithm implementations if they are too large for inline comments.

**Warning signs:** A later milestone re-implements an algorithm that was previously in the codebase as commented code.

**Detection:** Code review. Before approving a "remove dead code" PR, check each removed block against the project's algorithm documentation.

**Phase mapping:** Dead code removal phase. Requires judgment, not just automation.

**Confidence:** HIGH -- verified by examining the specific commented-out code blocks in `local_search.c`, `solver.c`, and `Branching.c`.

---

### Pitfall 8: API Cleanup That Breaks Backward Compatibility

**What goes wrong:** The v1.1 plan specifies "no breaking changes" but includes "clean local_search() API." The boundary between cleanup and breakage is subtle:

1. **Renaming a Python-visible method.** If `Model.local_search()` parameters are renamed (e.g., `stop_time` to `timeout_ms`), any user code using keyword arguments breaks.

2. **Changing default values.** If `distance=2` is changed to `distance=1` because that is "more sensible," user code that relied on the old default gets different results.

3. **Changing return type.** `local_search()` already returns `OptimizeResult`. If fields are added, removed, or renamed in `OptimizeResult`, downstream code that accesses those fields breaks.

4. **Removing deprecated parameters.** The plan says "clean deprecated BranchingStats implementation (keep API, improve internals)." If ANY public function signature changes, it is a breaking change.

5. **Changing error types.** If a function used to raise `ValueError` but after cleanup raises `TypeError` for the same input, try/except blocks in user code break.

**Why it happens:** "Cleanup" and "improvement" blur together. The developer sees an inconsistent API and wants to fix it, not realizing that consistency with the old version is more important than consistency within the new version.

**Consequences:** User code breaks. For a research tool, this means existing benchmark scripts and paper reproduction scripts stop working.

**Prevention:**
1. **Define "backward compatible" precisely:** Same function names, same parameter names, same default values, same return types, same exception types. NOTHING visible to `help(Model)` or `dir(Model)` changes.
2. Internal improvements are fine: refactoring the C implementation behind a stable Cython interface.
3. If a parameter must be renamed, add the new name and keep the old name as a deprecated alias:
   ```python
   def local_search(self, distance=2, stop_time=None, timeout_ms=None, ...):
       if stop_time is not None and timeout_ms is None:
           warnings.warn("stop_time is deprecated, use timeout_ms", DeprecationWarning)
           timeout_ms = stop_time
   ```
4. Write a "public API surface" test that asserts all public method signatures match a known-good snapshot.

**Warning signs:** The words "rename," "remove," or "change default" appear in a v1.1 commit message.

**Detection:** API surface test. Also: try running any existing example scripts or benchmarks after changes.

**Phase mapping:** API cleanup phase. Requires explicit backward compatibility review.

**Confidence:** HIGH -- the project context explicitly states "no breaking changes" which means this constraint must be actively enforced.

---

### Pitfall 9: Bare `except` Clause Fix Catching Wrong Exceptions

**What goes wrong:** The v1.1 plan includes "fix bare except clause in Model.pyx (should be `except Exception`)." This is a good fix, but the precise replacement matters:

1. **`except:` catches `KeyboardInterrupt` and `SystemExit`.** Replacing with `except Exception:` STOPS catching these. If the code relies on catching `KeyboardInterrupt` (e.g., the SATISFY mode uses `signal.raise_signal(signal.SIGINT)` at `SearchLib.pyx:237`), the fix may cause unhandled exceptions.

2. **The `except` block's behavior determines the replacement.** If the bare `except` is catching C-level crashes (segfaults do not become Python exceptions -- they kill the process), the replacement is irrelevant. But if it is catching Cython errors from invalid memory access (which can become `MemoryError` or `SystemError`), the replacement needs `except BaseException:` rather than `except Exception:`.

**Why it happens:** "Replace bare except with except Exception" is a standard linting fix. But the reason the bare except was written may be that the developer WANTED to catch everything, including signals.

**Prevention:**
1. Before replacing, identify WHAT the bare except catches in practice. Is it keyboard interrupts? Memory errors? Cython internal errors?
2. Check if the SATISFY mode's `signal.raise_signal(signal.SIGINT)` path depends on a bare except anywhere in the call chain.
3. If the bare except is in a cleanup/finally pattern, consider replacing with `try/finally` instead.

**Warning signs:** After the fix, `Ctrl+C` during a solve does not cleanly stop the solver.

**Detection:** Test keyboard interrupt handling: start a solve with a long timeout, press Ctrl+C, verify clean shutdown.

**Phase mapping:** Bug fix phase. Low risk if analyzed carefully, high risk if done mechanically.

**Confidence:** MEDIUM -- the specific bare except location in Model.pyx was not identified in the code I examined; the plan references it but it may be in a code path I did not read. The SATISFY/SIGINT interaction is a verified concern.

---

### Pitfall 10: Clean Rebuild Failures After Incremental Changes

**What goes wrong:** During cleanup work, developers make many small changes and rebuild incrementally (`pip install -e .`). Cython caches generated `.c` files from `.pyx` sources. If a `.pxd` file changes but the timestamp-based build system does not detect the dependency, the `.pyx` file is not recompiled. The resulting `.so` uses the OLD `.pxd` declarations with the NEW C headers, producing silent struct layout mismatches.

Specific scenarios:
1. Change `model.h` to add/remove a field.
2. Update `Model.pxd` to match.
3. Run `pip install -e .` -- but `Model.pyx` is not recompiled because its timestamp did not change.
4. The `Model.so` still uses the old struct layout. Silent corruption.

**Why it happens:** Cython's dependency tracking for `.pxd` files is not always reliable, especially with `setuptools` builds. The `.pxd` is a dependency of the `.pyx`, but the build system may not detect it.

**Prevention:**
1. After ANY `.pxd` or `.h` change, do a CLEAN build: `rm -rf build/ cbqs/*.so cbqs/*.c && pip install -e .`
2. Add a Makefile target: `make clean-build` that does the above.
3. In CI, always build from clean (this is already the case for CI, but developers skip it locally).
4. Consider adding `cythonize(force=True)` as an option for development builds.

**Warning signs:** "Works in CI but fails locally" or vice versa. Inconsistent test results between clean and incremental builds.

**Detection:** If any test fails after an incremental build, retry with a clean build before investigating further.

**Phase mapping:** All phases. This is a development workflow pitfall, not a code pitfall.

**Confidence:** HIGH -- standard Cython/setuptools issue, confirmed by the [Cython documentation on compilation](https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html).

---

## Minor Pitfalls

Mistakes that cause annoyance or minor issues but are easily recoverable.

---

### Pitfall 11: Removing `printf` Debug Output That Users Depend On

**What goes wrong:** The `initial_state_preparation()` function in `solver.c:175` has:
```c
printf("\r%f %%", (double) i / n * 100.);
```
This prints progress during the greedy initialization phase. Removing it is "cleanup," but users may have scripts that parse this output or rely on it as a progress indicator. Similarly, `print_state()`, `print_model()`, and various `print_*` functions in the C code are called from Python code.

**Prevention:**
1. Do not remove `printf` from functions that are callable from Python (listed in `.pxd` files).
2. For solver-internal printf (like the progress bar), replace with a debug-gated output: `if (ctx && ctx->debug_enabled) fprintf(stderr, ...)`.
3. Distinguish between "debug output" (should be removed or gated) and "user-facing output" (should be kept or moved to a callback).

**Phase mapping:** Dead code/cleanup phase.

**Confidence:** HIGH -- `initial_state_preparation` progress output at `solver.c:175` is called from `Model.pyx:275`.

---

### Pitfall 12: Typo Fixes That Change Identifier Names

**What goes wrong:** The codebase has several misspelled identifiers:
- `increse_large_state` (should be `increase`) in `state.h:20` and `state.c:45`
- `num_cahnges` (should be `num_changes`) in `local_search.c:284` and `local_search.c:647`

Fixing these is good practice, but these are C symbols that may be referenced from `.pxd` files or other C files. Renaming without updating all references causes build failures or, worse, shadows a different symbol.

**Prevention:**
1. For each typo fix, do a project-wide search for the old name: `grep -rn 'increse_large_state' .`
2. Update ALL references atomically in one commit.
3. If the function is declared in a `.pxd` file, update the `.pxd` too.
4. `increse_large_state` is only called from `state.c:137` (internally) -- safe to rename with local impact.
5. `num_cahnges` is a local variable -- safe to rename.

**Phase mapping:** Cleanup phase. Low risk per instance.

**Confidence:** HIGH -- directly observed in `state.h:20`, `local_search.c:284`.

---

### Pitfall 13: `#define false 0` / `#define true 1` Conflicting with `<stdbool.h>`

**What goes wrong:** `definitions.h:46-47` defines:
```c
#define false 0
#define true 1
```

If any cleanup work adds `#include <stdbool.h>` (which defines `bool`, `true`, `false` as C11 keywords), these macros conflict. The result is a compile error or, if include order varies, silent redefinition.

**Prevention:**
1. If adding `<stdbool.h>` for the `atomic_bool` or other C11 features, remove the `#define false/true` from `definitions.h` first.
2. Or: use `<stdbool.h>` consistently and remove the manual defines.
3. Check for any code that depends on `true`/`false` being `int` rather than `_Bool` (they have different size/alignment on some platforms).

**Phase mapping:** Compiler warning fix phase or any phase that adds C11 includes.

**Confidence:** HIGH -- `definitions.h:46-47` directly conflicts with C11 `<stdbool.h>`. `solver_ctx.h:3` already includes `<stdatomic.h>` which may transitively include `<stdbool.h>` on some compilers.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| SATISFY mode crash fix | Fix changes stop_val semantics, affecting OPTIMIZE mode | Write SATISFY test BEFORE fixing. Verify OPTIMIZE tests unchanged. |
| Bare except fix | Stops catching KeyboardInterrupt needed for SATISFY SIGINT pattern | Analyze what the bare except actually catches before replacing. |
| GCC warning fixes | Parenthesizing `&&`/`||` changes evaluation order | One warning per commit. Document intended semantics. |
| Dead code removal | Removing function used from .pxd/.pyx but not from C | Grep ALL file types before removing any function. |
| Commented code removal | Losing optimized algorithm implementations | Categorize as debug/algorithm/TODO before removing. |
| VLA replacement | Memory leak on error paths in multi-return functions | Audit all return paths. Use cleanup label pattern. |
| Callback rework | Module-level cdef state not thread-safe | Change callback_t to accept void* context. Update all C callers. |
| local_search API cleanup | Renaming parameters breaks user code | Keep old parameter names as deprecated aliases. |
| .pxd updates | Stale Cython cache uses old struct layout | Clean build after every .pxd change. |
| BranchingStats cleanup | Removing deprecated global breaks code that still reads it | Keep global as read-only shim delegating to ctx. |

---

## Pre-Cleanup Checklist

Before starting any v1.1 cleanup work:

- [ ] Run full test suite and record baseline: `pytest -x --tb=short` (all 200+ tests pass)
- [ ] Run C tests and record baseline: `ctest` (all 58+ tests pass)
- [ ] Record benchmark baseline: pick 3 representative instances, run with fixed seed, save results
- [ ] Verify clean build works: `rm -rf build/ cbqs/*.so && pip install -e . && pytest`
- [ ] Create a git tag `v1.0-pre-cleanup` as a rollback point
- [ ] Verify ASan build works: `CMAKE_BUILD_TYPE=ASan make test`
- [ ] Verify Valgrind passes: zero leaks, zero errors on existing tests

## Sources

- Codebase analysis: all `.c`, `.h`, `.pyx`, `.pxd` files in `cbqs/` and `cbqs/src/`
- [SciPy Public Cython API documentation](https://docs.scipy.org/doc/scipy/dev/contributor/public_cython_api.html) -- ABI compatibility rules for `.pxd` files
- [Cython Free Threading documentation](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) -- Module-level variable thread safety
- [SEI CERT MSC07-C: Detect and remove dead code](https://wiki.sei.cmu.edu/confluence/display/c/MSC07-C.+Detect+and+remove+dead+code) -- Safe dead code removal practices
- [SEI CERT MEM05-C: Avoid large stack allocations](https://wiki.sei.cmu.edu/confluence/display/c/MEM05-C.+Avoid+large+stack+allocations) -- VLA replacement guidance
- [GCC Warning Options documentation](https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html) -- Warning semantics reference
- [Pitfalls of VLA in C](https://jorenar.com/blog/vla-pitfalls) -- VLA replacement considerations
- [Cython compilation and source files](https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html) -- Build dependency tracking
- [OpenSSF Compiler Hardening Guide](https://best.openssf.org/Compiler-Hardening-Guides/Compiler-Options-Hardening-Guide-for-C-and-C++.html) -- Compiler warning interpretation guidance
