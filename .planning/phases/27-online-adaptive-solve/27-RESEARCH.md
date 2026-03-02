# Phase 27: Online Adaptive Solve - Research

**Researched:** 2026-03-02
**Domain:** Online adaptation loop with EMA weight updates for CBQS solver
**Confidence:** HIGH

## Summary

Phase 27 implements a multi-round adaptive solve function (`adaptive_solve`) that iteratively improves branching weights between solve rounds using Exponential Moving Average (EMA) updates. The implementation lives entirely in `cbqs/ml/adaptation.py` (currently a stub) and follows the established standalone-function-in-ML-module pattern from Phase 26's `collect_training_data()` and `evaluate()`.

The core challenge is designing the reward signal that combines objective improvement rate and constraint satisfaction rate (ADAPT-02), while maintaining determinism (ADAPT-03) and thread safety (ADAPT-04). The existing codebase provides all necessary building blocks: `Model.set_param('branching_weights', ...)` for applying weights, `Model.solve()` for per-round execution, `np.random.RandomState` for deterministic RNG, and `_rank_result()` for feasibility-first ranking.

**Primary recommendation:** Implement `adaptive_solve()` and `AdaptiveResult` as a TDD two-plan phase: Plan 01 covers the core adaptive loop with EMA updates and AdaptiveResult (ADAPT-01, ADAPT-02), Plan 02 covers determinism and thread safety testing (ADAPT-03, ADAPT-04). Both plans are wave 1 since the thread safety tests exercise the same function.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Standalone function `adaptive_solve(model, ...)` in `cbqs.ml.adaptation` -- mirrors `collect_training_data()` pattern
- Returns `AdaptiveResult` object with `.best_result`, `.best_weights`, `.history`, `.n_rounds_completed`
- `initial_weights` param accepts either ndarray or WeightPredictor -- if WeightPredictor, calls `predict(model)` automatically; if None, starts uniform
- Explicit key params: `model, n_rounds, stopping_time, num_workers, ema_alpha, seed, initial_weights`
- Fixed number of rounds only -- no convergence detection or early stopping
- Default: 5 rounds
- Same `stopping_time` budget for every round
- Default EMA alpha: 0.3 -- `new_weights = 0.3 * reward_adjusted + 0.7 * old_weights`
- Default to `np.ones(n_vars)` when `initial_weights=None`
- Always copy input weights (never mutate user's array or predictor state)
- Validate `len(initial_weights) == n_vars`, raise ValueError on mismatch
- Clip weights to non-negative after each EMA update
- Print per-round one-line summary by default (verbose param)
- History stores core metrics per round: `{round, objective, feasible, reward, weights}`
- `best_weights` tracks weights from best-performing round (not final EMA'd weights)
- Restore model's `branching_weights` to pre-adaptive state after completion

### Claude's Discretion
- Exact reward signal formula combining objective improvement rate and constraint satisfaction rate
- AdaptiveResult class implementation details (dataclass vs namedtuple vs regular class)
- Determinism implementation (seed propagation to per-round solves)
- Thread safety implementation for concurrent adaptive_solve calls on different models

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ADAPT-01 | User can run an adaptive multi-round solve where weights update between rounds via EMA | Core adaptive loop with EMA formula: `new = alpha * reward_adjusted + (1 - alpha) * old`. AdaptiveResult return type. Per-round solve via set_param + solve pattern. |
| ADAPT-02 | Adaptation uses a combined reward signal (objective improvement rate + constraint satisfaction rate) | Reward signal design: normalized objective delta + feasibility bonus. See Architecture Patterns section for formula. |
| ADAPT-03 | Online adaptation preserves solver determinism (same seed + threads = same result) | Seed propagation via `np.random.RandomState(seed)` for initial weight generation; solver determinism via `set_param('seed', derived_seed)` per round. |
| ADAPT-04 | Online adaptation preserves thread safety (no shared mutable weight arrays between workers) | All state is local to function scope. Weight arrays are copied on input and per-round. No module-level mutable state. Concurrent calls on different models are independent. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | (existing) | Weight arrays, EMA computation, clipping | Already in project, standard for numeric ops |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | AdaptiveResult class | Clean, minimal result container with type hints |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dataclass | namedtuple | dataclass allows mutable defaults and docstrings; namedtuple is immutable but harder to document |
| dataclass | regular class | dataclass reduces boilerplate for pure data containers |

**No new dependencies required.** Everything uses numpy (already installed) and Python stdlib.

## Architecture Patterns

### Module Structure
```
cbqs/ml/
├── __init__.py          # Add adaptive_solve, AdaptiveResult exports
├── features.py          # FeatureExtractor (Phase 25, unchanged)
├── training.py          # WeightPredictor, collect_training_data, evaluate (Phase 26, unchanged)
└── adaptation.py        # adaptive_solve, AdaptiveResult (Phase 27, target)
```

### Pattern 1: Standalone Function with Result Object
**What:** `adaptive_solve(model, ...)` returns `AdaptiveResult`, same as `collect_training_data()` returns list of tuples
**When to use:** For ML utilities that operate on Model instances
**Example:**
```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union
import numpy as np

@dataclass
class AdaptiveResult:
    """Result of an adaptive multi-round solve."""
    best_result: object          # OptimizeResult from best round
    best_weights: np.ndarray     # Weights that produced best_result
    history: List[Dict]          # Per-round metrics
    n_rounds_completed: int      # Total rounds executed

def adaptive_solve(model, n_rounds=5, stopping_time=5, num_workers=2,
                   ema_alpha=0.3, seed=None, initial_weights=None,
                   verbose=True):
    ...
```

### Pattern 2: Weight Initialization with WeightPredictor Duck-Typing
**What:** Accept either ndarray or WeightPredictor as `initial_weights`
**When to use:** When the parameter could be a raw array or a predictor that generates arrays
**Example:**
```python
from cbqs.ml.training import WeightPredictor

def _resolve_initial_weights(initial_weights, model, n_vars):
    if initial_weights is None:
        return np.ones(n_vars)
    if isinstance(initial_weights, WeightPredictor):
        return initial_weights.predict(model).copy()
    weights = np.array(initial_weights, dtype=np.float64).copy()
    if len(weights) != n_vars:
        raise ValueError(
            f"initial_weights length {len(weights)} != model n_vars {n_vars}"
        )
    return weights
```

### Pattern 3: Reward Signal Formula (ADAPT-02)
**What:** Combined reward that balances objective improvement and constraint satisfaction
**When to use:** To compute per-round weight adjustment direction

**Recommended formula:**
```python
def _compute_reward(current_result, prev_result, weights, n_vars):
    """Compute per-variable reward signal for EMA weight update.

    The reward combines two signals:
    1. Feasibility bonus: 1.0 if feasible, 0.0 if not
    2. Objective improvement rate: normalized delta from previous round

    Combined: reward = feasibility_weight * feasibility + (1 - feasibility_weight) * obj_improvement
    Default feasibility_weight = 0.5 (equal weighting)

    The reward is broadcast to all variables (uniform signal) and used as the
    "ideal weights" target in the EMA update. This means:
    - Good rounds (high reward) pull weights toward current values
    - Bad rounds (low reward) pull weights away from current values
    """
    # Feasibility component: binary 0/1
    feasibility = 1.0 if current_result.feasible else 0.0

    # Objective improvement component: normalized to [0, 1]
    if prev_result is not None and prev_result.objective != 0:
        obj_delta = (current_result.objective - prev_result.objective) / abs(prev_result.objective)
        obj_improvement = max(0.0, min(1.0, obj_delta))  # clamp to [0, 1]
    else:
        obj_improvement = 0.5  # neutral for first round

    # Combined reward: weighted average
    reward = 0.5 * feasibility + 0.5 * obj_improvement

    # Scale current weights by reward to create adjustment target
    # High reward -> target near current weights (reinforce)
    # Low reward -> target near zero (reduce these weights)
    reward_adjusted = reward * weights

    return reward, reward_adjusted
```

**EMA update:**
```python
# alpha = 0.3 by default
# new_weights = alpha * reward_adjusted + (1 - alpha) * old_weights
new_weights = ema_alpha * reward_adjusted + (1 - ema_alpha) * current_weights
new_weights = np.clip(new_weights, 0, None)  # enforce non-negative
```

**Rationale:** This approach:
- Satisfies ADAPT-02: combines both objective improvement rate AND constraint satisfaction rate
- Is simple and deterministic (no randomness in reward computation)
- Scales naturally: feasibility is binary, objective improvement is normalized
- The reward-scaled weights create a natural "reinforce good weights, dampen bad weights" dynamic

### Pattern 4: Determinism via Seed Propagation (ADAPT-03)
**What:** Derive per-round seeds from a master RNG to ensure reproducibility
**IMPORTANT:** `seed` is a direct property on Model (`model.seed = value`), NOT a set_param key. It is not in `_PARAM_DEFS`. Use property assignment, not `set_param('seed', ...)`.
**Example:**
```python
rng = np.random.RandomState(seed)
for round_idx in range(n_rounds):
    round_seed = int(rng.randint(0, 2**31))
    model.seed = round_seed       # Property, NOT set_param!
    model.set_param('branching_weights', current_weights.copy())
    model.set_param('stopping_time', stopping_time)
    model.set_param('num_workers', num_workers)
    result = model.solve()
```

### Pattern 5: State Restoration (Thread Safety, ADAPT-04)
**What:** Save and restore model branching_weights before/after adaptive solve
**Example:**
```python
# Save original state
try:
    original_weights = model.get_param('branching_weights')
except:
    original_weights = None

try:
    # ... run adaptive loop ...
    return AdaptiveResult(...)
finally:
    # Restore original state
    model.set_param('branching_weights', original_weights)
```

**Thread safety guarantee:** Since all weight arrays are local variables (copied on input, created fresh each round), concurrent `adaptive_solve()` calls on different Model instances cannot interfere. The function has no module-level mutable state.

### Anti-Patterns to Avoid
- **Mutating input weights:** Always `.copy()` before modifying. The user's array or predictor state must not change.
- **Module-level weight storage:** Never store weights in global/module variables. All state must be function-local.
- **Convergence detection:** The user explicitly requested fixed round count only. Do not add early stopping.
- **Per-round different stopping_time:** Same budget for every round as specified in CONTEXT.md.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Result ranking | Custom comparator | `_rank_result()` from training.py | Already handles feasibility-first ranking correctly |
| Weight clipping | Custom clipping | `np.clip(weights, 0, None)` | Standard numpy, matches WeightPredictor convention |
| Feature extraction for initial weights | Custom feature code | `WeightPredictor.predict(model)` | Duck-typing check, already handles extraction internally |

## Common Pitfalls

### Pitfall 1: Mutating Shared Weight Arrays
**What goes wrong:** If the same weight array reference is stored in history AND used for next round, modifications corrupt history.
**Why it happens:** Python passes arrays by reference; `weights` assigned to history and also used in EMA update.
**How to avoid:** `.copy()` before storing in history and before EMA update.
**Warning signs:** History entries all showing the same weights values.

### Pitfall 2: Non-Deterministic Seed Propagation
**What goes wrong:** If seed is not propagated to per-round solves, results vary between runs.
**Why it happens:** The solver has its own internal RNG; without explicit seed, it uses system entropy.
**How to avoid:** Derive per-round seeds from `np.random.RandomState(seed)` and pass via `set_param('seed', round_seed)`.
**Warning signs:** Test `test_determinism` fails intermittently.

### Pitfall 3: Division by Zero in Objective Improvement
**What goes wrong:** If previous objective is 0, computing `delta / abs(prev_objective)` raises ZeroDivisionError.
**Why it happens:** Some models have trivial objectives or initial solves may return 0.
**How to avoid:** Guard with `if prev_result is not None and prev_result.objective != 0`.
**Warning signs:** ZeroDivisionError during adaptive solve on models with zero objective.

### Pitfall 4: Forgetting to Restore Model State
**What goes wrong:** After adaptive_solve, model retains the last round's branching_weights.
**Why it happens:** Missing cleanup in error paths.
**How to avoid:** Use try/finally to restore original branching_weights.
**Warning signs:** Subsequent operations on the model use unexpected weights.

### Pitfall 5: WeightPredictor Import at Module Level
**What goes wrong:** Circular import or unnecessary import failure if WeightPredictor is imported at top of adaptation.py.
**Why it happens:** adaptation.py importing from training.py which might transitively import.
**How to avoid:** Import WeightPredictor inside the function or use `isinstance` check with a late import. Since both are in the same package, a direct import from `.training` should be safe, but test it.
**Warning signs:** ImportError when importing cbqs.ml.adaptation.

## Code Examples

### Complete Adaptive Solve Loop
```python
def adaptive_solve(model, n_rounds=5, stopping_time=5, num_workers=2,
                   ema_alpha=0.3, seed=None, initial_weights=None,
                   verbose=True):
    n_vars = len(model.variables)

    # Resolve initial weights
    current_weights = _resolve_initial_weights(initial_weights, model, n_vars)

    # Save original state for restoration
    original_weights = model.get_param('branching_weights')

    # Deterministic RNG for per-round seeds
    rng = np.random.RandomState(seed)

    history = []
    best_result = None
    best_weights = None
    prev_result = None

    try:
        for round_idx in range(n_rounds):
            # Set per-round solver parameters
            round_seed = int(rng.randint(0, 2**31))
            model.seed = round_seed  # Property, NOT set_param
            model.set_param('branching_weights', current_weights.copy())
            model.set_param('stopping_time', stopping_time)
            model.set_param('num_workers', num_workers)

            result = model.solve()

            # Compute reward signal
            reward, reward_adjusted = _compute_reward(
                result, prev_result, current_weights, n_vars
            )

            # Track best round
            if best_result is None or _rank_result(result) > _rank_result(best_result):
                best_result = result
                best_weights = current_weights.copy()

            # Record history
            weight_delta = 0.0
            history.append({
                'round': round_idx + 1,
                'objective': result.objective,
                'feasible': result.feasible,
                'reward': reward,
                'weights': current_weights.copy(),
            })

            # Verbose output
            if verbose:
                print(f"Round {round_idx + 1}/{n_rounds}: "
                      f"obj={result.objective}, "
                      f"feasible={result.feasible}, "
                      f"reward={reward:.4f}")

            # EMA weight update (skip after last round)
            if round_idx < n_rounds - 1:
                new_weights = ema_alpha * reward_adjusted + (1 - ema_alpha) * current_weights
                new_weights = np.clip(new_weights, 0, None)
                current_weights = new_weights

            prev_result = result

        return AdaptiveResult(
            best_result=best_result,
            best_weights=best_weights,
            history=history,
            n_rounds_completed=n_rounds,
        )

    finally:
        model.set_param('branching_weights', original_weights)
```

### Testing Determinism (ADAPT-03)
```python
def test_adaptive_solve_deterministic():
    model = _make_test_model(10)
    r1 = adaptive_solve(model, n_rounds=3, stopping_time=2, num_workers=1,
                        seed=42, verbose=False)
    r2 = adaptive_solve(model, n_rounds=3, stopping_time=2, num_workers=1,
                        seed=42, verbose=False)
    assert r1.n_rounds_completed == r2.n_rounds_completed
    for h1, h2 in zip(r1.history, r2.history):
        np.testing.assert_array_equal(h1['weights'], h2['weights'])
        assert h1['objective'] == h2['objective']
        assert h1['feasible'] == h2['feasible']
```

### Testing Thread Safety (ADAPT-04)
```python
import threading

def test_concurrent_adaptive_solves():
    model1 = _make_test_model(5)
    model2 = _make_test_model(8)
    results = [None, None]
    errors = [None, None]

    def run(idx, model):
        try:
            results[idx] = adaptive_solve(model, n_rounds=3, stopping_time=2,
                                          num_workers=1, seed=42, verbose=False)
        except Exception as e:
            errors[idx] = e

    t1 = threading.Thread(target=run, args=(0, model1))
    t2 = threading.Thread(target=run, args=(1, model2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors[0] is None, f"Thread 1 error: {errors[0]}"
    assert errors[1] is None, f"Thread 2 error: {errors[1]}"
    assert results[0].best_weights.shape == (5,)
    assert results[1].best_weights.shape == (8,)
```

## Open Questions

1. **Model.get_param('branching_weights') behavior when unset**
   - What we know: `set_param('branching_weights', None)` resets weights in collect_training_data. `get_param` returns the default from `_PARAM_DEFS` if not explicitly set (default for branching_weights is None).
   - Resolution: `get_param('branching_weights')` returns None when never set -- safe to use for save/restore.

2. **RESOLVED: Model.seed is a property, NOT a set_param key**
   - `seed` is NOT in `_PARAM_DEFS`. It's a direct property: `model.seed = 42` (setter validates int or None).
   - `model.seed_used` returns the actual seed used after solve (populated by SearchLib).
   - For determinism: set `model.seed = derived_int` before each round's `model.solve()`.

## Sources

### Primary (HIGH confidence)
- `cbqs/ml/training.py` - Established patterns for standalone ML functions (collect_training_data, evaluate, _rank_result)
- `cbqs/ml/features.py` - Feature extraction patterns (FeatureExtractor, VARIABLE_FEATURE_NAMES)
- `cbqs/ml/__init__.py` - Module export patterns
- `.planning/phases/26-offline-training-pipeline/26-01-PLAN.md` - Plan format reference
- `.planning/phases/26-offline-training-pipeline/26-02-PLAN.md` - Plan format reference

### Secondary (MEDIUM confidence)
- EMA weight update formula is standard in online learning literature
- Reward signal design follows common multi-objective optimization patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, no new deps
- Architecture: HIGH - follows established Phase 26 patterns exactly
- Pitfalls: HIGH - identified from direct codebase analysis of collect_training_data
- Reward signal: MEDIUM - formula is Claude's discretion, design is reasonable but could be tuned

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable domain, no external dependency changes expected)
