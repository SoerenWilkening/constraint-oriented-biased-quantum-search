#!/usr/bin/env python3
"""Profile solver behavior across time budgets and instance sizes.

Runs the default solver (no ML parameters) on selected instances at
increasing time budgets to understand when exploration starts to matter.
Each configuration is repeated 5 times to capture stochastic variation.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE
import time

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


INSTANCES_DIR = PROJECT_ROOT / "training" / "knapsack_instances"

# Pick 4 sizes: n=20, 45, 75, 100
SIZES = [20, 45, 75, 100]
TIME_BUDGETS = [0.5, 2.0, 5.0, 10.0, 30.0]  # seconds
REPEATS = 5


def find_instance(n):
    """Find the first test instance for a given size."""
    for d in INSTANCES_DIR.iterdir():
        if d.is_dir() and d.name.startswith(f"n_{n}_"):
            f = d / "test_0.in"
            if f.exists():
                return f
    raise FileNotFoundError(f"No instance found for n={n}")


def run_solve(model, time_budget, use_greedy_init=False):
    """Run one solve, return (best_objective, time_to_best_s, total_oracle_calls)."""
    model.reset()

    if use_greedy_init:
        model.general_greedy()
    greedy_obj = model.objective_value

    # Track history via callback
    state = {'best_obj': model.objective_value, 'time_to_best': 0.0}

    def callback():
        obj = model.objective_value
        if obj is not None and (state['best_obj'] is None or obj > state['best_obj']):
            state['best_obj'] = obj
            state['time_to_best'] = model.runtime

    model.set_param('stopping_time', float(time_budget))
    model.set_param('callback', callback)
    result = model.solve()

    best_obj = state['best_obj']
    if best_obj is None:
        best_obj = float(result.objective or 0)

    return {
        'objective': float(best_obj),
        'greedy_obj': float(greedy_obj) if greedy_obj is not None else None,
        'time_to_best': state['time_to_best'],
        'solve_time_ms': result.solve_time,
        'oracle_calls': result.oracle_calls,
    }


def main():
    print(f"{'n':>4}  {'budget':>6}  {'run':>3}  {'greedy':>10}  {'best_obj':>10}  "
          f"{'improved':>8}  {'ttb_s':>8}  {'oracles':>10}")
    print("-" * 80)

    for n in SIZES:
        instance_path = find_instance(n)
        print(f"\n--- Instance: {instance_path.relative_to(INSTANCES_DIR)} (n={n}) ---")

        for budget in TIME_BUDGETS:
            objectives = []
            for rep in range(REPEATS):
                model = load_knapsack_file(instance_path)

                # Run with greedy init (matches training setup)
                res = run_solve(model, budget, use_greedy_init=True)
                improved = "YES" if (res['greedy_obj'] is not None and
                                     res['objective'] > res['greedy_obj']) else "no"
                objectives.append(res['objective'])

                print(f"{n:>4}  {budget:>6.1f}  {rep:>3}  {res['greedy_obj']:>10.0f}  "
                      f"{res['objective']:>10.0f}  {improved:>8}  "
                      f"{res['time_to_best']:>8.3f}  {res['oracle_calls']:>10}")

            mean_obj = sum(objectives) / len(objectives)
            spread = max(objectives) - min(objectives)
            print(f"  >> mean={mean_obj:.0f}  spread={spread:.0f}  "
                  f"min={min(objectives):.0f}  max={max(objectives):.0f}")


if __name__ == "__main__":
    main()
