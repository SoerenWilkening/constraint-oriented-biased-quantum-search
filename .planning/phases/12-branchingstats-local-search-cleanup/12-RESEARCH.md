# Phase 12: BranchingStats & Local Search Cleanup - Research

**Researched:** 2026-02-08
**Domain:** Branching parameter propagation, generic parameter API, mutex-protected shared state
**Confidence:** HIGH

## Summary

Phase 12 addresses three interconnected gaps in the CBQS codebase: (1) branching parameters set via the Python API do not currently propagate to the per-solve `solver_ctx_t` used by both sampling and local search solvers, (2) the global branching setters need deprecation warnings, and (3) the `accept_best_routine` in `local_search.c` writes to `global_opt` without mutex protection, creating a race condition when threads run concurrently.

The codebase already has all the C-level infrastructure needed -- `solver_ctx_t` has an embedded `BranchingStats_t`, and `solver_ctx_set_*` functions exist. The primary work is: wiring the Python-level `set_param`/`get_param` API through Cython to the C solver context, adding deprecation warnings to the Cython-level branching wrappers, and adding a `pthread_mutex_t` to `accept_best_routine` for `global_opt` writes.

**Primary recommendation:** Implement a `_params` dict on `Model`, wire `set_param`/`get_param`, propagate branching params to `solver_ctx_t` in both `run_sampling` and `run_local_search`, add deprecation warnings to `branching.pyx` wrappers, and add `pthread_mutex_trylock` for `global_opt` writes in `accept_best_routine`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Deprecation Strategy:**
- Deprecated global branching setters emit `DeprecationWarning` once per session (Python default warning filter)
- Warning message is generic (e.g., "set_branching_bias is deprecated"), no migration hint
- If user passes branching via both `set_param` and old global setter, `set_param` wins silently

**Branching API Surface:**
- New generic `model.set_param(name, value)` and `model.get_param(name)` methods on Model
- Strict validation: `set_param` raises `ValueError` on unknown parameter names
- Supports all solver parameters initially (num_workers, timeout, track_history, branching_bias, branching_factors, etc.)
- Parameters persist across multiple `solve()` calls until changed
- Existing `solve()` keyword arguments remain for backward compatibility
- **Precedence: `set_param` values win over `solve()` kwargs** -- if both are specified, `set_param` value is used
- `solve()` kwargs exist for backward compat only; they do NOT override `set_param` values

**Mutex Scope:**
- Global mutex (single mutex protecting all `global_opt` writes)
- Mutex protects writes only in `accept_best_routine` -- reads are not locked
- If mutex lock fails, skip the write (solver continues, loses one update)

**Verification Approach:**
- Deterministic test: fixed seed + known problem, assert exact solution match with branching params applied
- Combined test exercising both sampling solver and local search solver paths
- ThreadSanitizer test runs in CI automatically (catches regressions on every push)
- Deprecation warning test verifies `DeprecationWarning` type only (not message text)

**Specific Ideas:**
- User wants `set_param` style (like `model.set_param("branching_bias", value)`) rather than solve() kwargs or dedicated methods
- Generic parameter API is extensible for future solver parameters
- `set_param` is the canonical way to configure solver behavior; `solve()` kwargs are legacy

### Claude's Discretion

1. **Deprecated setters: functional or no-ops** -- constrained by "no breaking changes" rule. Recommendation: keep them functional (they still set the global `BranchingStats`), but `set_param` values on the per-solve `solver_ctx_t` always win because the solver functions read from `ctx->branching_stats`, not the global.

2. **Blocking `pthread_mutex_lock` vs non-blocking `pthread_mutex_trylock`** -- Recommendation: Use `pthread_mutex_trylock`. The user decision says "if mutex lock fails, skip the write", which maps directly to trylock semantics. Blocking lock would never fail, so trylock is the correct choice to match the stated behavior.

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library/Tool | Purpose | Why Standard |
|-------------|---------|--------------|
| pthread | Mutex protection for `global_opt` | Already used throughout codebase for threading |
| Python `warnings` module | DeprecationWarning emission | Standard Python deprecation mechanism |
| Cython | Python-C bridge for `set_param`/`get_param` | Already the middleware layer |
| CMocka | C-level thread safety tests | Already the C test framework |
| pytest | Python-level parameter API and deprecation tests | Already the Python test framework |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| ThreadSanitizer (TSan) | Detect data races in `accept_best_routine` | CI pipeline, already configured in `.github/workflows/test.yml` |
| `pytest.warns` | Verify deprecation warnings | Python-level deprecation tests |

## Architecture Patterns

### Current Branching Parameter Flow (THE GAP)

```
Python Model.solve()
  |
  v
Model.solve() calls set_bias_wrapper(bias) and set_factors_wrapper(...)
  |
  v
branching.pyx: set_bias(bias) -> C: BranchingStats.bias = bias  [GLOBAL]
branching.pyx: set_factors(...) -> C: BranchingStats.* = ...    [GLOBAL]
  |
  v
run_sampling() creates solver_ctx_t *ctx
  - ctx->branching_stats initialized with DEFAULTS (bias=5, factors=default)
  - NEVER receives the values set by set_bias_wrapper/set_factors_wrapper
  |
  v
solver.c: CSearch_opt(ctx, ...) reads ctx->branching_stats
  -> USES DEFAULT VALUES, not the user-specified ones!
```

**The root cause:** `Model.solve()` calls `set_bias_wrapper(bias)` and `set_factors_wrapper(...)` which set the global `BranchingStats` in `Branching.c`, but the solver functions (`CSearch_opt`, `CSearch_opt_sat`, `CSearch_sat`) all read from `ctx->branching_stats` (the per-solve context). The per-solve context is never populated with the user's branching parameters.

**Exception:** In the SATISFY path within `run_sampling`, there IS a call to `solver_ctx_set_bias(ctx, ...)` inside the delta loop. But the OPTIMIZE path never sets branching params on the context.

### Target Architecture (After Phase 12)

```
Python Model.set_param("branching_bias", value)
  |
  v
Model._params["branching_bias"] = value  [stored on Model instance]
  |
  v
Model.solve() reads _params, passes to run_sampling()
  OR Model.local_search() reads _params, passes to run_local_search()
  |
  v
run_sampling()/run_local_search():
  ctx = solver_ctx_create()
  solver_ctx_set_bias(ctx, bias_value)       # from _params
  solver_ctx_set_factors(ctx, obj, con, ...)  # from _params
  solver_ctx_set_obj_dependence(ctx, ...)     # if set via _params
  |
  v
solver.c: CSearch_opt(ctx, ...) reads ctx->branching_stats
  -> NOW USES USER-SPECIFIED VALUES
```

### Pattern 1: Generic Parameter Storage on Model

**What:** A `_params` dict on the `Model` class that stores all solver parameters set via `set_param`.

**When to use:** Any solver parameter that needs to persist across multiple `solve()` calls.

**Key considerations:**
- The `_params` dict must be initialized in `__init__` with known parameter names and default values (or `None` for "not set")
- `set_param` validates against known parameter names, raises `ValueError` for unknown
- `get_param` returns the value or raises `ValueError` for unknown
- In `solve()` and `local_search()`, `_params` values take precedence over kwargs

```python
# In Model.__init__:
self._params = {}  # No defaults -- None means "not set"

# In Model.set_param:
KNOWN_PARAMS = {
    "branching_bias", "branching_factors", "num_workers",
    "timeout", "track_history", ...
}
def set_param(self, name, value):
    if name not in KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: {name}")
    self._params[name] = value

# In Model.get_param:
def get_param(self, name):
    if name not in KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: {name}")
    return self._params.get(name)
```

### Pattern 2: Parameter Propagation in run_sampling/run_local_search

**What:** After creating `solver_ctx_t`, propagate branching parameters from the model's `_params` before calling solver functions.

**Where:** In `SearchLib.pyx`, both `run_sampling()` and `run_local_search()`.

```python
# After solver_ctx_create(), before solver calls:
# Branching bias
if hasattr(mod, '_params') and mod._params.get('branching_bias') is not None:
    solver_ctx_set_bias(ctx, mod._params['branching_bias'])
elif bias_from_kwarg is not None:
    solver_ctx_set_bias(ctx, bias_from_kwarg)

# Branching factors
if hasattr(mod, '_params') and mod._params.get('branching_factors') is not None:
    factors = mod._params['branching_factors']
    solver_ctx_set_factors(ctx, factors[0], factors[1], factors[2], factors[3])
```

### Pattern 3: Mutex in accept_best_routine for global_opt

**What:** Use `pthread_mutex_trylock` around `global_opt` writes in `accept_best_routine`.

**Where:** `local_search.c`, inside `accept_best_routine()` and the `local_search()` main function.

**Current code (SearchLib.c ctg function, line 183-189):**
```c
// In ctg() - already has mutex:
pthread_mutex_lock(&update_lock);
if (mod->global_opt->tot_profit > cur_sol->tot_profit){
    copy_state_inplace(mod->global_opt, cur_sol);
    if (callback && mod->global_opt->feasible) callback();
}
pthread_mutex_unlock(&update_lock);
```

**Target code (local_search.c accept_best_routine):**
```c
// In accept_best_routine:
extern pthread_mutex_t update_lock;  // declared in SearchLib.c

// Where global_opt is written (via accept_move):
if (pthread_mutex_trylock(&update_lock) == 0) {
    accept_move(new_sol, cur_best, global_opt);
    pthread_mutex_unlock(&update_lock);
} else {
    // Skip this update -- solver continues, loses one update
    // Only skip the global_opt write; local cur_best still updated
}
```

**Important detail:** The `accept_move` function in `local_search.c` (line 68-92) writes to both `new_sol` (the local state) and `global_opt` (the shared state). The mutex only needs to protect the `global_opt` writes. The function currently combines both operations. The mutex should wrap the `accept_move` call that touches `global_opt`, or the function should be refactored to separate local vs global updates.

### Pattern 4: Deprecation Warnings in branching.pyx

**What:** Add `warnings.warn(..., DeprecationWarning)` to the Cython wrapper functions.

**Where:** `cbqs/branching.pyx`

```python
import warnings

def set_bias_wrapper(double bias):
    warnings.warn(
        "set_branching_bias is deprecated",
        DeprecationWarning,
        stacklevel=2
    )
    set_bias(bias)
```

**Important consideration:** `Model.close()` currently calls `set_bias_wrapper(self.n / 4)` on line 270. This internal call should NOT trigger the deprecation warning for the user. Options:
1. Add an `_internal=False` parameter to `set_bias_wrapper` that suppresses the warning
2. Move the `close()` call to use a different internal path
3. Call the C function `set_bias()` directly from `Model.close()` bypassing the wrapper

Option 1 is cleanest. Alternatively, since `set_param` values will override these globals in the solver context anyway, the `close()` call to `set_bias_wrapper` could be left as-is (the warning only matters when users call it directly, and `close()` is an internal path -- but `set_bias_wrapper` is imported in `Model.pyx` and called from `Model.solve()` too).

**Another critical detail:** `Model.solve()` itself calls `set_bias_wrapper(bias)` and `set_factors_wrapper(...)` on lines 311-312. These calls will trigger deprecation warnings every time `solve()` is called. This needs to be handled: either make `solve()` use the new `_params` path instead, or have `solve()` call the C functions directly without going through the deprecated wrappers.

### Anti-Patterns to Avoid

- **Don't add mutex to reads:** The decision explicitly says "mutex protects writes only." Don't lock around `global_opt` reads in the search threads.
- **Don't break existing solve() kwargs:** The decision says existing kwargs remain for backward compat. Don't remove any `solve()` parameters.
- **Don't use blocking mutex when trylock is specified:** The user decision says "if mutex lock fails, skip the write." This means `pthread_mutex_trylock`, not `pthread_mutex_lock`.
- **Don't emit deprecation from internal Model methods:** Only user-facing calls should warn.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mutex for `global_opt` | Custom lock implementation | `pthread_mutex_t` with `trylock` | Already used in `SearchLib.c`; `update_lock` is globally declared |
| Deprecation warnings | Custom warning system | `warnings.warn(..., DeprecationWarning)` | Standard Python mechanism; integrates with warning filters |
| Parameter validation | Custom string matching | Simple set lookup (`KNOWN_PARAMS`) | Fast, maintainable, extensible |

## Common Pitfalls

### Pitfall 1: Internal calls triggering deprecation warnings

**What goes wrong:** `Model.close()` (line 270) and `Model.solve()` (lines 311-312) both call `set_bias_wrapper()` and `set_factors_wrapper()`. After adding deprecation warnings to these wrappers, every `close()` and `solve()` call will emit warnings even though the user didn't call the deprecated functions.

**Why it happens:** The deprecated wrappers are used internally by non-deprecated methods.

**How to avoid:** Either:
1. Have `Model.solve()` stop calling the global wrappers entirely and instead pass params through `_params` -> `run_sampling()` -> `solver_ctx_set_*()`. The global wrappers become user-only.
2. Add an `_internal` flag to suppress warnings on internal calls.
3. Since the solver functions now read from `ctx->branching_stats` (not global `BranchingStats`), `Model.solve()` could skip calling the global setters entirely when `_params` has branching values.

**Recommended approach:** Option 1 is cleanest -- remove the calls to `set_bias_wrapper`/`set_factors_wrapper` from `Model.solve()` entirely, and propagate branching params through the solver context in `run_sampling`/`run_local_search`. The global `BranchingStats` only gets set when users explicitly call the deprecated standalone functions.

**Warning signs:** Test suite floods with DeprecationWarnings from every `solve()` call.

### Pitfall 2: The `accept_move` function conflates local and global writes

**What goes wrong:** `accept_move()` in `local_search.c` (line 68-92) writes to both `new_sol` (local thread state) and `global_opt` (shared state) in a single function. If you mutex the entire function, you over-protect; if you don't mutex it, the `global_opt` write races.

**Why it happens:** The function was written for single-threaded use and the dual-purpose wasn't a problem.

**How to avoid:** The mutex needs to wrap specifically the `global_opt` writes inside `accept_best_routine` -- which is the function that calls `accept_move`. Looking at the flow:
- `accept_best_routine()` at line 457 calls `accept_move(new_sol, cur_best, global_opt)` -- this is the one that writes to `global_opt`
- Thread workers in `explore_neighbourhood` call `accept_move` on thread-local `cur_best` -- these don't touch `global_opt` directly (they pass their own `cur_best` which gets merged later)
- So the mutex only needs to go around the final `accept_move` call in `accept_best_routine()` that targets `global_opt`

**Warning signs:** ThreadSanitizer reports data races on `global_opt` fields.

### Pitfall 3: set_param precedence over solve() kwargs requires careful merge logic

**What goes wrong:** If `set_param("branching_bias", 10.0)` is called, and then `solve(bias=5.0)`, the `set_param` value (10.0) must win. But the current `Model.solve()` unconditionally calls `set_bias_wrapper(bias)` where `bias` comes from the kwarg default. If the user doesn't pass `bias=` explicitly, it defaults to `-1`, which triggers `if bias == -1: bias = self.n / 4`.

**Why it happens:** Python doesn't distinguish "user passed kwarg" from "kwarg has default value."

**How to avoid:** The merge logic in `solve()` should be:
1. If `_params` has a value for the parameter, use it
2. Else if the kwarg was explicitly provided by the user (not the default), use it
3. Else use the default

Since Python doesn't natively distinguish "explicitly passed" from "default," use sentinel values (the existing `-1` for bias works as a sentinel). The logic becomes: if `_params.get("branching_bias") is not None`, use that; else if `bias != -1` (user passed it), use that; else use `n/4`.

**Warning signs:** Branching params don't match expected values in deterministic tests.

### Pitfall 4: Reusing the global update_lock for local_search

**What goes wrong:** The `update_lock` mutex is declared in `SearchLib.c` as a file-level global. `local_search.c` needs to use the same mutex, but it's in a different compilation unit.

**Why it happens:** The mutex is declared in `SearchLib.c` but not exposed via a header.

**How to avoid:** Declare `extern pthread_mutex_t update_lock;` in a header (e.g., `SearchLib.h` or a new shared header). Alternatively, define the mutex in a shared location. Since `SearchLib.c` includes `Python.h` which complicates things, the cleanest approach may be to declare the mutex in `solver_ctx.h` or a new `locks.h` and define it in one `.c` file.

**Warning signs:** Linker errors about undefined `update_lock` in `local_search.o`.

### Pitfall 5: The close() call to set_bias_wrapper

**What goes wrong:** `Model.close()` calls `set_bias_wrapper(self.n / 4)` to set a default bias. After deprecation, this triggers a warning.

**Why it happens:** `close()` uses the global setter to establish a default.

**How to avoid:** `close()` should set the default via `_params` (if not already set) or call the C function directly. Since `close()` is about compilation/preparation, it could set `_params["branching_bias"]` as a default if the user hasn't explicitly set it.

**Warning signs:** Every `close()` call emits a deprecation warning.

## Code Examples

### Example 1: set_param / get_param on Model (Model.pyx)

```python
# Known parameter names and their types
_KNOWN_PARAMS = {
    "branching_bias": (float, int),
    "branching_factors": (tuple, list),
    "num_workers": (int,),
    "timeout": (int, float),
    "track_history": (bool,),
    "manual_bias": (list, type(None)),
    "bias_factor": (float, int),
    "manual_bias_factor": (float, int),
    "look_ahead_factor": (float, int),
}

def set_param(self, str name, value):
    """Set a solver parameter by name.

    Parameters persist across multiple solve() calls until changed.
    set_param values take precedence over solve() keyword arguments.
    """
    if name not in _KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: '{name}'")
    self._params[name] = value

def get_param(self, str name):
    """Get a solver parameter by name.

    Returns None if the parameter has not been set via set_param.
    """
    if name not in _KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: '{name}'")
    return self._params.get(name)
```

### Example 2: Branching propagation in run_sampling (SearchLib.pyx)

```python
# After solver_ctx_create(), before solver calls:

# Propagate branching bias from model params
branching_bias = None
if hasattr(mod, '_params'):
    branching_bias = mod._params.get('branching_bias')

if branching_bias is not None:
    solver_ctx_set_bias(ctx, branching_bias)
elif bias_kwarg != -1:  # User passed bias kwarg explicitly
    solver_ctx_set_bias(ctx, bias_kwarg)
else:
    solver_ctx_set_bias(ctx, n / 4)  # Default

# Propagate branching factors
branching_factors = None
if hasattr(mod, '_params'):
    branching_factors = mod._params.get('branching_factors')

if branching_factors is not None:
    solver_ctx_set_factors(ctx, branching_factors[0], branching_factors[1],
                           branching_factors[2], branching_factors[3])
```

### Example 3: Mutex in accept_best_routine (local_search.c)

```c
/* In local_search.c, near top: */
extern pthread_mutex_t update_lock;

/* In accept_best_routine, around the final accept_move that writes global_opt: */
if (pthread_mutex_trylock(&update_lock) == 0) {
    int accepted = accept_move(new_sol, cur_best, global_opt);
    pthread_mutex_unlock(&update_lock);
} else {
    /* Lock contended -- skip this global_opt update.
     * The solver continues; worst case is one missed improvement. */
    int accepted = 0;
    /* Still update local state (new_sol from cur_best) without global_opt */
    if (cur_best->tot_profit < new_sol->tot_profit) {
        sw_set_inplace(new_sol->vector, cur_best->vector);
        new_sol->tot_profit = cur_best->tot_profit;
        new_sol->feasible = cur_best->feasible;
        accepted = 1;
    }
}
```

### Example 4: Deprecation warning (branching.pyx)

```python
import warnings

def set_bias_wrapper(double bias, _internal=False):
    if not _internal:
        warnings.warn(
            "set_branching_bias is deprecated",
            DeprecationWarning,
            stacklevel=2
        )
    set_bias(bias)

def set_factors_wrapper(double objective_factor, double constraint_factor,
                        double bias_factor, double look_factor, _internal=False):
    if not _internal:
        warnings.warn(
            "set_branching_factors is deprecated",
            DeprecationWarning,
            stacklevel=2
        )
    set_factors(objective_factor, constraint_factor, bias_factor, look_factor)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global `BranchingStats` struct | Per-solve `solver_ctx_t.branching_stats` | Phase 3 (solver ctx architecture) | Each solve can have independent branching params |
| `set_bias()` / `set_factors()` global setters | `solver_ctx_set_bias()` / `solver_ctx_set_factors()` | Phase 3 | Thread-safe, per-context branching configuration |
| No parameter API on Model | `Model.set_param()` / `Model.get_param()` | This phase (12) | Canonical way to configure solver behavior |
| Unprotected `global_opt` writes in local_search | Mutex-protected via `update_lock` | This phase (12) | Safe concurrent local search with ThreadSanitizer-clean runs |

**Deprecated/outdated:**
- `set_bias_wrapper()`: Deprecated in favor of `model.set_param("branching_bias", value)`
- `set_factors_wrapper()`: Deprecated in favor of `model.set_param("branching_factors", (obj, con, bias, look))`
- `set_obj_dependence_wrapper()`: Deprecated in favor of `model.set_param("manual_bias", [...])`
- `solve(bias=...)`: Legacy kwarg, overridden by `set_param`

## Key Files to Modify

### Python/Cython Layer
| File | Changes |
|------|---------|
| `cbqs/Model.pyx` | Add `_params` dict, `set_param()`, `get_param()`, update `solve()` and `local_search()` to read from `_params` with precedence |
| `cbqs/Model.pxd` | Add `_params` declaration (`cdef public object _params`) |
| `cbqs/SearchLib.pyx` | In `run_sampling()` and `run_local_search()`, propagate branching params from model to `solver_ctx_t` |
| `cbqs/branching.pyx` | Add `DeprecationWarning` to `set_bias_wrapper`, `set_factors_wrapper`, `set_obj_dependence_wrapper` |

### C Layer
| File | Changes |
|------|---------|
| `cbqs/src/local_search.c` | Add `extern pthread_mutex_t update_lock;`, wrap `global_opt` writes in `accept_best_routine` with `pthread_mutex_trylock` |
| `cbqs/src/SearchLib.c` | (Possibly) move `update_lock` declaration to a shared header |

### Test Files
| File | Changes |
|------|---------|
| `tests/test_model_py.py` (or new) | Tests for `set_param`/`get_param` API, validation, precedence |
| `tests/test_branching_params.py` (new) | Deterministic test: fixed seed + branching params -> verify solution differs from default |
| `tests/test_deprecation.py` (new) | Verify `DeprecationWarning` on old setter calls |
| `tests/test_thread_safety.c` | Add test for `accept_best_routine` with `global_opt` mutex |

### CI
| File | Changes |
|------|---------|
| `.github/workflows/test.yml` | Already has TSan job -- ensure `test_thread_safety` covers new mutex test |

## Open Questions

1. **Exact list of parameters for `set_param`**
   - What we know: "branching_bias", "branching_factors", "num_workers", "timeout", "track_history" are explicitly mentioned
   - What's unclear: Should ALL `solve()` kwargs be represented (e.g., `M`, `stop_val`, `max_delta`, `reset_delta`, `distance`, `stopping_condition`, `max_worse_acceptances`)? The decision says "all solver parameters initially."
   - Recommendation: Start with the branching-related params plus commonly-used solve params. The generic API is extensible, so not everything needs to be in v1. Use: `branching_bias`, `branching_factors`, `manual_bias`, `bias_factor`, `manual_bias_factor`, `look_ahead_factor`, `num_workers`, `timeout`, `track_history`.

2. **How `Model.solve()` branching kwarg defaults interact with `_params`**
   - What we know: `set_param` wins over kwargs. `bias=-1` is the sentinel for "use default."
   - What's unclear: Should `solve(bias=5.0)` be silently ignored when `set_param("branching_bias", 10.0)` was called? Or should it emit a warning?
   - Recommendation: Silent ignore (per user decision: "`set_param` wins silently"). No warning needed.

3. **Scope of `accept_best_routine` mutex protection**
   - What we know: Mutex around `global_opt` writes. The `accept_move` function writes to both local state AND `global_opt`.
   - What's unclear: Should we refactor `accept_move` to separate local/global writes, or wrap the whole call?
   - Recommendation: Since `accept_move` is a short critical section and `trylock` is specified (fail-fast), wrapping the full `accept_move` call that passes `global_opt` is acceptable. The lock duration is very short (a few memory copies).

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all modified files
- `cbqs/src/solver_ctx.h` and `solver_ctx.c` -- existing ctx infrastructure
- `cbqs/src/Branching.h` and `Branching.c` -- current global branching system
- `cbqs/src/local_search.c` -- current `accept_best_routine` (no mutex)
- `cbqs/src/SearchLib.c` -- existing `update_lock` mutex in `ctg()`
- `cbqs/src/solver.c` -- CSearch_* functions reading from `ctx->branching_stats`
- `cbqs/SearchLib.pyx` -- current `run_sampling` and `run_local_search` (gap confirmed)
- `cbqs/Model.pyx` -- current solve() and branching parameter handling
- `cbqs/branching.pyx` -- current wrapper functions
- `.github/workflows/test.yml` -- existing CI TSan configuration

### Secondary (MEDIUM confidence)
- POSIX pthreads documentation for `pthread_mutex_trylock` behavior
- Python `warnings` module documentation for `DeprecationWarning` semantics

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries/tools already in use in the project
- Architecture: HIGH -- direct codebase analysis of exact files to modify, with gap confirmed
- Pitfalls: HIGH -- identified from specific code paths and interaction patterns
- Code examples: HIGH -- based on actual codebase patterns and existing infrastructure

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable codebase, internal architecture)
