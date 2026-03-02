# Roadmap: CBQS

## Milestones

- ✅ **v1.0 Stabilization & Optimization** — Phases 1-8 (shipped 2026-02-06) — [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Bug Fixes & Polish** — Phases 9-13 (shipped 2026-02-08) — [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v2.0 API Cleanup** — Phases 14-17 (shipped 2026-02-14) — [archive](milestones/v2.0-ROADMAP.md)
- ✅ **v2.1 Code Audit & Optimization** — Phases 18-24 (shipped 2026-02-26) — [archive](milestones/v2.1-ROADMAP.md)
- 🚧 **v3.0 Adaptive Branching** — Phases 25-28 (in progress)

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

<details>
<summary>✅ v2.1 Code Audit & Optimization (Phases 18-24) — SHIPPED 2026-02-26</summary>

- [x] Phase 18: Dead Code Removal (1/1 plan) — completed 2026-02-25
- [x] Phase 19: Incremental Evaluation (2/2 plans) — completed 2026-02-25
- [x] Phase 20: API Consistency (2/2 plans) — completed 2026-02-25
- [x] Phase 21: Build & Packaging (2/2 plans) — completed 2026-02-26
- [x] Phase 22: Documentation (3/3 plans) — completed 2026-02-26
- [x] Phase 23: Fix C Test API Rename (1/1 plan) — completed 2026-02-26
- [x] Phase 24: Phase Verification (3/3 plans) — completed 2026-02-26

</details>

### 🚧 v3.0 Adaptive Branching (In Progress)

**Milestone Goal:** Add ML-based learning of branching weights — train on small/medium instances, generalize to larger ones, with real-time online adaptation during solve.

- [x] **Phase 25: Feature Extraction & ML Foundation** - Package skeleton, optional dependency wiring, per-variable and instance-level feature extraction (completed 2026-02-26)
- [ ] **Phase 26: Offline Training Pipeline** - Weight predictor training from collected solve data, model persistence, baseline evaluation
- [ ] **Phase 27: Online Adaptive Solve** - Multi-round adaptive solve loop with EMA weight updates, combined reward signal, determinism and thread safety
- [ ] **Phase 28: Transfer Learning & Diagnostics** - Small-to-large generalization validation, weight evaluation utilities, diagnostic reporting

## Phase Details

### Phase 25: Feature Extraction & ML Foundation
**Goal**: Users can extract structural features from any Model and import the ML module without breaking existing non-ML workflows
**Depends on**: Phase 24 (v2.1 complete)
**Requirements**: FEAT-01, FEAT-02, FEAT-03, INTG-01, INTG-02, INTG-03
**Success Criteria** (what must be TRUE):
  1. User can run `pip install cbqs[ml]` and import `cbqs.ml` with sklearn available
  2. User can `from cbqs import Model` without sklearn installed and receive no import errors
  3. User receives a clear error message when importing `cbqs.ml` without sklearn installed
  4. User can call a feature extractor on a closed Model and receive a per-variable feature matrix of shape (n_vars, n_features) where row i corresponds to variable i
  5. User can extract an instance-level feature vector (constraint density, variable count, coefficient statistics) from any Model regardless of size
**Plans**: TBD

Plans:
- [ ] 25-01: TBD
- [ ] 25-02: TBD

### Phase 26: Offline Training Pipeline
**Goal**: Users can collect training data, train a weight predictor, and use it to predict branching weights for new problem instances
**Depends on**: Phase 25
**Requirements**: TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04, TRAIN-05
**Success Criteria** (what must be TRUE):
  1. User can call fit() on a collection of (Model, best_weights) pairs to train a weight predictor
  2. User can call predict() on a new Model and receive a numpy array directly compatible with set_param('branching_weights', ...)
  3. User can save a trained predictor to disk and load it in a new Python session via joblib serialization
  4. User can run an automated data collection utility that solves instances with diverse weight strategies and returns training pairs
  5. Training evaluation always includes a uniform-weights baseline so users can verify the predictor outperforms naive defaults
**Plans**: 2 plans

Plans:
- [ ] 26-01-PLAN.md — WeightPredictor class (fit/predict/save/load) with ExtraTreesRegressor
- [ ] 26-02-PLAN.md — Data collection utility and evaluation with baseline comparison

### Phase 27: Online Adaptive Solve
**Goal**: Users can run a multi-round adaptive solve where branching weights improve between rounds based on observed solver performance
**Depends on**: Phase 25 (feature extraction); benefits from Phase 26 (pre-trained predictor for initial weights)
**Requirements**: ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04
**Success Criteria** (what must be TRUE):
  1. User can run an adaptive multi-round solve that updates branching weights between rounds using EMA
  2. Adaptation reward signal combines both objective improvement rate and constraint satisfaction rate
  3. Running the same adaptive solve with the same seed and thread count produces identical results across runs
  4. Concurrent adaptive solves on different models do not share or corrupt weight arrays between workers
**Plans**: TBD

Plans:
- [ ] 27-01: TBD
- [ ] 27-02: TBD

### Phase 28: Transfer Learning & Diagnostics
**Goal**: Users can validate that learned weights generalize across instance sizes and evaluate weight quality against baselines
**Depends on**: Phase 26 (trained predictor), Phase 27 (adaptive solve)
**Requirements**: DIAG-01, DIAG-02, DIAG-03
**Success Criteria** (what must be TRUE):
  1. User can train a predictor on small instances (e.g., n=50 variables) and apply the learned weights to larger instances (e.g., n=500) of the same problem type
  2. User can call an evaluate_weights utility that compares learned weights against uniform and default baselines on a set of test instances
  3. Evaluation report includes both objective improvement and convergence speed relative to baselines, so users can quantify the ML benefit
**Plans**: TBD

Plans:
- [ ] 28-01: TBD
- [ ] 28-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 25 -> 26 -> 27 -> 28

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
| 18. Dead Code Removal | v2.1 | 1/1 | Complete | 2026-02-25 |
| 19. Incremental Evaluation | v2.1 | 2/2 | Complete | 2026-02-25 |
| 20. API Consistency | v2.1 | 2/2 | Complete | 2026-02-25 |
| 21. Build & Packaging | v2.1 | 2/2 | Complete | 2026-02-26 |
| 22. Documentation | v2.1 | 3/3 | Complete | 2026-02-26 |
| 23. Fix C Test API Rename | v2.1 | 1/1 | Complete | 2026-02-26 |
| 24. Phase Verification | v2.1 | 3/3 | Complete | 2026-02-26 |
| 25. Feature Extraction & ML Foundation | v3.0 | Complete    | 2026-02-26 | - |
| 26. Offline Training Pipeline | 1/2 | In Progress|  | - |
| 27. Online Adaptive Solve | v3.0 | 0/0 | Not started | - |
| 28. Transfer Learning & Diagnostics | v3.0 | 0/0 | Not started | - |
