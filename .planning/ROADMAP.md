# Roadmap: CBQS

## Milestones

- SHIPPED **v1.0 Stabilization & Optimization** — Phases 1-8 (shipped 2026-02-06) — [archive](milestones/v1.0-ROADMAP.md)
- IN PROGRESS **v1.1 Bug Fixes & Polish** — Phases 9-13

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

### v1.1 Bug Fixes & Polish (In Progress)

**Milestone Goal:** Fix all known bugs, eliminate tech debt, and clean up code quality issues from v1.0. Zero breaking changes.

- [x] **Phase 9: SATISFY Mode Crash Fixes** (2/2 plans) — completed 2026-02-06
- [x] **Phase 10: C23 Migration & VLA Elimination** (2/2 plans) — completed 2026-02-08
- [x] **Phase 11: Callback Concurrency Rework** (2/2 plans) — completed 2026-02-08
- [x] **Phase 12: BranchingStats & Local Search Cleanup** (2/2 plans) — completed 2026-02-08
- [ ] **Phase 13: Dead Code & Documentation Cleanup** - Remove dead code, fix bare except, document local_search fields

## Phase Details

### Phase 9: SATISFY Mode Crash Fixes
**Goal**: Users can solve SATISFY-mode problems without crashes, with correct signal handling and meaningful result objects
**Depends on**: Nothing (first v1.1 phase)
**Requirements**: CRASH-01, CRASH-02, CRASH-03, CRASH-04
**Success Criteria** (what must be TRUE):
  1. A Model with solver=SATISFY completes solve() without TypeError or crash
  2. Stopping a SATISFY solve mid-execution does not raise SIGINT (uses solver_ctx_request_stop instead)
  3. OptimizeResult from a SATISFY solve reports objective_value as None (not a meaningless violation count)
  4. OptimizeResult from a SATISFY solve contains feasibility-based history (not objective-based)
**Plans**: 2 plans

Plans:
- [x] 09-01-PLAN.md — Fix all four SATISFY mode bugs in SearchLib.pyx and Model.pyx
- [x] 09-02-PLAN.md — Add SATISFY-mode integration tests and None-objective unit tests

### Phase 10: C23 Migration & VLA Elimination
**Goal**: Codebase compiles cleanly under GCC 15 with zero warnings, and no VLAs remain anywhere
**Depends on**: Nothing (independent of Phase 9; can run in parallel)
**Requirements**: GCC-01, GCC-02, GCC-03, GCC-04, GCC-05, MEM-01
**Success Criteria** (what must be TRUE):
  1. Building with GCC 15 using -Wall -Wextra produces zero warnings
  2. callback_t typedef uses explicit (void) parameter list (C23-forward-compatible)
  3. No #define true/false macros exist — stdbool.h used throughout
  4. No VLA declarations remain in any C source file (grep for variable-length array patterns returns empty)
  5. All existing tests pass after compiler flag and type changes (no behavioral regressions)
**Plans**: 2 plans

Plans:
- [x] 10-01-PLAN.md — Migrate C headers/sources to C23-compatible patterns (stdbool.h, callback_t(void), portability macros, VLA elimination)
- [x] 10-02-PLAN.md — Enable strict warning flags, fix type mismatches, update CI with -Werror

### Phase 11: Callback Concurrency Rework
**Goal**: Concurrent solve() calls on different Model instances produce independent, correct history tracking
**Depends on**: Phase 9 (callback reads global_opt which differs in SATISFY mode; SATISFY must work first)
**Requirements**: CB-01, CB-02, CB-03
**Success Criteria** (what must be TRUE):
  1. Two concurrent solve() calls on different Models each receive their own complete history list (no cross-contamination)
  2. History callback uses per-thread state (not module-level cdef variables)
  3. SATISFY-mode history reports feasibility progress (constraint satisfaction count), not objective value
  4. ThreadSanitizer reports zero data races during concurrent solve with num_workers>=4
**Plans**: 2 plans

Plans:
- [x] 11-01-PLAN.md — Replace module-level callback state with per-thread _SolveState, add track_history param, update history format to 2-tuple
- [x] 11-02-PLAN.md — Update all history tests for 2-tuple format, add concurrent solve independence tests

### Phase 12: BranchingStats & Local Search Cleanup
**Goal**: Branching parameters set via Python API actually reach the solver, and local_search writes to shared state safely
**Depends on**: Phase 11 (touches same files as callback rework — SearchLib.pyx, local_search.c)
**Requirements**: BRANCH-01, BRANCH-02, BRANCH-03, MEM-02
**Success Criteria** (what must be TRUE):
  1. Branching bias/factors passed to solve() are used by the sampling solver (verifiable via fixed-seed deterministic run)
  2. Branching bias/factors passed to solve() are used by the local search solver (verifiable via fixed-seed deterministic run)
  3. Calling deprecated global branching setters emits a DeprecationWarning
  4. local_search accept_best_routine uses a mutex when writing to global_opt (verifiable via ThreadSanitizer clean run)
**Plans**: 2 plans

Plans:
- [x] 12-01-PLAN.md — Add set_param/get_param API, deprecation warnings, branching propagation, and mutex protection
- [x] 12-02-PLAN.md — Add tests for API, deprecation, and deterministic branching propagation

### Phase 13: Dead Code & Documentation Cleanup
**Goal**: Codebase contains no dead code, no bare except clauses, and local_search fields are documented
**Depends on**: Phases 9-12 (last phase to avoid merge conflicts with functional changes)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04
**Success Criteria** (what must be TRUE):
  1. No commented-out VLA code remains in local_search.c (lines 158, 445 area cleaned)
  2. No commented-out debug printf/print statements remain in Model.pyx, Expression.pyx, or local_search.c
  3. No bare except clause exists in Model.pyx (all except clauses specify exception types)
  4. local_search() C function has read/write field annotations documenting which model_t fields are read vs written
  5. Full test suite passes after all removals (no behavioral changes from cleanup)
**Plans**: TBD

Plans:
- [ ] 13-01: TBD
- [ ] 13-02: TBD

## Progress

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
| 13. Dead Code & Documentation Cleanup | v1.1 | 0/0 | Not started | - |
