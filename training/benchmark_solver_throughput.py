#!/usr/bin/env python3
"""Benchmark solver throughput: measure how many samples/solutions the solver
produces per second of wall-clock time.

This measures the actual C solver performance — more samples/sec means the
pre-allocation and signal() optimizations are working.

Usage:
    python training/benchmark_solver_throughput.py
"""

import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE
from cbqs.ml.polynomial import PolynomialPredictor, default_theta
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


def benchmark_instance(filepath, solve_budget=2.0, repeats=5):
    """Benchmark solver on one instance: measure qtg_applications/sec."""
    model = load_knapsack_file(filepath)
    n = len(model.variables)

    theta = default_theta()
    predictor = PolynomialPredictor(theta)

    results = []
    for r in range(repeats):
        model.reset()
        model.general_greedy()
        model.seed = 42 + r

        params = predictor.predict(model)
        set_predicted_params(
            model,
            params['branching_bias'],
            params['branching_factor'],
            params['bias_factor'],
            params['branching_weights'],
            params['variable_priorities'],
            n,
        )
        model.set_param('stopping_time', solve_budget)

        t0 = time.perf_counter()
        result = model.solve()
        elapsed = time.perf_counter() - t0

        qtg = result.oracle_calls if hasattr(result, 'oracle_calls') else 0
        results.append({
            'elapsed': elapsed,
            'objective': result.objective,
            'qtg': qtg,
        })

    mean_elapsed = np.mean([r['elapsed'] for r in results])
    mean_qtg = np.mean([r['qtg'] for r in results])
    rate = mean_qtg / mean_elapsed if mean_elapsed > 0 else 0
    mean_obj = np.mean([r['objective'] or 0 for r in results])

    return {
        'n': n,
        'mean_elapsed_s': mean_elapsed,
        'mean_qtg': mean_qtg,
        'qtg_per_sec': rate,
        'mean_objective': mean_obj,
    }


def main():
    instances_dir = PROJECT_ROOT / 'training' / 'knapsack_instances'
    target_sizes = [75, 100, 300, 500]
    solve_budget = 2.0
    repeats = 5

    print("=" * 70)
    print(f"  Solver Throughput Benchmark (budget={solve_budget}s, repeats={repeats})")
    print("=" * 70)

    for d in sorted(instances_dir.iterdir()):
        if not d.is_dir():
            continue
        parts = d.name.split('_')
        try:
            idx = parts.index('n')
            n = int(parts[idx + 1])
        except (ValueError, IndexError):
            continue
        if n not in target_sizes:
            continue

        in_files = sorted(d.glob('*.in'))
        if not in_files:
            continue

        filepath = in_files[0]
        print(f"\n--- n={n} ---")

        r = benchmark_instance(filepath, solve_budget=solve_budget, repeats=repeats)
        print(f"  Elapsed:     {r['mean_elapsed_s']:.3f}s")
        print(f"  QTG calls:   {r['mean_qtg']:.0f}")
        print(f"  Throughput:  {r['qtg_per_sec']:.0f} qtg/sec")
        print(f"  Objective:   {r['mean_objective']:.0f}")


if __name__ == '__main__':
    main()
