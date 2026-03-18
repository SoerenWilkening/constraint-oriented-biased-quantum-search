# Sub-Linear Model Training Evaluation

## Model Configuration

- **THETA_SIZE**: 146 parameters
- **Instance-level**: 3 outputs x 12 terms (intercept + 11 linear) = 36 params
- **Per-variable**: 2 outputs x 55 terms (degree-2 polynomial) = 110 params
- **Outputs**: bias_delta, branching_factor, bias_factor (instance); weight, priority (per-var)

## Training Runs

### Run 1: Conservative (10 steps, sigma=0.02, lr=0.001)

| Metric | Value |
|--------|-------|
| Training time | 96.3s |
| Final theta norm | 0.046 |
| bias_factor intercept | -0.001 |
| branching_factor intercept | 0.007 |
| Weight coeffs norm | 0.028 |
| Evaluation | 4 predicted wins / 6 default wins |

Pipeline works end-to-end. With small theta values near zero, predicted params
are close to defaults. Competitive but not winning.

### Run 2: Aggressive (30 steps, sigma=0.05, lr=0.01)

| Metric | Value |
|--------|-------|
| Training time | 346.8s |
| Final theta norm | 0.760 |
| bias_factor intercept | -0.006 |
| branching_factor intercept | -0.150 |
| Weight coeffs norm | 0.435 |
| Evaluation | 0 predicted wins / 10 default wins |

Diverged. Higher sigma/lr pushed branching_factor to 1.4 (too high), bias_factor
clipped to 0 (from negative). Predicted solver consistently worse. Many steps
had grad_norm=0 (constant signal diffs), indicating perturbations were too large
and solver performance was not differentiable at that scale.

### Run 3: Moderate (20 steps, sigma=0.02, lr=0.002)

| Metric | Value |
|--------|-------|
| Training time | 436.5s |
| Final theta norm | 0.134 |
| bias_factor intercept | -0.011 |
| branching_factor intercept | 0.007 |
| Weight coeffs norm | 0.081 |
| Evaluation | 0 predicted wins / 9 default wins / 1 tie |

Similar to Run 2 but less extreme. branching_factor ~0.66 and bias_factor=0
alter the solver away from effective defaults. All per-variable weights are
zero after clipping (raw values are negative).

## Key Findings

### 1. Pipeline Verified End-to-End
The 146-param sub-linear model trains, checkpoints, saves predictor, loads
and predicts correctly. Training loop runs without errors.

### 2. branching_factor Converges to O(1) Values
With conservative settings: ~0.007 (positive, small).
With moderate settings: ~0.66 (positive, reasonable O(1)).
With aggressive settings: ~1.4 (too high, hurts performance).

### 3. bias_factor Does Not Converge to ~1
In all runs, bias_factor intercept remains negative (clipped to 0).
The model has not learned to set bias_factor to a useful positive value.
This may indicate that bias_factor is not useful for these knapsack instances,
or that training needs more steps / different signal.

### 4. branching_weights Learn Non-Trivial Coefficients
Weight polynomial coefficients are nonzero (norm up to 0.435). However,
when evaluated on actual instances, the resulting per-variable weights tend
to be negative and get clipped to zero by `np.maximum(0.0, weights)`.
The clipping behavior prevents learned negative-weight patterns from having
any effect.

### 5. Predicted Solver Degrades with More Training
Paradoxically, more training makes the predicted solver worse. This is because
the model moves parameters away from the known-good defaults (n/4 bias,
no branching modifications). The training signal (best objective found) is
too noisy with short eval times (1-3s) on small instances to consistently
reward perturbations that help.

## Success Criteria Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| bias_factor ~ 1 | NOT MET | Stays near 0 (clipped from negative) |
| branching_factor > 0 | MET | Positive with conservative sigma |
| Weights non-trivial | PARTIALLY MET | Coefficients nonzero but clipped to 0 on eval |
| Predicted >= default | NOT MET | Defaults win on held-out instances |

## Recommendations

1. **More training steps**: 10-30 steps is insufficient for 146 parameters.
   Need hundreds of steps minimum, which requires faster evaluation.

2. **Lower sigma**: sigma=0.02 works better than 0.05. The solver response
   to parameter perturbations is non-smooth; large perturbations produce
   uninformative gradient estimates.

3. **Longer eval time**: 1s eval is too short for signal differentiation.
   With 1s, all perturbations often produce the same objective, yielding
   zero gradient (grad_norm=0 steps).

4. **Remove or relax weight clipping**: The `np.maximum(0, weights)` clipping
   zeroes out all learned per-variable weight patterns. Consider allowing
   negative weights or using a different parameterization.

5. **Pre-initialize bias_factor**: Starting bias_factor at 1.0 instead of 0.0
   (via intercept initialization) would help the model start from a more
   useful baseline.
