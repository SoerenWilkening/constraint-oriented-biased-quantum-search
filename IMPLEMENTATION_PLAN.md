# Implementation Plan: Polynomial ES Training Pipeline

## Context

The current ExtraTreesRegressor ML pipeline fails at bias prediction (predicts ~30 vs correct ~750 for n=3000), uses the wrong training signal (AUC rewards greedy feasibility over quality), and can't generalize across instance sizes. This plan replaces it with a degree-2 polynomial model (344 coefficients) trained via evolutionary strategy gradient estimation, per PRD.md and ml-pipeline-specs-v2.md.

## Dependency Graph

```
M1 (polynomial.py) ----+----> M3 (es_evaluator.py) ----+
                        |                                |
M2 (adam.py) -----------+----> M4 (es_checkpoint.py) ---+--> M5 (es_trainer.py) --> M6 (integration)
```

M1 & M2 can be developed in parallel. Each milestone is one beads issue.

---

## M1: Polynomial Expansion & Predictor

**Issue**: `feat(ES-M1): polynomial expansion, pack/unpack theta, PolynomialPredictor`
**Deps**: None
**Files**: `cbqs/ml/polynomial.py` (~250 LOC), `tests/test_polynomial.py` (~300 LOC)

**What it does**:
- `poly_expand(X, degree=2)` — 9 features -> 55 terms, 11 features -> 78 terms (1 + n + n*(n-1)/2 + n)
- `pack_theta(W_var, W_inst) -> theta[344]`, `unpack_theta(theta) -> (W_var[2,55], W_inst[3,78])`
- `PolynomialPredictor(theta)` with `.predict(model) -> dict`, `.save(path)`, `.load(path)`
- Post-processing: `bias = n/4 + clip(delta, +/-3% n/4)`, factors clipped >= 0

**Tests**: shape correctness, value correctness (known inputs), pack/unpack roundtrip, zero-theta produces bias=n/4, clipping, save/load roundtrip

**Reuses**: `FeatureExtractor` from `cbqs/ml/features.py`

---

## M2: Adam Optimizer

**Issue**: `feat(ES-M2): standalone Adam optimizer for ES training`
**Deps**: None
**Files**: `cbqs/ml/adam.py` (~100 LOC), `tests/test_adam.py` (~150 LOC)

**What it does**:
- `Adam(lr=0.001, beta1=0.9, beta2=0.999, eps=1e-8)`
- `.step(theta, gradient) -> theta_new` (immutable)
- `.state_dict()` / `.load_state_dict(d)` for checkpoint support

**Tests**: single step changes theta, convergence on f(x)=x^2, state_dict roundtrip preserves exact behavior

---

## M3: ES Evaluator

**Issue**: `feat(ES-M3): evaluation function wiring predictor to solver`
**Deps**: M1
**Files**: `cbqs/ml/es_evaluator.py` (~120 LOC), `tests/test_es_evaluator.py` (~200 LOC)

**What it does**:
- `evaluate(theta, model, time_budget) -> (best_objective, -time_to_best)`
- `normalize_signals(diffs) -> zero-mean, unit-var` (per-instance normalization before gradient aggregation)
- Creates PolynomialPredictor from theta, sets params on model, calls solve()

**Tests**: correct tuple structure, all param keys set on model, normalization zero-mean/unit-var, constant-signal edge case, bias always in valid range

**Reuses**: `PolynomialPredictor` from M1

---

## M4: Checkpoint Save/Load/Resume

**Issue**: `feat(ES-M4): ES checkpoint save, load, and resume support`
**Deps**: M2
**Files**: `cbqs/ml/es_checkpoint.py` (~150 LOC), `tests/test_es_checkpoint.py` (~200 LOC)

**What it does**:
- `save_checkpoint(path, theta, optimizer, step, config, pool, best_theta, best_signal)`
- `load_checkpoint(path) -> dict` with all fields
- `add_instances(checkpoint_path, new_paths)` to extend training pool
- Format: `.npz` for arrays + `.json` sidecar for metadata (no pickle)

**Tests**: save/load roundtrip, add instances, missing optional fields use defaults, corrupt checkpoint error

---

## M5: ES Training Loop

**Issue**: `feat(ES-M5): ES training loop with antithetic sampling`
**Deps**: M1, M2, M3, M4
**Files**: `cbqs/ml/es_trainer.py` (~350 LOC), `tests/test_es_trainer.py` (~350 LOC)

**What it does**:
- `ESTrainerConfig` dataclass: lr, sigma, K, batch_size, max_steps, checkpoint_interval, eval_time, delta_pct
- `ESTrainer(config, theta_init=None, log_path=None)`
- `.train(training_pool, validation_pool=None) -> theta`
- `.resume(checkpoint_path, training_pool=None) -> theta`
- Per-step: sample batch, K antithetic perturbation pairs, normalize signals per-instance, estimate gradient, Adam update, log, periodic checkpoint

**Tests**: theta changes after step, antithetic sampling verified, checkpoint at correct intervals, resume continues correctly, constant signals produce zero gradient, config validation

**Reuses**: `TrainingLog` from `cbqs/ml/training_log.py` (new ESStepEvent/ESEpochEvent types)

---

## M6: Integration & Entry Point

**Issue**: `feat(ES-M6): integrate ES pipeline, update training entry point`
**Deps**: M5
**Files modified**: `training/train.py`, `cbqs/ml/__init__.py`, `cbqs/ml/signals.py`
**Files created**: `tests/test_es_integration.py` (~250 LOC)

**What it does**:
- Add `train_es()` to `training/train.py` with `--mode es` CLI argument
- Export `PolynomialPredictor`, `ESTrainer`, `ESTrainerConfig` from `cbqs/ml/__init__.py`
- End-to-end: generate instances -> train -> checkpoint -> predict

**Tests**: end-to-end on small knapsack (3 steps), loaded predictor produces valid predictions, bias near n/4 for various sizes, old trainers still work, CLI argument parsing

**Reuses**: instance generators from `training/train.py` (`make_random_knapsack`, etc.)

---

## Summary

| Milestone | Module | Est. LOC | Test LOC | Deps |
|-----------|--------|----------|----------|------|
| M1 | `cbqs/ml/polynomial.py` | ~250 | ~300 | -- |
| M2 | `cbqs/ml/adam.py` | ~100 | ~150 | -- |
| M3 | `cbqs/ml/es_evaluator.py` | ~120 | ~200 | M1 |
| M4 | `cbqs/ml/es_checkpoint.py` | ~150 | ~200 | M2 |
| M5 | `cbqs/ml/es_trainer.py` | ~350 | ~350 | M1-M4 |
| M6 | integration | ~150 mod | ~250 | M5 |

## Key Files to Reference
- `cbqs/ml/features.py` — FeatureExtractor (reused as-is)
- `cbqs/ml/regressors.py` — interface pattern to follow for PolynomialPredictor
- `cbqs/ml/exploration_trainer.py` — analogous trainer lifecycle, FakeModel testing pattern
- `ml-pipeline-specs-v2.md` — authoritative spec (theta layout, term counts, hyperparameters)
- `training/train.py` — instance generators, entry point to modify

## Verification
1. Each milestone: `pytest tests/test_<module>.py -v`
2. After M6: `python training/train.py --mode es --max-steps 5 --vars 20` runs without error
3. Acceptance: trained predictor produces bias within +/-3% of n/4 on instances of any size
4. Old pipeline: `python training/train.py --mode sat` still works
