# Architecture Research: v1.1 Bug Fixes and Code Polish

**Domain:** C/Cython/Python solver (CBQS) -- cleanup milestone targeting history callback, local_search API, SATISFY mode crash, VLA removal, and deprecated BranchingStats
**Researched:** 2026-02-06
**Confidence:** HIGH (direct codebase analysis of every relevant source file)

---

## Executive Summary

The v1.0 milestone delivered the `solver_ctx_t` architecture, arena allocator, per-thread PRNG, and an `OptimizeResult` return type. However, five cleanup items remain that intersect with the existing architecture in non-trivial ways. This document maps each cleanup item onto the current code, identifies the root cause, analyzes dependencies between fixes, and recommends a fix order.

The key architectural insight: four of the five items (history callback, local_search API, SATISFY mode, deprecated BranchingStats) share a common pattern -- they are remnants of pre-`solver_ctx_t` global/module-level state that was left in place for backward compatibility during the v1.0 migration. The fifth (VLA replacement) is a portability fix already partially addressed by pre-allocated per-thread buffers.

---

## Item 1: History Callback Rework

### Current Architecture

The history callback is implemented as module-level `cdef` state in `SearchLib.pyx` (lines 134-159):

```python
# Module-level state for history callback wrapper.
cdef object _history_list = None
cdef object _history_prev_best = None
cdef object _history_original_callback = None
cdef Model _history_mod = None
```

The callback function `_history_callback_fn()` (line 143) reads from these module-level variables. It is set as the global `python_callback` before the solve loop starts (lines 201-206 in `run_sampling`, lines 297-302 in `run_local_search`).

**Call chain:**

```
Model.solve() [Python]
  -> joblib.Parallel(n_jobs=N, backend="threading")
    -> run_sampling(Model, callback, not_stop) [Cython, per-worker]
      1. Sets module-level: _history_list = [], _history_mod = mod, etc.
      2. Sets module-level: python_callback = _history_callback_fn
      3. Calls ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent) [C, nogil]
        4. On improvement: callback() [C, acquires GIL]
          5. my_callback_c() [Cython, with gil]
            6. python_callback() -> _history_callback_fn() [Python]
              7. Reads _history_mod.mod[0].global_opt[0].tot_profit
              8. Appends to _history_list
```

### The Concurrency Problem

When `Model.solve()` uses `joblib.Parallel(backend="threading")` with `num_workers > 1`, all N workers execute `run_sampling()` in separate threads. Each thread:

1. **Overwrites** the same module-level `_history_list`, `_history_mod`, `_history_prev_best`, `_history_original_callback`
2. **Overwrites** the same module-level `python_callback`

This is a data race on Python objects. Because of the GIL, it does not cause memory corruption, but it causes logical corruption: one worker's history setup overwrites another's. The last worker to set up wins; earlier workers' callback state is lost.

**Observed behavior:** All workers share the same `_history_list` and `_history_mod`, so history entries from all workers end up in one list. The `_history_prev_best` deduplication check races between workers. The merged history in `Model.solve()` (lines 333-336) then collects from all workers' `res[6]`, but each worker returns the same shared `_history_list` at that point.

### Why Module-Level State Was Used

Cython imposes a constraint: `cpdef` functions cannot capture closures. A regular Python class cannot access `cdef` attributes on Cython extension types. The workaround was module-level `cdef` variables that act as a manual closure.

### Recommended Rework: Per-Worker History via Thread-Local Dictionary

**Approach:** Replace the four module-level `cdef` variables with a thread-keyed dictionary. Each worker stores its own history state under `threading.get_ident()`.

```python
import threading

# Thread-keyed history state (replaces module-level cdef variables)
cdef dict _history_state = {}  # {thread_id: (list, prev_best, original_callback, Model)}

def _history_callback_fn():
    tid = threading.get_ident()
    state = _history_state.get(tid)
    if state is None:
        return
    hist_list, prev_best, orig_cb, mod = state
    obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
    elapsed_ms = mod.mod[0].runtime * 1000.0
    is_feasible = bool(mod.mod[0].global_opt[0].feasible)
    iteration = mod.mod[0].qtg_applications
    if prev_best is None or obj_val != prev_best:
        hist_list.append((iteration, obj_val, elapsed_ms, is_feasible))
        _history_state[tid] = (hist_list, obj_val, orig_cb, mod)
    if orig_cb is not None:
        orig_cb()
```

**Setup in run_sampling (replaces lines 200-206):**

```python
tid = threading.get_ident()
hist = []
_history_state[tid] = (hist, None, callback, mod)
python_callback = _history_callback_fn
```

**Teardown after solve loop:**

```python
history = list(_history_state.get(tid, ([], None, None, None))[0])
_history_state.pop(tid, None)
```

**Why this works:**
- `threading.get_ident()` is fast (no syscall on CPython, just reads a cached value)
- The GIL protects dictionary writes, so `_history_state[tid] = ...` is atomic from Python's perspective
- Each worker gets its own history list, preventing cross-worker corruption
- The `python_callback` module-level variable is still shared, but it points to the same function -- the function itself dispatches per-thread. This is safe because the callback is always `_history_callback_fn` for all workers.

**Remaining issue with `python_callback`:** The module-level `python_callback` variable is still shared. If `run_quantum_local_search` sets it to a different callback while sampling is running, there is a race. However, `run_quantum_local_search` is not called concurrently with `run_sampling` in practice. To be safe, the `python_callback` global could also be keyed by thread, but this requires changing `my_callback_c()` which acquires the GIL -- adding `threading.get_ident()` there is acceptable since the GIL is already held.

**Alternative approach (not recommended):** Embed callback pointer and user data in `solver_ctx_t` at the C level. This would require changing the C `callback_t` typedef from `void (*)()` to `void (*)(void *userdata)` and threading `userdata` through `ctg()`, `local_search()`, etc. This is cleaner architecturally but touches many C function signatures and is a larger change than v1.1 scope warrants.

### Impact on solver_ctx_t

No changes needed to `solver_ctx_t`. The history callback operates entirely at the Python/Cython level, above the nogil boundary. The C kernel just calls `callback()` which acquires the GIL and enters Python code.

---

## Item 2: SATISFY Mode Crash Analysis

### Current Architecture: OPTIMIZE vs SATISFY Code Paths

The `mod.solver` field determines the code path at two levels:

**C level (SearchLib.c, `ctg()` function, lines 110-122):**

```c
if (mod->solver == SATISFY) search_function = CSearch_sat;
if (mod->solver == OPTIMIZE && !feasible) search_function = CSearch_opt_sat;
if (mod->solver == OPTIMIZE && feasible) {
    prepare(mod->obj, cur_sol, &fulfilled_objective_terms);
    stage = 3;
    search_function = CSearch_opt;
}
```

For SATISFY mode:
- Uses `CSearch_sat` only (no objective function involved)
- `tot_profit` represents negative constraint violation count (not objective value)
- Stop condition: `cur_sol->tot_profit == -(int64_t)mod->con->num_constraints` (all constraints satisfied)
- `mod->global_opt->tot_profit` comparison: `> cur_sol->tot_profit` (lower is better, since values are negative)

For OPTIMIZE mode:
- Uses `CSearch_opt_sat` then transitions to `CSearch_opt`
- `tot_profit` represents actual objective value
- Different stop conditions based on `stop_val`

**Cython level (SearchLib.pyx, `run_sampling()` lines 213-239):**

OPTIMIZE path (line 213-216): calls `ctg()` once.

SATISFY path (lines 217-239): calls `ctg()` in a loop with increasing delta, adjusting M and bias each iteration. Signals SIGINT when solution found.

**Python level (Model.pyx, `solve()` lines 327-367):**

After workers complete, `solve()`:
1. `self.final_state = self.global_opt` (line 330) -- but `self.global_opt` is a Python attribute that is `None` unless set; not the C `mod->global_opt`
2. Extracts solution from `self.mod[0].global_opt[0].vector` (lines 339-340)
3. Reads `self.objective_value` which is `self.mod[0].global_opt[0].tot_profit * self.sense` (line 467-468)

### Root Cause of SATISFY Mode Crash

**Location of crash:** The crash occurs in the history callback (`_history_callback_fn`, line 151) or in the `objective_value` property (line 468) when the model is in SATISFY mode.

**The problem chain:**

1. When `Model.__init__` runs, `self.mod.solver = SATISFY` (line 103) and `self.sense = MAXIMIZE` (line 96), which is `-1`.

2. If the user never calls `set_objective()`, `self.sense` remains `MAXIMIZE = -1`.

3. In `_history_callback_fn()` (line 151):
   ```python
   obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
   ```
   In SATISFY mode, `tot_profit` is a negative violation count (e.g., `-3`). Multiplying by `sense = -1` gives `3`, which is meaningless as an objective value.

4. More critically, `self.objective_value` (line 467-468) does the same multiplication. For SATISFY mode, there is no meaningful "objective value" -- the solver is finding feasibility, not optimizing.

5. **The actual crash:** In SATISFY mode in `run_sampling`, the code at line 220:
   ```python
   stpvl = -len(mod.mod[0].con[0].num_constraints)
   ```
   This accesses `mod.mod[0].con[0].num_constraints` as if it were a Python object with `len()`. But `num_constraints` is a C `size_t` (integer), not a sequence. `len()` on an integer raises `TypeError`.

   **Wait -- looking more carefully:** In the Cython `.pxd` declarations, `new_constraints_t` has `num_constraints` as `size_t`. In Cython, `len()` on a `size_t` would indeed fail. However, this code has been working for OPTIMIZE mode because the SATISFY branch is only entered when `mod.mod[0].solver != OPTIMIZE`.

   **Actually, re-reading line 220:** `mod.mod[0].con[0].num_constraints` -- this dereferences `con[0]` which is a `new_constraints_t` struct. The `.num_constraints` field is a `size_t`. Wrapping it in `-len(...)` treats it as if it had a length. This is likely the crash: **`len()` called on a C integer type**.

   The correct code should be: `stpvl = -mod.mod[0].con[0].num_constraints` (without `len()`).

6. **Secondary crash path:** Even if line 220 is fixed, `Model.solve()` unconditionally accesses `self.mod[0].global_opt[0].vector` (lines 339-340) and `self.objective_value` (line 356). In SATISFY mode without an objective function, `objective_value` returns `tot_profit * sense` which is a constraint violation count times -1 -- semantically wrong.

### How SATISFY Differs Architecturally from OPTIMIZE

| Aspect | OPTIMIZE | SATISFY |
|--------|----------|---------|
| `mod->solver` | `2` | `3` |
| `tot_profit` semantics | Objective value (lower is better internally) | Negative constraint violation count |
| `global_opt` semantics | Best objective found so far | Most-feasible solution found so far |
| Stop condition (C) | `tot_profit <= stop_val` | `tot_profit == -num_constraints` |
| Stop condition (Cython) | Single `ctg()` call | Loop over delta values, SIGINT on solve |
| Objective function | Required (set via `set_objective()`) | Not required |
| `self.sense` | Set by `set_objective()` | Remains `MAXIMIZE = -1` (default) |
| History callback meaning | Objective improvement events | Feasibility improvement events |

### Recommended Fix

**Fix 1 (Critical): Line 220 in SearchLib.pyx:**
```python
# BEFORE (crashes):
stpvl = -len(mod.mod[0].con[0].num_constraints)
# AFTER (correct):
stpvl = -<int>mod.mod[0].con[0].num_constraints
```

**Fix 2: Guard objective_value for SATISFY mode in Model.pyx:**
```python
@property
def objective_value(self):
    if self.mod[0].solver == SATISFY:
        # In SATISFY mode, tot_profit is constraint violation count, not objective
        return None
    return self.mod[0].global_opt[0].tot_profit * self.sense
```

**Fix 3: Guard history callback for SATISFY mode:**
In `_history_callback_fn()`, check solver mode. For SATISFY, report constraint satisfaction progress instead of objective value:
```python
if mod.mod[0].solver == SATISFY:
    obj_val = mod.mod[0].global_opt[0].tot_profit  # raw violation count
else:
    obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
```

**Fix 4: Guard OptimizeResult construction in Model.pyx solve():**
```python
if self.mod[0].solver == SATISFY:
    objective = None  # or number of satisfied constraints
else:
    objective = self.objective_value
```

### SATISFY Mode Signal Handling Concern

In SATISFY mode, `run_sampling()` raises `SIGINT` (line 236) when a solution is found:
```python
signal.raise_signal(signal.SIGINT)
```

This is architecturally problematic because:
- `SIGINT` is process-global; it will interrupt ALL threads, not just the current worker
- When run inside joblib, this can cause the entire parallel pool to tear down
- The signal handler in SearchLib.c (`handle_signal`, lines 53-56) sets `solver_ctx_request_stop(g_active_ctx)`, but `g_active_ctx` is a global pointing to the last worker's context

This is a pre-existing issue but should be noted for the fix: the SATISFY mode stop mechanism should use `solver_ctx_request_stop()` directly instead of `SIGINT`.

---

## Item 3: local_search() API Layer Mismatch

### Current Call Chain

```
Model.local_search() [Python, Model.pyx line 371]
  -> Parameters: distance, callback, stop_time, max_worse_acceptances, stopping_condition, verify
  -> Sets: mod.distance, mod.stopping_time, mod.stop_val=-1, mod.max_worse_acceptances, mod.stopping_condition
  -> Calls: run_local_search(self, callback) [Cython]

run_local_search() [Cython, SearchLib.pyx line 269]
  -> Creates solver_ctx_t
  -> Sets up history callback
  -> Calls: local_search(ctx, st, mod.mod, cb_ptr) [C, nogil]

local_search() [C, local_search.c line 478]
  -> Signature: int local_search(solver_ctx_t *ctx, state_t *cur_sol, model_t *mod, callback_t callback)
  -> Reads: mod->distance, mod->con, mod->obj, mod->stopping_time, mod->stop_val
  -> Reads: mod->max_worse_acceptances, mod->stopping_condition
  -> Writes: mod->runtime, mod->global_opt (via accept_move)
  -> Calls: accept_best_routine(ctx, cur_sol, mod->global_opt, mod->con, mod->obj, ...)
```

### The Mismatch

The `local_search()` C function reads parameters from `model_t` and also writes to `model_t.runtime` and `model_t.global_opt`. This creates two problems:

1. **Parameter bundling:** `local_search()` takes the entire `model_t*` to access 7+ parameters. The `model_t` was designed as a flat bag for all solver parameters. `local_search()` only needs a subset: `{distance, con, obj, stopping_time, stop_val, max_worse_acceptances, stopping_condition, global_opt}`.

2. **Mutable shared state through model_t:** `local_search()` writes `mod->runtime` on every iteration (line 538) and writes `mod->global_opt` via `accept_move()`. If `local_search()` were ever called from multiple workers (like `ctg` is via joblib), this would be a data race.

### Current State: Is This Actually Broken?

**No, `local_search()` is currently single-threaded at the Python level.** `Model.local_search()` does NOT use joblib. It calls `run_local_search()` once, not in parallel. The parallelism happens INSIDE `local_search.c` via pthreads in `accept_best_routine()`.

However, `local_search.c` internally spawns `num_threads` pthreads for neighborhood exploration, and those threads share `mod->global_opt` via `accept_move()` called from `accept_best_routine()` (lines 445-446). The `accept_move()` on `global_opt` is NOT protected by a mutex in the local_search path (unlike `ctg()` which has `pthread_mutex_lock(&update_lock)` on line 184).

### Recommended Cleanup

**Approach: Extract parameter struct for local_search (LOW priority)**

Since `local_search()` is single-threaded at the Python level, the main cleanup is cosmetic: make the API clearer about what it reads and writes. Options:

**Option A (Minimal, recommended for v1.1):** Keep `model_t*` parameter. Add a comment documenting which fields are read and which are written. Add mutex protection to `global_opt` writes inside `accept_best_routine`.

**Option B (Cleaner, deferred to v1.2):** Create a `local_search_params_t` struct with just the needed fields, and pass that instead of the full `model_t*`. This decouples local_search from the model layer.

For v1.1, Option A is sufficient. The key safety fix is ensuring `accept_move()` on `global_opt` in `accept_best_routine()` (line 445) uses the `update_lock` mutex, matching the pattern already used in `ctg()`:

```c
// In accept_best_routine(), line 445:
// BEFORE:
int accepted = accept_move(new_sol, cur_best, global_opt);
// AFTER:
pthread_mutex_lock(&update_lock);
int accepted = accept_move(new_sol, cur_best, global_opt);
pthread_mutex_unlock(&update_lock);
```

### Integration Point: Callback in local_search

The `callback` parameter flows through `local_search()` to line 542:
```c
if (callback) callback();
```

This callback is the same `my_callback_c` that acquires the GIL and calls `python_callback`. It is called from the main thread of `local_search()` (after `accept_best_routine()` joins all pthreads), so there is no concurrency issue with the callback in the local_search path.

---

## Item 4: VLA Replacement in accept_best_routine

### Current State

The VLA has already been partially addressed. Looking at `accept_best_routine()` (local_search.c line 332):

```c
int64_t remainings[C];  // <-- THIS IS THE REMAINING VLA
```

**What has already been fixed:**
- `totals[C]` in `explore_neighbourhood()` replaced with `data[i].thread_totals = malloc(C * sizeof(int64_t))` (line 377)
- `bits[d]` in `explore_neighbourhood()` replaced with `data[i].thread_bits = malloc(d * sizeof(int))` (line 378)
- Per-thread scratch buffers properly allocated and freed

**What remains:**
- `int64_t remainings[C]` in `accept_best_routine()` at line 332 is still a VLA on the stack

### Risk Assessment

`C` is `con->num_constraints`. For typical problem sizes (C < 100), this is 800 bytes on the stack -- not a problem. For large problems (C > 10000), this could cause stack overflow (80KB+). VLAs are also not standard in C11 (they are optional) and not supported at all in MSVC.

### Recommended Fix

Replace with heap allocation:

```c
int64_t *remainings = malloc(C * sizeof(int64_t));
if (remainings == NULL) {
    // ... cleanup and return -1
}
for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, new_sol, i);
// ... use remainings ...
free(remainings);  // before every return path
```

Or use arena allocation since `ctx` is available:

```c
int64_t *remainings = (int64_t*)arena_alloc(ctx->arena, C * sizeof(int64_t), 8);
// No free needed -- arena_reset handles it
```

The arena approach is preferred since `accept_best_routine()` already calls `solver_ctx_arena_reset(ctx)` at line 437. The `remainings` array's lifetime fits within one call to `accept_best_routine()`, and the arena is reset at the end.

### Dependency

This fix is independent of all other items. It can be done first or last.

---

## Item 5: Deprecated BranchingStats Global

### Current Architecture

The global `BranchingStats` in `Branching.c` (line 6) coexists with the per-context `ctx->branching_stats` in `solver_ctx_t`. The migration status:

| Function | Uses Global | Uses ctx | Status |
|----------|------------|----------|--------|
| `BranchingFunction()` | No (takes `const BranchingStats_t *stats`) | Via caller | Migrated |
| `StateProbability()` | No (uses `&ctx->branching_stats`) | Yes | Migrated |
| `set_bias()` | Yes (writes `BranchingStats.bias`) | No | DEPRECATED |
| `set_factors()` | Yes (writes `BranchingStats.*`) | No | DEPRECATED |
| `set_obj_dependence()` | Yes (writes `BranchingStats.obj_dependent`) | No | DEPRECATED |
| `set_constraint_dependence()` | Yes (writes `BranchingStats.constraint_dependent`) | No | DEPRECATED |
| `solver_ctx_set_bias()` | No | Yes | NEW (replacement) |
| `solver_ctx_set_factors()` | No | Yes | NEW (replacement) |

The deprecated global setters are still called from Python-level wrappers:

```python
# In Model.pyx solve(), line 309:
set_bias_wrapper(bias)
set_factors_wrapper(manual_bias_factor, 0, bias_factor, look_ahead_factor)
```

These call through to `branching.pxd` wrappers which call `set_bias()` and `set_factors()` -- the **global** versions.

Meanwhile, in `run_sampling()` (SearchLib.pyx), the context is created and configured:
```python
cdef solver_ctx_t *ctx = solver_ctx_create()  # line 184
solver_ctx_set_bias(ctx, cur_sol.state[0].vector.bits / delta - 1)  # line 228 (SATISFY only)
```

But the bias/factors from `solve()` parameters are set on the GLOBAL, not on the context. The `solver_ctx_create()` initializes `branching_stats` with defaults (bias=5, bias_factor=1, etc.), NOT from the global.

### The Bug

There is an inconsistency: `Model.solve()` calls `set_bias_wrapper(bias)` which sets the global, but the actual solve uses `ctx->branching_stats` which has defaults. The global bias value is never propagated to the context.

**In OPTIMIZE mode:** `run_sampling()` does not call `solver_ctx_set_bias()`, so the context keeps the default bias of 5. The `solve()` method set `bias = self.n / 4` on the global, but the context does not see this.

**In SATISFY mode:** `run_sampling()` calls `solver_ctx_set_bias(ctx, ...)` on each delta iteration (line 228), overriding the context bias. But the factors (objective_factor, constraint_factor, etc.) from `set_factors_wrapper()` are never propagated.

### Recommended Fix for v1.1

**Phase 1: Propagate bias/factors to context in run_sampling():**

Add to `run_sampling()` after context creation (after line 195):

```python
# Propagate branching parameters from global to context
# (bridges the gap until Model.solve() is updated to set these on ctx directly)
solver_ctx_set_bias(ctx, BranchingStats.bias)
solver_ctx_set_factors(ctx,
    BranchingStats.objective_factor,
    BranchingStats.constraint_factor,
    BranchingStats.bias_factor,
    BranchingStats.look_factor)
```

This requires exposing `BranchingStats` fields in the Cython declaration, which `branching.pxd` already does (line 17: `cdef BranchingStats_t BranchingStats`).

**Phase 2 (deferred to v1.2): Remove global setters entirely.**

Move bias/factor configuration from `Model.solve()` into `run_sampling()` where the context is available. Remove `set_bias_wrapper()` and `set_factors_wrapper()` calls from `solve()`. This is a breaking change if any user code calls these wrappers directly.

### Backward Compatibility

The deprecated global setters must remain for v1.1 because:
1. External code may call `set_bias_wrapper()` directly
2. `Model.solve()` still uses them
3. The `branching.py` module exposes them as public API

For v1.1: keep globals, add bridging code to propagate global values to context. Add deprecation warnings to `set_bias_wrapper()` etc. For v1.2: remove globals.

---

## Fix Order and Dependencies

```
                    +--------------------+
                    | 4. VLA replacement |  (independent, no deps)
                    +--------------------+

+---------------------+     +-------------------------+
| 1. SATISFY mode     |---->| 2. History callback     |
| crash fix (line 220)|     | per-thread rework       |
+---------------------+     +-------------------------+
         |                            |
         v                            v
+---------------------+     +-------------------------+
| 3. BranchingStats   |     | 5. local_search API     |
| global->ctx bridge  |     | mutex + cleanup         |
+---------------------+     +-------------------------+
```

### Recommended Order

**Step 1: SATISFY mode crash fix**
- Fix: `stpvl = -<int>mod.mod[0].con[0].num_constraints` (line 220)
- Fix: Guard `objective_value` property for SATISFY mode
- Fix: Guard `OptimizeResult` construction for SATISFY mode
- Why first: This is a crash bug. Nothing else can be properly tested in SATISFY mode until this is fixed.
- Risk: LOW. Localized fix, no architectural changes.
- Files: `SearchLib.pyx`, `Model.pyx`

**Step 2: VLA replacement in accept_best_routine**
- Fix: Replace `int64_t remainings[C]` with arena allocation
- Why second: Independent, low risk, easy to verify.
- Risk: LOW. Single location, arena infrastructure already exists.
- Files: `local_search.c`

**Step 3: History callback per-thread rework**
- Fix: Replace module-level `cdef` state with thread-keyed dictionary
- Why third: Depends on SATISFY crash being fixed (the callback reads `global_opt` which behaves differently in SATISFY mode).
- Risk: MEDIUM. Changes callback plumbing that all workers use.
- Files: `SearchLib.pyx`

**Step 4: BranchingStats global-to-context bridge**
- Fix: Propagate global bias/factors to solver context in `run_sampling()` and `run_local_search()`
- Why fourth: Requires understanding the callback rework (step 3) since the callback also reads model state.
- Risk: MEDIUM. Must verify that branching behavior does not change (regression test critical).
- Files: `SearchLib.pyx`, potentially `branching.pxd`

**Step 5: local_search API mutex + cleanup**
- Fix: Add `update_lock` mutex around `global_opt` writes in `accept_best_routine()`
- Fix: Document read/write fields on `local_search()` signature
- Why last: Lowest priority, not a user-facing bug.
- Risk: LOW. Adding mutex is additive.
- Files: `local_search.c`

### Dependency Justification

- Steps 1 and 2 are **fully independent** of each other and can be done in parallel.
- Step 3 depends on Step 1 because the history callback must handle SATISFY mode correctly (no objective value), and testing it requires the SATISFY crash to be fixed.
- Step 4 is logically independent but should follow Step 3 because both touch `run_sampling()` and `run_local_search()` setup code; doing them together would cause merge conflicts.
- Step 5 is fully independent and can be done at any point, but is lowest priority.

---

## Component Boundary Map

```
+------------------------------------------------------------------+
|  Model.pyx                                                        |
|  +-- solve()       : sets params on model_t, launches joblib     |
|  +-- local_search(): sets params on model_t, calls run_local_search|
|  +-- objective_value: reads global_opt.tot_profit * sense         |
|  TOUCHES: Items 1 (SATISFY crash), 3 (BranchingStats via set_bias)|
+--------+-----------------------+---------------------------------+
         |                       |
         v                       v
+------------------+    +------------------+
| SearchLib.pyx    |    | branching.pxd    |
| run_sampling()   |    | set_bias_wrapper |
| run_local_search |    | set_factors_wrap |
| _history_callback|    | (DEPRECATED)     |
| TOUCHES: Items   |    | TOUCHES: Item 4  |
| 1, 2, 3, 4       |    +------------------+
+--------+---------+
         |
         v (nogil)
+------------------------------------------------------------------+
|  C Kernel                                                         |
|  +-- SearchLib.c: ctg() -- OPTIMIZE/SATISFY dispatch             |
|  +-- local_search.c: local_search(), accept_best_routine()       |
|  +-- Branching.c: BranchingStats global, StateProbability()      |
|  +-- solver_ctx.c: solver_ctx_t lifecycle                        |
|  TOUCHES: Items 1 (SATISFY C path), 2 (VLA), 4 (global), 5 (mutex)|
+------------------------------------------------------------------+
```

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| History callback rework breaks existing callback behavior | MEDIUM | Test with user-supplied callback that counts invocations; verify count matches before/after |
| SATISFY mode fix changes stop semantics | LOW | Test SATISFY problems that have known solutions; verify solution found |
| BranchingStats bridge changes solve results | MEDIUM | Run existing benchmarks, compare objective values and iteration counts before/after |
| VLA removal changes behavior | NONE | Pure memory allocation change; identical behavior guaranteed |
| Mutex in local_search adds overhead | NEGLIGIBLE | Mutex is only taken once per neighborhood scan (not per move), and only for a pointer copy |

---

## Sources

- Direct codebase analysis of all listed source files (HIGH confidence)
- `SearchLib.pyx` lines 126-159: history callback implementation
- `SearchLib.pyx` line 220: SATISFY mode crash location
- `local_search.c` line 332: remaining VLA
- `Branching.c` lines 6-21: deprecated global
- `solver_ctx.h/c`: current solver_ctx_t architecture
- `Model.pyx` lines 277-369: solve() method (SATISFY/OPTIMIZE dispatch)
- `Model.pyx` lines 371-417: local_search() method
- `SearchLib.c` lines 89-217: ctg() function (OPTIMIZE/SATISFY C-level dispatch)

---

*Architecture research for: CBQS v1.1 bug fixes and code polish*
*Researched: 2026-02-06*
