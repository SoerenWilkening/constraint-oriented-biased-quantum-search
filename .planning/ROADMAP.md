# Roadmap: CBQS

## Milestones

- ✅ **v1.0 Stabilization & Optimization** — Phases 1-8 (shipped 2026-02-06) — [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Bug Fixes & Polish** — Phases 9-13 (shipped 2026-02-08) — [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v2.0 API Cleanup** — Phases 14-17 (shipped 2026-02-14) — [archive](milestones/v2.0-ROADMAP.md)
- 🚧 **v2.1 Code Audit & Optimization** — Phases 18-22 (in progress)

## Phases

<details>
<summary>✅ v1.0 Stabilization & Optimization (Phases 1-8) — SHIPPED 2026-02-06</summary>

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
<summary>✅ v1.1 Bug Fixes & Polish (Phases 9-13) — SHIPPED 2026-02-08</summary>

- [x] Phase 9: SATISFY Mode Crash Fixes (2/2 plans) — completed 2026-02-06
- [x] Phase 10: C23 Migration & VLA Elimination (2/2 plans) — completed 2026-02-08
- [x] Phase 11: Callback Concurrency Rework (2/2 plans) — completed 2026-02-08
- [x] Phase 12: BranchingStats & Local Search Cleanup (2/2 plans) — completed 2026-02-08
- [x] Phase 13: Dead Code & Documentation Cleanup (2/2 plans) — completed 2026-02-08

</details>

<details>
<summary>✅ v2.0 API Cleanup (Phases 14-17) — SHIPPED 2026-02-14</summary>

- [x] Phase 14: Unified Branching Model (2/2 plans) — completed 2026-02-14
- [x] Phase 15: Solve API Migration (2/2 plans) — completed 2026-02-14
- [x] Phase 16: Global State Removal (2/2 plans) — completed 2026-02-14
- [x] Phase 17: Test Suite Finalization (2/2 plans) — completed 2026-02-14

</details>

### 🚧 v2.1 Code Audit & Optimization (In Progress)

**Milestone Goal:** Comprehensive codebase cleanup — eliminate dead code, enforce API consistency, fix build/packaging, fill documentation gaps, and verify+adopt incremental evaluation for performance.

- [x] **Phase 18: Dead Code Removal** - Remove orphaned model_t fields and all remaining dead/commented-out code across C, Cython, and Python (completed 2026-02-25)
- [x] **Phase 19: Incremental Evaluation** - Benchmark and adopt incremental constraint evaluation in local_search, replacing full recalculation (completed 2026-02-25)
- [x] **Phase 20: API Consistency** - Unify parameter naming, audit _PARAM_DEFS, and align Cython type declarations with C headers (completed 2026-02-25)
- [x] **Phase 21: Build & Packaging** - Eliminate source duplication in setup.py, remove unused deps, clean artifacts, bump version (completed 2026-02-26)
- [x] **Phase 22: Documentation** - Fill all docstring gaps across Python classes and add algorithmic comments to C kernel (completed 2026-02-26)

## Phase Details

### Phase 18: Dead Code Removal
**Goal**: The C kernel, Cython bindings, and Python layer contain no orphaned fields, commented-out code blocks, or stale declarations
**Depends on**: Phase 17 (v2.0 complete)
**Requirements**: DEAD-01, DEAD-02, DEAD-03, DEAD-04
**Success Criteria** (what must be TRUE):
  1. The 4 orphaned model_t fields (manual_bias, bias_factor, manual_bias_factor, look_ahead_factor) are absent from model.h, model.c, and Model.pxd — compiler and grep confirm no references
  2. Model.pxd contains no Cython declarations for fields that no longer exist in the C struct
  3. solver.h contains no commented-out function signatures
  4. local_search.c contains no commented-out code blocks
  5. Full test suite (56 C + 390 Python) passes after removal with zero new failures
**Plans**: 1/1 complete

Plans:
- [x] 18-01: Remove orphaned model_t fields, commented-out code, and stale Cython declarations (completed 2026-02-25)

### Phase 19: Incremental Evaluation
**Goal**: local_search uses incremental constraint evaluation instead of full recalculation, with benchmarks confirming correctness and measuring performance delta
**Depends on**: Phase 18 (clean code base for safe modification)
**Requirements**: INCR-01, INCR-02, INCR-03
**Success Criteria** (what must be TRUE):
  1. Before/after benchmark results exist showing wall-clock time for representative problem sizes under both full-recalc and incremental evaluation paths
  2. local_search calls adjusted_constraint_violation() (or equivalent incremental path) instead of full constraint recalculation for objective evaluation on each move
  3. All 446 tests pass after the incremental adoption — no correctness regression
  4. Benchmark output (or summary) is committed alongside the implementation change
**Plans**: 2/2 complete

Plans:
- [x] 19-01: Adopt incremental constraint evaluation in explore_neighbourhood() and accept_best_routine() (completed 2026-02-25)
- [x] 19-02: Create benchmark script and BENCHMARK.md with timing results (completed 2026-02-25)

### Phase 20: API Consistency
**Goal**: Parameter naming is consistent across all three layers (C/Cython/Python), _PARAM_DEFS has no disconnected entries, and Cython type declarations match C headers
**Depends on**: Phase 18 (dead fields removed before auditing naming)
**Requirements**: API-01, API-02, API-03
**Success Criteria** (what must be TRUE):
  1. A single parameter name is used for the look-ahead depth factor across C (solver internals), Cython (bindings), and Python (_PARAM_DEFS) — no aliases or mismatched names
  2. Every entry in _PARAM_DEFS connects to an actual set_param/get_param path that reads and writes the underlying C field — any orphaned entries are removed
  3. Cython declarations for uint32_t fields use uint32_t consistently (not unsigned int), matching C header types
  4. Full test suite passes with all parameter round-trips (set_param then get_param) returning expected values
**Plans**: TBD

Plans:
- [ ] 20-01: TBD

### Phase 21: Build & Packaging
**Goal**: setup.py compiles each C source exactly once, no unused dependencies are declared, build artifacts are gitignored, and the package version reflects v2.1.0
**Depends on**: Phase 17 (v2.0 baseline)
**Requirements**: BUILD-01, BUILD-02, BUILD-03, BUILD-04
**Success Criteria** (what must be TRUE):
  1. Each C source file appears exactly once in setup.py Extension definitions — no duplicate compilation entries
  2. pandas is absent from install_requires (or any dependency list) unless a concrete usage is found in the codebase
  3. Common build artifact patterns (*.so, *.pyc, build/, dist/, *.egg-info/) are covered by .gitignore — git status shows clean working tree after a fresh build
  4. The installed package reports version 2.1.0 (e.g., via importlib.metadata or __version__)
**Plans**: 0/2

Plans:
- [ ] 21-01: Deduplicate C sources in setup.py, modernize pyproject.toml, create MANIFEST.in (BUILD-01)
- [ ] 21-02: Audit dependencies, update .gitignore, bump version to 2.1.0 (BUILD-02, BUILD-03, BUILD-04)

### Phase 22: Documentation
**Goal**: Every public Python method has a docstring, and the C kernel has algorithmic comments explaining the branching formula, preprocessing, look-ahead logic, and all _PARAM_DEFS entries
**Depends on**: Phase 20 (API names finalized before documenting them), Phase 21 (version finalized)
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):
  1. Every public method on the Model class has a docstring — pydoc/help() produces readable output for all methods
  2. Every public method on the Expression and Constraint classes has a docstring — pydoc/help() produces readable output for all methods
  3. The C source for branching formula, preprocessing, and look-ahead logic has block comments explaining the algorithm (what it computes and why, not just what the code does line-by-line)
  4. Each entry in _PARAM_DEFS includes a description string and documents the acceptable value range or valid options
**Plans**: 3/3 complete

Plans:
- [x] 22-01: Model class docstrings and _PARAM_DEFS documentation (DOC-01, DOC-04) (completed 2026-02-26)
- [x] 22-02: Expression and Constraint class docstrings (DOC-02) (completed 2026-02-26)
- [x] 22-03: C kernel algorithm block comments (DOC-03) (completed 2026-02-26)

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
| 13. Dead Code & Documentation Cleanup | v1.1 | 2/2 | Complete | 2026-02-08 |
| 14. Unified Branching Model | v2.0 | 2/2 | Complete | 2026-02-14 |
| 15. Solve API Migration | v2.0 | 2/2 | Complete | 2026-02-14 |
| 16. Global State Removal | v2.0 | 2/2 | Complete | 2026-02-14 |
| 17. Test Suite Finalization | v2.0 | 2/2 | Complete | 2026-02-14 |
| 18. Dead Code Removal | 1/1 | Complete   | 2026-02-25 | - |
| 19. Incremental Evaluation | v2.1 | 2/2 | Complete | 2026-02-25 |
| 20. API Consistency | 2/2 | Complete    | 2026-02-25 | - |
| 21. Build & Packaging | 2/2 | Complete    | 2026-02-26 | - |
| 22. Documentation | v2.1 | Complete    | 2026-02-26 | 2026-02-26 |
