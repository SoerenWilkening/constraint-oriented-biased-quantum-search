# Phase 27: Online Adaptive Solve - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Multi-round adaptive solve loop that updates branching weights between rounds using EMA and a combined reward signal (objective improvement + constraint satisfaction). Must preserve determinism and thread safety. Lives in `cbqs/ml/adaptation.py` (stub exists).

</domain>

<decisions>
## Implementation Decisions

### API shape
- Standalone function `adaptive_solve(model, ...)` in `cbqs.ml.adaptation` — mirrors `collect_training_data()` pattern, keeps ML isolated from core Model
- Returns `AdaptiveResult` object with `.best_result` (OptimizeResult), `.best_weights` (ndarray), `.history` (list of per-round dicts), `.n_rounds_completed` (int)
- `initial_weights` param accepts either ndarray or WeightPredictor — if WeightPredictor, calls `predict(model)` automatically; if None, starts uniform
- Explicit key params in signature: `model, n_rounds, stopping_time, num_workers, ema_alpha, seed, initial_weights` — no **kwargs forwarding

### Round configuration
- Fixed number of rounds only — no convergence detection or early stopping
- Default: 5 rounds
- Same `stopping_time` budget for every round (no special treatment for round 1)
- Default EMA alpha: 0.3 — `new_weights = 0.3 * reward_adjusted + 0.7 * old_weights`

### Initial weights
- Default to `np.ones(n_vars)` when `initial_weights=None`
- Always copy input weights (never mutate user's array or predictor state) — required for ADAPT-04
- Validate `len(initial_weights) == n_vars`, raise ValueError on mismatch
- Clip weights to non-negative (`np.clip(weights, 0, None)`) after each EMA update — matches WeightPredictor.predict() convention and branching_weights validation

### Progress feedback
- Print per-round one-line summary by default: round number, objective, feasibility, weight delta
- Controllable via `verbose` param (default True, set False to silence)
- History stores core metrics per round: `{round, objective, feasible, reward, weights}` — no full OptimizeResult per round
- `best_weights` on AdaptiveResult tracks the weights from the best-performing round (not final EMA'd weights)
- Restore model's `branching_weights` to pre-adaptive state after completion — no side effects, matches `collect_training_data()` pattern

### Claude's Discretion
- Exact reward signal formula combining objective improvement rate and constraint satisfaction rate
- AdaptiveResult class implementation details (dataclass vs namedtuple vs regular class)
- Determinism implementation (seed propagation to per-round solves)
- Thread safety implementation for concurrent adaptive_solve calls on different models

</decisions>

<specifics>
## Specific Ideas

- API should feel like `collect_training_data()` and `evaluate()` from Phase 26 — same standalone-function-in-ml-module pattern
- Per-round print format: `Round 1/5: obj=42, feasible=True, weight_delta=0.15`
- The combined reward signal from ADAPT-02 is left to Claude — domain-specific implementation detail

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cbqs/ml/adaptation.py`: Empty stub file — implementation target
- `WeightPredictor.predict(model)`: Returns clipped non-negative ndarray — can provide initial weights
- `FeatureExtractor`: Available but not directly needed for online adaptation (weights are adjusted, not re-predicted from features)
- `collect_training_data()`: Reference pattern for standalone function that calls model.solve() with diverse weights
- `evaluate()`: Reference pattern for running multiple solves and comparing strategies
- `_rank_result()`: Feasibility-first ranking helper — reusable for identifying best round
- `OptimizeResult`: Return type from model.solve() with `.objective` and `.feasible`

### Established Patterns
- `set_param('branching_weights', weights)` then `solve()` — how weights are applied per round
- `set_param('branching_weights', None)` to reset after — cleanup pattern from collect_training_data
- `np.clip(raw, 0, None)` for non-negative weight enforcement — from WeightPredictor.predict()
- `np.random.RandomState(random_state)` for reproducible RNG — from collect_training_data

### Integration Points
- `cbqs/ml/__init__.py`: Must export `adaptive_solve` and `AdaptiveResult`
- `cbqs/ml/training.py`: `WeightPredictor` used as optional initial_weights input
- `Model.solve()`: Called once per round with updated branching_weights
- `Model.set_param()` / `Model.get_param()`: For setting/restoring branching_weights

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 27-online-adaptive-solve*
*Context gathered: 2026-03-02*
