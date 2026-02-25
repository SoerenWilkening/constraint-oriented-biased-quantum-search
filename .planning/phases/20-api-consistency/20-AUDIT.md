# Phase 20: API Consistency — Audit Report

**Date:** 2026-02-25
**Phase:** 20-api-consistency
**Requirements:** API-01, API-02, API-03

## 1. Parameter Naming Audit (API-01)

### Renames Applied

| Layer | Old Name | New Name | File | Lines |
|-------|----------|----------|------|-------|
| C (BranchingStats_t field) | `look_factor` | `look_ahead_factor` | Branching.h | 24 |
| C (BranchingFunction local) | `look_factor` | `look_ahead_factor` | Branching.h | 33, 35, 41, 62 |
| C (setter function) | `solver_ctx_set_look_factor` | `solver_ctx_set_look_ahead_factor` | solver_ctx.h | 170 |
| C (implementation) | `solver_ctx_set_look_factor` | `solver_ctx_set_look_ahead_factor` | solver_ctx.c | 190 |
| C (default init) | `look_factor` | `look_ahead_factor` | solver_ctx.c | 37 |
| C (setter body) | `look_factor` | `look_ahead_factor` | solver_ctx.c | 194 |
| C (debug JSON key) | `"look_factor"` | `"look_ahead_factor"` | solver_ctx.c | 220 |
| C (debug JSON value) | `look_factor` | `look_ahead_factor` | solver_ctx.c | 228 |
| Cython (extern decl) | `solver_ctx_set_look_factor` | `solver_ctx_set_look_ahead_factor` | SearchLib.pxd | 26 |
| Cython (solve path) | `solver_ctx_set_look_factor` | `solver_ctx_set_look_ahead_factor` | SearchLib.pyx | 247 |
| Cython (local_search path) | `solver_ctx_set_look_factor` | `solver_ctx_set_look_ahead_factor` | SearchLib.pyx | 390 |
| Python (_PARAM_DEFS) | `look_ahead_factor` | `look_ahead_factor` | Model.pyx | 121 (unchanged) |

### Parameters Already Consistent (No Rename Needed)

| Parameter | C Name | Cython Name | Python Name | Status |
|-----------|--------|-------------|-------------|--------|
| `depth_look_ahead` | model_t.depth_look_ahead | Model.pxd depth_look_ahead | _PARAM_DEFS depth_look_ahead | Consistent |
| `bias_factor` | BranchingStats_t.bias_factor | solver_ctx_set_bias_factor | _PARAM_DEFS bias_factor | Consistent |
| `branching_factor` | BranchingStats_t.branching_factor | solver_ctx_set_branching_factor | _PARAM_DEFS branching_factor | Consistent |
| `branching_bias` | BranchingStats_t.bias | solver_ctx_set_bias | _PARAM_DEFS branching_bias | Consistent |
| `branching_weights` | BranchingStats_t.branching_weights | solver_ctx_set_branching_weights | _PARAM_DEFS branching_weights | Consistent |
| `M` | model_t.M | Model.pxd M | _PARAM_DEFS M | Consistent |
| `stopping_time` | model_t.stopping_time | Model.pxd stopping_time | _PARAM_DEFS stopping_time | Consistent |
| `stop_val` | model_t.stop_val | Model.pxd stop_val | _PARAM_DEFS stop_val | Consistent |
| `max_delta` | model_t.max_delta | Model.pxd max_delta | _PARAM_DEFS max_delta | Consistent |
| `reset_delta` | model_t.reset_delta | Model.pxd reset_delta | _PARAM_DEFS reset_delta | Consistent |
| `num_workers` | model_t.num_workers | Model.pxd num_workers | _PARAM_DEFS num_workers | Consistent |
| `ignore_constraint_search` | model_t.ignore_constraint_search | Model.pxd ignore_constraint_search | _PARAM_DEFS ignore_constraint_search | Consistent |
| `monte_carlo_estimate` | model_t.monte_carlo_estimate | Model.pxd monte_carlo_estimate | _PARAM_DEFS monte_carlo_estimate | Consistent |
| `max_worse_acceptances` | model_t.max_worse_acceptances | Model.pxd max_worse_acceptances | _PARAM_DEFS max_worse_acceptances | Consistent |
| `stopping_condition` | model_t.stopping_condition | Model.pxd stopping_condition | _PARAM_DEFS stopping_condition | Consistent |
| `distance` | model_t.distance | Model.pxd distance | _PARAM_DEFS distance | Consistent |
| `timeout` | solver_ctx.timeout_ms | SearchLib.pyx | _PARAM_DEFS timeout | Consistent |

## 2. _PARAM_DEFS Connectivity Audit (API-02)

### Connected Entries (All Valid)

| _PARAM_DEFS Entry | Connection Type | Connection Path |
|-------------------|----------------|-----------------|
| `M` | model_t field | solve() -> mod.M |
| `stopping_time` | model_t field | solve()/local_search() -> mod.stopping_time |
| `stop_val` | model_t field | solve() -> mod.stop_val |
| `callback` | Python logic | solve()/local_search() -> run_sampling/run_local_search argument |
| `max_delta` | model_t field | solve() -> mod.max_delta |
| `reset_delta` | model_t field | solve() -> mod.reset_delta |
| `depth_look_ahead` | model_t field | solve() -> mod.depth_look_ahead |
| `num_workers` | Python logic | solve() -> Parallel(n_jobs=), quantum_local_search() -> Parallel(n_jobs=) |
| `ignore_constraint_search` | model_t field | solve() -> mod.ignore_constraint_search |
| `monte_carlo_estimate` | model_t field | solve() -> mod.monte_carlo_estimate |
| `verify` | Python logic | solve()/local_search() -> verify_solution() |
| `track_history` | Python logic | solve()/local_search() -> history merging |
| `distance` | model_t field | local_search() -> mod.distance |
| `max_worse_acceptances` | model_t field | local_search() -> mod.max_worse_acceptances |
| `stopping_condition` | model_t field | local_search() -> mod.stopping_condition |
| `branching_bias` | solver_ctx setter | SearchLib.pyx -> solver_ctx_set_bias() |
| `branching_weights` | solver_ctx setter | SearchLib.pyx -> solver_ctx_set_branching_weights() |
| `branching_factor` | solver_ctx setter | SearchLib.pyx -> solver_ctx_set_branching_factor() |
| `bias_factor` | solver_ctx setter | SearchLib.pyx -> solver_ctx_set_bias_factor() |
| `look_ahead_factor` | solver_ctx setter | SearchLib.pyx -> solver_ctx_set_look_ahead_factor() |
| `timeout` | solver_ctx field | SearchLib.pyx -> ctx.timeout_ms |

### Orphaned Entries Removed

| Entry | Reason | Action |
|-------|--------|--------|
| `results` | Read by solve() into local variable but never consumed (no min/average logic) | Removed from _PARAM_DEFS |
| `bfs` | Read by solve() into local variable but never consumed (no BFS logic) | Removed from _PARAM_DEFS |

### Missing Entries (Reverse Audit)

No C-accessible parameters were found missing from _PARAM_DEFS. All solver_ctx setters and model_t fields written from Python are covered.

Internal C fields not exposed (by design):
- `model_t.break_item` -- set by C-internal preprocessing, not user-configurable
- `model_t.n` -- set by add_variables(), not via set_param
- `solver_ctx.debug_enabled` -- controlled by CBQS_DEBUG env var, not API
- `solver_ctx.arena` -- internal memory management

## 3. Migration Notes

### For C API Users

- `BranchingStats_t.look_factor` renamed to `BranchingStats_t.look_ahead_factor`
- `solver_ctx_set_look_factor()` renamed to `solver_ctx_set_look_ahead_factor()`
- All other C API names unchanged

### For Python API Users

- `set_param('look_ahead_factor', ...)` -- unchanged (already used correct name)
- `set_param('results', ...)` -- **removed**, was silently unused
- `set_param('bfs', ...)` -- **removed**, was silently unused
- All other Python parameter names unchanged

---

*Audit completed: 2026-02-25*
*Phase: 20-api-consistency*
