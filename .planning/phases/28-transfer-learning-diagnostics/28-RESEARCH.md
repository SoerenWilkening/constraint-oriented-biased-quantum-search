# Phase 28: Transfer Learning & Diagnostics - Research

**Researched:** 2026-03-03
**Domain:** Transfer validation and weight evaluation diagnostics for CBQS ML pipeline
**Confidence:** HIGH

## Summary

Phase 28 adds two new public functions to `cbqs/ml/training.py`: `evaluate_weights()` and `validate_transfer()`. Both follow the established standalone-function-in-ML-module pattern from Phase 26's `evaluate()` and `collect_training_data()`. The implementation is straightforward because the existing codebase provides all necessary building blocks: `WeightPredictor.fit()/predict()` for training and inference, `collect_training_data()` for generating training pairs, `_rank_result()` for feasibility-first ranking, `_print_comparison_table()` as a reference for table printing, and `OptimizeResult.history` as `(value, elapsed_seconds)` tuples for time-to-best extraction.

The key new concept is **convergence speed**: extracting time-to-best from `OptimizeResult.history` and computing speedup ratios relative to the uniform baseline. The `evaluate_weights()` function generalizes the existing `evaluate()` by accepting strategies as a dict of named callables (rather than requiring a `WeightPredictor` instance), adding convergence metrics, and computing speedup ratios. `validate_transfer()` is an orchestration wrapper that trains internally on small models and evaluates on large models via `evaluate_weights()`.

**Primary recommendation:** Implement as a two-plan phase: Plan 01 covers `evaluate_weights()` with convergence speed metrics (DIAG-02, DIAG-03), Plan 02 covers `validate_transfer()` with end-to-end transfer validation (DIAG-01). Plan 02 depends on Plan 01 since `validate_transfer()` calls `evaluate_weights()` internally.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `validate_transfer()` utility function in `cbqs.ml` -- self-contained, one call does everything
- Takes `train_models` (small) + `test_models` (large), trains a WeightPredictor internally via `collect_training_data()` + `fit()`
- No verification of "same problem type" -- user is responsible for providing appropriate model sets
- Returns both the evaluation results AND the fitted WeightPredictor (so user can save/reuse after validation)
- Calls `evaluate_weights()` internally and passes through its output -- one report format, no duplication
- New standalone function `evaluate_weights()` -- separate from existing `evaluate()` which takes a WeightPredictor
- Accepts strategies as a dict of named callables: `{'learned': lambda model: weights_array, ...}` -- handles variable-count differences naturally (each callable returns weights per model)
- Automatically adds 'uniform' baseline (same pattern as existing `evaluate()`)
- Single function covers both DIAG-02 and DIAG-03 -- returns all metrics including convergence speed
- Convergence speed metric: **time-to-best** -- elapsed time until the best objective value was first found, using solve history `(value, elapsed_seconds)` tuples
- If best is found at the end or never improves, time_to_best = stopping_time (ceiling -- penalizes late convergence)
- Report includes both absolute `mean_time_to_best` per strategy AND speedup ratio vs uniform baseline (e.g., "learned is 2.3x faster than uniform")
- `evaluate_weights()` returns a dict AND prints a human-readable comparison table -- matches existing `evaluate()` pattern from Phase 26
- Each strategy entry contains core trio: `mean_objective`, `feasibility_rate`, `mean_time_to_best`, plus `speedup_vs_uniform` ratio
- Printed table includes columns: Strategy | Mean Objective | Feasibility Rate | Time-to-Best | Speedup vs Uniform
- `validate_transfer()` reuses `evaluate_weights()` output directly -- no custom transfer report

### Claude's Discretion
- Internal implementation of validate_transfer() orchestration (collect_training_data params, WeightPredictor config)
- How time-to-best is extracted from solve history (parsing logic)
- Speedup ratio calculation details (handling edge cases like uniform time = 0)
- Public API re-export pattern in `cbqs/ml/__init__.py`
- Test structure and helper utilities

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DIAG-01 | User can train on small instances and apply learned weights to larger instances of the same problem type | `validate_transfer()` orchestrates: `collect_training_data(train_models)` -> `WeightPredictor.fit()` -> `evaluate_weights(test_models, strategies={'learned': predictor.predict, ...})`. Per-variable prediction model is already size-invariant (Phase 26 architecture). |
| DIAG-02 | User can evaluate learned weights against uniform and default baselines via evaluate_weights utility | `evaluate_weights(test_models, strategies, ...)` accepts named callables, auto-adds 'uniform', solves each model per strategy, returns dict with metrics. Generalizes existing `evaluate()` pattern. |
| DIAG-03 | Evaluation reports objective improvement and convergence speed relative to baselines | Time-to-best extracted from `OptimizeResult.history` `(value, elapsed_seconds)` tuples. Speedup ratio = `uniform_time / strategy_time`. Report dict includes `mean_objective`, `feasibility_rate`, `mean_time_to_best`, `speedup_vs_uniform`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | (existing) | Array operations, statistics | Already in project; used for weight arrays, mean/std calculations |
| sklearn | (existing, optional) | ExtraTreesRegressor via WeightPredictor | Already in project as optional dep; no new sklearn features needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | (existing) | Parallel processing (unused here, but in dependency tree) | Already available via sklearn |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom time-to-best parser | scipy signal processing | Overkill -- history is simple list of tuples, plain Python loop suffices |
| Separate convergence analysis lib | pandas DataFrame | Overkill -- metrics are scalar aggregates, numpy.mean is sufficient |

**Installation:**
```bash
# No new dependencies -- uses existing numpy and sklearn from cbqs[ml]
pip install cbqs[ml]
```

## Architecture Patterns

### Recommended Project Structure
```
cbqs/ml/
  __init__.py            # Add evaluate_weights, validate_transfer exports
  training.py            # Add evaluate_weights() and validate_transfer() here
  features.py            # (unchanged)
  adaptation.py          # (unchanged)
tests/
  test_ml_training.py    # Add tests for evaluate_weights and validate_transfer
```

### Pattern 1: Strategy Evaluation Loop (evaluate_weights)
**What:** Generalized version of existing `evaluate()` that accepts any callable strategies and adds convergence speed metrics.
**When to use:** For `evaluate_weights()` implementation.
**Example:**
```python
# Source: Existing evaluate() in cbqs/ml/training.py lines 327-390
def evaluate_weights(test_models, strategies, stopping_time=5, num_workers=2):
    # Auto-add uniform baseline (same as existing evaluate())
    all_strategies = {'uniform': lambda m: np.ones(len(m.variables))}
    all_strategies.update(strategies)

    results = {}
    for strategy_name, weight_fn in all_strategies.items():
        objectives = []
        feasible_count = 0
        times_to_best = []

        for model in test_models:
            weights = weight_fn(model)
            model.set_param('branching_weights', np.asarray(weights, dtype=np.float64))
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)
            # Ensure history is tracked for time-to-best
            model.set_param('track_history', True)

            result = model.solve()

            objectives.append(result.objective)
            if result.feasible:
                feasible_count += 1

            ttb = _compute_time_to_best(result.history, stopping_time)
            times_to_best.append(ttb)

            model.set_param('branching_weights', None)

        n = len(test_models)
        results[strategy_name] = {
            'mean_objective': float(np.mean(objectives)) if objectives else 0.0,
            'feasibility_rate': feasible_count / n if n > 0 else 0.0,
            'mean_time_to_best': float(np.mean(times_to_best)) if times_to_best else 0.0,
        }

    # Compute speedup ratios relative to uniform
    uniform_ttb = results['uniform']['mean_time_to_best']
    for name, metrics in results.items():
        if uniform_ttb > 0:
            metrics['speedup_vs_uniform'] = uniform_ttb / metrics['mean_time_to_best'] if metrics['mean_time_to_best'] > 0 else float('inf')
        else:
            metrics['speedup_vs_uniform'] = 1.0  # Both instant -> no speedup

    _print_evaluation_table(results)
    return results
```

### Pattern 2: Time-to-Best Extraction
**What:** Extract the elapsed time at which the best objective value was first found from solve history.
**When to use:** For computing convergence speed metric from `OptimizeResult.history`.
**Example:**
```python
# Source: cbqs/result.py -- history is list of (value, elapsed_seconds) tuples
def _compute_time_to_best(history, stopping_time):
    """Compute time-to-best from solve history.

    Scans history for the entry with the best objective value and
    returns the elapsed_seconds when it was first achieved.
    If history is empty, returns stopping_time (ceiling penalty).
    """
    if not history:
        return stopping_time

    best_value = max(entry[0] for entry in history)
    # Find first occurrence of best value
    for value, elapsed in history:
        if value == best_value:
            return elapsed

    return stopping_time  # Should not reach here
```

### Pattern 3: Transfer Validation Orchestration (validate_transfer)
**What:** Self-contained function that trains on small models and evaluates on large models.
**When to use:** For `validate_transfer()` implementation.
**Example:**
```python
# Source: Combines collect_training_data + WeightPredictor.fit + evaluate_weights
def validate_transfer(train_models, test_models, n_strategies=10,
                      stopping_time=5, num_workers=2, random_state=None):
    # Step 1: Collect training data from small models
    training_pairs = collect_training_data(
        train_models, n_strategies=n_strategies,
        stopping_time=stopping_time, num_workers=num_workers,
        random_state=random_state,
    )

    # Step 2: Train predictor
    predictor = WeightPredictor(random_state=random_state)
    predictor.fit(training_pairs)

    # Step 3: Evaluate on large models via evaluate_weights
    strategies = {'learned': lambda m: predictor.predict(m)}
    results = evaluate_weights(
        test_models, strategies,
        stopping_time=stopping_time, num_workers=num_workers,
    )

    return results, predictor
```

### Pattern 4: Extended Comparison Table
**What:** Extends existing `_print_comparison_table()` with additional columns for convergence metrics.
**When to use:** For the new table printed by `evaluate_weights()`.
**Example:**
```python
# Source: Existing _print_comparison_table() in training.py lines 300-324
def _print_evaluation_table(results):
    """Print comparison table with convergence speed columns."""
    name_width = max(len(name) for name in results)
    name_width = max(name_width, len("Strategy"))

    header = (f"{'Strategy':<{name_width}}  {'Mean Objective':>15}  "
              f"{'Feasibility Rate':>17}  {'Time-to-Best':>13}  "
              f"{'Speedup vs Uniform':>19}")
    separator = "-" * len(header)

    print(separator)
    print(header)
    print(separator)
    for name, m in results.items():
        print(f"{name:<{name_width}}  {m['mean_objective']:>15.4f}  "
              f"{m['feasibility_rate']:>17.4f}  "
              f"{m['mean_time_to_best']:>13.4f}  "
              f"{m['speedup_vs_uniform']:>19.2f}x")
    print(separator)
```

### Anti-Patterns to Avoid
- **Duplicating solve logic between evaluate_weights and evaluate:** `evaluate_weights()` is the new generalized version; don't copy-paste the solve loop. The existing `evaluate()` remains for backward compatibility and simplicity when a predictor is already available.
- **Modifying OptimizeResult for convergence:** Don't add new fields to OptimizeResult. Time-to-best is derived from the existing `history` attribute at evaluation time.
- **Forcing track_history via model mutation without cleanup:** Must ensure `track_history` is set to True before solve and consider restoring it afterward, although its default is already True.
- **Raw array comparison for time-to-best:** History values may be float; use `>=` comparison with the max value, not `==`, or find the first entry that equals `max()` using numeric comparison.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Training data collection | Custom per-model trial loop | `collect_training_data()` | Already handles strategy generation, solve, ranking, weight cleanup |
| Weight prediction | Custom ML pipeline | `WeightPredictor.fit()/predict()` | Already handles feature extraction, tiling, regression, clipping |
| Feasibility-first ranking | Custom comparison | `_rank_result()` | Already used in collect_training_data and adaptive_solve |
| Table formatting | Custom string building from scratch | Extend `_print_comparison_table()` pattern | Consistent with existing output format |

**Key insight:** Phase 28 is primarily an orchestration and metrics layer. The heavy lifting (training data collection, weight prediction, solver execution) is already implemented in Phases 26-27. The new code should compose existing functions, not reimplement their internals.

## Common Pitfalls

### Pitfall 1: Empty History Edge Case
**What goes wrong:** `OptimizeResult.history` can be empty if `track_history` is False or the solver finds no improvements during the solve window.
**Why it happens:** The default for `track_history` is True, but if a user has changed it, or if the solver times out immediately, history will be `[]`.
**How to avoid:** `_compute_time_to_best()` must handle empty history by returning `stopping_time` as the ceiling penalty. Additionally, `evaluate_weights()` should explicitly set `track_history=True` before each solve.
**Warning signs:** `mean_time_to_best` equals `stopping_time` for all strategies.

### Pitfall 2: Speedup Division by Zero
**What goes wrong:** If uniform baseline's `mean_time_to_best` is 0 (all solves found best immediately at t=0), speedup ratio computation divides by zero.
**Why it happens:** Very small or trivial problems may solve instantly.
**How to avoid:** Guard: if `uniform_ttb == 0`, set `speedup_vs_uniform = 1.0` (no meaningful speedup when baseline is already instant). If strategy's `mean_time_to_best` is 0 and uniform is nonzero, report `float('inf')` or a large cap value.
**Warning signs:** `speedup_vs_uniform` values that are `inf` or `NaN`.

### Pitfall 3: Strategy Name Collision with 'uniform'
**What goes wrong:** User passes a strategy named 'uniform' in the strategies dict, colliding with the auto-added baseline.
**Why it happens:** `evaluate_weights()` auto-adds 'uniform' like `evaluate()` does.
**How to avoid:** Add 'uniform' to `all_strategies` first, then update with user strategies. This way user's 'uniform' override replaces the auto-added one (consistent with dict semantics). Or raise a warning. The existing `evaluate()` pattern adds uniform first and then user baselines override -- follow the same convention.
**Warning signs:** Missing uniform baseline in output or unexpected uniform weights.

### Pitfall 4: Model State Pollution Between Strategies
**What goes wrong:** Weights or params from one strategy leak into the next strategy's solve.
**Why it happens:** Not resetting `branching_weights` to None between strategies or models.
**How to avoid:** Always call `model.set_param('branching_weights', None)` after each solve, exactly as done in existing `evaluate()` and `collect_training_data()`.
**Warning signs:** All strategies producing identical results.

### Pitfall 5: History Value Semantics Across Solver Modes
**What goes wrong:** History `value` field meaning differs between OPTIMIZE mode (objective value) and SATISFY mode (constraint satisfaction count).
**Why it happens:** `OptimizeResult.history` documentation says: "value is the objective for OPTIMIZE mode or the constraint satisfaction count for SATISFY mode."
**How to avoid:** For time-to-best, find the entry with the maximum `value` regardless of mode semantics. The "best" objective in both modes is the highest value in history. This works correctly for both modes.
**Warning signs:** Unexpected time-to-best values for satisfy-mode problems.

## Code Examples

Verified patterns from existing codebase:

### OptimizeResult.history Format
```python
# Source: cbqs/result.py lines 34-37
# history : list of tuple
#     Improvement history. Each entry is (value, elapsed_seconds)
#     where value is the objective for OPTIMIZE mode or the constraint
#     satisfaction count for SATISFY mode.

# Usage example from result.py summary():
first = self.history[0]   # (value, elapsed_seconds)
last = self.history[-1]    # (value, elapsed_seconds)
# first[0] = value, first[1] = elapsed_seconds
```

### Existing evaluate() Pattern (to generalize)
```python
# Source: cbqs/ml/training.py lines 327-390
def evaluate(predictor, test_models, stopping_time=5, num_workers=2, baselines=None):
    strategies = {
        'predicted': lambda m: predictor.predict(m),
        'uniform': lambda m: np.ones(len(m.variables)),
    }
    if baselines is not None:
        strategies.update(baselines)

    results = {}
    for strategy_name, weight_fn in strategies.items():
        objectives = []
        feasible_count = 0
        for model in test_models:
            weights = weight_fn(model)
            model.set_param('branching_weights', np.asarray(weights, dtype=np.float64))
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)
            result = model.solve()
            objectives.append(result.objective)
            if result.feasible:
                feasible_count += 1
            model.set_param('branching_weights', None)
        n_models = len(test_models)
        results[strategy_name] = {
            'mean_objective': float(np.mean(objectives)) if objectives else 0.0,
            'feasibility_rate': feasible_count / n_models if n_models > 0 else 0.0,
        }
    _print_comparison_table(results)
    return results
```

### Weight Cleanup Pattern
```python
# Source: cbqs/ml/training.py line 292 (collect_training_data)
model.set_param('branching_weights', None)
# Source: cbqs/ml/training.py line 380 (evaluate)
model.set_param('branching_weights', None)
```

### Test Helper Pattern
```python
# Source: tests/test_ml_training.py lines 13-32
def _make_test_model(n_vars):
    m = Model()
    xs = m.add_variables(n_vars)
    if n_vars >= 2:
        m.add_constraint(xs[0] + xs[1] <= 1)
    else:
        m.add_constraint(xs[0] + 0 <= 1)
    obj_expr = xs[0] + 0
    for i in range(1, n_vars):
        obj_expr = obj_expr + xs[i]
    m.set_objective(obj_expr)
    m.close(validate=False)
    return m
```

### __init__.py Export Pattern
```python
# Source: cbqs/ml/__init__.py
from .training import WeightPredictor, collect_training_data, evaluate
from .adaptation import adaptive_solve, AdaptiveResult
__all__ = [
    "FeatureExtractor",
    "WeightPredictor",
    "collect_training_data",
    "evaluate",
    "adaptive_solve",
    "AdaptiveResult",
]
# Phase 28 adds: evaluate_weights, validate_transfer
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `evaluate(predictor, ...)` requires WeightPredictor | `evaluate_weights(models, strategies_dict)` accepts any callables | Phase 28 | More flexible; enables user-defined weight strategies without wrapping in a predictor |
| No convergence speed metrics | Time-to-best from solve history + speedup ratio | Phase 28 | Users can quantify not just quality but speed of convergence |
| Manual train-on-small + predict-on-large workflow | `validate_transfer()` one-call orchestration | Phase 28 | Lowers barrier to validating transfer learning |

**Deprecated/outdated:**
- None. The existing `evaluate()` function remains for backward compatibility and simple predictor-vs-uniform comparisons. `evaluate_weights()` is the new generalized version.

## Open Questions

1. **track_history default behavior**
   - What we know: `track_history` defaults to True in Model (line 112 of Model.pyx). So `evaluate_weights()` should get history by default.
   - What's unclear: Whether setting it explicitly to True is redundant or protective.
   - Recommendation: Set it explicitly to True in `evaluate_weights()` for defensive programming, since users may have changed the default. Cost is zero, safety is high.

2. **validate_transfer return type**
   - What we know: CONTEXT.md says "returns both the evaluation results AND the fitted WeightPredictor."
   - What's unclear: Whether to return a tuple `(results, predictor)` or a named container.
   - Recommendation: Return a plain tuple `(results, predictor)` for simplicity. This matches Python conventions for functions returning multiple values. A dedicated dataclass would be overkill for two return values.

3. **evaluate_weights stopping_time for time-to-best ceiling**
   - What we know: CONTEXT.md says "if best is found at the end or never improves, time_to_best = stopping_time."
   - What's unclear: The `stopping_time` param is in seconds, but `OptimizeResult.solve_time` is in milliseconds. Need to confirm history elapsed_seconds units.
   - Recommendation: History uses elapsed_seconds (confirmed in `result.py` line 35 and `SearchLib.pyx` callback). The `stopping_time` param passed to `set_param` is in seconds. Units are consistent -- no conversion needed.

## Sources

### Primary (HIGH confidence)
- `cbqs/ml/training.py` -- existing `evaluate()`, `collect_training_data()`, `_print_comparison_table()`, `_rank_result()` patterns (read in full)
- `cbqs/ml/features.py` -- `FeatureExtractor`, feature names, per-variable architecture (read in full)
- `cbqs/ml/adaptation.py` -- `adaptive_solve()`, `AdaptiveResult` patterns (read in full)
- `cbqs/ml/__init__.py` -- current exports (read in full)
- `cbqs/result.py` -- `OptimizeResult` with `history` as `(value, elapsed_seconds)` tuples (read in full)
- `cbqs/Model.pyx` -- `track_history` parameter default True, solve flow (grep verified)
- `tests/test_ml_training.py` -- test patterns, `_make_test_model` helper (read in full)
- `tests/test_ml_adaptation.py` -- test patterns for Phase 27 (read in full)

### Secondary (MEDIUM confidence)
- `cbqs/SearchLib.pyx` -- history callback implementation confirming elapsed_seconds units (grep verified)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all tools already in project
- Architecture: HIGH -- directly follows existing evaluate() and collect_training_data() patterns with well-defined extensions
- Pitfalls: HIGH -- edge cases identified from reading actual code (empty history, division by zero, state cleanup)

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable domain -- pure Python utility functions over existing API)
