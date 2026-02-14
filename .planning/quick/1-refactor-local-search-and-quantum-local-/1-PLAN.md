# Quick Task 1: Refactor local_search and quantum_local_search to set_param API

## Goal
Migrate `local_search()` and `quantum_local_search()` from individual arguments to the `set_param()`/`get_param()` pattern already used by `solve()`.

## Tasks

### Task 1: Add new parameters to _PARAM_DEFS
- Add `distance` (default: 2, int, >= 1)
- Add `max_worse_acceptances` (default: 10, int, >= 0)
- Add `stopping_condition` (default: STOPATFIRST=1, int, in {0, 1})

### Task 2: Refactor method signatures
- `local_search()` → zero args, read all params via `_get_effective()`
- `quantum_local_search()` → zero args, read distance/callback/num_workers via `_get_effective()`

### Task 3: Update tests
- Convert all `m.local_search(stop_time=X, ...)` calls to `m.set_param(); m.local_search()`
- Files: test_branching_propagation.py, test_diagnostics_py.py
