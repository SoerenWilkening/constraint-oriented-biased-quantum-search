# Phase 15: Solve API Migration - Research

**Researched:** 2026-02-14
**Domain:** Python/Cython API refactoring -- parameter storage and method signature migration
**Confidence:** HIGH

## Summary

Phase 15 removes all keyword arguments from `solve()` and migrates them to the existing `set_param()`/`get_param()` API. The codebase already has a functional `set_param()`/`get_param()` system (from Phase 12/14) with 8 known parameters, a `_params` dict on Model, and validation logic. The task is to: (1) expand `_KNOWN_PARAMS` with all 13 former solve() parameters, (2) add per-param validation and type coercion to `set_param()`, (3) change `get_param()` to return defaults instead of None, (4) rewrite `solve()` to read exclusively from `_params`, and (5) update ~80 solve() calls across tests/benchmarks.

The current solve() signature has 14 keyword arguments. Three are being dropped entirely (`bias`, `manual_bias` conceptually, and `bias_factor` from model_t -- though `manual_bias` and `bias_factor` were already removed from `_KNOWN_PARAMS` in Phase 14). The remaining parameters map cleanly to flat keys. The `monte_calor_estimate` typo gets fixed to `monte_carlo_estimate`. The C-level model_t struct fields that receive solve() params (M, stopping_time, stop_val, etc.) remain unchanged; only the Python-level flow changes.

**Primary recommendation:** Implement in 3 sub-plans: (1) expand _KNOWN_PARAMS and add defaults/validation/coercion, (2) rewrite solve() internals to read from _params, (3) update all tests to use set_param() before solve().

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Parameter naming & grouping:**
- Keep original solve() parameter names exactly (M, bfs, stop_val, etc.) -- no renaming
- Fix the `monte_calor_estimate` typo to `monte_carlo_estimate` -- this is the one name change
- Flat keys only -- no namespacing (set_param('M', 100), not set_param('solver.M', 100))
- Drop the `bias` param entirely -- `branching_bias` from Phase 14 replaces it
- `manual_bias` and `bias_factor` silently removed -- Phase 14's `branching_weights` supersedes them

**Default & reset behavior:**
- Params persist across multiple solve() calls -- configure once, solve many
- `set_param(name, None)` resets that specific param to its default value
- No bulk reset_params() method -- individual reset via None is sufficient
- Callback persists like all other params -- consistent behavior, no special clearing
- `get_param(name)` always returns a value: the set value if configured, or the documented default -- never returns None for params that have defaults

**Validation & error messages:**
- Validate at set-time -- set_param('M', -5) raises immediately, fail fast
- Unknown parameter names raise ValueError -- strict, catches typos immediately
- Type coercion when possible -- set_param('M', '100') coerces to int, fails only when coercion impossible
- Warn on known conflicting parameter combinations -- log warnings but don't block

**Deprecation transition:**
- Hard break in v2.0 -- solve(M=100) raises TypeError, no deprecation period
- Simple rejection message -- "TypeError: solve() takes no arguments"
- Removed params (bias, manual_bias, bias_factor) treated as unknown -- standard ValueError, no special redirect messages

### Claude's Discretion

- Internal parameter storage implementation
- Coercion rules for each specific param type
- Which param combinations trigger conflict warnings
- How solve() internally reads from the params dict

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

This phase is purely internal refactoring of existing Python/Cython code. No new libraries are needed.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Cython | existing | Model.pyx is the primary file being modified | Already in project |
| numpy | existing | Used for branching_weights validation (np.asarray) | Already in project |
| warnings | stdlib | For conflict warnings on param combinations | Python stdlib |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | existing | Testing all new parameter paths | Already in project |

### Alternatives Considered
None -- this is internal refactoring, not a library choice.

## Architecture Patterns

### Current Architecture (Pre-Migration)

```
User calls:   solve(M=100, stopping_time=5, num_workers=2, ...)
                |
                v
Model.solve():  self.mod.M = M             (writes directly to C model_t)
                self.mod.stopping_time = stopping_time
                ...
                Parallel(n_jobs=num_workers, ...)(run_sampling(self, callback, ...))
                                                    |
                                                    v
SearchLib.run_sampling():  reads mod._params for branching params
                           writes to solver_ctx_t via setters
                           writes mod.mod[0].field for model_t fields
```

### Target Architecture (Post-Migration)

```
User calls:   m.set_param('M', 100)
              m.set_param('stopping_time', 5)
              m.set_param('num_workers', 2)
              m.solve()
                |
                v
Model.solve():  reads ALL params from self._params (with defaults)
                self.mod.M = self._params.get('M', default)
                self.mod.stopping_time = self._params.get('stopping_time', default)
                ...
                num_workers = self._params.get('num_workers', default)
                Parallel(n_jobs=num_workers, ...)(run_sampling(self, ...))
                                                    |
                                                    v
SearchLib.run_sampling():  SAME as before -- reads mod._params for branching params
                           (branching_bias, branching_weights, etc. already in _params)
```

### Pattern 1: Parameter Registry with Defaults and Coercion

**What:** A `_PARAM_DEFS` dict that maps each parameter name to its type, default value, validation function, and coercion function. `set_param()` looks up the definition, coerces the value, validates it, and stores it. `get_param()` returns the stored value or the registered default.

**When to use:** When migrating a kwargs-based API to a configure-then-execute pattern.

**Recommended implementation:**

```python
# At module level (outside the class), define param specs
_PARAM_DEFS = {
    'M': {
        'type': int,
        'default': -1,  # -1 means "auto: n**2 // 16"
        'coerce': lambda v: int(v),
        'validate': None,  # no constraint beyond type
    },
    'stopping_time': {
        'type': int,
        'default': 300,
        'coerce': lambda v: int(v),
        'validate': lambda v: v > 0,
        'validate_msg': 'stopping_time must be positive',
    },
    'num_workers': {
        'type': int,
        'default': 12,
        'coerce': lambda v: int(v),
        'validate': lambda v: v >= 1,
        'validate_msg': 'num_workers must be >= 1',
    },
    # ... etc for all params
}

_KNOWN_PARAMS = set(_PARAM_DEFS.keys())
```

### Pattern 2: solve() Reads from _params with Defaults

**What:** `solve()` reads every parameter from `_params`, falling back to the registered default for any unset param. No kwargs on solve() at all.

**Example flow inside solve():**

```python
def solve(self):
    if not self.constraints_compiled:
        raise ValueError("No constraints compiled")

    # Read all params with defaults
    M = self._get_effective('M')
    stopping_time = self._get_effective('stopping_time')
    stop_val = self._get_effective('stop_val')
    callback = self._get_effective('callback')
    max_delta = self._get_effective('max_delta')
    reset_delta = self._get_effective('reset_delta')
    depth_look_ahead = self._get_effective('depth_look_ahead')
    num_workers = self._get_effective('num_workers')
    results = self._get_effective('results')
    bfs = self._get_effective('bfs')
    ignore_constraint_search = self._get_effective('ignore_constraint_search')
    monte_carlo_estimate = self._get_effective('monte_carlo_estimate')
    verify = self._get_effective('verify')
    track_history = self._get_effective('track_history')

    # Auto-compute M if sentinel
    if M == -1:
        M = self.n ** 2 // 16

    # ... rest of solve logic unchanged
```

### Anti-Patterns to Avoid

- **Dual-path code:** Do NOT keep solve() kwargs alongside set_param() as a "transition." The decision is a hard break. Remove all kwargs immediately.
- **Default duplication:** Do NOT hard-code defaults in both `_PARAM_DEFS` and inside `solve()`. The single source of truth is `_PARAM_DEFS`. The `solve()` body reads from `_params` via a helper that consults `_PARAM_DEFS` for defaults.
- **Overcomplicating coercion:** Keep coercion simple. `int()` for ints, `float()` for floats, `bool()` for bools. Catch ValueError/TypeError from the coercion call. Do not build a type system.
- **Breaking SearchLib.run_sampling():** The `run_sampling()` function in SearchLib.pyx currently receives `callback` and `track_history` as arguments. These must now come from `mod._params`. The function signature may need to change or the function should read from `mod._params` directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parameter registry | Custom parameter class hierarchy | Simple dict of dicts (`_PARAM_DEFS`) | All params are flat key-value pairs with simple types; a dict is sufficient |
| Type coercion | Complex type dispatch system | Direct `int()`, `float()`, `bool()` calls with try/except | Only 4 types needed (int, float, bool, callable/None); Python builtins handle coercion |

**Key insight:** The parameter space is small (13 params) and static. A simple dict-of-dicts registry is the right level of abstraction. Do not build a framework.

## Common Pitfalls

### Pitfall 1: Default Duplication Leading to Drift

**What goes wrong:** Defaults are defined in two places (e.g., `_PARAM_DEFS` and inside `solve()`) and they drift apart over time.
**Why it happens:** Developers update one location and forget the other.
**How to avoid:** Single source of truth in `_PARAM_DEFS`. `solve()` always reads via `_get_effective(name)` which consults `_PARAM_DEFS[name]['default']`. Never hard-code a default in `solve()`.
**Warning signs:** Any numeric literal inside `solve()` that matches a default value.

### Pitfall 2: Breaking run_sampling() / run_local_search() Signatures

**What goes wrong:** `run_sampling()` currently takes `callback` and `track_history` as function arguments. If solve() stops passing them, the functions break.
**Why it happens:** The refactoring changes where parameters are read but the downstream functions still expect them as arguments.
**How to avoid:** Two options: (A) have `run_sampling()` read `callback` and `track_history` from `mod._params` directly (preferred -- keeps the pattern consistent), or (B) continue passing them as args from solve() after reading from `_params` (simpler change). Option B is recommended for Phase 15 since `run_sampling` is in a separate .pyx file and keeping its explicit arguments makes the dependency clear.
**Warning signs:** Test failures in concurrent tests that exercise callbacks and history.

### Pitfall 3: Sentinel Values vs None for "Auto" Behavior

**What goes wrong:** Some params use -1 as "auto-compute" (M=-1 means `n**2 // 16`, bias=-1 means `n/4`). The user decision says `set_param(name, None)` resets to default. If the default is -1, then `get_param('M')` returns -1, which is confusing.
**Why it happens:** The original solve() signature used -1 sentinels for "auto" behavior, but the set_param API uses None for "reset to default."
**How to avoid:** The default stored in `_PARAM_DEFS` should be the sentinel value (-1 for M, -1 for stop_val). `get_param('M')` returns -1 when unset (the documented default). The "auto" logic (`if M == -1: M = self.n**2 // 16`) stays inside `solve()`. Document that -1 means "auto" for M and stop_val.
**Warning signs:** Users confused by `get_param('M')` returning -1.

### Pitfall 4: Forgetting to Handle `results` Param as String

**What goes wrong:** The `results` param is a string ("min" or "average"), not a numeric type. Coercion via `str()` is trivial but validation must check against the allowed set.
**Why it happens:** Most params are numeric; string params need different handling.
**How to avoid:** Add an `allowed_values` field to the param def for string params. Validate against it in set_param().
**Warning signs:** `set_param('results', 'max')` silently accepted.

### Pitfall 5: Callback is a Callable or None

**What goes wrong:** The `callback` param is a callable or None. Type coercion does not apply. Setting `callback` to a non-callable (like a string) should raise ValueError.
**Why it happens:** Callback is the only param that accepts a callable type.
**How to avoid:** For the `callback` param, skip coercion and just validate that the value is callable or None.
**Warning signs:** `set_param('callback', 'not_a_function')` silently accepted.

### Pitfall 6: Test Blast Radius

**What goes wrong:** Changing solve() signature breaks ~80 test calls across 14 test files and benchmarks. If done in a single commit, bisecting regressions becomes impossible.
**Why it happens:** The hard break means every test must be updated.
**How to avoid:** Structure the work so that (1) the new param infrastructure is added first (testable independently), (2) solve() is changed next, (3) tests are updated in the same commit as the solve() change (they must change together since the old signature will be rejected).
**Warning signs:** Intermediate commits where tests fail.

## Code Examples

### Complete Parameter Registry

Based on the current solve() signature and defaults from model.c/Model.pyx:

```python
# Current solve() signature for reference:
# def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1,
#           stop_val: int = -1, callback = None, max_delta = 7, reset_delta = True,
#           depth_look_ahead = 0, num_workers: int = 12, results = "min",
#           bfs = False, ignore_constraint_search = False,
#           monte_calor_estimate = False, verify = False, track_history = True)

_PARAM_DEFS = {
    # --- Former solve() params (new in Phase 15) ---
    'M':                        {'default': -1,    'coerce': int,   'validate': None},
    'stopping_time':            {'default': 300,   'coerce': int,   'validate': lambda v: v > 0},
    'stop_val':                 {'default': -1,    'coerce': int,   'validate': None},
    'callback':                 {'default': None,  'coerce': None,  'validate': lambda v: v is None or callable(v)},
    'max_delta':                {'default': 7,     'coerce': int,   'validate': lambda v: v >= 0},
    'reset_delta':              {'default': True,  'coerce': bool,  'validate': None},
    'depth_look_ahead':         {'default': 0,     'coerce': int,   'validate': lambda v: v >= 0},
    'num_workers':              {'default': 12,    'coerce': int,   'validate': lambda v: v >= 1},
    'results':                  {'default': 'min', 'coerce': str,   'validate': lambda v: v in ('min', 'average')},
    'bfs':                      {'default': False, 'coerce': bool,  'validate': None},
    'ignore_constraint_search': {'default': False, 'coerce': bool,  'validate': None},
    'monte_carlo_estimate':     {'default': False, 'coerce': bool,  'validate': None},
    'verify':                   {'default': False, 'coerce': bool,  'validate': None},
    'track_history':            {'default': True,  'coerce': bool,  'validate': None},

    # --- Existing params (from Phase 12/14, already in _KNOWN_PARAMS) ---
    'branching_bias':           {'default': None,  'coerce': float, 'validate': None},
    'branching_weights':        {'default': None,  'coerce': None,  'validate': 'special'},
    'branching_factor':         {'default': None,  'coerce': float, 'validate': lambda v: v >= 0},
    'bias_factor':              {'default': None,  'coerce': float, 'validate': lambda v: v >= 0},
    'look_ahead_factor':        {'default': None,  'coerce': float, 'validate': lambda v: v >= 0},
    'timeout':                  {'default': None,  'coerce': int,   'validate': lambda v: v > 0},
}
```

**Notes on defaults:**
- `branching_bias` default is `None` because it's auto-computed as `n/4` during `close()`. This is a branching param, not a solve() param, so it keeps its existing Phase-14 behavior.
- `M` default is `-1` (sentinel for "auto: n^2 // 16"). This matches the original solve() default.
- `callback` default is `None` (no callback). No coercion -- must be callable or None.

### Type Coercion Rules (Discretion Area)

| Param Type | Coerce Function | Example | Failure |
|------------|----------------|---------|---------|
| int | `int(value)` | `'100'` -> `100`, `100.0` -> `100` | `'abc'` -> ValueError |
| float | `float(value)` | `'3.14'` -> `3.14`, `1` -> `1.0` | `'abc'` -> ValueError |
| bool | `bool(value)` | `1` -> `True`, `0` -> `False` | Never fails (everything is truthy/falsy) |
| str | `str(value)` | any -> string | Never fails, but validation catches invalid values |
| callable | No coercion | Must be callable or None | Non-callable, non-None -> ValueError |

**Note on bool coercion:** Python's `bool()` never fails. `bool('False')` returns `True` (non-empty string). This is acceptable because the user decision says "coerce when possible, fail only when coercion impossible." However, this could be surprising. Recommendation: for bool params, accept only `True`, `False`, `0`, `1` and reject other types. This prevents `bool('False') == True` surprises.

**Revised bool coercion recommendation:**
```python
def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f"Cannot coerce {type(value).__name__} to bool")
```

### Conflict Warning Combinations (Discretion Area)

Recommended param conflict warnings (log.warning, don't block):

1. **`bfs=True` with `M` set:** BFS mode ignores M. Warn: "M is ignored when bfs=True"
2. **`monte_carlo_estimate=True` with large `num_workers`:** Monte Carlo estimation is sequential. Warn: "monte_carlo_estimate runs sequentially; num_workers > 1 has no effect"
3. **`stop_val` set in SATISFY mode:** stop_val is ignored in SAT mode (existing warning already in solve()). Migrate the warning to set-time or keep at solve-time.
4. **`ignore_constraint_search=True` with SATISFY mode:** Constraint search is the core of SAT solving. Warn: "ignore_constraint_search=True may prevent finding feasible solutions in SATISFY mode"

### How solve() Internally Reads Params (Discretion Area)

Recommended: Add a private helper method `_get_effective(name)` that returns the stored value or the default:

```python
cdef class Model:
    def _get_effective(self, str name):
        """Get effective param value: stored value if set, else default from _PARAM_DEFS."""
        val = self._params.get(name)
        if val is not None:
            return val
        return _PARAM_DEFS[name]['default']
```

**Important edge case:** Some params have `None` as their actual stored value (e.g., `callback=None` means no callback). The helper must distinguish between "not set" and "set to None." Solution: use a sentinel object:

```python
_UNSET = object()

def _get_effective(self, str name):
    val = self._params.get(name, _UNSET)
    if val is _UNSET:
        return _PARAM_DEFS[name]['default']
    return val
```

But wait -- the decision says `set_param(name, None)` resets to default. So after `set_param('callback', None)`, the value is effectively removed from `_params` (or stored as the default). Implementation: `set_param(name, None)` should **delete the key from `_params`**, and `_get_effective()` returns the default when the key is absent. This cleanly handles the None/unset distinction.

### Internal Storage Implementation (Discretion Area)

**Recommendation:** Keep using `self._params = {}` (already exists). When `set_param(name, None)` is called, delete the key:

```python
def set_param(self, str name, value):
    if name not in _KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: '{name}'")
    if value is None:
        self._params.pop(name, None)  # reset to default
        return
    # ... coercion and validation ...
    self._params[name] = coerced_value
```

This keeps the dict sparse (only explicitly-set params are stored), which makes `__copy__` cheap and the state easy to inspect.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `solve(M=100, ...)` kwargs | `set_param('M', 100); solve()` | Phase 15 (this phase) | All test/user code must change |
| `bias` param on solve() | `branching_bias` via set_param() | Phase 14 | Already done |
| `monte_calor_estimate` typo | `monte_carlo_estimate` fixed | Phase 15 (this phase) | Typo fix in param name |
| `manual_bias`, `bias_factor` on model_t | `branching_weights` via set_param() | Phase 14 | Already superseded |

**Deprecated/outdated:**
- `bias` solve() kwarg: Replaced by `branching_bias` (Phase 14)
- `manual_bias`, `manual_bias_factor` on model_t: Superseded by `branching_weights` (Phase 14)
- `monte_calor_estimate` typo: Fixed to `monte_carlo_estimate`

## Detailed Parameter Inventory

### Complete solve() Parameter Map

| Parameter | Python Default | C model_t field | Type | Notes |
|-----------|---------------|------------------|------|-------|
| M | -1 (auto: n^2//16) | `mod.M` (size_t) | int | -1 sentinel for auto |
| stopping_time | 300 | `mod.stopping_time` (int) | int | seconds |
| stop_val | -1 | `mod.stop_val` (int) | int | -1 means no target |
| callback | None | N/A (Python-level) | callable/None | Passed to run_sampling |
| max_delta | 7 | `mod.max_delta` (int) | int | SAT mode delta bound |
| reset_delta | True | `mod.reset_delta` (int) | bool | 1/0 in C |
| depth_look_ahead | 0 | `mod.depth_look_ahead` (int) | int | |
| num_workers | 12 | N/A (Python-level Parallel n_jobs) | int | Parallel thread count |
| results | "min" | N/A (Python-level) | str | "min" or "average" |
| bfs | False | N/A (Python-level, currently unused in solve body!) | bool | **Not actually used in solve()** |
| ignore_constraint_search | False | `mod.ignore_constraint_search` (int) | bool | 1/0 in C |
| monte_carlo_estimate | False (was `monte_calor_estimate`) | `mod.monte_carlo_estimate` (int) | bool | 1/0 in C. Typo fixed. |
| verify | False | N/A (Python-level) | bool | Triggers verify_solution() |
| track_history | True | N/A (Python-level, passed to run_sampling) | bool | |
| **bias** | **-1 (DROPPED)** | N/A | N/A | Replaced by branching_bias |

### Parameters Already in _KNOWN_PARAMS (Phase 14)

| Parameter | Current Default | Notes |
|-----------|----------------|-------|
| branching_bias | auto: n/4 (set during close()) | Already works |
| branching_weights | None | Already validated |
| branching_factor | None (ctx default: 1.0) | Already validated |
| bias_factor | None (ctx default: 1.0) | Already validated |
| look_ahead_factor | None (ctx default: 0.0) | Already validated |
| num_workers | None | Exists but not used by solve() yet |
| timeout | None | Exists but not used by solve() yet |
| track_history | None | Exists but not used by solve() yet |

### Key Observation: Overlap Between Existing and New Params

The current `_KNOWN_PARAMS` already contains `num_workers`, `timeout`, and `track_history`. However, these are NOT yet read by `solve()`. Phase 15 must wire these up:

- `num_workers`: Currently in `_KNOWN_PARAMS` but solve() still takes it as kwarg. Merge: set_param value takes precedence.
- `track_history`: Currently in `_KNOWN_PARAMS` but solve() still takes it as kwarg. Merge: set_param value takes precedence.
- `timeout`: In `_KNOWN_PARAMS` but never used by solve(). This was a forward-looking addition. Wire it to `stopping_time` or keep as a separate concept? **Recommendation:** `timeout` and `stopping_time` are different concepts (timeout is wall-clock kill switch via solver_ctx, stopping_time is the C-level stopping parameter). Keep both. `timeout` maps to `ctx.timeout_ms`, `stopping_time` maps to `mod.stopping_time`.

### Observation: `bfs` Parameter is Dead Code

The `bfs` parameter is accepted by solve() but never actually used in the solve() body. It should still be migrated to set_param() for API completeness (the param was documented), but note that it has no effect.

### Observation: `results` Parameter is Partially Dead

The `results` parameter is validated ("min" or "average") but the actual branching between "min" and "average" result aggregation is not visible in the current solve() body. It may affect downstream code not visible here. Migrate it as-is.

## Files to Modify

### Primary Changes

| File | Change | Complexity |
|------|--------|------------|
| `cbqs/Model.pyx` | Expand `_KNOWN_PARAMS` -> `_PARAM_DEFS`, rewrite `set_param()` with coercion, rewrite `get_param()` with defaults, strip all solve() kwargs, add `_get_effective()` helper | HIGH |
| `cbqs/SearchLib.pyx` | Update `run_sampling()` to read callback/track_history from `mod._params` (or keep as args from solve()) | LOW-MEDIUM |

### Test Updates (~80 calls across 14 files)

| File | # of solve() calls | Unique kwargs used |
|------|--------------------|--------------------|
| tests/test_model_py.py | 10 | stopping_time, num_workers, verify |
| tests/test_set_param.py | 4 | stopping_time, num_workers, bias |
| tests/test_verification_py.py | 11 | stopping_time, num_workers, verify |
| tests/test_diagnostics_py.py | 17 | stopping_time, num_workers, verify, track_history |
| tests/test_concurrent_history.py | 5 | stopping_time, num_workers, track_history, callback |
| tests/test_determinism.py | 8 | M, stopping_time, num_workers |
| tests/test_branching_propagation.py | 8 | stopping_time, num_workers |
| tests/test_memory_stress.py | 7 | stopping_time, num_workers |
| tests/test_cython_memory.py | 1 | stopping_time, num_workers |
| tests/test_stress.py | 1 | stopping_time, num_workers |
| tests/test_validation_model_py.py | 3 | results, num_workers, stopping_time |
| benchmarks/test_bench_solver.py | 12 | stopping_time, num_workers |

### Kwargs Frequency Analysis

| Kwarg | Usage Count | Notes |
|-------|-------------|-------|
| stopping_time | ~80 | Used in virtually every call |
| num_workers | ~80 | Used in virtually every call |
| verify | ~10 | Used in verification/diagnostic tests |
| track_history | ~8 | Used in history/concurrent tests |
| M | ~8 | Used in determinism tests |
| callback | ~3 | Used in concurrent callback tests |
| bias | ~1 | Used once (test_set_param.py precedence test) |
| results | ~2 | Used in validation tests |

## Open Questions

1. **Should `run_sampling()` and `run_local_search()` signatures change?**
   - Currently they take `callback` and `track_history` as explicit args
   - Option A: Read from `mod._params` inside the function (cleaner long-term)
   - Option B: Keep as args, solve() reads from _params and passes them (less change)
   - **Recommendation:** Option B for Phase 15. Option A can be done later if desired. This minimizes the blast radius of changes to SearchLib.pyx.

2. **How to handle `num_workers` already being in `_KNOWN_PARAMS`?**
   - It was added in Phase 12/14 but never wired to solve()
   - Phase 15 wires it up. The existing `num_workers` in `_KNOWN_PARAMS` just gets a proper default (12) and coercion rule. No conflict.

3. **Test helper pattern for setting common params?**
   - Most tests set `stopping_time=5, num_workers=1`. With set_param(), this becomes 2 extra lines per test.
   - **Recommendation:** Create a test helper `_configure_for_test(model, stopping_time=5, num_workers=1)` or have `_make_small_model()` pre-configure defaults. This keeps tests concise.

## Sources

### Primary (HIGH confidence)
- `cbqs/Model.pyx` lines 75-84, 86-180, 322-424 -- Current _KNOWN_PARAMS, set_param/get_param, solve() signature and body
- `cbqs/SearchLib.pyx` lines 185-334 -- run_sampling() implementation showing how params flow
- `cbqs/src/model.h` lines 10-36 -- C model_t struct definition
- `cbqs/src/model.c` lines 7-37 -- C model_t defaults (init_model)
- `cbqs/src/solver_ctx.h` lines 31-64 -- solver_ctx_t struct
- `cbqs/src/solver_ctx.c` lines 24-65, 131-194 -- solver_ctx lifecycle and setters
- `cbqs/Model.pxd` lines 1-79 -- Cython declarations for Model class
- `cbqs/result.py` -- OptimizeResult container
- `cbqs/src/Branching.h` lines 17-72 -- BranchingStats_t and BranchingFunction
- `tests/test_set_param.py` -- Existing set_param test suite
- `tests/test_model_py.py` -- Model integration tests
- `.planning/phases/15-solve-api-migration/15-CONTEXT.md` -- User decisions

### Secondary (MEDIUM confidence)
- All 14 test files with solve() calls -- grep analysis of kwargs usage patterns

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, purely internal refactoring
- Architecture: HIGH -- directly read from existing code, all patterns are visible
- Pitfalls: HIGH -- derived from concrete code analysis, not speculation
- Parameter inventory: HIGH -- exhaustive analysis of solve() signature and model_t struct

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable -- internal refactoring, no external dependencies)
