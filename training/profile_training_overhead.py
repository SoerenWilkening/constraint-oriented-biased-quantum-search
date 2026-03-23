#!/usr/bin/env python3
"""Profile training overhead: measure time spent in each component of the
ES training loop to identify optimization opportunities.

Measures:
  1. Model loading & compilation
  2. model.reset() + model.general_greedy()
  3. PolynomialPredictor creation + prediction (C pipeline)
  4. set_predicted_params (Python dict writes)
  5. Callback setup
  6. model.solve() (actual C solver time)
  7. Full _single_solve() end-to-end
  8. Full evaluate() with repeats
  9. Monitoring evaluations overhead in training step

Usage:
    python training/profile_training_overhead.py
    python training/profile_training_overhead.py --instance-sizes 75 100 300
"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE
from cbqs.ml.polynomial import PolynomialPredictor, THETA_SIZE, default_theta
from cbqs.ml.es_evaluator import evaluate, _single_solve, _make_history_callback
from cbqs.SearchLib import set_predicted_params


def load_knapsack_file(filepath):
    lines = Path(filepath).read_text().strip().split('\n')
    n = int(lines[0])
    weights = [0] * n
    values = [0] * n
    for i in range(1, n + 1):
        parts = lines[i].split()
        idx = int(parts[0])
        weights[idx] = int(parts[1])
        values[idx] = int(parts[2])
    capacity = int(lines[n + 1])

    m = Model()
    xs = m.add_variables(n)
    m.add_constraint(sum(xs[i] * weights[i] for i in range(n)) <= capacity)
    m.set_objective(sum(xs[i] * values[i] for i in range(n)), MAXIMIZE)
    m.close()
    return m


def find_instances(instances_dir, target_sizes=None):
    """Find one instance per target size."""
    base = Path(instances_dir)
    if target_sizes is None:
        target_sizes = [75, 100, 300, 500]

    instances = {}
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        # Parse n from directory name like n_100_c_...
        parts = d.name.split('_')
        try:
            idx = parts.index('n')
            n = int(parts[idx + 1])
        except (ValueError, IndexError):
            continue

        if n in target_sizes:
            in_files = sorted(d.glob('*.in'))
            if in_files:
                instances[n] = in_files[0]

    return instances


def time_it(fn, repeats=10):
    """Time a function over multiple repeats, return (mean_ms, std_ms)."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    arr = np.array(times)
    return float(np.mean(arr)), float(np.std(arr)), result


def profile_instance(filepath, solve_budget=0.5):
    """Profile all components for a single instance."""
    n_label = filepath.parent.name

    # 1. Model loading
    t0 = time.perf_counter()
    model = load_knapsack_file(filepath)
    load_ms = (time.perf_counter() - t0) * 1000
    n = len(model.variables)

    theta = default_theta()
    predictor = PolynomialPredictor(theta)

    results = {'n': n, 'label': n_label}
    results['load_model_ms'] = load_ms

    reps = 20

    # 2. model.reset()
    mean, std, _ = time_it(lambda: model.reset(), repeats=reps)
    results['reset_ms'] = mean
    results['reset_std'] = std

    # 3. model.general_greedy()
    def do_greedy():
        model.reset()
        model.general_greedy()
    mean, std, _ = time_it(do_greedy, repeats=reps)
    results['reset_greedy_ms'] = mean
    results['reset_greedy_std'] = std
    results['greedy_only_ms'] = results['reset_greedy_ms'] - results['reset_ms']

    # 4. PolynomialPredictor creation
    mean, std, _ = time_it(lambda: PolynomialPredictor(theta), repeats=reps)
    results['predictor_create_ms'] = mean

    # 5. Prediction (C pipeline)
    model.reset()
    model.general_greedy()
    mean, std, _ = time_it(lambda: predictor.predict(model), repeats=reps)
    results['predict_ms'] = mean
    results['predict_std'] = std

    # 6. set_predicted_params
    params = predictor.predict(model)
    def do_set_params():
        set_predicted_params(
            model,
            params['branching_bias'],
            params['branching_factor'],
            params['bias_factor'],
            params['branching_weights'],
            params['variable_priorities'],
            n,
        )
    mean, std, _ = time_it(do_set_params, repeats=reps)
    results['set_params_ms'] = mean

    # 7. Callback setup
    mean, std, _ = time_it(lambda: _make_history_callback(model), repeats=reps)
    results['callback_setup_ms'] = mean

    # 8. Full solve (with setup)
    def do_solve():
        model.reset()
        model.general_greedy()
        model.seed = 42
        p = predictor.predict(model)
        model.set_param('stopping_time', solve_budget)
        set_predicted_params(model, p['branching_bias'], p['branching_factor'],
                           p['bias_factor'], p['branching_weights'],
                           p['variable_priorities'], n)
        cb, state = _make_history_callback(model)
        model.set_param('callback', cb)
        model.solve()
        return state['best_objective']

    solve_reps = 5
    mean, std, _ = time_it(do_solve, repeats=solve_reps)
    results['full_solve_ms'] = mean
    results['full_solve_std'] = std

    # 9. _single_solve (from es_evaluator)
    mean, std, _ = time_it(
        lambda: _single_solve(model, theta, solve_budget, seed=42),
        repeats=solve_reps,
    )
    results['single_solve_ms'] = mean

    # 10. evaluate() with repeats=5
    eval_repeats = 5
    mean, std, _ = time_it(
        lambda: evaluate(theta, model, solve_budget * eval_repeats,
                        seed=42, repeats=eval_repeats),
        repeats=3,
    )
    results['evaluate_ms'] = mean
    results['evaluate_per_repeat_ms'] = mean / eval_repeats

    # Compute overhead breakdown
    solver_time_ms = solve_budget * 1000
    setup_overhead_ms = (results['reset_greedy_ms'] + results['predictor_create_ms']
                        + results['predict_ms'] + results['set_params_ms']
                        + results['callback_setup_ms'])
    results['setup_overhead_ms'] = setup_overhead_ms
    results['overhead_pct'] = 100.0 * setup_overhead_ms / (solver_time_ms + setup_overhead_ms)

    return results


def profile_training_step_overhead(model, theta, K=50, batch_size=5,
                                    eval_time=5.0, eval_repeats=10):
    """Profile a simulated training step to see where time goes."""
    n = len(model.variables)
    sigma = 0.02

    timings = {
        'epsilon_gen': 0,
        'theta_perturb': 0,
        'evaluate_calls': 0,
        'normalize': 0,
        'gradient_accum': 0,
        'monitoring_evals': 0,
    }

    # Generate epsilons
    t0 = time.perf_counter()
    epsilons = [np.random.randn(THETA_SIZE) for _ in range(K)]
    timings['epsilon_gen'] = (time.perf_counter() - t0) * 1000

    # Simulate one instance from batch
    t0 = time.perf_counter()
    diffs = np.empty(K, dtype=np.float64)
    for k, eps in enumerate(epsilons):
        theta_plus = theta + sigma * eps
        theta_minus = theta - sigma * eps
    timings['theta_perturb'] = (time.perf_counter() - t0) * 1000

    # Time evaluate calls (just 2 perturbations to estimate per-call cost)
    t0 = time.perf_counter()
    pair_seed = 42
    sig_plus = evaluate(theta, model, eval_time, seed=pair_seed,
                       repeats=eval_repeats)
    sig_minus = evaluate(theta, model, eval_time, seed=pair_seed + 1,
                        repeats=eval_repeats)
    two_eval_ms = (time.perf_counter() - t0) * 1000
    single_eval_ms = two_eval_ms / 2

    # Estimated total evaluate time per step
    # 2*K*batch_size evaluations for perturbation pairs
    perturbation_evals = 2 * K * batch_size
    timings['evaluate_calls'] = single_eval_ms * perturbation_evals

    # Monitoring evaluations: batch_size evaluations at current theta
    timings['monitoring_evals'] = single_eval_ms * batch_size

    # Total
    total_ms = timings['evaluate_calls'] + timings['monitoring_evals']
    timings['total_estimated_ms'] = total_ms
    timings['single_eval_ms'] = single_eval_ms
    timings['perturbation_evals'] = perturbation_evals
    timings['monitoring_evals_count'] = batch_size
    timings['monitoring_overhead_pct'] = 100.0 * timings['monitoring_evals'] / total_ms

    return timings


def main():
    parser = argparse.ArgumentParser(description='Profile training overhead')
    parser.add_argument('--instances-dir', type=str,
                       default=str(PROJECT_ROOT / 'training' / 'knapsack_instances'))
    parser.add_argument('--instance-sizes', type=int, nargs='+',
                       default=[75, 100, 300, 500])
    parser.add_argument('--solve-budget', type=float, default=0.5,
                       help='Solve time budget per solve in seconds')
    args = parser.parse_args()

    print("=" * 70)
    print("  Training Overhead Profiler")
    print("=" * 70)

    instances = find_instances(args.instances_dir, args.instance_sizes)
    if not instances:
        print("No instances found!")
        return

    print(f"\nFound instances for n = {sorted(instances.keys())}")

    # ----------------------------------------------------------------
    # Part 1: Per-component profiling
    # ----------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  Part 1: Per-Component Timing (solve_budget={args.solve_budget}s)")
    print(f"{'='*70}")

    all_results = []
    for n in sorted(instances.keys()):
        filepath = instances[n]
        print(f"\n--- n={n} ({filepath.parent.name}) ---")

        results = profile_instance(filepath, solve_budget=args.solve_budget)
        all_results.append(results)

        print(f"  Model load:        {results['load_model_ms']:8.2f} ms")
        print(f"  model.reset():     {results['reset_ms']:8.3f} ms")
        print(f"  general_greedy():  {results['greedy_only_ms']:8.3f} ms")
        print(f"  Predictor create:  {results['predictor_create_ms']:8.3f} ms")
        print(f"  predict() [C]:     {results['predict_ms']:8.3f} ms")
        print(f"  set_params():      {results['set_params_ms']:8.3f} ms")
        print(f"  callback setup:    {results['callback_setup_ms']:8.3f} ms")
        print(f"  --- ")
        print(f"  Setup overhead:    {results['setup_overhead_ms']:8.3f} ms "
              f"({results['overhead_pct']:.1f}% of solve+setup)")
        print(f"  Full solve:        {results['full_solve_ms']:8.1f} ms")
        print(f"  _single_solve():   {results['single_solve_ms']:8.1f} ms")
        print(f"  evaluate(r=5):     {results['evaluate_ms']:8.1f} ms "
              f"({results['evaluate_per_repeat_ms']:.1f} ms/repeat)")

    # ----------------------------------------------------------------
    # Part 2: Training step overhead estimation
    # ----------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  Part 2: Training Step Overhead Estimation")
    print(f"{'='*70}")

    # Use first available instance
    first_n = sorted(instances.keys())[0]
    model = load_knapsack_file(instances[first_n])
    theta = default_theta()

    for K, bs, et, er in [(50, 5, 5.0, 10), (10, 3, 2.0, 5)]:
        print(f"\n--- Config: K={K}, batch={bs}, eval_time={et}s, repeats={er} ---")
        timings = profile_training_step_overhead(
            model, theta, K=K, batch_size=bs, eval_time=et, eval_repeats=er)

        total_evals = timings['perturbation_evals'] + timings['monitoring_evals_count']
        step_s = timings['total_estimated_ms'] / 1000

        print(f"  Single evaluate():     {timings['single_eval_ms']:8.1f} ms")
        print(f"  Perturbation evals:    {timings['perturbation_evals']:>5d} calls "
              f"({timings['evaluate_calls']/1000:.1f}s)")
        print(f"  Monitoring evals:      {timings['monitoring_evals_count']:>5d} calls "
              f"({timings['monitoring_evals']/1000:.1f}s) "
              f"[{timings['monitoring_overhead_pct']:.1f}% of step]")
        print(f"  Total evals per step:  {total_evals:>5d}")
        print(f"  Estimated step time:   {step_s:.1f}s ({step_s/60:.1f}min)")
        print(f"  1000 steps:            {step_s*1000/3600:.1f}h")

    # ----------------------------------------------------------------
    # Part 3: Summary of optimization opportunities
    # ----------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  Part 3: Optimization Opportunities")
    print(f"{'='*70}")

    if all_results:
        r = all_results[-1]  # largest instance
        n = r['n']
        print(f"\n  Analysis for n={n}:")
        print(f"  Per-solve setup overhead: {r['setup_overhead_ms']:.3f} ms")
        print(f"  Solve budget:             {args.solve_budget*1000:.0f} ms")
        print(f"  Overhead ratio:           {r['overhead_pct']:.2f}%")
        print()
        print(f"  Largest setup components:")
        components = [
            ('reset()', r['reset_ms']),
            ('general_greedy()', r['greedy_only_ms']),
            ('PolynomialPredictor()', r['predictor_create_ms']),
            ('predict() [C]', r['predict_ms']),
            ('set_params()', r['set_params_ms']),
            ('callback setup', r['callback_setup_ms']),
        ]
        components.sort(key=lambda x: -x[1])
        for name, ms in components:
            print(f"    {name:25s} {ms:8.3f} ms")


if __name__ == '__main__':
    main()
