# Phase 26: Offline Training Pipeline - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Train a weight predictor from solved instances and use it to predict branching weights for new problems. Covers: automated data collection, fit/predict API, model persistence (joblib), and baseline evaluation against uniform weights. Online/adaptive solving and transfer learning are separate phases (27, 28).

</domain>

<decisions>
## Implementation Decisions

### Data collection strategy
- Weight strategy generation: Claude's discretion (random, structured grid, or hybrid — whatever produces useful training signal)
- Solve budget: configurable by user via parameter (iterations or time), with sensible defaults
- "Best weights" selection: primary criterion is feasibility (constraint satisfaction), tiebreak by best objective value
- Data output: in-memory only — returns list of (Model, best_weights) pairs

### Predictor model design
- ML model choice: Claude's discretion (sklearn-based — RF, GBT, or other as appropriate)
- Feature input: concatenate per-variable features (9) with instance features (11) = 20 features per sample. One model predicts weight for any variable.
- Training target representation: Claude's discretion (raw weights, normalized, or other)
- Training mode: batch fit() only, no partial_fit/incremental learning

### Serialization & versioning
- Saved artifact includes metadata: feature names, training date, number of training instances, CBQS version
- Compatibility check: error on feature name mismatch when loading (prevents silent wrong predictions)
- Format: joblib as specified in success criteria
- File extension/naming: Claude's discretion

### Baseline evaluation
- Metrics: best objective value and feasibility rate
- Report format: returns Python dict AND prints human-readable comparison table to stdout
- Evaluation mode: self-contained — evaluate() takes test Models, solves internally with predicted vs. baseline weights
- Baselines: uniform weights by default, but user can pass additional weight strategies to compare against (extensible)

### Claude's Discretion
- Weight strategy generation approach for data collection
- ML model choice (within sklearn)
- Training target representation
- File extension convention for saved predictors
- Internal implementation details (solver integration, parallelism, etc.)

</decisions>

<specifics>
## Specific Ideas

- Feature input is a concatenation of Phase 25's per-variable features (9 from FeatureExtractor) and instance features (11), giving 20 features per sample
- Predictor should produce numpy array directly compatible with `set_param('branching_weights', ...)`
- Feasibility-first ranking aligns with the combined reward signal planned for Phase 27 (ADAPT-02)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 26-offline-training-pipeline*
*Context gathered: 2026-03-02*
