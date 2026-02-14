# Roadmap: CBQS

## Milestones

- SHIPPED **v1.0 Stabilization & Optimization** — Phases 1-8 (shipped 2026-02-06) — [archive](milestones/v1.0-ROADMAP.md)
- SHIPPED **v1.1 Bug Fixes & Polish** — Phases 9-13 (shipped 2026-02-08) — [archive](milestones/v1.1-ROADMAP.md)
- IN PROGRESS **v2.0 API Cleanup** — Phases 14-17

## Phases

<details>
<summary>v1.0 Stabilization & Optimization (Phases 1-8) — SHIPPED 2026-02-06</summary>

- [x] Phase 1: Test Foundation (5/5 plans) — completed 2026-02-04
- [x] Phase 2: Critical Correctness Fixes (6/6 plans) — completed 2026-02-05
- [x] Phase 3: Solver Context Architecture (5/5 plans) — completed 2026-02-05
- [x] Phase 4: Thread Isolation (3/3 plans) — completed 2026-02-05
- [x] Phase 5: Memory Safety (5/5 plans) — completed 2026-02-05
- [x] Phase 6: Memory Optimization (5/5 plans) — completed 2026-02-06
- [x] Phase 7: API Robustness (3/3 plans) — completed 2026-02-06
- [x] Phase 8: Solve Diagnostics (2/2 plans) — completed 2026-02-06

</details>

<details>
<summary>v1.1 Bug Fixes & Polish (Phases 9-13) — SHIPPED 2026-02-08</summary>

- [x] Phase 9: SATISFY Mode Crash Fixes (2/2 plans) — completed 2026-02-06
- [x] Phase 10: C23 Migration & VLA Elimination (2/2 plans) — completed 2026-02-08
- [x] Phase 11: Callback Concurrency Rework (2/2 plans) — completed 2026-02-08
- [x] Phase 12: BranchingStats & Local Search Cleanup (2/2 plans) — completed 2026-02-08
- [x] Phase 13: Dead Code & Documentation Cleanup (2/2 plans) — completed 2026-02-08

</details>

### v2.0 API Cleanup (In Progress)

**Milestone Goal:** Remove all deprecated APIs, unify the branching model into a single-array design, and clean the solve() signature so all configuration flows through set_param().

- [x] **Phase 14: Unified Branching Model** — Replace dual-array branching struct with single unified array and 3-term formula at the C layer — completed 2026-02-14
- [ ] **Phase 15: Solve API Migration** — Remove all solve() keyword arguments and expand set_param()/get_param() to cover every former solve() parameter
- [ ] **Phase 16: Global State Removal** — Delete global BranchingStats variable, deprecated C setters, branching.pyx module, and stale .pxd declarations
- [ ] **Phase 17: Test Suite Finalization** — Update all existing tests for new API, add branching_weights coverage, and verify memory safety

## Phase Details

### Phase 14: Unified Branching Model
**Goal**: Researchers can configure branching with a single weights array and one factor instead of separate objective/constraint arrays
**Depends on**: Nothing (first v2.0 phase)
**Requirements**: BRANCH-01, BRANCH-02, BRANCH-03, BRANCH-04, BRANCH-05
**Success Criteria** (what must be TRUE):
  1. BranchingStats_t contains a single `double *branching_weights` array — obj_dependent and constraint_dependent fields no longer exist in the struct
  2. BranchingStats_t contains a single `double branching_factor` — objective_factor and constraint_factor fields no longer exist in the struct
  3. BranchingFunction computes scores using the 3-term formula (branching_weights * branching_factor + assignment_bias * bias_factor + look_ahead * look_factor) and produces correct branching decisions
  4. `model.set_param('branching_weights', array)` in Python flows the array through Cython into the solver context's BranchingStats_t, and the values are used during solve
  5. solver_ctx_set_branching_weights() is the only context setter for branching weight data — solver_ctx_set_obj_dependence() and solver_ctx_set_constraint_dependence() are replaced
**Plans**: 2 plans

Plans:
- [x] 14-01-PLAN.md -- C layer: restructure BranchingStats_t, rewrite BranchingFunction with 3-term formula, new solver_ctx setters, update all C tests
- [x] 14-02-PLAN.md -- Cython/Python layer: update .pxd declarations, wire branching_weights propagation, add set_param validation, update Python tests

### Phase 15: Solve API Migration
**Goal**: All solver configuration happens through set_param()/get_param() — solve() takes no arguments
**Depends on**: Phase 14 (branching model must be in place before removing solve() branching kwargs)
**Requirements**: API-01, API-02, API-03, API-04
**Success Criteria** (what must be TRUE):
  1. `model.solve()` accepts zero keyword arguments — calling `model.solve(M=100)` raises TypeError
  2. Every former solve() parameter (M, stopping_time, stop_val, callback, max_delta, reset_delta, depth_look_ahead, num_workers, results, bfs, ignore_constraint_search, verify, track_history) is settable via `model.set_param(name, value)` and readable via `model.get_param(name)`
  3. A user who never passed kwargs to solve() gets identical solver behavior after the migration — all defaults preserved
  4. `model.get_param(name)` returns the current value for any configured param, or the documented default — never returns None for params that have defaults
**Plans**: 2 plans

Plans:
- [ ] 15-01-PLAN.md -- Expand param infrastructure: _PARAM_DEFS registry with coercion/validation/defaults, rewrite set_param/get_param, add _get_effective helper
- [ ] 15-02-PLAN.md -- Strip solve() kwargs, rewrite internals to read from _params, update all ~80 test/benchmark solve() calls to use set_param()

### Phase 16: Global State Removal
**Goal**: No deprecated global branching state or setter functions exist anywhere in the codebase
**Depends on**: Phase 14 (unified model replaces globals), Phase 15 (solve() no longer passes branching args through deprecated paths)
**Requirements**: GLOB-01, GLOB-02, GLOB-03, GLOB-04
**Success Criteria** (what must be TRUE):
  1. No global or file-scope BranchingStats_t variable exists in Branching.h or Branching.c — no extern declaration, no static instance
  2. The C functions set_factors(), set_bias(), set_obj_dependence(), and set_constraint_dependence() do not exist in any .c or .h file
  3. The file branching.pyx does not exist — no Python-level deprecated wrappers remain
  4. No Cython .pxd file contains declarations for the removed C functions — the build compiles cleanly without them
**Plans**: TBD

Plans:
- [ ] 16-01: TBD

### Phase 17: Test Suite Finalization
**Goal**: The full test suite passes against the v2.0 API with no regressions, new branching coverage, and verified memory safety
**Depends on**: Phase 14 (branching model), Phase 15 (solve API), Phase 16 (global removal)
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. All existing Python tests pass with zero solve() kwargs — every test uses set_param() for configuration
  2. New tests verify that branching_weights values set via set_param() reach BranchingFunction and produce correct branching scores
  3. Deterministic branching propagation tests pass — same seed and weights produce identical branching decisions across runs
  4. Valgrind reports zero leaks for branching_weights allocation, deallocation, and reallocation across solve lifecycles
**Plans**: TBD

Plans:
- [ ] 17-01: TBD
- [ ] 17-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 14 -> 15 -> 16 -> 17

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Test Foundation | v1.0 | 5/5 | Complete | 2026-02-04 |
| 2. Critical Correctness Fixes | v1.0 | 6/6 | Complete | 2026-02-05 |
| 3. Solver Context Architecture | v1.0 | 5/5 | Complete | 2026-02-05 |
| 4. Thread Isolation | v1.0 | 3/3 | Complete | 2026-02-05 |
| 5. Memory Safety | v1.0 | 5/5 | Complete | 2026-02-05 |
| 6. Memory Optimization | v1.0 | 5/5 | Complete | 2026-02-06 |
| 7. API Robustness | v1.0 | 3/3 | Complete | 2026-02-06 |
| 8. Solve Diagnostics | v1.0 | 2/2 | Complete | 2026-02-06 |
| 9. SATISFY Mode Crash Fixes | v1.1 | 2/2 | Complete | 2026-02-06 |
| 10. C23 Migration & VLA Elimination | v1.1 | 2/2 | Complete | 2026-02-08 |
| 11. Callback Concurrency Rework | v1.1 | 2/2 | Complete | 2026-02-08 |
| 12. BranchingStats & Local Search Cleanup | v1.1 | 2/2 | Complete | 2026-02-08 |
| 13. Dead Code & Documentation Cleanup | v1.1 | 2/2 | Complete | 2026-02-08 |
| 14. Unified Branching Model | v2.0 | 2/2 | Complete | 2026-02-14 |
| 15. Solve API Migration | v2.0 | 0/TBD | Not started | - |
| 16. Global State Removal | v2.0 | 0/TBD | Not started | - |
| 17. Test Suite Finalization | v2.0 | 0/TBD | Not started | - |
