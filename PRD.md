# Product Requirements Document: CBQS Polynomial ES Training Pipeline

**Version**: 3.0
**Date**: 2026-03-17
**Status**: Draft

---

## 1. Executive Summary

The current ML pipeline for the CBQS solver uses ExtraTreesRegressor to predict per-variable branching parameters. While per-variable weights show reasonable quality, the approach suffers from three critical problems: (1) predicted bias values are far too small relative to the known-good default of `n/4`, (2) the AUC-based training signal rewards greedy feasibility-finding over objective quality, and (3) the tree ensemble model does not generalize from small training instances to large deployment instances.

This PRD defines a replacement ML pipeline based on **polynomial parameter functions** trained via **evolutionary strategy (ES) gradient estimation**. The model learns small perturbations around known-good defaults, uses a scale-invariant architecture, and optimizes directly for best objective found.

---

## 2. Problem Statement

### 2.1 Current Limitations

1. **Bias magnitude failure**: For n=3000, the default bias should be ~750 (`n/4`), but the current model predicts ~30. The model fails to learn the n-dependence of bias.

2. **Wrong training signal**: AUC rewards early feasibility over objective quality. The model learns to greedily satisfy constraints rather than explore for better solutions.

3. **Poor size generalization**: ExtraTreesRegressor trained on small instances (n=50-200) cannot extrapolate to large instances (n=3000). Tree models do not extrapolate by nature.

4. **Black-box optimization**: Random parameter sampling with best-of-N selection is sample-inefficient and provides no gradient signal for incremental improvement.

5. **Model loading overhead**: Large ExtraTrees ensembles (high `n_estimators`) take too long to load at prediction time.

6. **Prediction pipeline overhead**: Feature extraction is implemented in pure Python loops over C-backed expression data. Profiling shows this dominates prediction time: ~4.2 seconds for n=3000 (99% of predict() time), scaling O(n²) due to co-occurrence set construction. This overhead eliminates any solver improvement the optimized parameters provide.

### 2.2 Desired Outcome

A lightweight, scale-invariant model that:
- Learns small perturbations around `n/4` (bias) and around zero (weights)
- Trains via gradient-based optimization for sample efficiency
- Generalizes from small/medium instances to large instances by design
- Optimizes for best objective found, not speed-to-feasibility
- Can be incrementally improved by adding more training instances
- Loads instantly (just ~365 floating-point coefficients)
- **Predicts in microseconds, not milliseconds** — feature extraction in C, not Python

---

## 3. Requirements

### 3.1 Functional Requirements

#### FR-1: Polynomial Per-Variable Model
The system SHALL use a degree-2 polynomial function to map the 9 per-variable features to per-variable outputs (branching weight, variable priority).

- Input: 9 z-score-normalized per-variable features
- Output per variable: weight (perturbation), priority score
- Polynomial terms: 9 linear + 45 cross-terms + 9 squared + 1 intercept = 64 coefficients per output
- Total per-variable coefficients: 128 (64 per output x 2 outputs)
- Same function applied to every variable in every instance (scale-invariant)

#### FR-2: Polynomial Instance-Level Model
The system SHALL use a degree-2 polynomial function to map the 11 instance-level features to instance-level outputs.

- Input: 11 instance features (n_variables, n_constraints, constraint_density, etc.)
- Output: bias delta, branching_factor, bias_factor
- Polynomial terms: 11 linear + 55 cross-terms + 11 squared + 1 intercept = 78 coefficients per output
- Total instance-level coefficients: 234 (78 per output x 3 outputs)

#### FR-3: Structural Bias Scaling
The bias output SHALL be computed as `n/4 + delta`, where `delta` is the model's predicted bias delta. The delta SHALL be bounded to `[-0.03 * n/4, +0.03 * n/4]` (±3% of `n/4`). This ensures the model acts as a perturbation around the known-good default, regardless of instance size.

#### FR-4: Training Signal
The training signal SHALL be **best objective value found** within the evaluation time budget (primary), with **time to best solution** as tiebreaker (lower is better). AUC is no longer used as a training signal.

#### FR-5: Evolutionary Strategy Training
The system SHALL train model coefficients using evolutionary strategy (ES) gradient estimation:

1. Maintain a current coefficient vector theta (~365 params)
2. For each update step:
   a. Sample a batch of training instances
   b. Generate K random perturbation vectors (epsilon_k ~ N(0, sigma))
   c. Evaluate theta + epsilon_k and theta - epsilon_k on the batch (antithetic sampling)
   d. Compute estimated gradient: g = (1/K*sigma) * sum(signal_k * epsilon_k)
   e. Update theta via SGD: theta = theta + lr * g
3. Repeat until convergence or budget exhausted

#### FR-6: Incremental Training
Training SHALL support stop/resume and incremental improvement:
- Coefficient checkpoint saves: theta vector + optimizer state + training instance list
- New instances can be added to the training pool at any time
- Training continues from the last checkpoint with the expanded pool
- No retraining from scratch required

#### FR-7: Training Logging
Training SHALL log:
- **Per-step**: current theta, gradient norm, mean signal across batch, best signal seen
- **Per-epoch** (full pass over training pool): mean/std signal, coefficient snapshot
- **Checkpoints**: full state for resumption

Logs SHALL be stored as JSON, queryable via Python API.

#### FR-8: Feature Normalization
Per-variable features SHALL be z-score normalized per column (as currently implemented). Instance features SHALL be used as raw values (as currently implemented).

#### FR-9: Per-Variable Output as Perturbation
Per-variable branching weights SHALL act as perturbations. The polynomial output is used directly as the weight value (not added to a baseline), but the output magnitude is expected to be small due to the training signal favoring exploration.

#### FR-10: Phase-Specific Parameters
The model SHALL output parameters for each solver phase (SAT, OPT-SAT, OPT) as defined in the existing phase-specific parameter infrastructure. Each phase uses its own polynomial coefficients, or a shared polynomial may be used with phase as an additional input.

#### FR-11: C-Level Feature Extraction
Feature extraction SHALL be implemented in C, operating directly on the solver's internal expression data structures (`dyn_expression_t`, variable metadata). A single-pass C function SHALL compute both per-variable features (n_vars × 9) and instance features (11,) in one traversal of the expression data — avoiding the redundant iteration that separate functions would require.

The C function signature:
```c
void extract_features(
    const dyn_expression_t *obj_exprs, int n_obj,
    const dyn_expression_t *con_exprs, int n_con,
    const variable_meta_t *vars, int n_vars,
    double *out_var_features,   // (n_vars * 9) row-major
    double *out_inst_features   // (11,)
);
```

Features SHALL be z-score normalized (per-variable) and raw (instance-level), matching the current Python implementation exactly.

#### FR-12: Consolidated Parameter Setter
A single C function SHALL set all predicted parameters on the solver context, replacing the current ~12 separate Cython→C calls:

```c
void solver_ctx_set_predicted_params(
    solver_ctx_t *ctx,
    double bias, double branching_factor, double bias_factor,
    const double *weights, const int *variable_order, int n
);
```

This writes to all three phase stats (sat, opt_sat, opt) in one call. The Cython layer SHALL expose this as a single function call.

#### FR-13: Option A / Option B Fallback
The initial implementation (Option A) SHALL keep polynomial expansion and matrix multiplication in Python/numpy, with only feature extraction and parameter passing in C. If profiling shows this is insufficient, Option B SHALL move the entire prediction pipeline to C (load theta, extract features, polynomial expand, matmul, clip, write to solver_ctx) with zero Python involvement after initiation.

### 3.2 Non-Functional Requirements

#### NFR-1: Model Size
The complete model SHALL be storable as a single small file (~365 floating-point coefficients + metadata). Loading time SHALL be negligible.

#### NFR-2: Prediction Speed
Prediction for a new instance SHALL complete in sub-millisecond time for instances up to n=3000. Feature extraction in C SHALL be O(n_variables × n_constraints) with no Python loop overhead. The full predict() pipeline (C feature extraction + numpy polynomial math + C parameter setting) SHALL be at least 100x faster than the current pure-Python implementation.

#### NFR-3: Training Compute
Each training step requires 2K solver evaluations per batch instance (K perturbations, antithetic). With K=50 and batch size=5, this is 500 evaluations per step. Training on small instances (n<200) should be fast enough for interactive iteration.

#### NFR-4: Generalization
The model SHALL produce at least as good results as the default `n/4` baseline on instances larger than those seen during training. The bounded delta (±3% of `n/4`) ensures this by construction for bias; per-variable weights generalize via the shared polynomial.

---

## 4. Architecture

### 4.1 Model Architecture

```
Per-Variable Polynomial (shared across all variables):
  Input: x = [degree, coeff_mean, coeff_max, coeff_min, obj_coeff,
              bounds_width, is_integer, avg_neighbor_degree, n_co_occurring]
  (z-score normalized, 9 features)

  Terms: [1, x1, x2, ..., x9, x1*x2, x1*x3, ..., x8*x9, x1^2, ..., x9^2]
  (64 terms)

  Output: [weight, priority] = W_var @ terms
  (W_var is 2 x 64 coefficient matrix = 128 params)

Instance-Level Polynomial:
  Input: z = [n_vars, n_constraints, constraint_density, ..., bounds_tightness_std]
  (11 features, raw values)

  Terms: [1, z1, ..., z11, z1*z2, ..., z10*z11, z1^2, ..., z11^2]
  (78 terms)

  Output: [bias_delta, branching_factor, bias_factor] = W_inst @ terms
  (W_inst is 3 x 78 coefficient matrix = 234 params)

Post-processing:
  bias = n/4 + clip(bias_delta, -0.03 * n/4, +0.03 * n/4)
  weights: used as-is (small perturbations)
  priorities: argsort for variable ordering
  factors: clipped >= 0
```

### 4.2 Training Loop

```
Initialize:
  theta = zeros(362)  # or small random
  optimizer = Adam(lr=0.001)
  training_pool = [list of problem instances]

For each step:
  batch = sample(training_pool, batch_size=5)
  perturbations = [N(0, sigma) for _ in range(K)]  # K=50

  For each instance in batch:
    For each perturbation epsilon_k:
      signal_plus  = evaluate(theta + epsilon_k, instance)
      signal_minus = evaluate(theta - epsilon_k, instance)
      gradient_k = (signal_plus - signal_minus) * epsilon_k / (2 * sigma)

  gradient = mean(all gradient_k)
  theta = optimizer.step(theta, gradient)
  log(step, gradient_norm, mean_signal)

Checkpoint every N steps:
  save(theta, optimizer_state, training_pool)
```

### 4.3 Evaluation Function (Option A: C features + numpy math)

```
evaluate(theta, instance):
  W_var, W_inst = unpack(theta)

  # Feature extraction — C function, single pass over expressions
  var_features, inst_features = c_extract_features(instance)  # C → numpy arrays

  # Polynomial expansion + prediction — numpy (trusted, fast for small matrices)
  var_terms = polynomial_expand(var_features, degree=2)  # (n_vars, 55)
  var_outputs = var_terms @ W_var.T  # (n_vars, 2) -> [weight, priority]

  inst_terms = polynomial_expand(inst_features, degree=2)  # (78,)
  inst_outputs = inst_terms @ W_inst  # (3,) -> [bias_delta, branching_factor, bias_factor]

  # Post-process
  bias = n/4 + clip(inst_outputs[0], -0.03*n/4, 0.03*n/4)
  branching_factor = max(0, inst_outputs[1])
  bias_factor = max(0, inst_outputs[2])

  # Parameter passing — single consolidated C call
  solver_ctx_set_predicted_params(ctx, bias, branching_factor, bias_factor, weights, order, n)

  result = model.solve(time_budget)
  return (result.best_objective, -result.time_to_best)
```

### 4.3.1 Option B Fallback (full C pipeline)

If Option A is insufficient, the entire prediction pipeline moves to C:

```
  # Single C call: load theta + extract features + poly expand + matmul + set params
  c_predict_and_set_params(ctx, theta, obj_exprs, con_exprs, vars, n_vars)
```

No Python involvement after initiation. Requires reimplementing polynomial expansion and small matrix multiply in C (trivial for fixed-size matrices).

### 4.4 Data Flow

```
Training Instances (small/medium)
        |
        v
  ES Training Loop
  ├── Polynomial evaluation per instance
  ├── Solver evaluation (stochastic, single-thread)
  ├── Gradient estimation from perturbation pairs
  └── Coefficient update via Adam
        |
        v
  Checkpoint: theta (~365 floats) + optimizer state
        |
        v
  Deployment (any instance size)
  ├── C feature extraction (single pass over expressions)
  ├── numpy polynomial evaluation (small matrices)
  ├── Post-processing (clip, scale bias)
  ├── C consolidated parameter setter (single call)
  └── model.solve()
```

---

## 5. Acceptance Criteria

- [ ] Polynomial model produces bias values within ±3% of `n/4` for all instance sizes
- [ ] Training signal uses best-objective with time-to-best as tiebreaker (not AUC)
- [ ] ES training loop converges: mean signal improves over training steps on held-out instances
- [ ] Model trained on instances with n<=200 performs at least as well as default `n/4` on instances with n>=1000
- [ ] Training can be stopped, new instances added, and training resumed from checkpoint
- [ ] Training log captures per-step metrics and is queryable
- [ ] Model file is small (<10KB) and loads instantly
- [ ] Per-variable weights act as perturbations (magnitudes remain small relative to bias)
- [ ] C feature extraction produces identical results to Python implementation (verified by tests)
- [ ] Full predict() pipeline completes in <1ms for n=3000 instances (vs current ~4200ms)
- [ ] Consolidated parameter setter replaces multi-call Cython propagation

---

## 6. Migration from Current Pipeline

The new pipeline replaces the ExtraTreesRegressor-based pipeline entirely:

| Aspect | Current | New |
|--------|---------|-----|
| Model type | ExtraTreesRegressor ensemble | Degree-2 polynomial |
| Parameters | Per-variable (thousands) | ~365 coefficients |
| Training method | Random sampling + best-of-N | ES gradient estimation |
| Training signal | AUC (area under incumbent) | Best objective + time tiebreaker |
| Bias prediction | Absolute value (undershoots) | n/4 + bounded delta |
| Size generalization | Poor (no extrapolation) | By design (scale-invariant) |
| Model file size | Large (.joblib) | Tiny (~365 floats) |
| Incremental training | warm_start (add trees) | Resume from checkpoint |
| Feature extraction | Pure Python loops (~4.2s for n=3000) | C single-pass (~ms) |
| Parameter passing | ~12 separate Cython→C calls | Single consolidated C call |

The existing feature extraction logic is reimplemented in C for performance. The Python version (`features.py`) is retained as reference/test oracle. The existing phase-specific parameter infrastructure (three BranchingStats, variable ordering) is reused.

---

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Degree-2 polynomial not expressive enough | Per-variable predictions too coarse | Bounded perturbation limits downside; can increase degree later |
| ES gradient estimation too noisy | Slow convergence | Antithetic sampling, batch averaging, tunable sigma and K |
| ±3% delta bound too restrictive | Model can't learn meaningful improvements | Bound is configurable; start conservative, relax if needed |
| Training compute cost (2K evals per step per instance) | Slow training | Use small instances; parallelize evaluations |
| Polynomial cross-terms overfit on small training pools | Poor generalization | Z-score normalization, small coefficients via regularization |
| C feature extraction diverges from Python | Silent correctness bugs | Bit-exact comparison tests against Python reference implementation |
| Option A still too slow for large instances | Predict overhead still visible | Fall back to Option B (full C pipeline) |

---

## 8. Future Considerations

- **Higher-degree polynomials**: If degree-2 proves insufficient, degree-3 can be explored (at the cost of more parameters)
- **Phase-specific polynomials**: Separate coefficient sets per solver phase (SAT, OPT-SAT, OPT) rather than shared
- **Learned sigma schedule**: Adapt perturbation scale during training based on gradient signal-to-noise ratio
- **Multi-threaded evaluation**: Evaluate perturbations in parallel across CPU cores to speed up training
- **Neural network upgrade**: If polynomial capacity is limiting, replace with a small neural network while keeping the ES training framework
- **Option B (full C pipeline)**: If Option A numpy overhead matters, move polynomial expansion + matmul to C as well — trivial for fixed-size matrices
- **Multi-threaded feature extraction**: For very large instances, parallelize the constraint iteration loop across threads
