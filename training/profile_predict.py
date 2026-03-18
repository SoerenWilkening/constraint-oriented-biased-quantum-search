#!/usr/bin/env python3
"""Profile the ML prediction pipeline to identify bottlenecks.

Measures time for each stage:
  1. Model file load (np.load + unpack theta)
  2. Feature extraction (variable + instance features)
  3. Polynomial expansion
  4. Matrix multiply + post-processing
  5. Parameter passing (set_param calls)

Tests across multiple model sizes and reports per-stage timings.
"""
import sys
import time
import random
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE
from cbqs.ml.features import FeatureExtractor
from cbqs.SearchLib import c_extract_features, c_predict_params
from cbqs.ml.polynomial import (
    PolynomialPredictor, poly_expand, unpack_theta, THETA_SIZE,
    N_VAR_TERMS, N_INST_TERMS, N_VAR_OUTPUTS, N_INST_OUTPUTS,
)


def make_knapsack(n_vars, seed=42):
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n_vars)
    weights = [rng.randint(1, 20) for _ in range(n_vars)]
    values = [rng.randint(1, 30) for _ in range(n_vars)]
    capacity = sum(weights) // 3
    m.add_constraint(sum(xs[i] * weights[i] for i in range(n_vars)) <= capacity)
    m.set_objective(sum(xs[i] * values[i] for i in range(n_vars)), MAXIMIZE)
    m.close()
    return m


def make_sat(n_vars, clause_ratio=4.2, seed=42):
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n_vars)
    n_clauses = int(clause_ratio * n_vars)
    for _ in range(n_clauses):
        clause_vars = rng.sample(range(n_vars), min(3, n_vars))
        literals = []
        for v in clause_vars:
            if rng.random() < 0.5:
                literals.append(xs[v])
            else:
                literals.append(-1 * xs[v] + 1)
        m.add_constraint(sum(literals) >= 1)
    m.close()
    return m


def profile_stage(fn, n_reps=100, warmup=5):
    """Run fn() n_reps times, return (mean_us, std_us, min_us)."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(n_reps):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        times.append((t1 - t0) / 1000.0)  # nanoseconds -> microseconds
    arr = np.array(times)
    return arr.mean(), arr.std(), arr.min()


def profile_model(model, theta, label, n_reps=100):
    """Profile all stages for a given model."""
    extractor = FeatureExtractor()
    W_var, W_inst = unpack_theta(theta)

    # Pre-compute for stages that need inputs from prior stages
    var_features = extractor.extract_variable_features(model)
    inst_features = extractor.extract_instance_features(model)
    var_terms = poly_expand(var_features, degree=2)
    inst_terms = poly_expand(inst_features, degree=2)

    n = len(model.variables)

    print(f"\n{'='*65}")
    print(f"  {label}  (n_vars={n}, n_cons={len(model.con_expr)})")
    print(f"  {n_reps} repetitions per stage")
    print(f"{'='*65}")
    print(f"  {'Stage':<35} {'Mean (us)':>10} {'Std':>10} {'Min':>10}")
    print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10}")

    total_mean = 0.0

    # Stage 1a: Feature extraction (variable) - Python
    mean, std, mn = profile_stage(
        lambda: extractor.extract_variable_features(model), n_reps)
    print(f"  {'Variable features (Python)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")

    # Stage 1b: Feature extraction (instance) - Python
    mean_i, std_i, mn_i = profile_stage(
        lambda: extractor.extract_instance_features(model), n_reps)
    print(f"  {'Instance features (Python)':<35} {mean_i:>10.1f} {std_i:>10.1f} {mn_i:>10.1f}")
    python_feat_total = mean + mean_i

    # Stage 1c: Feature extraction - C (combined)
    mean_c, std_c, mn_c = profile_stage(
        lambda: c_extract_features(model), n_reps)
    print(f"  {'Features (C via Cython)':<35} {mean_c:>10.1f} {std_c:>10.1f} {mn_c:>10.1f}")
    if mean_c > 0:
        print(f"  {'  -> Speedup vs Python':<35} {python_feat_total/mean_c:>10.1f}x")
    total_mean += mean_c

    # Stage 3: Polynomial expansion (variable)
    mean, std, mn = profile_stage(
        lambda: poly_expand(var_features, degree=2), n_reps)
    print(f"  {'Poly expand (variable)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")
    total_mean += mean

    # Stage 4: Polynomial expansion (instance)
    mean, std, mn = profile_stage(
        lambda: poly_expand(inst_features, degree=2), n_reps)
    print(f"  {'Poly expand (instance)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")
    total_mean += mean

    # Stage 5: Matrix multiply + post-process (variable)
    def var_matmul():
        out = var_terms @ W_var.T
        np.maximum(0.0, out[:, 0])
        np.argsort(-out[:, 1])
    mean, std, mn = profile_stage(var_matmul, n_reps)
    print(f"  {'Matmul + postproc (variable)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")
    total_mean += mean

    # Stage 6: Matrix multiply + post-process (instance)
    def inst_matmul():
        out = W_inst @ inst_terms
        np.clip(out[0], -0.5, 0.5)
        max(0.0, float(out[1]))
        max(0.0, float(out[2]))
    mean, std, mn = profile_stage(inst_matmul, n_reps)
    print(f"  {'Matmul + postproc (instance)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")
    total_mean += mean

    # Stage 7: Full predict() call (end-to-end)
    predictor = PolynomialPredictor(theta)
    mean, std, mn = profile_stage(
        lambda: predictor.predict(model), n_reps)
    print(f"  {'-'*35} {'-'*10} {'-'*10} {'-'*10}")
    print(f"  {'Full predict() end-to-end':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")
    print(f"  {'Sum of stages':<35} {total_mean:>10.1f}")

    # Stage 8: Fused C pipeline (features + poly + matmul + postprocess)
    mean, std, mn = profile_stage(
        lambda: c_predict_params(model, W_var, W_inst, 0.03), n_reps)
    print(f"  {'Fused C predict_params()':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")

    # Stage 9: Parameter passing (set_param calls)
    params = predictor.predict(model)

    def set_params():
        model.set_param('branching_weights', params['branching_weights'])
        model.set_param('branching_bias', params['branching_bias'])
        model.set_param('branching_factor', params['branching_factor'])
        model.set_param('bias_factor', params['bias_factor'])
    mean, std, mn = profile_stage(set_params, n_reps)
    print(f"  {'Parameter passing (set_param)':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")

    # Stage 9: Model load from file (if available)
    predictor_path = PROJECT_ROOT / 'training' / 'output' / '20260317_164323' / 'es_predictor.npz'
    if predictor_path.exists():
        mean, std, mn = profile_stage(
            lambda: PolynomialPredictor.load(str(predictor_path)), n_reps)
        print(f"  {'Load from .npz file':<35} {mean:>10.1f} {std:>10.1f} {mn:>10.1f}")

    print()


def read_knapsack_file(filepath):
    """Load a knapsack instance from the others/KP format."""
    with open(filepath) as f:
        dat = f.read().split()
    n = int(dat[0])
    Z_init = int(dat[-1])
    dat = dat[1:-1]
    p_list = [int(dat[3 * i + 1]) for i in range(n)]
    z_list = [int(dat[3 * i + 2]) for i in range(n)]

    m = Model()
    xs = m.add_variables(n)
    m.set_objective(sum(xs[i] * p_list[i] for i in range(n)), MAXIMIZE)
    m.add_constraint(sum(xs[i] * z_list[i] for i in range(n)) <= Z_init)
    m.close()
    return m


def main():
    theta = np.random.RandomState(42).randn(THETA_SIZE) * 0.01
    n_reps = 200

    # Small knapsack (typical training size)
    m_kp_small = make_knapsack(20)
    profile_model(m_kp_small, theta, "Knapsack n=20", n_reps)

    # Medium knapsack
    m_kp_med = make_knapsack(50)
    profile_model(m_kp_med, theta, "Knapsack n=50", n_reps)

    # Large knapsack
    m_kp_large = make_knapsack(100)
    profile_model(m_kp_large, theta, "Knapsack n=100", n_reps)

    # SAT instances (many constraints)
    m_sat_small = make_sat(20)
    profile_model(m_sat_small, theta, "3-SAT n=20 (84 clauses)", n_reps)

    m_sat_large = make_sat(65)
    profile_model(m_sat_large, theta, "3-SAT n=65 (273 clauses)", n_reps)

    # Large real-world knapsack (n=3000)
    kp_file = PROJECT_ROOT / 'others' / 'KP' / 'n_3000_c_10000000000_g_14_f_0.3_eps_1e-05_s_300' / 'test_0.in'
    if kp_file.exists():
        print("Loading n=3000 knapsack instance...")
        m_kp_3000 = read_knapsack_file(str(kp_file))
        profile_model(m_kp_3000, theta, "Knapsack n=3000 (real instance)", n_reps=10)


if __name__ == '__main__':
    main()
