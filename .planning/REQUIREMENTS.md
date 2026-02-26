# Requirements: CBQS

**Defined:** 2026-02-25
**Core Value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## v2.1 Requirements

Requirements for Code Audit & Optimization milestone. Each maps to roadmap phases.

### Dead Code Removal

- [x] **DEAD-01**: All 4 orphaned model_t fields removed (manual_bias, bias_factor, manual_bias_factor, look_ahead_factor) from model.h, model.c, and Model.pxd
- [x] **DEAD-02**: Orphaned Cython declarations for removed fields removed from Model.pxd
- [x] **DEAD-03**: Commented-out function signature in solver.h removed
- [x] **DEAD-04**: Commented-out code blocks in local_search.c removed

### Incremental Evaluation

- [x] **INCR-01**: Current full-recalculation paths benchmarked with before/after metrics
- [x] **INCR-02**: Incremental objective evaluation adopted in local_search using adjusted_constraint_violation() pattern
- [x] **INCR-03**: Benchmark confirms no correctness regression after incremental adoption

### API Consistency

- [x] **API-01**: Parameter naming unified across C/Cython/Python layers (look_factor/look_ahead_factor/depth_look_ahead resolved to single consistent name)
- [x] **API-02**: Unused or disconnected _PARAM_DEFS entries audited and either connected or removed
- [x] **API-03**: Cython type declarations aligned with C headers (uint32_t vs unsigned int consistency)

### Build & Packaging

- [x] **BUILD-01**: setup.py source duplication eliminated (each C source compiled once)
- [x] **BUILD-02**: pandas dependency verified and removed if unused
- [x] **BUILD-03**: Stray build artifacts cleaned and .gitignore updated
- [x] **BUILD-04**: Package version updated to 2.1.0

### Documentation

- [x] **DOC-01**: All public Python methods on Model class have docstrings
- [x] **DOC-02**: All public Python methods on Expression and Constraint classes have docstrings
- [x] **DOC-03**: C algorithm documentation added for branching formula, preprocessing, and look-ahead logic
- [x] **DOC-04**: _PARAM_DEFS entries documented with descriptions and acceptable ranges

## Future Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Solver Extensions

- **SOLV-01**: ML-based branching strategy selection
- **SOLV-02**: Adaptive branching that learns during search
- **SOLV-03**: Automatic multi-heuristic solver (combining sampling + local search)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Branch-and-bound extension | Architectural change, not cleanup |
| Circuit backend / quantum hardware | Exists as submodule but not active |
| GUI or web interface | CLI/API only |
| Python free-threading (nogil) | Cython support experimental |
| Metal/GPU acceleration | macOS-only, not relevant to solver stabilization |
| README rewrite | Defer to a documentation-focused milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEAD-01 | Phase 18, 24 | Complete |
| DEAD-02 | Phase 18, 24 | Complete |
| DEAD-03 | Phase 18, 24 | Complete |
| DEAD-04 | Phase 18, 24 | Complete |
| INCR-01 | Phase 19, 24 | Complete |
| INCR-02 | Phase 19, 24 | Complete |
| INCR-03 | Phase 19, 24 | Complete |
| API-01 | Phase 20, 23 | Complete |
| API-02 | Phase 20 | Complete |
| API-03 | Phase 20 | Complete |
| BUILD-01 | Phase 21 | Complete |
| BUILD-02 | Phase 21 | Complete |
| BUILD-03 | Phase 21 | Complete |
| BUILD-04 | Phase 21 | Complete |
| DOC-01 | Phase 22, 24 | Complete |
| DOC-02 | Phase 22, 24 | Complete |
| DOC-03 | Phase 22, 24 | Complete |
| DOC-04 | Phase 22, 24 | Complete |

**Coverage:**
- v2.1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-25*
*Last updated: 2026-02-26 after Phase 24 verification completed all remaining requirements*
