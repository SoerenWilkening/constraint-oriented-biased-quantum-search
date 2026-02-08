# Phase 11: Callback Concurrency Rework - Research

**Researched:** 2026-02-08
**Domain:** Thread-safe callback state isolation in Cython/C hybrid system
**Confidence:** HIGH

## Summary

This phase replaces module-level `cdef` callback state in `SearchLib.pyx` with per-solve-call isolation, enabling concurrent `solve()` calls to produce independent, correct history lists. The current architecture uses five module-level globals (`python_callback`, `_history_list`, `_history_prev_best`, `_history_original_callback`, `_history_mod`) that are overwritten by every worker thread, creating a classic shared-mutable-state bug.

The standard approach is to replace these globals with a `threading.get_ident()`-keyed dictionary (a prior decision from STATE.md). When a Joblib worker thread enters `run_sampling()`, it registers its thread ID and a fresh history list in the dict. The C callback, which already acquires the GIL via `with gil:`, looks up the calling thread's ID to find the correct history list. Since the GIL serializes Python execution, no additional locking is needed for the dict lookup.

**Primary recommendation:** Use `threading.get_ident()` keyed dictionary with per-thread `_HistoryState` namedtuple/dataclass entries. The GIL provides all necessary synchronization for the Python-level dict. Keep the C-level `update_lock` mutex for `global_opt` updates. Merge worker histories in `Model.solve()` by collecting per-thread lists after all workers complete.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### History semantics
- Each history entry is a tuple: (value, elapsed_seconds) -- value is objective for OPTIMIZE, constraint satisfaction count for SATISFY
- Only record improvements: append when value is strictly better than last entry (convergence staircase, not full activity log)
- Unlimited history length -- no cap needed since improvements-only keeps it small
- SATISFY mode format: (satisfaction_count, elapsed_seconds) -- consistent tuple pattern across modes
- Empty history is valid when no improvements occur during solve

#### Concurrency model
- Primary use case: parameter sweeps (same model structure, different params in parallel via ThreadPoolExecutor)
- Same Model instance must support concurrent solve() calls (e.g., different seeds simultaneously) -- each call gets independent history

#### Error & edge cases
- Partial history returned on stop/timeout -- whatever was collected before stopping is included in OptimizeResult
- Callback exceptions: silent drop -- log warning, skip entry, continue solving (history may be incomplete but solve not ruined)
- Immediate cleanup: per-thread/per-solve history state removed right after solve returns (no stale data, predictable memory)
- Empty history is valid (no guarantee of at least one entry)

#### Deprecation strategy
- New API: solve(track_history=True) opt-in parameter -- zero overhead when not tracking
- Old module-level callback: silent redirect to new mechanism (no warning, no breakage, v1.1 zero-breaking-change constraint)
- History access: OptimizeResult.history -- per-solve ownership, no global state
- When track_history=False (default): OptimizeResult.history returns empty list [] (safe to iterate without checking)

### Claude's Discretion
- Thread ID vs solve-call ID for state isolation (based on GIL/C solver analysis)
- Worker thread history: orchestrator-only vs merged
- Internal data structures for thread-safe history collection
- Exact timestamp source (monotonic clock preferred)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

This phase does not introduce new external libraries. All work uses existing Python stdlib, Cython, and C facilities.

### Core
| Library/Tool | Version | Purpose | Why Standard |
|---|---|---|---|
| `threading` (Python stdlib) | 3.13+ | `get_ident()` for thread identification | Part of Python; reliable, zero-overhead thread ID |
| `time.monotonic()` | Python 3.3+ | Monotonic clock for elapsed time measurement | Cannot go backwards; immune to NTP adjustments |
| `logging` (Python stdlib) | 3.13+ | Warning on callback exceptions | Standard Python logging; no external deps |
| `pthread_mutex` (C) | POSIX | Existing `update_lock` for `global_opt` protection | Already in use in SearchLib.c |

### Supporting
| Library/Tool | Version | Purpose | When to Use |
|---|---|---|---|
| `concurrent.futures.ThreadPoolExecutor` | 3.13+ | External concurrent solve calls | User-facing parameter sweeps |
| `joblib.Parallel` | Existing | Internal worker thread pool | Already used in `Model.solve()` |
| CMocka | 1.1.7 | C-level thread safety tests | Existing test infrastructure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|---|---|---|
| `threading.get_ident()` dict | Unique solve-call UUID | UUID adds allocation overhead per callback; thread ID is free. Thread ID works because Joblib threading backend assigns distinct OS threads. |
| Python dict for state | `threading.local()` | `threading.local()` is simpler but harder to clean up and harder to test. Dict gives explicit lifecycle control. |
| Python-level history tracking | C-level history array in solver_ctx_t | C-level would avoid GIL overhead entirely but requires marshalling to Python. Current callback is already GIL-serialized, so no gain. |

## Architecture Patterns

### Current Architecture (PROBLEM)

```
Model.solve()
  |
  +--> Parallel(n_jobs=num_workers, backend="threading")
         |
         +--> run_sampling(self, callback, not_stop)  [Thread 1]
         |      |
         |      +--> Sets MODULE-LEVEL globals:
         |      |      _history_list = []          <-- RACE: all threads overwrite
         |      |      _history_prev_best = None   <-- RACE: all threads overwrite
         |      |      _history_mod = mod          <-- RACE: all threads overwrite
         |      |      python_callback = _history_callback_fn
         |      |
         |      +--> with nogil: ctg(ctx, mod_ptr, stt, cb_ptr, ...)
         |             |
         |             +--> pthread_mutex_lock(&update_lock)
         |             |     if better: callback()  --> my_callback_c() with gil
         |             |                                  --> python_callback()  [reads module globals]
         |             +--> pthread_mutex_unlock(&update_lock)
         |
         +--> run_sampling(self, callback, not_stop)  [Thread 2]
                |
                +--> OVERWRITES SAME MODULE GLOBALS  <-- history cross-contaminated
```

**Key problems:**
1. All `num_workers` threads write to the same `_history_list` -- last to set it before `nogil` "wins"
2. `_history_prev_best` is shared -- improvements are compared against wrong baseline
3. The `update_lock` mutex + GIL serializes callback execution but does NOT isolate state
4. After `ctg()` returns, `list(_history_list)` captures whatever is in the global at that moment

### Target Architecture (SOLUTION)

```
Module-level in SearchLib.pyx:
  _solve_states = {}   # dict[int, _SolveState] keyed by threading.get_ident()
  _solve_lock = threading.Lock()  # protects dict mutation only

Model.solve()
  |
  +--> Parallel(n_jobs=num_workers, backend="threading")
         |
         +--> run_sampling(self, callback, not_stop)  [Thread 1, tid=1001]
         |      |
         |      +--> _solve_states[1001] = _SolveState(
         |      |        history=[], prev_best=None, mod=mod,
         |      |        original_callback=callback, start_time=monotonic())
         |      |
         |      +--> with nogil: ctg(ctx, mod_ptr, stt, cb_ptr, ...)
         |             |
         |             +--> callback() --> my_callback_c() with gil
         |                     |
         |                     +--> tid = threading.get_ident()
         |                     +--> state = _solve_states[tid]
         |                     +--> state.history.append(...)  [ISOLATED]
         |
         +--> run_sampling(self, callback, not_stop)  [Thread 2, tid=1002]
                |
                +--> _solve_states[1002] = _SolveState(...)  [INDEPENDENT]
```

**Why this works:**
1. Each Joblib worker thread has a unique `threading.get_ident()` (OS thread IDs)
2. Dict registration happens with GIL held (before `with nogil:`)
3. Callback lookup happens with GIL held (`with gil:` in `my_callback_c`)
4. GIL serializes all Python operations, so no race on `_solve_states` dict
5. Cleanup: `del _solve_states[tid]` in `finally:` block after capturing history

### Pattern 1: Per-Thread State Registration

**What:** Register a state object keyed by thread ID before entering nogil, look it up in callback.
**When to use:** When C code calls back into Python via GIL-acquiring callbacks and you need per-caller isolation.

```python
# In SearchLib.pyx
import threading

# Module-level state dict (replaces individual cdef globals)
_solve_states = {}  # dict[int, _SolveState]

class _SolveState:
    """Per-thread/per-solve callback state."""
    __slots__ = ('history', 'prev_best', 'mod', 'original_callback',
                 'start_time', 'mode')

    def __init__(self, mod, original_callback, start_time, mode):
        self.history = []
        self.prev_best = None
        self.mod = mod
        self.original_callback = original_callback
        self.start_time = start_time
        self.mode = mode

def _history_callback_fn():
    """Thread-safe callback: looks up state by thread ID."""
    tid = threading.get_ident()
    state = _solve_states.get(tid)
    if state is None:
        return  # No state registered (shouldn't happen)

    try:
        if state.mode == SATISFY:
            # Count satisfied constraints
            value = _compute_satisfaction_count(state.mod)
        else:
            value = state.mod.mod[0].global_opt[0].tot_profit * state.mod.sense

        elapsed = time.monotonic() - state.start_time

        if state.prev_best is None or value != state.prev_best:
            state.history.append((value, elapsed))
            state.prev_best = value
    except Exception:
        import logging
        logging.warning("History callback exception (skipped)", exc_info=True)

    if state.original_callback is not None:
        state.original_callback()
```

### Pattern 2: History Format Change

**What:** Change from 4-tuple `(iteration, obj_val, elapsed_ms, is_feasible)` to 2-tuple `(value, elapsed_seconds)`.
**When to use:** This is a locked decision from CONTEXT.md.

```python
# Current format (to be replaced):
# (iteration, objective_value, elapsed_ms, is_feasible)

# New format (from CONTEXT.md):
# (value, elapsed_seconds)
# - OPTIMIZE mode: value = objective_value (sign-corrected)
# - SATISFY mode: value = satisfaction_count (number of satisfied constraints)
# - elapsed_seconds (float, from time.monotonic())
```

**Impact on OptimizeResult:** The `history` field changes from 4-tuple to 2-tuple. The `OptimizeResult` class, `summary()`, `to_dict()`, and all tests need updating. Since this is accessed via `OptimizeResult.history` (which is a new-ish field), and the old format was only introduced recently, the breakage is minimal.

### Pattern 3: track_history Opt-In

**What:** Add `track_history=True` parameter to `solve()` and `local_search()` for zero-overhead when not tracking.
**When to use:** Always -- gives users control over overhead.

```python
# In Model.pyx solve():
def solve(self, ..., track_history=True):
    ...
    res = Parallel(n_jobs=num_workers, backend="threading")(
        delayed(run_sampling)(self, callback, not_stop, track_history) for _ in range(num_workers)
    )
    ...
    if track_history:
        merged_history = []
        for r in res:
            merged_history.extend(r[6])
        merged_history.sort(key=lambda entry: entry[1])  # sort by elapsed_seconds
    else:
        merged_history = []
```

### Anti-Patterns to Avoid

- **Passing history list through C**: The C `callback_t` is `void (*)(void)` -- no parameters. Cannot pass data through C. Must use Python-level state lookup.
- **Using `threading.local()`**: Harder to clean up, harder to test, and the state must be accessible from a different code path (the callback function) than where it's created (run_sampling).
- **Changing C callback signature**: Would break the entire C kernel API. The `callback_t` typedef is deeply embedded.
- **Using module-level cdef objects for per-thread state**: `cdef` objects cannot be dict values easily. Use plain Python classes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Thread identification | Custom ID generation | `threading.get_ident()` | OS-level unique, zero cost, already available |
| Monotonic timestamps | `time.time()` differences | `time.monotonic()` | Immune to clock adjustments, guaranteed non-decreasing |
| Thread-safe dict access | Custom locking around dict | Python GIL | Dict operations are atomic under GIL; callback has GIL via `with gil:` |
| Worker thread pool | Custom pthread pool | Joblib Parallel (existing) | Already handles thread lifecycle, error propagation |
| Exception logging | Print statements | `logging.warning()` | Standard, suppressible, structured |

**Key insight:** The GIL is the primary synchronization mechanism here. Since `my_callback_c()` uses `with gil:` to call Python, and dict operations are atomic under the GIL, no additional locking is needed for the history state dict itself. The only lock needed is the existing C-level `update_lock` for `global_opt` updates.

## Common Pitfalls

### Pitfall 1: Callback Under Mutex Deadlock Risk

**What goes wrong:** The C callback is currently called inside `pthread_mutex_lock(&update_lock)`. The callback then acquires the GIL (`with gil:`). If another thread holds the GIL and tries to acquire `update_lock`, classic deadlock occurs.
**Why it happens:** Lock ordering violation (mutex -> GIL in one thread, GIL -> mutex in another).
**How to avoid:** This is the *existing* behavior and has not deadlocked in practice because: (1) Joblib worker threads release the GIL via `with nogil:` before entering `ctg()`, (2) The only GIL acquisition inside `ctg()` is the callback itself, (3) No Python code acquires `update_lock`. Do NOT introduce any Python code that acquires `update_lock`.
**Warning signs:** Hangs during concurrent solve with no CPU usage.

### Pitfall 2: Thread ID Reuse Between Solve Calls

**What goes wrong:** If `_solve_states` is not cleaned up in `finally:`, stale entries accumulate. Thread IDs can be reused by the OS, leading to incorrect state lookup.
**Why it happens:** Missing cleanup in error paths.
**How to avoid:** Always clean up in `finally:` block. Use `_solve_states.pop(tid, None)` to safely remove.
**Warning signs:** History lists growing across multiple solve calls, stale data appearing.

### Pitfall 3: History Format Inconsistency Between Modes

**What goes wrong:** OPTIMIZE mode returns objective values but SATISFY mode needs satisfaction counts. If the callback reads the wrong field, history entries are meaningless.
**Why it happens:** The C `global_opt` struct stores `tot_profit` which means different things in each mode.
**How to avoid:** Check `mod.mod[0].solver` in the callback and compute the appropriate value:
- OPTIMIZE: `mod.mod[0].global_opt[0].tot_profit * mod.sense`
- SATISFY: Count of satisfied constraints = `mod.mod[0].con[0].num_constraints + mod.mod[0].global_opt[0].tot_profit` (since `tot_profit` is negative constraint count)
**Warning signs:** SATISFY mode history contains large negative numbers instead of counts 0..N.

### Pitfall 4: Worker Thread History Merging

**What goes wrong:** After Joblib workers complete, histories from different threads have overlapping timestamps that don't reflect a single timeline.
**Why it happens:** Each worker has its own `start_time` but they all start at approximately the same wall-clock time.
**How to avoid:** Use a shared `start_time` set before `Parallel(...)` call. Pass it to `run_sampling()` so all workers compute elapsed time relative to the same origin.
**Warning signs:** Merged history has entries that appear out of order or with duplicate timestamps.

### Pitfall 5: track_history=False Still Pays Callback Overhead

**What goes wrong:** Even when `track_history=False`, the C callback still fires (because C doesn't know about `track_history`).
**Why it happens:** The C callback pointer is always set.
**How to avoid:** When `track_history=False` and no user callback is provided, pass `NULL` as the callback pointer to C. Only set up the callback machinery when actually needed.
**Warning signs:** No performance difference between `track_history=True` and `False`.

### Pitfall 6: Changing OptimizeResult.history Format is a Breaking Change

**What goes wrong:** Existing user code that unpacks 4-tuples from history breaks with the new 2-tuple format.
**Why it happens:** History format change from `(iteration, obj_val, elapsed_ms, is_feasible)` to `(value, elapsed_seconds)`.
**How to avoid:** The v1.1 constraint says "no breaking changes". However, the history format was only recently introduced (not in any published release). Verify whether any user-facing documentation or tests depend on the 4-tuple format. If so, either keep backward compatibility or document the change clearly in release notes.
**Warning signs:** Test failures in `test_result_py.py` when checking history tuple length.

## Code Examples

### Example 1: Thread-Safe State Registration Pattern

```python
# SearchLib.pyx - Module level
import threading
import time as time_mod
import logging

_solve_states = {}  # {thread_id: _SolveState}

class _SolveState:
    __slots__ = ('history', 'prev_best', 'mod', 'original_callback',
                 'start_time', 'mode')
    def __init__(self, mod, original_callback, start_time, mode):
        self.history = []
        self.prev_best = None
        self.mod = mod
        self.original_callback = original_callback
        self.start_time = start_time
        self.mode = mode
```

### Example 2: Updated Callback Function

```python
def _history_callback_fn():
    """Thread-safe history callback using per-thread state."""
    tid = threading.get_ident()
    state = _solve_states.get(tid)
    if state is None:
        return

    try:
        cdef Model mod = state.mod
        elapsed = time_mod.monotonic() - state.start_time

        if state.mode == SATISFY:
            # satisfaction_count = num_constraints - violations
            num_con = mod.mod[0].con[0].num_constraints
            tot_profit = mod.mod[0].global_opt[0].tot_profit
            value = num_con + tot_profit  # tot_profit is negative
        else:
            value = mod.mod[0].global_opt[0].tot_profit * mod.sense

        if state.prev_best is None or value != state.prev_best:
            state.history.append((value, elapsed))
            state.prev_best = value
    except Exception:
        logging.warning("CBQS: history callback exception (entry skipped)",
                        exc_info=True)

    if state.original_callback is not None:
        try:
            state.original_callback()
        except Exception:
            logging.warning("CBQS: user callback exception",
                            exc_info=True)
```

### Example 3: Registration in run_sampling

```python
cpdef run_sampling(Model mod, object callback, not_stop, bint track_history):
    import threading

    # ... existing setup code ...

    cdef callback_t cb_ptr
    if track_history or callback is not None:
        cb_ptr = <callback_t> my_callback_c
    else:
        cb_ptr = NULL  # No callback overhead

    if track_history:
        tid = threading.get_ident()
        solve_start = time_mod.monotonic()
        mode = mod.mod[0].solver
        _solve_states[tid] = _SolveState(mod, callback, solve_start, mode)

    try:
        with nogil:
            feasible = ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent)

        if track_history:
            history = list(_solve_states[tid].history)
        else:
            history = []

        # ... rest of function ...
        return cur_sol, qtg_apps, feasible, arr, t_total, incumb, history, preprocess_ms
    finally:
        if track_history:
            _solve_states.pop(threading.get_ident(), None)
        solver_ctx_free(ctx)
```

### Example 4: Updated Model.solve() with track_history

```python
def solve(self, ..., track_history=True):
    # ... existing setup ...

    res = Parallel(n_jobs=num_workers, backend="threading")(
        delayed(run_sampling)(self, callback, not_stop, track_history)
        for _ in range(num_workers)
    )

    # History merging
    if track_history:
        merged_history = []
        for r in res:
            merged_history.extend(r[6])
        merged_history.sort(key=lambda entry: entry[1])  # sort by elapsed_seconds
    else:
        merged_history = []

    result = OptimizeResult(
        ...,
        history=merged_history,
        ...
    )
    return result
```

### Example 5: Concurrent Solve Test

```python
def test_concurrent_solve_independent_histories():
    """Two concurrent solves on same Model get independent histories."""
    from concurrent.futures import ThreadPoolExecutor

    m = create_simple_model()
    m.close()
    m.general_greedy()

    results = []
    def solve_with_seed(seed):
        m2 = copy(m)
        m2.seed = seed
        return m2.solve(M=100, stopping_time=5, num_workers=1,
                        track_history=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(solve_with_seed, s) for s in [1, 2]]
        results = [f.result() for f in futures]

    # Each result has its own history (no cross-contamination)
    assert isinstance(results[0].history, list)
    assert isinstance(results[1].history, list)
    # History entries are 2-tuples
    if results[0].history:
        assert len(results[0].history[0]) == 2
```

## Discretion Recommendations

### Thread ID vs Solve-Call ID

**Recommendation: Use `threading.get_ident()`** (thread ID keying)

**Rationale:**
1. **Joblib threading backend** creates actual OS threads, each with a unique `threading.get_ident()`.
2. **GIL behavior**: The C solver runs with `nogil`. When the C callback fires, it acquires the GIL via `with gil:`. At this point, `threading.get_ident()` returns the ID of the thread that is executing the callback -- which is the same thread that registered the state.
3. **Zero allocation cost**: `threading.get_ident()` is a simple integer read, no object creation.
4. **Solve-call UUID** would require generating a UUID per solve, passing it through C (impossible with `void (*)(void)` callback signature), or storing it in a thread-local variable (which is just thread ID with extra steps).

**Edge case**: If a user were to use async/await with a single thread, multiple solve calls could interleave on the same thread. However, this cannot happen because `with nogil:` blocks the Python thread for the duration of the C solve. So only one `solve()` can be active per thread.

### Worker Thread History: Merged

**Recommendation: Merge all worker histories into a single sorted list**

**Rationale:**
1. **Current behavior**: `Model.solve()` already merges histories from all Joblib workers (line 334-336 in Model.pyx: `merged_history.extend(r[6])`; `merged_history.sort(key=...)`).
2. **Worker threads see global_opt improvements**: The C callback in `ctg()` fires when a worker finds a better solution than the current `global_opt`. Since all workers share the same `model_t` and `global_opt`, they all compete to improve the same global optimum. History entries from different workers represent genuine improvements to the shared optimum.
3. **Orchestrator-only** would lose visibility into which workers found improvements and when.
4. **Shared start_time**: All workers should use the same `start_time` (set before `Parallel(...)`) so elapsed times are comparable when merged.

**Implementation**: Pass `solve_start_time` as a parameter to `run_sampling()`. Each worker uses this shared origin for elapsed time computation.

### Internal Data Structures

**Recommendation: Plain Python dict with `_SolveState` class**

```python
class _SolveState:
    __slots__ = ('history', 'prev_best', 'mod', 'original_callback',
                 'start_time', 'mode')
```

**Rationale:**
1. **GIL protects dict**: All dict operations happen with GIL held (before `nogil` and in `with gil:` callback). No additional lock needed.
2. **`__slots__` for memory efficiency**: Each solve spawns up to `num_workers` state objects. `__slots__` avoids per-instance `__dict__`.
3. **Plain class over namedtuple**: Need mutability for `prev_best` and `history` (append).
4. **Not a cdef class**: Must be storable in a regular Python dict and accessible from a regular `def` function (the callback).

### Timestamp Source

**Recommendation: `time.monotonic()` (Python)**

**Rationale:**
1. **Monotonic guarantee**: Cannot go backwards due to NTP adjustments.
2. **Consistent with existing code**: `preprocess_start = time_mod.monotonic()` is already used in `run_sampling()`.
3. **Python-level sufficiency**: The callback acquires the GIL anyway, so there's no benefit to using C-level `clock_gettime(CLOCK_MONOTONIC)`.
4. **Resolution**: `time.monotonic()` provides sub-microsecond resolution on Linux, more than sufficient for improvement tracking.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Module-level `cdef` globals | Per-thread state dict | This phase | Enables concurrent solve with independent histories |
| 4-tuple history entries | 2-tuple (value, elapsed_seconds) | This phase | Simpler format, consistent across OPTIMIZE/SATISFY |
| Always-on history | `track_history=True` opt-in | This phase | Zero overhead when not tracking |
| `time.time()` for elapsed | `time.monotonic()` for elapsed | This phase | Immune to clock adjustments |

## Open Questions

1. **`update_lock` scope for concurrent Model instances**
   - What we know: `update_lock` is a single global `pthread_mutex_t` in `SearchLib.c`. All concurrent `ctg()` calls share it, even across different `Model` instances.
   - What's unclear: Whether the global mutex creates contention when truly independent Model instances solve concurrently (parameter sweeps).
   - Recommendation: Keep the global mutex for now. It only serializes the `global_opt` comparison+copy+callback, which is fast. Per-model mutexes would require passing the mutex through the C API, which is a larger change. Document as a known limitation.

2. **History format backward compatibility**
   - What we know: Current format is `(iteration, obj_val, elapsed_ms, is_feasible)`. New format is `(value, elapsed_seconds)`. Tests in `test_result_py.py` use the 4-tuple format.
   - What's unclear: Whether any external users depend on the 4-tuple format.
   - Recommendation: Since the library is v1.0.1 and history was recently added, treat the format change as acceptable. Update all tests. The new format is cleaner and matches the CONTEXT.md decision.

3. **SATISFY mode satisfaction count computation**
   - What we know: In SATISFY mode, `global_opt.tot_profit` equals negative violation count (e.g., -3 means 3 constraints violated). The total number of constraints is `mod.con.num_constraints`. So `satisfaction_count = num_constraints + tot_profit` (since tot_profit is negative).
   - What's unclear: Whether this calculation is correct in all edge cases (partial constraint satisfaction, equality constraints).
   - Recommendation: Verify with existing SATISFY mode tests. The formula `num_constraints + tot_profit` should give 0 when all constraints are violated and `num_constraints` when all are satisfied.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of:
  - `cbqs/SearchLib.pyx` (lines 123-269) -- callback mechanism and module-level state
  - `cbqs/SearchLib.pxd` (lines 1-68) -- C function declarations, callback_t typedef
  - `cbqs/Model.pyx` (lines 277-380) -- solve() with Parallel and history merging
  - `cbqs/src/SearchLib.c` (lines 88-216) -- ctg() with update_lock and callback invocation
  - `cbqs/src/solver_ctx.h/c` -- solver context lifecycle and thread safety
  - `cbqs/src/definitions.h` -- callback_t typedef, CBQS_THREAD_LOCAL macro
  - `cbqs/src/local_search.c` (lines 492-571) -- local_search callback invocation pattern
  - `cbqs/result.py` -- OptimizeResult structure and history handling
  - `tests/test_result_py.py` -- existing history format tests
  - `tests/test_determinism.py` -- existing thread isolation tests
  - `tests/test_thread_safety.c` -- C-level thread safety tests
  - `.github/workflows/test.yml` -- CI configuration including TSan
  - `.planning/STATE.md` -- prior decisions including threading.get_ident() keying

### Secondary (MEDIUM confidence)
- Python `threading` module documentation: `get_ident()` returns a unique non-zero integer for each active thread
- Python GIL semantics: dict operations are atomic under GIL, `with gil:` in Cython acquires GIL before executing Python code
- Joblib threading backend: uses Python `threading.Thread` objects, which map to OS threads

### Tertiary (LOW confidence)
- None -- all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all stdlib/existing
- Architecture: HIGH -- based on direct codebase analysis and understanding of GIL/callback interaction
- Pitfalls: HIGH -- identified through code tracing and understanding of threading model
- Discretion recommendations: HIGH -- based on analysis of actual callback invocation path and GIL behavior

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable domain, no external dependencies changing)
