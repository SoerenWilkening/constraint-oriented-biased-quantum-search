# Phase 25: Feature Extraction & ML Foundation - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Package skeleton with optional sklearn dependency (`pip install cbqs[ml]`), per-variable feature matrix extraction, and instance-level feature vector extraction from Model objects. Training, prediction, and adaptation are separate phases (26-28).

</domain>

<decisions>
## Implementation Decisions

### Feature set design
- Per-variable features combine domain info AND constraint participation: variable degree (# constraints), coefficient magnitude stats (mean/max/min), constraint type distribution, bounds width, integrality flag, objective coefficient
- Include basic neighbor/interaction features: average neighbor degree, number of unique co-occurring variables — captures local graph structure without GNN complexity
- Instance-level features go beyond requirements: constraint density, variable count, coefficient statistics PLUS constraint/variable ratio, objective density, integer variable fraction, bounds tightness stats
- Follow standard MIP feature sets from solver ML literature (e.g., Khalil et al. branching features) as reference
- Features are normalized/standardized by default

### API surface & return types
- FeatureExtractor class (not standalone function, not Model method)
- Separate methods: `extract_variable_features(model)` returns ndarray (n_vars, n_features), `extract_instance_features(model)` returns ndarray (n_features,)
- Returns plain numpy arrays (not result objects)
- Fixed feature set for v3.0 — no configurability for which features to compute

### Module layout
- Subpackage structure: `cbqs.ml.features`, `cbqs.ml.training`, `cbqs.ml.adaptation`
- sklearn availability check lives in `cbqs.ml.__init__` — clear error at import time if sklearn missing
- Create stub modules for future phases (training, adaptation) to establish structure upfront
- `import cbqs` without sklearn must work with zero import errors (INTG-02)

### Edge cases & validation
- Raise `ValueError('Model must be closed before feature extraction')` on unclosed models
- Return zeros for constraint-related features when model has no constraints (allows pipeline to continue)
- No size limits or warnings for large models — extract regardless of variable count

### Claude's Discretion
- Feature naming convention (string labels vs positional) — Claude picks what best serves debugging and downstream ML usage
- Normalization scope (per-instance vs fit/transform pattern) — Claude decides what integrates best with sklearn pipelines
- Public API re-export pattern (top-level `from cbqs.ml import FeatureExtractor` vs explicit subpackage imports)
- Type checking approach (isinstance vs duck typing) for Model validation

</decisions>

<specifics>
## Specific Ideas

- Follow Khalil et al. branching feature patterns from MIP solver ML literature as the reference point for feature selection
- Objective coefficient should be included as a per-variable feature (key signal for branching importance)
- Basic neighbor features (avg neighbor degree, co-occurrence count) provide local graph structure signal without the complexity of full GNN approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 25-feature-extraction-ml-foundation*
*Context gathered: 2026-02-26*
