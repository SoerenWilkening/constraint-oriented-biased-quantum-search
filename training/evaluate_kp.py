#!/usr/bin/env python3
"""Evaluate solver performance on a knapsack instance across training stages.

Loads a .in knapsack file, solves it with:
  1. Default parameters (no ML)
  2. Trained predictor from the latest training run

Compares objective values, feasibility, and solve times.
Plots the incumbent history for each configuration.

Usage:
    python training/evaluate_kp.py
    python training/evaluate_kp.py --instance path/to/test_0.in --time-budget 30
    python training/evaluate_kp.py --training-dir training/output/20260312_124319/opt
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE


# ------------------------------------------------------------------
# Knapsack .in parser
# ------------------------------------------------------------------

def load_knapsack(filepath):
    """Parse a knapsack .in file.

    Format:
        Line 1: n (number of items)
        Lines 2..n+1: index weight value
        Last line: capacity

    Returns (weights, values, capacity).
    """
    lines = Path(filepath).read_text().strip().split('\n')
    n = int(lines[0])
    weights = np.zeros(n, dtype=np.int64)
    values = np.zeros(n, dtype=np.int64)
    for i in range(1, n + 1):
        parts = lines[i].split()
        idx = int(parts[0])
        weights[idx] = int(parts[1])
        values[idx] = int(parts[2])
    capacity = int(lines[n + 1])
    return weights, values, capacity


def build_knapsack_model(weights, values, capacity):
    """Build a CBQS Model for a 0-1 knapsack instance."""
    n = len(weights)
    m = Model()
    xs = m.add_variables(n)
    m.add_constraint(sum(xs[i] * int(weights[i]) for i in range(n)) <= int(capacity))
    m.set_objective(sum(xs[i] * int(values[i]) for i in range(n)), MAXIMIZE)
    m.close()
    return m


# ------------------------------------------------------------------
# Solve helpers
# ------------------------------------------------------------------

def solve_with_params(weights, values, capacity, params, time_budget,
                      num_workers, label=""):
    """Build model, apply params, solve, return result and callback history."""
    m = build_knapsack_model(weights, values, capacity)
    m.set_param('stopping_time', time_budget)
    m.set_param('num_workers', num_workers)
    m.set_param('track_history', False)

    m.general_greedy()

    for key, value in params.items():
        m.set_param(key, value)

    history = []

    def callback():
        history.append((m.objective_value, m.runtime))

    m.set_param("callback", callback)

    print(f"  Solving [{label}]...", end=" ", flush=True)
    result = m.solve()
    print(f"obj={result.objective}, feasible={result.feasible}, "
          f"time={result.solve_time:.0f}ms")
    return result, history


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def find_latest_training_dir():
    """Find the most recent training output directory."""
    output_dir = Path(__file__).parent / 'output'
    if not output_dir.exists():
        return None
    runs = sorted(output_dir.iterdir())
    if not runs:
        return None
    # Look for opt subdirectory first
    latest = runs[-1]
    opt_dir = latest / 'opt'
    if opt_dir.exists():
        return str(opt_dir)
    sat_dir = latest / 'sat'
    if sat_dir.exists():
        return str(sat_dir)
    return str(latest)


def main():
    default_instance = (
        PROJECT_ROOT / 'others' / 'KP'
        / 'n_3000_c_10000000000_g_14_f_0.3_eps_1e-05_s_300' / 'test_0.in'
    )

    parser = argparse.ArgumentParser(
        description='Evaluate CBQS on a knapsack instance with and without ML')
    parser.add_argument('--instance', type=str, default=str(default_instance),
                        help='Path to knapsack .in file')
    parser.add_argument('--training-dir', type=str, default=None,
                        help='Training output dir (auto-detected if omitted)')
    parser.add_argument('--time-budget', type=float, default=60,
                        help='Solve time budget in seconds (default: 30)')
    parser.add_argument('--num-workers', type=int, default=12,
                        help='Number of parallel workers (default: 12)')
    parser.add_argument('--repeats', type=int, default=1,
                        help='Number of repeated solves per config (default: 1)')
    args = parser.parse_args()

    # Load instance
    print(f"Loading knapsack instance: {args.instance}")
    weights, values, capacity = load_knapsack(args.instance)
    print(f"  n={len(weights)}, capacity={capacity}")

    # Configurations to evaluate
    configs = []

    # 1) Default (no ML)
    configs.append(("Default", {}))

    # 2) Trained predictor
    training_dir = args.training_dir or find_latest_training_dir()
    if training_dir:
        print(f"\nLoading trained predictor from: {training_dir}")
        try:
            from cbqs.ml.opt_trainer import OPTTrainer
            trainer = OPTTrainer.load(training_dir)
            # Build a temporary model to get predictions
            tmp_model = build_knapsack_model(weights, values, capacity)
            predicted_params = trainer.predict(tmp_model)
            configs.append(("ML-predicted", predicted_params))
            print(f"  Loaded successfully. Predicted params:")
            for k, v in predicted_params.items():
                if isinstance(v, list):
                    print(f"    {k}: array[{len(v)}] "
                          f"(mean={np.mean(v):.3f}, std={np.std(v):.3f})")
                else:
                    print(f"    {k}: {v:.4f}")
        except Exception as e:
            print(f"  Warning: could not load trainer: {e}")
    else:
        print("\nNo training directory found, skipping ML-predicted config.")

    # Run evaluations
    print(f"\n{'='*70}")
    print(f"  Evaluating {len(configs)} configurations "
          f"(time_budget={args.time_budget}s, workers={args.num_workers})")
    print(f"{'='*70}")

    results = {}
    for label, params in configs:
        run_results = []
        for rep in range(args.repeats):
            rep_label = f"{label} (rep {rep+1})" if args.repeats > 1 else label
            result, history = solve_with_params(
                weights, values, capacity, params,
                args.time_budget, args.num_workers, rep_label)
            run_results.append((result, history))
        results[label] = run_results

    # Summary table
    print(f"\n{'='*70}")
    print(f"  Summary")
    print(f"{'='*70}")
    print(f"  {'Config':<20} {'Objective':>12} {'Feasible':>10} {'Time (ms)':>12}")
    print(f"  {'-'*20} {'-'*12} {'-'*10} {'-'*12}")
    for label, runs in results.items():
        objs = [r.objective for r, _ in runs]
        times = [r.solve_time for r, _ in runs]
        feasibles = [r.feasible for r, _ in runs]
        if args.repeats > 1:
            print(f"  {label:<20} {np.mean(objs):>12.1f} "
                  f"{'all' if all(feasibles) else 'SOME INFEAS':>10} "
                  f"{np.mean(times):>12.0f}")
        else:
            print(f"  {label:<20} {objs[0]:>12} "
                  f"{'Yes' if feasibles[0] else 'NO':>10} "
                  f"{times[0]:>12.0f}")

    # Plot incumbent histories from callback data
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))
        has_data = False

        for label, runs in results.items():
            # Use first run for plotting
            _, history = runs[0]
            if not history:
                continue
            # history entries are (objective_value, runtime_seconds)
            # Keep only improving incumbents
            times_s = []
            objs = []
            best = None
            for obj, t in sorted(history, key=lambda h: h[1]):
                if best is None or obj > best:
                    best = obj
                    times_s.append(t)
                    objs.append(obj)
            if times_s:
                ax.step(times_s, objs, where='post', label=label, linewidth=2)
                has_data = True

        if has_data:
            ax.set_xlabel('Time (seconds)')
            ax.set_ylabel('Objective Value')
            ax.set_title(f'Incumbent History — Knapsack (n={len(weights)})')
            plt.xscale("log")
            plt.yscale("log")
            ax.legend()
            ax.grid(True, alpha=0.3)

            plot_path = Path(__file__).parent / 'kp_evaluation.png'
            fig.savefig(plot_path, dpi=150, bbox_inches='tight')
            print(f"\n  Plot saved to: {plot_path}")
        plt.close()
    except ImportError:
        print("\n  matplotlib not available, skipping plot.")


if __name__ == '__main__':
    main()
