# Phase 8: Solve Diagnostics - Research

**Researched:** 2026-02-06
**Domain:** Python result object design, C-level timing instrumentation, callback-driven history accumulation
**Confidence:** HIGH

## Summary

Phase 8 creates an `OptimizeResult` class that wraps all solve diagnostics into a single return object from `solve()` and `local_search()`. The implementation touches three layers: a pure Python `OptimizeResult` class (no C/Cython needed for the result object itself), Cython-level changes to `SearchLib.pyx` and `Model.pyx` to capture timing data and wire history accumulation, and minor C-level awareness of timing instrumentation points already present in `SearchLib.c` and `local_search.c`.

The current codebase already tracks most of the data needed: `mod->runtime` (wall clock in seconds), `mod->qtg_applications` (oracle calls), `mod->global_opt` (best solution), incumbent tracking via `incumbents_t`, and a callback mechanism that fires when a new best feasible solution is found. The primary work is (1) creating the `OptimizeResult` Python class, (2) wrapping the existing callback to accumulate improvement history entries, (3) adding preprocessing/solve time split instrumentation in the Cython `run_sampling()` and `run_local_search()` functions, and (4) changing the return types of `Model.solve()` and `Model.local_search()`.

**Primary recommendation:** Implement `OptimizeResult` as a pure Python class in a new `cbqs/result.py` module. Wire history accumulation by wrapping the user callback in `run_sampling()` and `run_local_search()` to append `(iteration, objective, elapsed_ms, is_feasible)` tuples to a list that gets passed into the result object. Capture preprocessing time as the delta between model.close() and solve start, and solve time from the C-level `mod->runtime`.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `time` | N/A | `time.monotonic()` for Python-level wall-clock timing | Already used in SearchLib.pyx via `time.time()` |
| Python stdlib `dataclasses` or plain class | N/A | OptimizeResult implementation | No external deps needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | N/A | JSON serialization for `.to_dict()` | For persistence/logging of results |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Plain Python class | `dataclasses.dataclass` | Dataclass gives `__repr__` for free but custom `__repr__` is specified in decisions; plain class offers full control |
| Dict subclass (scipy style) | Named attributes only | Decisions specify named attribute access, not dict-style; simpler to implement and test |

**Installation:** No new dependencies needed. All implementation uses Python stdlib and existing Cython infrastructure.

## Architecture Patterns

### Recommended Module Structure

```
cbqs/
  result.py              # NEW: OptimizeResult class (pure Python)
  Model.pyx              # MODIFIED: solve()/local_search() return OptimizeResult
  SearchLib.pyx           # MODIFIED: run_sampling()/run_local_search() capture timing + history
  __init__.py             # MODIFIED: export OptimizeResult
tests/
  test_result_py.py       # NEW: unit tests for OptimizeResult
  test_diagnostics_py.py  # NEW: integration tests for solve returning OptimizeResult
```

### Pattern 1: Pure Python Result Object

**What:** `OptimizeResult` is a regular Python class, not a Cython extension type. This is critical because it only stores Python-level data (floats, lists, numpy arrays) and needs rich `__repr__`, `__str__`, `summary()`, and `to_dict()` methods that are easiest to write and test in pure Python.

**When to use:** The result object is constructed after the C kernel finishes, from already-extracted Python values.

**Example:**
```python
class OptimizeResult:
    """Structured result from solve() or local_search().

    Follows scipy.optimize.OptimizeResult naming convention.
    """
    def __init__(self, *, solution, objective, feasible,
                 solve_time, preprocessing_time, iterations,
                 oracle_calls, history, verified, violations,
                 num_threads, seed):
        self.solution = solution           # numpy array or list
        self.objective = objective         # float
        self.feasible = feasible           # bool
        self.solve_time = solve_time       # float (ms)
        self.preprocessing_time = preprocessing_time  # float (ms)
        self.iterations = iterations       # int
        self.oracle_calls = oracle_calls   # int
        self.history = history             # list of tuples
        self.verified = verified           # bool or None
        self.violations = violations       # list of str or None
        self.num_threads = num_threads     # int
        self.seed = seed                   # int

    @property
    def time(self):
        """Total time (preprocessing + solve) in ms."""
        return self.preprocessing_time + self.solve_time

    def __repr__(self):
        return (f"OptimizeResult(obj={self.objective}, "
                f"feasible={self.feasible}, "
                f"time={self.time:.2f}ms, "
                f"iterations={self.iterations})")

    def summary(self):
        """Multi-line formatted report."""
        ...

    def to_dict(self):
        """JSON-serializable dictionary."""
        ...
```

### Pattern 2: Callback Wrapper for History Accumulation

**What:** Instead of adding new C-level instrumentation, wrap the user's callback in a Python closure that captures improvement history. The C callback mechanism fires `callback()` inside `ctg()` when `mod->global_opt` improves (line 188 of SearchLib.c) and inside `local_search()` every iteration (line 542 of local_search.c). The Cython `my_callback_c()` in SearchLib.pyx (line 125) bridges C to Python.

**When to use:** In `run_sampling()` and `run_local_search()`, before passing the callback to the C functions.

**How it works in ctg():** The callback fires at line 188 of SearchLib.c:
```c
if (mod->global_opt->tot_profit > cur_sol->tot_profit){
    copy_state_inplace(mod->global_opt, cur_sol);
    if (callback && mod->global_opt->feasible) callback();
}
```
This only fires when a new best *feasible* solution is found. The `mod->runtime` is already updated to the current elapsed time by line 157, and `mod->global_opt->tot_profit` holds the new objective.

**How it works in local_search():** The callback fires at line 542 of local_search.c:
```c
if (callback) callback();
```
This fires every iteration (not just on improvement), so the history wrapper needs to check if the objective actually improved.

**Example wrapper pattern:**
```python
# In run_sampling(), before passing to ctg():
history = []
_prev_best = [None]  # mutable container for closure

def _history_callback():
    obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
    elapsed_ms = mod.mod[0].runtime * 1000.0
    is_feasible = bool(mod.mod[0].global_opt[0].feasible)
    iteration = mod.mod[0].qtg_applications

    if _prev_best[0] is None or obj_val != _prev_best[0]:
        history.append((iteration, obj_val, elapsed_ms, is_feasible))
        _prev_best[0] = obj_val

    # Still call user's original callback
    if original_callback is not None:
        original_callback()
```

### Pattern 3: Timing Split at Cython Level

**What:** The preprocessing vs. solve time split is captured at the Python/Cython boundary, not in C. The C code already writes `mod->runtime` (solve time in seconds). Preprocessing time is the time spent in `model.close()` (which calls `process_constraints()`). The solve time comes from C.

**Where to instrument:**
1. **Preprocessing time:** In `Model.close()` or at the start of `run_sampling()`/`run_local_search()`, record `time.monotonic()` before and after `initial_state_preparation()`.
2. **Solve time:** Read `mod->runtime` after C returns (already stored in seconds, convert to ms).

**Key insight:** The C functions `ctg()` and `local_search()` already call `clock_gettime(CLOCK_MONOTONIC)` at their start and update `mod->runtime` throughout. After the function returns, `mod->runtime` contains total solve wall clock in seconds.

### Anti-Patterns to Avoid

- **Adding new C-level timing structs:** The C code already has `mod->runtime` and `clock_gettime`. Adding more C-level fields creates complexity with no benefit when timing can be captured at the Cython boundary.
- **Making OptimizeResult a Cython cdef class:** This would make it harder to test, document, and extend. The result object is constructed after solve completes -- there's no performance reason for C-level implementation.
- **Modifying the C callback_t signature:** `callback_t` is `void (*)()` with no parameters. Changing it would cascade through solver.h, SearchLib.h, local_search.h, and all call sites. The closure pattern in Python avoids this entirely.
- **History recording inside C hot loops:** Decisions explicitly say "History hooks into existing callback infrastructure rather than adding new C-level instrumentation."

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Monotonic timing | Custom time tracking | `time.monotonic()` (Python) / `clock_gettime(CLOCK_MONOTONIC)` (C, already used) | Cross-platform, not affected by NTP adjustments |
| JSON serialization | Manual string building | `json.dumps()` on dict from `.to_dict()` | Handles escaping, nested structures correctly |
| Solution array extraction | Manual bit extraction | Existing `sw_tstbit()` loop (already in Model.verify_solution line 510) | Proven pattern in codebase |

**Key insight:** The codebase already tracks nearly everything needed in C (`mod->runtime`, `mod->qtg_applications`, `mod->global_opt`, incumbents). Phase 8 is primarily about surfacing existing data through a well-designed Python API.

## Common Pitfalls

### Pitfall 1: Callback fires with GIL from C nogil blocks

**What goes wrong:** The C callback fires inside `with nogil` blocks in Cython. The existing `my_callback_c()` uses `with gil` to re-acquire the GIL before calling the Python callback. Any history accumulation callback wrapper must also work within this GIL/nogil dance.

**Why it happens:** `ctg()` and `local_search()` are called with `with nogil` in SearchLib.pyx. The C callback pointer is `my_callback_c` which has `with gil`.

**How to avoid:** Continue using the existing global `python_callback` variable pattern in SearchLib.pyx. The wrapper closure is set as the `python_callback` global before the `with nogil` block, just as the user callback currently is. No changes to the C callback mechanism needed.

**Warning signs:** Segfaults during solve when the callback accesses Python objects without the GIL.

### Pitfall 2: Thread safety of history accumulation in parallel solve()

**What goes wrong:** `Model.solve()` uses `joblib.Parallel(n_jobs=num_workers, backend="threading")` which runs `run_sampling()` on multiple threads (line 325 of Model.pyx). Each thread has its own `python_callback` global (it's a module-level variable), but the history list would need to be per-thread.

**Why it happens:** Each `run_sampling()` call creates its own local `history` list and its own closure. Since `python_callback` is a module-level `cdef object` in SearchLib.pyx, there's a race condition if multiple threads set it.

**How to avoid:** Each `run_sampling()` call already creates its own solver context and returns its own result tuple. The history list should be local to each `run_sampling()` call and returned alongside the other results. The `Model.solve()` method then merges histories from all workers. The existing `python_callback` race condition is a pre-existing issue -- for history, keep each thread's list separate and merge in `Model.solve()`.

**Warning signs:** Missing history entries, duplicated entries, or garbled data when num_workers > 1.

### Pitfall 3: Breaking change in solve() return type

**What goes wrong:** `solve()` currently returns a list (the `total_incumbent` list), and `local_search()` returns None (implicitly). Changing both to return `OptimizeResult` breaks all existing test assertions and any user code that unpacks the return value.

**Why it happens:** Decision explicitly says "Breaking change: solve() and local_search() both always return OptimizeResult."

**How to avoid:**
1. Update all existing tests in `test_model_py.py` and `test_verification_py.py` that check `solve()` return values
2. The old incumbent list data could be accessible via a field on OptimizeResult (e.g., `result.incumbents`)
3. Document the breaking change clearly

**Warning signs:** Existing tests failing with `AttributeError` or `TypeError` when trying to use the result as a list.

### Pitfall 4: local_search callback fires every iteration, not just on improvement

**What goes wrong:** In `ctg()`, the callback only fires when `global_opt` improves (guarded by the `if mod->global_opt->tot_profit > cur_sol->tot_profit` check). But in `local_search()`, `callback()` fires unconditionally every iteration (line 542). If the history wrapper records every callback, the history will be bloated with non-improvement entries for local_search.

**Why it happens:** Different calling conventions between the two solver paths.

**How to avoid:** The history wrapper must check whether the objective actually changed since the last recording. Use a `_prev_best` sentinel in the closure to track the previous best value and only append when it changes.

**Warning signs:** History entries with identical objective values in sequence.

### Pitfall 5: Objective value sign convention

**What goes wrong:** The C kernel stores objectives with a sign convention where `MAXIMIZE = -1` means `mod->global_opt->tot_profit` is negated. The user-facing objective needs `tot_profit * sense` to get the correct sign (as done in `Model.objective_value` property, line 423).

**Why it happens:** Internal C representation uses negation for maximization.

**How to avoid:** Always apply `* mod.sense` when extracting objective values for the result object and history entries.

**Warning signs:** Negative objective values for maximization problems.

## Code Examples

### Example 1: Extracting solution array from C state (existing pattern)

```python
# Source: Model.pyx, verify_solution() lines 509-511
cdef int n_bits = self.mod[0].global_opt[0].vector.bits
arr = [sw_tstbit(self.mod[0].global_opt[0].vector, i) for i in range(n_bits)]
```

This is the proven pattern for extracting a solution array from the C-level `state_t`. Use this same approach to populate `result.solution`.

### Example 2: Reading timing and iteration data from model_t (existing fields)

```python
# Source: Model.pyx properties (lines 422-438)
# Objective value (apply sense for user-facing value):
obj_val = self.mod[0].global_opt[0].tot_profit * self.sense

# Oracle calls:
oracle_calls = self.mod[0].qtg_applications

# Runtime (seconds, from C clock_gettime):
runtime_sec = self.mod[0].runtime
```

### Example 3: Current solve() return and how run_sampling returns data

```python
# Source: SearchLib.pyx, run_sampling() line 220
return cur_sol, mod.mod[0].qtg_applications, feasible, arr, t_total, incumb
```

Currently returns a 6-tuple: `(state_py, qtg_applications, feasible, arr, t_total, incumbents_list)`. This is consumed by `Model.solve()` which extracts values from the parallel results (line 325-348).

### Example 4: run_local_search current return

```python
# Source: SearchLib.pyx, run_local_search() line 263
return cur_sol
```

Currently returns just the `state_py` object. The timing and objective data is on `mod` properties.

### Example 5: Existing callback wiring pattern

```python
# Source: SearchLib.pyx lines 125-130
cdef void my_callback_c() with gil:
    if python_callback is not None:
        python_callback()

cdef object python_callback = None
```

The `python_callback` module-level variable is set before the `with nogil` C call, and `my_callback_c` (a C function with GIL re-acquisition) is passed as the C callback pointer.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| solve() returns incumbent list | Phase 8: returns OptimizeResult | This phase | Breaking change; all consuming code needs update |
| Properties on Model for diagnostics | Phase 8: all diagnostics in result object | This phase | Self-contained results; model state not needed post-solve |
| No timing breakdown | Phase 8: preprocessing + solve split | This phase | Researchers can identify bottlenecks |
| Manual callback for improvement tracking | Phase 8: automatic history accumulation | This phase | Post-solve convergence analysis from result object |

**Current state (pre-Phase 8):**
- `Model.objective_value` -- property reading from `mod.global_opt.tot_profit`
- `Model.oracle_calls` -- property reading from `mod.qtg_applications`
- `Model.runtime` -- property reading from `mod.runtime`
- `Model.solution` -- property that prints state but returns 0 (broken/debug)
- `Model._verified` -- set by verify_solution() (Phase 7)
- `Model.verify_solution()` -- post-solve check (Phase 7)
- Callbacks via `callback` parameter on solve/local_search

## Open Questions

### 1. Iteration count semantics for ctg()

**What we know:** In `ctg()`, `rounds` counts the number of loop iterations, and `m_tot` tracks total Grover iterations. `rounds` resets to 0 on improvement. `mod->qtg_applications` accumulates total oracle applications (2*j+1 per round).

**What's unclear:** The context says "iteration count" should be in the result. Is this `rounds` (resets on improvement) or `m_tot` (resets on improvement) or the cumulative total from all workers? Since `mod->qtg_applications` is cumulative and per-model (shared across threads via model pointer), it likely represents total oracle calls.

**Recommendation:** Use `mod->qtg_applications` as `oracle_calls`, and track a separate `iterations` counter in the Cython wrapper that counts the number of times the main solve loop executes across all workers. For solve(), this could be summed from per-worker iteration counts.

### 2. History merging across parallel workers

**What we know:** `Model.solve()` runs `run_sampling()` on `num_workers` threads via joblib. Each thread produces its own local history. The histories need to be merged into a single sorted timeline.

**What's unclear:** Should history entries be interleaved by elapsed_ms from all workers, or should each worker's history be separate?

**Recommendation:** Merge all worker histories into a single list sorted by elapsed_ms. This gives the researcher a unified convergence view. The elapsed_ms is relative to solve start (from C `mod->runtime`), so entries from different workers are directly comparable.

### 3. Preprocessing time measurement boundary

**What we know:** The decision says "preprocessing_time + solve_time (strict split, total = sum of both)". Currently `Model.close()` runs `process_constraints()` which does the preprocessing. But preprocessing (the ISP call `initial_state_preparation`) also happens at the start of `general_greedy()` or implicitly in solve.

**What's unclear:** Is "preprocessing" the constraint compilation in `close()`, or the initial state preparation in `solve()`/`run_sampling()`?

**Recommendation:** Define preprocessing as everything before the C solver loop starts: this includes `initial_state_preparation(mod)` called in `run_sampling()` (if `not initialized`, `manual_initial` is called in `Model.solve()` at line 307). The preprocessing time should be measured as the time between entering `run_sampling()` and starting the `ctg()` / C solve call. Solve time is `mod->runtime` from C. This gives the cleanest split.

## Sources

### Primary (HIGH confidence)

- Codebase analysis of all files in cbqs/src/*.c, cbqs/src/*.h, cbqs/*.pyx, cbqs/*.pxd
- [scipy.optimize.OptimizeResult documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.OptimizeResult.html) -- referenced for naming convention
- Existing test patterns in tests/test_model_py.py, tests/test_verification_py.py

### Secondary (MEDIUM confidence)

- Phase context decisions (08-CONTEXT.md) -- locked choices constraining design

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no external dependencies, pure Python + existing Cython
- Architecture: HIGH -- based on direct analysis of current codebase patterns
- Pitfalls: HIGH -- identified from actual code paths and thread safety analysis
- OptimizeResult design: HIGH -- constrained by locked decisions, scipy convention verified

**Research date:** 2026-02-06
**Valid until:** 2026-03-06 (stable domain, no fast-moving dependencies)
