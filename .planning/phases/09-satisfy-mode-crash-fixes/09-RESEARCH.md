# Phase 9: SATISFY Mode Crash Fixes - Research

**Researched:** 2026-02-06
**Domain:** Cython/C solver interface, SATISFY mode bug fixes
**Confidence:** HIGH

## Summary

Phase 9 addresses four related bugs that make SATISFY mode completely non-functional in the Python API. The bugs span two files (`SearchLib.pyx` and `Model.pyx`) plus the `OptimizeResult` container (`result.py`). All four bugs are well-understood from direct code inspection -- no external research was needed because these are internal implementation bugs in the three-layer architecture (Python API -> Cython middleware -> C kernel).

The root cause is that SATISFY mode was never properly integrated into the post-v1.0 OptimizeResult pipeline. The C kernel's `ctg()` function handles SATISFY correctly, but the Cython wrapper (`run_sampling` in `SearchLib.pyx`) and the Python model (`Model.pyx`) both assume OPTIMIZE mode throughout.

**Primary recommendation:** Fix all four bugs in a single coordinated pass through `SearchLib.pyx`, `Model.pyx`, and `result.py`, with SATISFY-mode-specific tests validating each fix. The fixes are small, localized, and low-risk.

## Standard Stack

No new libraries or dependencies needed. This phase modifies only existing project files:

### Core Files to Modify

| File | Lines | What Changes |
|------|-------|-------------|
| `cbqs/SearchLib.pyx` | ~220, ~233-236 | Fix `len()` TypeError on scalar; replace `signal.raise_signal(SIGINT)` with `solver_ctx_request_stop(ctx)` |
| `cbqs/Model.pyx` | ~354-368, ~466-468 | `objective_value` returns `None` in SATISFY mode; `solve()` passes `None` objective to `OptimizeResult` in SATISFY mode |
| `cbqs/result.py` | ~78-90 | Handle `None` objective in `OptimizeResult` (repr, summary, to_dict) |
| `cbqs/SearchLib.pyx` | ~143-159 | History callback records feasibility-based entries in SATISFY mode |

### Test Files

| File | Purpose |
|------|---------|
| `tests/test_model_py.py` | Add SATISFY-mode solve integration tests |
| `tests/test_result_py.py` | Add tests for `None`-objective OptimizeResult |

## Architecture Patterns

### Bug Analysis: CRASH-01 (TypeError on len() of uint32_t)

**Location:** `cbqs/SearchLib.pyx:220`

**Current code:**
```python
stpvl = -len(mod.mod[0].con[0].num_constraints)
```

**Problem:** `mod.mod[0].con[0].num_constraints` is a `uint32_t` scalar (defined in `cbqs/src/constraint.h:34`), not a sequence. Calling `len()` on a scalar raises `TypeError: object of type 'int' has no len()`.

**C equivalent (correct):** In `cbqs/src/SearchLib.c:194`:
```c
cur_sol->tot_profit == - (int64_t) mod->con->num_constraints
```
The C code directly negates the scalar value.

**Fix:** Replace `len(...)` with direct access:
```python
stpvl = -mod.mod[0].con[0].num_constraints
```

**Note on Cython type mapping:** The Cython declaration in `Constraint.pxd:7` declares `num_constraints` as `size_t`, but the C header uses `uint32_t`. This discrepancy is not a runtime issue (Cython handles the implicit cast), but the `len()` call is unambiguously wrong regardless.

**Confidence:** HIGH -- Direct code inspection confirms the bug.

### Bug Analysis: CRASH-02 (signal.raise_signal(SIGINT) instead of solver_ctx_request_stop)

**Location:** `cbqs/SearchLib.pyx:234-236`

**Current code:**
```python
if stt.tot_profit == stpvl:
    not_stop[0] = 0
    t_total = time.time() - t_start
    signal.raise_signal(signal.SIGINT)
    break
```

**Problem:** When the SATISFY solver finds a complete solution (all constraints satisfied), it raises a real SIGINT signal. This:
1. Terminates all parallel workers (not just the one that found the solution)
2. Can crash the Python process or trip the user's own signal handlers
3. Is the wrong mechanism now that `solver_ctx_t` exists with `solver_ctx_request_stop()`

**C-level behavior:** The C `ctg()` function in `SearchLib.c:131-214` already uses the `solver_ctx_request_stop` pattern via signal handlers (lines 48-57). The signal handler calls `solver_ctx_request_stop(g_active_ctx)`. But the Python-level code at line 236 bypasses this clean mechanism entirely.

**Fix:** Replace `signal.raise_signal(signal.SIGINT)` with `solver_ctx_request_stop(ctx)`:
```python
if stt.tot_profit == stpvl:
    not_stop[0] = 0
    t_total = time.time() - t_start
    solver_ctx_request_stop(ctx)
    break
```

This is safe because:
- `ctx` is already available in `run_sampling`'s scope (created at line 184)
- `solver_ctx_request_stop` is already declared in `SearchLib.pxd:21`
- The `break` after it already exits the delta loop
- Other workers will see the stop flag via `solver_ctx_should_stop(ctx)` -- actually, each worker has its own `ctx`. The `not_stop[0] = 0` list (shared across workers) is the cross-worker stop mechanism. So the fix is correct: set `not_stop[0] = 0` (stops other workers at their loop check) + `solver_ctx_request_stop(ctx)` (stops this worker's C-level loop) + `break` (exits the Python-level delta loop).

**Important detail:** Each worker has its OWN `solver_ctx_t` (created at `SearchLib.pyx:184` inside `run_sampling`). So `solver_ctx_request_stop(ctx)` only stops the current worker's C loop. The `not_stop[0] = 0` mechanism (a shared Python list) is what stops OTHER workers, and that's already in place at line 234.

**Confidence:** HIGH -- Direct code inspection + understanding of v1.0 solver_ctx architecture.

### Bug Analysis: CRASH-03 (objective_value returns meaningless number in SATISFY mode)

**Location:** `cbqs/Model.pyx:466-468`

**Current code:**
```python
@property
def objective_value(self):
    return self.mod[0].global_opt[0].tot_profit * self.sense
```

**Problem:** In SATISFY mode:
- `self.sense` defaults to `MAXIMIZE = -1` (set in `__init__` at line 96, never changed because `set_objective()` is never called)
- `tot_profit` holds the negative violation count (e.g., `-5` for 5 unsatisfied constraints out of total)
- So `objective_value` returns `(-5) * (-1) = 5`, which is a meaningless number to the user

The C kernel uses `tot_profit` internally for SATISFY mode to track constraint satisfaction progress (negated count of total constraints -> 0 as constraints get satisfied, with the stop condition at `-(int64_t)num_constraints` meaning all satisfied). This internal representation should never leak to the user as an "objective value."

**Fix:** Check `self.mod[0].solver` and return `None` in SATISFY mode:
```python
@property
def objective_value(self):
    if self.mod[0].solver == SATISFY:
        return None
    return self.mod[0].global_opt[0].tot_profit * self.sense
```

**Downstream impact:** This changes `objective_value` from always returning a number to sometimes returning `None`. Callers:
1. `Model.solve()` line 356: `objective=self.objective_value` -- passes `None` to `OptimizeResult`
2. `Model.local_search()` line 403: same
3. `Model.__str__()` line 140: `f"Found solution with Objective = {self.objective_value}"` -- would print `None`, acceptable
4. `Model.verify_solution()` line 571-573: compares `recomputed_obj` with `reported_obj` -- needs SATISFY guard
5. `_history_callback_fn` line 151: `mod.mod[0].global_opt[0].tot_profit * mod.sense` -- independent access, addressed in CRASH-04

**Confidence:** HIGH -- Direct code inspection.

### Bug Analysis: CRASH-04 (OptimizeResult and history in SATISFY mode)

**Location:** `cbqs/result.py`, `cbqs/SearchLib.pyx:143-159`, `cbqs/Model.pyx:354`

**Problem 1: OptimizeResult with None objective**
`OptimizeResult.__init__` stores `self.objective = objective` directly (line 80). If `None` is passed:
- `__repr__` line 108: `f"obj={self.objective}"` -- prints `obj=None`, acceptable
- `summary()` line 137: `f"  objective: {self.objective}"` -- prints `objective: None`, acceptable
- `to_dict()` line 222: `"objective": self.objective` -- serializes as `null`, acceptable
- `int(seed)` coercion in `__init__` line 90 -- not affected
- There's no coercion on `self.objective` at line 80, so `None` passes through cleanly

**Verdict:** `OptimizeResult` already handles `None` objective correctly with minimal changes. The `__repr__` and `summary()` output is reasonable. No code changes needed in `result.py` for basic None support.

**However**, the `summary()` should ideally note that this is a SATISFY solve. Consider adding a `mode` field or adjusting the objective display. This is an enhancement, not a requirement.

**Problem 2: History callback records objective-based values in SATISFY mode**

In `_history_callback_fn` (SearchLib.pyx:151):
```python
obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
```

In SATISFY mode, `tot_profit` tracks violation count progress (negative). Multiplied by `sense = -1`, it becomes a positive number that means nothing to the user. History entries should instead report feasibility progress.

**What SATISFY history should report:** The history tuple format is `(iteration, objective_value, elapsed_ms, is_feasible)`. For SATISFY mode:
- `objective_value` field should be `None` (there is no objective in SAT)
- `is_feasible` is already correctly computed from `mod.mod[0].global_opt[0].feasible`
- Alternatively, report constraint satisfaction count (how many constraints are satisfied out of total)

**Recommended approach for history:** In SATISFY mode, replace `obj_val` with `None` in history tuples:
```python
if mod.mod[0].solver == SATISFY:
    obj_val = None
else:
    obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
```

This keeps the tuple format consistent while signaling that objective is not applicable.

**Problem 3: verify_solution() in SATISFY mode**

`Model.verify_solution()` at line 568-579 compares recomputed vs. reported objective:
```python
recomputed_obj = self.objective.eval_obj(st) * self.sense
reported_obj = self.objective_value
```

In SATISFY mode:
- `self.objective` is an empty `new_constraint()` (no objective expressions added)
- `eval_obj` on an empty constraint set may return 0 or garbage
- `self.objective_value` now returns `None`
- Comparison `abs(None - 0) > EPSILON` would raise `TypeError`

**Fix:** Skip objective verification in SATISFY mode:
```python
if self.mod[0].solver != SATISFY:
    recomputed_obj = self.objective.eval_obj(st) * self.sense
    reported_obj = self.objective_value
    EPSILON = 1e-9
    if abs(recomputed_obj - reported_obj) > EPSILON:
        ...
```

**Confidence:** HIGH -- All issues identified through direct code inspection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-worker stop signaling | Custom signal handler for Python | `not_stop[0] = 0` (already exists) + `solver_ctx_request_stop()` | v1.0 already built the right mechanism; just use it |
| History format for SATISFY | New history tuple format | Same tuple format with `None` for objective | Keeps OptimizeResult format stable, no breaking changes |
| SATISFY mode detection | Runtime type checks | `self.mod[0].solver == SATISFY` (C-level field) | Already available, no new infrastructure needed |

## Common Pitfalls

### Pitfall 1: Type mismatch between Cython and C declarations

**What goes wrong:** `Constraint.pxd` declares `num_constraints` as `size_t` but `constraint.h` declares it as `uint32_t`. While Cython handles this implicitly, it can cause subtle issues with signedness and overflow on 32-bit platforms.

**Why it happens:** The Cython `.pxd` file was written to mirror the C header but used Pythonic `size_t` instead of exact `uint32_t`.

**How to avoid:** When fixing CRASH-01, use a direct integer cast or rely on Cython's automatic conversion. Do NOT try to fix the `.pxd` type mismatch in this phase -- that's a broader cleanup task.

**Warning signs:** Type casting warnings during Cython compilation.

### Pitfall 2: Breaking the solve() return contract

**What goes wrong:** Changing `objective_value` to return `None` could break user code that does `result.objective > 0` without checking for SATISFY mode.

**Why it happens:** The v1.0 API never formally supported SATISFY mode (it crashed), so no user code should depend on SATISFY objective values. But defensive coding says to document the change.

**How to avoid:** This is acceptable because SATISFY mode was completely broken before (crashed on line 220). Any code that "worked" with SATISFY was getting wrong results. Returning `None` is a cleaner contract.

**Warning signs:** If any existing tests check `objective_value` in SATISFY mode (none do currently).

### Pitfall 3: History callback fires during SATISFY solve

**What goes wrong:** In SATISFY mode, the C-level callback fires when `mod->global_opt->feasible && callback` (SearchLib.c:188-189). This means the callback only fires ONCE when feasibility is first achieved, not on every improvement step. History will have at most one entry.

**Why it happens:** The SATISFY solver in `ctg()` updates `global_opt` only when `global_opt->tot_profit > cur_sol->tot_profit` (line 185), which tracks the violation count. The callback is guarded by `global_opt->feasible`, so it only fires when the first feasible solution is found.

**How to avoid:** Understand that SATISFY history will typically have 0 or 1 entries. This is correct behavior -- there's no "improvement" concept in pure SAT, only "found solution" or "didn't." The history callback for SATISFY richer tracking is deferred to Phase 11 (CB-03).

### Pitfall 4: The not_stop mechanism is a shared Python list

**What goes wrong:** The `not_stop = [1]` list is shared across all workers via joblib threading backend. Mutating `not_stop[0] = 0` is not atomic, but because it's a Python integer assignment on a list reference, GIL ensures safety.

**Why it happens:** Pre-v1.0 design used a mutable list as a stop signal between threads.

**How to avoid:** Don't try to replace this with an `atomic_bool` or threading Event in Phase 9 -- it works correctly with the GIL. Just remove the `signal.raise_signal()` and use `solver_ctx_request_stop()` instead.

### Pitfall 5: verify_solution with empty objective

**What goes wrong:** In SATISFY mode, `self.objective` is an empty `new_constraint` (zero constraints). Calling `eval_obj()` on it may return 0, and comparing with `None` from `objective_value` would raise TypeError.

**How to avoid:** Guard the objective verification block with a solver-mode check. Only verify objective in OPTIMIZE mode.

## Code Examples

### Fix for CRASH-01: Replace len() with direct scalar access

**File:** `cbqs/SearchLib.pyx`, line 220

```python
# BEFORE (crashes):
stpvl = -len(mod.mod[0].con[0].num_constraints)

# AFTER (correct):
stpvl = -mod.mod[0].con[0].num_constraints
```

**Reasoning:** `num_constraints` is a `uint32_t` scalar in the C struct. The C kernel does `-(int64_t) mod->con->num_constraints` (SearchLib.c:194). The Python equivalent is just negation.

### Fix for CRASH-02: Replace signal.raise_signal with solver_ctx_request_stop

**File:** `cbqs/SearchLib.pyx`, lines 233-237

```python
# BEFORE (raises real SIGINT):
if stt.tot_profit == stpvl:
    not_stop[0] = 0
    t_total = time.time() - t_start
    signal.raise_signal(signal.SIGINT)
    break

# AFTER (uses ctx stop mechanism):
if stt.tot_profit == stpvl:
    not_stop[0] = 0
    t_total = time.time() - t_start
    solver_ctx_request_stop(ctx)
    break
```

**Note:** `solver_ctx_request_stop` is already declared in `cbqs/SearchLib.pxd:21` and `ctx` is already in scope.

### Fix for CRASH-03: objective_value returns None in SATISFY mode

**File:** `cbqs/Model.pyx`, lines 466-468

```python
# BEFORE:
@property
def objective_value(self):
    return self.mod[0].global_opt[0].tot_profit * self.sense

# AFTER:
@property
def objective_value(self):
    if self.mod[0].solver == SATISFY:
        return None
    return self.mod[0].global_opt[0].tot_profit * self.sense
```

### Fix for CRASH-04: History callback in SATISFY mode

**File:** `cbqs/SearchLib.pyx`, lines 149-157

```python
# BEFORE:
obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense

# AFTER:
if mod.mod[0].solver == SATISFY:
    obj_val = None
else:
    obj_val = mod.mod[0].global_opt[0].tot_profit * mod.sense
```

### Fix for verify_solution in SATISFY mode

**File:** `cbqs/Model.pyx`, lines 568-579

```python
# BEFORE:
recomputed_obj = self.objective.eval_obj(st) * self.sense
reported_obj = self.objective_value
EPSILON = 1e-9
if abs(recomputed_obj - reported_obj) > EPSILON:
    ...

# AFTER:
if self.mod[0].solver != SATISFY:
    recomputed_obj = self.objective.eval_obj(st) * self.sense
    reported_obj = self.objective_value
    EPSILON = 1e-9
    if abs(recomputed_obj - reported_obj) > EPSILON:
        ...
```

### Test pattern for SATISFY mode

```python
def test_satisfy_mode_completes():
    """A SATISFY-mode solve completes without crash."""
    m = Model()
    xs = m.add_variables(4)
    x = [xs[i] for i in range(4)]
    # No objective -- pure constraint satisfaction
    m.add_constraint((x[0] + x[1]) <= 1)
    m.add_constraint((x[2] + x[3]) <= 1)
    m.close()
    result = m.solve(stopping_time=5, num_workers=1)
    assert isinstance(result, OptimizeResult)
    assert result.objective is None  # No objective in SATISFY mode
    assert result.feasible  # Should find a feasible solution

def test_satisfy_objective_value_is_none():
    """objective_value property returns None in SATISFY mode."""
    m = Model()
    xs = m.add_variables(3)
    x = [xs[i] for i in range(3)]
    m.add_constraint((x[0] + x[1] + x[2]) <= 2)
    m.close()
    m.solve(stopping_time=5, num_workers=1)
    assert m.objective_value is None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global stop flag | solver_ctx_t per-solve stop | Phase 3 (v1.0) | CRASH-02 fix uses existing infrastructure |
| Raw C values in Python | OptimizeResult container | Phase 8 (v1.0) | CRASH-04 fix extends OptimizeResult for SATISFY |
| No signal handling | solver_ctx_request_stop + SIGINT handler | Phase 3 (v1.0) | CRASH-02 replaces Python signal.raise_signal with ctx mechanism |

## Open Questions

1. **Should SATISFY history include constraint satisfaction progress?**
   - What we know: The C callback only fires when feasibility is first achieved. So SATISFY history will have 0-1 entries.
   - What's unclear: Should we add richer SATISFY history tracking (e.g., how many constraints satisfied over time)?
   - Recommendation: Defer to Phase 11 (CB-03). Phase 9 just fixes the crash and ensures the history entries that DO exist have `None` for objective instead of a meaningless number.

2. **Should OptimizeResult have a `mode` field (SATISFY vs OPTIMIZE)?**
   - What we know: Currently no way to tell from OptimizeResult alone what mode was used.
   - What's unclear: Whether this is valuable enough for Phase 9.
   - Recommendation: Defer. Phase 9 scope is bug fixes only. A `mode` field could be added in Phase 11 or later.

3. **What happens if user calls verify=True on a SATISFY solve?**
   - What we know: Constraint check will work correctly. Objective check would crash without the guard.
   - What's unclear: Nothing -- the fix is clear (skip objective verification in SATISFY mode).
   - Recommendation: Apply the guard. Constraint verification should still work in SATISFY mode.

## Sources

### Primary (HIGH confidence)

All findings are from direct inspection of the project source code:

- `cbqs/SearchLib.pyx` -- SATISFY mode execution path (lines 217-239), history callback (lines 143-159)
- `cbqs/Model.pyx` -- `objective_value` property (line 466-468), `solve()` method (lines 277-369), `verify_solution()` (lines 535-582)
- `cbqs/src/SearchLib.c` -- C kernel `ctg()` function (lines 89-217), SATISFY stop condition (line 194)
- `cbqs/src/constraint.h` -- `num_constraints` field type (line 34: `uint32_t`)
- `cbqs/Constraint.pxd` -- Cython declaration of `num_constraints` (line 7: `size_t`)
- `cbqs/SearchLib.pxd` -- `solver_ctx_request_stop` declaration (line 21)
- `cbqs/result.py` -- `OptimizeResult` class (complete file)
- `cbqs/Constants.py` -- `SATISFY = 3`, `MAXIMIZE = -1`

### No external sources needed

This phase is entirely about fixing internal bugs. No external libraries, patterns, or tools are involved.

## Metadata

**Confidence breakdown:**
- Bug identification: HIGH -- All four bugs confirmed by direct code inspection
- Fix approach: HIGH -- Each fix is 1-5 lines, well-understood
- Side effects: HIGH -- Impact analysis covers all callers of changed code
- Test strategy: HIGH -- Clear test cases follow existing patterns in `tests/test_model_py.py`

**Research date:** 2026-02-06
**Valid until:** Indefinite (internal codebase analysis, not library-dependent)
