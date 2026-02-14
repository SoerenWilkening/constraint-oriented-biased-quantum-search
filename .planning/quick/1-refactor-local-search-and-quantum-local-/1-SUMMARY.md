# Quick Task 1: Summary

## What Changed

### Model.pyx
- Added 3 new parameters to `_PARAM_DEFS`: `distance`, `max_worse_acceptances`, `stopping_condition`
- `local_search()` now takes zero arguments — reads all params from `_get_effective()`
- `quantum_local_search()` now takes zero arguments — reads distance/callback/num_workers from `_get_effective()`

### Tests Updated
- `test_branching_propagation.py`: All `local_search(stop_time=2)` → `set_param("stopping_time", 2); local_search()`
- `test_diagnostics_py.py`: All `local_search(stop_time=3, verify=True)` → `set_param(...); local_search()`

## Results
- 140 tests pass (test_set_param + test_branching_propagation + test_diagnostics_py)
- No Cython/C layer changes needed — only Python API surface changed
- Commit: 364a2c4
