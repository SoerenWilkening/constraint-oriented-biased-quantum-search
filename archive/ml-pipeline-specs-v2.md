# ML Pipeline v2 — Polynomial ES Training Specification

## 1. Motivation

The v1 ML pipeline (ExtraTreesRegressor) produces per-variable weights of reasonable quality but fails at bias prediction (predicts ~30 instead of ~750 for n=3000) and encourages greedy feasibility-finding over objective exploration. The core issues are: (1) tree models cannot extrapolate across instance sizes, (2) AUC signal rewards speed over quality, (3) black-box best-of-N optimization is sample-inefficient.

This specification defines a replacement: **degree-2 polynomial parameter functions** trained via **evolutionary strategy gradient estimation**, predicting perturbations around known-good defaults.

## 2. Model Architecture

### 2.1 Overview

The model consists of two polynomial functions sharing no parameters:

1. **Per-variable polynomial**: maps 9 variable features → (weight, priority) per variable
2. **Instance-level polynomial**: maps 11 instance features → (bias_delta, branching_factor, bias_factor)

Total learnable parameters: ~362 floating-point coefficients.

### 2.2 Per-Variable Polynomial

**Input features** (9, z-score normalized per column across variables within an instance):

| # | Feature | Description |
|---|---------|-------------|
| 1 | `degree` | Number of constraints the variable participates in |
| 2 | `coeff_mean` | Mean absolute coefficient across constraints |
| 3 | `coeff_max` | Max absolute coefficient |
| 4 | `coeff_min` | Min absolute coefficient |
| 5 | `objective_coefficient` | Coefficient in the objective function |
| 6 | `bounds_width` | Upper bound - lower bound |
| 7 | `is_integer` | 1.0 if integer variable, else 0.0 |
| 8 | `avg_neighbor_degree` | Mean degree of co-occurring variables |
| 9 | `num_co_occurring_vars` | Count of unique co-occurring variables |

**Polynomial expansion** (degree 2, full cross-terms):

```
terms(x) = [1,                          # intercept (1)
            x1, x2, ..., x9,            # linear (9)
            x1*x2, x1*x3, ..., x8*x9,  # cross-terms (36)
            x1^2, x2^2, ..., x9^2]      # squared (9)
                                          # Total: 55 terms
```

Note: 1 + 9 + 36 + 9 = 55 terms (not 64 — corrected from earlier estimate).

**Output**: 2 values per variable
```
[weight, priority] = W_var @ terms(x)
```
where `W_var` is a (2 x 55) coefficient matrix = **110 parameters**.

**Post-processing**:
- `weight`: used as-is (perturbation, expected to be small)
- `priority`: used for argsort to determine variable ordering (highest priority first)

### 2.3 Instance-Level Polynomial

**Input features** (11, raw values — not normalized):

| # | Feature | Description |
|---|---------|-------------|
| 1 | `n_variables` | Number of variables |
| 2 | `n_constraints` | Number of constraints |
| 3 | `constraint_density` | n_constraints / n_variables |
| 4 | `constraint_variable_ratio` | Same as density |
| 5 | `objective_density` | Fraction of variables with nonzero objective |
| 6 | `integer_variable_fraction` | Fraction of integer variables |
| 7 | `coeff_mean` | Global mean of absolute coefficients |
| 8 | `coeff_std` | Global std of absolute coefficients |
| 9 | `coeff_max` | Global max absolute coefficient |
| 10 | `bounds_tightness_mean` | Mean of (ub - lb) across variables |
| 11 | `bounds_tightness_std` | Std of (ub - lb) across variables |

**Polynomial expansion** (degree 2, full cross-terms):

```
terms(z) = [1,                             # intercept (1)
            z1, z2, ..., z11,              # linear (11)
            z1*z2, z1*z3, ..., z10*z11,    # cross-terms (55)
            z1^2, z2^2, ..., z11^2]        # squared (11)
                                            # Total: 78 terms
```

**Output**: 3 values
```
[bias_delta, branching_factor, bias_factor] = W_inst @ terms(z)
```
where `W_inst` is a (3 x 78) coefficient matrix = **234 parameters**.

**Post-processing**:
- `bias = n/4 + clip(bias_delta, -0.03 * n/4, +0.03 * n/4)`
- `branching_factor = max(0, branching_factor)`
- `bias_factor = max(0, bias_factor)`

### 2.4 Total Parameter Count

| Component | Coefficients |
|-----------|-------------|
| Per-variable polynomial (2 outputs x 55 terms) | 110 |
| Instance-level polynomial (3 outputs x 78 terms) | 234 |
| **Total** | **344** |

### 2.5 Coefficient Vector Layout

All coefficients are packed into a single flat vector `theta` of length 344:

```
theta[0:110]    = W_var flattened (weight coefficients, then priority coefficients)
theta[110:344]  = W_inst flattened (bias_delta, branching_factor, bias_factor coefficients)
```

## 3. Training Algorithm

### 3.1 Evolutionary Strategy (ES) with Antithetic Sampling

The solver is a black-box function — we cannot backpropagate through it. Instead, we estimate gradients numerically using random perturbations.

**Algorithm**:

```python
def train(theta_init, training_pool, config):
    theta = theta_init  # (344,) vector, zeros or small random
    optimizer = Adam(lr=config.learning_rate)  # default lr=0.001

    for step in range(config.max_steps):
        # Sample training batch
        batch = random.sample(training_pool, config.batch_size)  # default 5

        # Generate perturbations
        epsilons = [np.random.randn(len(theta)) for _ in range(config.K)]  # default K=50

        # Evaluate all perturbations on all batch instances
        gradient = np.zeros_like(theta)
        for instance in batch:
            for epsilon in epsilons:
                signal_plus  = evaluate(theta + config.sigma * epsilon, instance)
                signal_minus = evaluate(theta - config.sigma * epsilon, instance)
                gradient += (signal_plus - signal_minus) * epsilon

        gradient /= (2 * config.sigma * config.K * config.batch_size)

        # Update
        theta = optimizer.step(theta, gradient)

        # Log
        log_step(step, theta, gradient, batch_signals)

        # Checkpoint
        if step % config.checkpoint_interval == 0:
            save_checkpoint(theta, optimizer, training_pool, step)

    return theta
```

### 3.2 Hyperparameters

| Parameter | Symbol | Default | Description |
|-----------|--------|---------|-------------|
| Learning rate | lr | 0.001 | Adam optimizer learning rate |
| Perturbation scale | sigma | 0.02 | Std dev of perturbation vectors |
| Perturbations per step | K | 50 | Number of perturbation directions |
| Batch size | batch_size | 5 | Training instances per step |
| Max steps | max_steps | 1000 | Training budget |
| Checkpoint interval | checkpoint_interval | 50 | Steps between checkpoints |
| Solver time budget | eval_time | instance-dependent | Time budget per solver evaluation |
| Delta bound | delta_pct | 0.03 | Max bias delta as fraction of n/4 |

### 3.3 Evaluation Function

```python
def evaluate(theta, instance):
    W_var, W_inst = unpack(theta)

    # Per-variable predictions
    var_features = extract_variable_features(instance)    # (n_vars, 9)
    var_features_norm = zscore_normalize(var_features)     # per-column z-score
    var_terms = poly_expand(var_features_norm, degree=2)   # (n_vars, 55)
    var_out = var_terms @ W_var.T                          # (n_vars, 2)
    weights = var_out[:, 0]
    priorities = var_out[:, 1]

    # Instance-level predictions
    inst_features = extract_instance_features(instance)    # (11,)
    inst_terms = poly_expand(inst_features, degree=2)      # (78,)
    inst_out = W_inst @ inst_terms                         # (3,)

    # Post-process
    n = instance.n_variables
    bias_delta = np.clip(inst_out[0], -0.03 * n/4, 0.03 * n/4)
    bias = n / 4 + bias_delta
    branching_factor = max(0.0, inst_out[1])
    bias_factor = max(0.0, inst_out[2])

    # Solve
    instance.set_param('branching_weights', weights)
    instance.set_param('variable_priorities', priorities)
    instance.set_param('branching_bias', bias)
    instance.set_param('branching_factor', branching_factor)
    instance.set_param('bias_factor', bias_factor)

    result = instance.solve(time_budget=config.eval_time)

    # Signal: best objective (primary), faster is better (tiebreaker)
    return (result.best_objective, -result.time_to_best)
```

Signal comparison: tuples are compared lexicographically — best_objective dominates, time_to_best breaks ties.

### 3.4 Signal Normalization

Since different instances have different objective scales, signals should be normalized per-instance before averaging across the batch:

```python
# Per-instance: normalize signals across perturbations to zero mean, unit variance
signals_for_instance = [signal_plus_k - signal_minus_k for k in range(K)]
normalized = (signals_for_instance - mean) / (std + 1e-8)
# Use normalized signals for gradient computation
```

This ensures no single instance dominates the gradient due to its objective scale.

## 4. Incremental Training

### 4.1 Checkpoint Format

```python
checkpoint = {
    'theta': np.array,            # (344,) coefficient vector
    'optimizer_state': dict,       # Adam moments (m, v, step count)
    'training_pool': list,         # paths to training instance files
    'step': int,                   # current training step
    'config': dict,                # training hyperparameters
    'log_path': str,               # path to training log file
    'best_theta': np.array,        # best theta by validation signal
    'best_validation_signal': float
}
```

### 4.2 Resumption

```python
def resume_training(checkpoint_path, new_instances=None):
    ckpt = load_checkpoint(checkpoint_path)
    if new_instances:
        ckpt['training_pool'].extend(new_instances)
    return train(ckpt['theta'], ckpt['training_pool'], ckpt['config'],
                 optimizer_state=ckpt['optimizer_state'],
                 start_step=ckpt['step'])
```

### 4.3 Adding New Instances

New training instances can be added at any time between or during training sessions. The ES algorithm naturally adapts — new instances appear in sampled batches and shift the gradient toward configurations that also work for them.

No retraining from scratch is needed. The coefficient vector smoothly evolves to accommodate the expanded training distribution.

## 5. Training Logging

### 5.1 Per-Step Log Entry

```json
{
    "step": 42,
    "mean_signal": 1523.4,
    "best_signal_this_step": 1612.0,
    "best_signal_overall": 1650.3,
    "gradient_norm": 0.0023,
    "theta_norm": 1.45,
    "batch_instance_ids": ["knapsack_50_01", "maxcut_100_03", ...],
    "timestamp": "2026-03-17T14:30:00"
}
```

### 5.2 Per-Epoch Log Entry (full pass over pool)

```json
{
    "epoch": 3,
    "step_range": [200, 300],
    "mean_signal_all_instances": 1580.2,
    "std_signal_all_instances": 45.3,
    "theta_snapshot": [0.01, -0.003, ...],
    "validation_signal": 1545.0,
    "timestamp": "2026-03-17T15:00:00"
}
```

### 5.3 Display Interface

```python
log = TrainingLog("training_log.json")
log.summary()                    # learning curve: signal vs step
log.plot_learning_curve()        # matplotlib plot
log.theta_at_step(step)          # retrieve coefficients at any step
log.compare(other_log)           # side-by-side comparison
```

## 6. Prediction (Deployment)

At deployment time, prediction is a simple polynomial evaluation:

```python
class PolynomialPredictor:
    def __init__(self, theta):
        self.W_var, self.W_inst = unpack(theta)

    def predict(self, model):
        # Per-variable
        vf = extract_variable_features(model)
        vf_norm = zscore_normalize(vf)
        vt = poly_expand(vf_norm, degree=2)
        var_out = vt @ self.W_var.T
        weights, priorities = var_out[:, 0], var_out[:, 1]

        # Instance-level
        inst_f = extract_instance_features(model)
        inst_t = poly_expand(inst_f, degree=2)
        inst_out = self.W_inst @ inst_t
        n = model.n_variables
        bias = n/4 + np.clip(inst_out[0], -0.03*n/4, 0.03*n/4)
        branching_factor = max(0.0, inst_out[1])
        bias_factor = max(0.0, inst_out[2])

        return {
            'branching_weights': weights,
            'variable_priorities': priorities,
            'branching_bias': bias,
            'branching_factor': branching_factor,
            'bias_factor': bias_factor,
        }

    def save(self, path):
        np.savez(path, theta=pack(self.W_var, self.W_inst))

    @classmethod
    def load(cls, path):
        data = np.load(path)
        return cls(data['theta'])
```

## 7. Integration with Existing Infrastructure

### 7.1 Reused Components
- **Feature extraction** (`cbqs/ml/features.py`): `extract_variable_features()`, `extract_instance_features()` — no changes
- **Phase-specific parameters**: Three `BranchingStats_t` in `solver_ctx_t` — no changes
- **Variable ordering**: Priority-based ordering in CSearch functions — no changes
- **Model API**: `model.set_param()`, `model.solve()` — no changes

### 7.2 Replaced Components
- `cbqs/ml/regressors.py` — ExtraTreesRegressor wrappers → `PolynomialPredictor`
- `cbqs/ml/data_collection.py` — Random sampling + best-of-N → ES training loop
- `cbqs/ml/signals.py` — AUC computation → best-objective signal
- `cbqs/ml/sat_trainer.py` — SATTrainer class → `ESTrainer`
- `cbqs/ml/opt_trainer.py` — OPTTrainer class → `ESTrainer`
- `cbqs/ml/exploration_trainer.py` — ExplorationTrainer class → `ESTrainer`

### 7.3 New Components
- `cbqs/ml/polynomial.py` — Polynomial expansion and predictor class
- `cbqs/ml/es_trainer.py` — ES training loop with Adam optimizer
- `cbqs/ml/checkpoint.py` — Checkpoint save/load/resume

## 8. Implementation Order

1. **Polynomial expansion and predictor**: `polynomial.py` — expand features, evaluate, pack/unpack theta
2. **Evaluation function**: Wire predictor to solver, compute signal
3. **ES training loop**: `es_trainer.py` — perturbation sampling, gradient estimation, Adam updates
4. **Checkpointing**: Save/load/resume support
5. **Training logging**: Per-step and per-epoch JSON logging
6. **Integration**: Replace old pipeline imports, update training scripts
7. **Validation**: Train on small instances, test on large instances, compare to `n/4` baseline

## 9. Resolved Design Decisions

### 9.1 Polynomial Degree
**Decision**: Degree 2 with full cross-terms. Degree 3 was considered but rejected due to parameter explosion (~300+ terms for 9 features). Can be revisited if degree 2 proves insufficient.

### 9.2 Bias Representation
**Decision**: Structural scaling (`n/4 + bounded delta`) rather than learned absolute value. Previous attempt to learn `n/4` directly failed. The ±3% bound is configurable.

### 9.3 Training Signal
**Decision**: Best objective found (primary), time-to-best as tiebreaker. Replaces AUC, which over-rewarded early feasibility.

### 9.4 Single Trainer
**Decision**: One `ESTrainer` replaces the separate SAT/OPT/Exploration trainers. Phase-specific parameters are handled by the polynomial outputs, not by separate training pipelines.

### 9.5 Per-Variable vs. Functional Prediction
**Decision**: Polynomial function applied per-variable (not per-variable free parameters). This enables generalization across instance sizes — the same function produces appropriate weights regardless of n.
