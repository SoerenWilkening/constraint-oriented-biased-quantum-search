# Requirements: CBQS v3.0 Adaptive Branching

**Defined:** 2026-02-26
**Core Value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## v3.0 Requirements

Requirements for ML-based adaptive branching weight learning. Each maps to roadmap phases.

### Feature Extraction

- [x] **FEAT-01**: User can extract per-variable feature matrix (n_vars x n_features) from a closed Model
- [x] **FEAT-02**: User can extract instance-level feature vector (constraint density, variable count, coefficient statistics)
- [x] **FEAT-03**: Feature extraction works on models of any size without coupling to a fixed dimension

### Offline Training

- [x] **TRAIN-01**: User can train a weight predictor from a collection of (Model, best_weights) pairs via fit()
- [x] **TRAIN-02**: User can predict branching weights for a new Model via predict(), returning a numpy array compatible with set_param()
- [x] **TRAIN-03**: User can save and load a trained predictor via joblib serialization
- [x] **TRAIN-04**: User can collect training data automatically via a utility that runs short solves with diverse weight strategies
- [x] **TRAIN-05**: Training pipeline includes uniform-weights baseline in evaluation

### Online Adaptation

- [x] **ADAPT-01**: User can run an adaptive multi-round solve where weights update between rounds via EMA
- [x] **ADAPT-02**: Adaptation uses a combined reward signal (objective improvement rate + constraint satisfaction rate)
- [x] **ADAPT-03**: Online adaptation preserves solver determinism (same seed + threads = same result)
- [x] **ADAPT-04**: Online adaptation preserves thread safety (no shared mutable weight arrays between workers)

### Transfer & Diagnostics

- [x] **DIAG-01**: User can train on small instances and apply learned weights to larger instances of the same problem type
- [x] **DIAG-02**: User can evaluate learned weights against uniform and default baselines via evaluate_weights utility
- [x] **DIAG-03**: Evaluation reports objective improvement and convergence speed relative to baselines

### Integration

- [x] **INTG-01**: sklearn is an optional dependency installed via `pip install cbqs[ml]`
- [x] **INTG-02**: Importing cbqs without sklearn installed does not raise errors
- [x] **INTG-03**: ML module has clear import error message when sklearn is missing

## Future Requirements

Deferred to v3.1+.

### Advanced ML

- **ADV-01**: GNN-based weight prediction using bipartite constraint-variable graph
- **ADV-02**: Reinforcement learning training loop for weight optimization
- **ADV-03**: Custom ML model plugin interface for user-supplied estimators

### Extended Solvers

- **EXT-01**: Local search solver weight adaptation
- **EXT-02**: Multi-solver orchestration combining sampling + local search with learned strategy selection

### Visualization

- **VIS-01**: Real-time weight evolution visualization during adaptive solve
- **VIS-02**: Training convergence dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| PyTorch / TensorFlow dependency | Overkill for 10-20 features and 10-100 training instances; sklearn sufficient |
| GNN-based prediction | Requires thousands of training instances and PyTorch; deferred to v3.1+ |
| Intra-solve C-level weight mutation | Thread-safety and determinism risk; inter-solve multi-round approach achieves same goal safely |
| Algorithm portfolio / multi-solver | Separate milestone scope; requires both solvers to have ML weights first |
| GPU acceleration | Not relevant for sklearn-based tabular regression |
| PassiveAggressiveRegressor | Deprecated in sklearn 1.8, removed in 1.10; use SGDRegressor instead |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FEAT-01 | Phase 25 | Complete |
| FEAT-02 | Phase 25 | Complete |
| FEAT-03 | Phase 25 | Complete |
| TRAIN-01 | Phase 26 | Complete |
| TRAIN-02 | Phase 26 | Complete |
| TRAIN-03 | Phase 26 | Complete |
| TRAIN-04 | Phase 26 | Complete |
| TRAIN-05 | Phase 26 | Complete |
| ADAPT-01 | Phase 27 | Complete |
| ADAPT-02 | Phase 27 | Complete |
| ADAPT-03 | Phase 27 | Complete |
| ADAPT-04 | Phase 27 | Complete |
| DIAG-01 | Phase 28 | Complete |
| DIAG-02 | Phase 28 | Complete |
| DIAG-03 | Phase 28 | Complete |
| INTG-01 | Phase 25 | Complete |
| INTG-02 | Phase 25 | Complete |
| INTG-03 | Phase 25 | Complete |

**Coverage:**
- v3.0 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-02-26*
*Last updated: 2026-03-03 after Phase 28 completion*
