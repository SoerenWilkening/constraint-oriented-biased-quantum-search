# Requirements: CBQS v2.0

**Defined:** 2026-02-14
**Core Value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## v2.0 Requirements

### Global State Removal

- [ ] **GLOB-01**: Global BranchingStats_t variable deleted from Branching.h/c — no extern, no file-scope instance
- [ ] **GLOB-02**: Deprecated setter functions removed — set_factors(), set_bias(), set_obj_dependence(), set_constraint_dependence() deleted from C layer
- [ ] **GLOB-03**: branching.pyx module deleted — no Python-level deprecated wrappers remain
- [ ] **GLOB-04**: All Cython .pxd declarations for removed C functions deleted

### Solve API Cleanup

- [ ] **API-01**: solve() takes zero keyword arguments — signature is `def solve(self)`
- [ ] **API-02**: All former solve() params available via set_param() — M, stopping_time, stop_val, callback, max_delta, reset_delta, depth_look_ahead, num_workers, results, bfs, ignore_constraint_search, verify, track_history
- [ ] **API-03**: set_param() defaults match current solve() defaults — users who never called solve() with kwargs get identical behavior after migration
- [ ] **API-04**: get_param() returns current value or default for all params (never None for params with defaults)

### Branching Model

- [ ] **BRANCH-01**: BranchingStats_t has single `double *branching_weights` array replacing obj_dependent and constraint_dependent
- [ ] **BRANCH-02**: BranchingStats_t has single `double branching_factor` replacing objective_factor and constraint_factor
- [ ] **BRANCH-03**: BranchingFunction uses 3-term formula: branching_weights (branching_factor) + assignment bias (bias_factor) + look-ahead (look_factor)
- [ ] **BRANCH-04**: `model.set_param('branching_weights', array)` sets per-variable branching values — array flows from Python through Cython to C context
- [ ] **BRANCH-05**: solver_ctx_set_branching_weights() replaces solver_ctx_set_obj_dependence() and solver_ctx_set_constraint_dependence()

### Testing

- [ ] **TEST-01**: All existing tests updated for new API (no solve() kwargs, set_param() instead)
- [ ] **TEST-02**: New tests for branching_weights array input — correct values reach BranchingFunction
- [ ] **TEST-03**: Deterministic branching propagation tests pass with unified model
- [ ] **TEST-04**: No memory leaks (Valgrind clean) for branching_weights allocation/deallocation

## Future Requirements

- ML-based branching strategy selection — deferred
- Adaptive branching that learns during search — deferred

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deprecation period for solve() args | User chose hard break (v2.0), no backward compatibility |
| Backward-compatible branching.pyx shim | Deprecated in v1.1, removing now |
| New branching strategies | v2.0 is API cleanup, not new algorithms |
| Python free-threading support | Cython support still experimental |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GLOB-01 | Phase 16 | Pending |
| GLOB-02 | Phase 16 | Pending |
| GLOB-03 | Phase 16 | Pending |
| GLOB-04 | Phase 16 | Pending |
| API-01 | Phase 15 | Pending |
| API-02 | Phase 15 | Pending |
| API-03 | Phase 15 | Pending |
| API-04 | Phase 15 | Pending |
| BRANCH-01 | Phase 14 | Pending |
| BRANCH-02 | Phase 14 | Pending |
| BRANCH-03 | Phase 14 | Pending |
| BRANCH-04 | Phase 14 | Pending |
| BRANCH-05 | Phase 14 | Pending |
| TEST-01 | Phase 17 | Pending |
| TEST-02 | Phase 17 | Pending |
| TEST-03 | Phase 17 | Pending |
| TEST-04 | Phase 17 | Pending |

**Coverage:**
- v2.0 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-14 after roadmap creation*
