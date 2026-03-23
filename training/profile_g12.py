#!/usr/bin/env python3
"""Profile g=12 instances (n=75, 100, 125) for 60s single-threaded."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE

INSTANCES_DIR = PROJECT_ROOT / "training" / "knapsack_instances"


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


KP_DIR = PROJECT_ROOT / "others" / "KP"

CONFIGS = [
    (KP_DIR / "n_3000_c_10000000000_g_14_f_0.3_eps_1e-05_s_300" / "test_0.in",),
]

TIME_BUDGET = 60.0

for (path,) in CONFIGS:
    print(f"\n{'='*70}")
    print(f"Instance: {path.relative_to(PROJECT_ROOT)}")
    print(f"{'='*70}")

    model = load_knapsack_file(path)
    n = len(model.variables)
    print(f"Variables: {n}")

    model.set_param('num_workers', 1)
    model.set_param('stopping_time', TIME_BUDGET)

    history = []

    def callback(h=history, m=model):
        obj = m.objective_value
        t = m.runtime
        if not h or (obj is not None and obj > h[-1][0]):
            h.append((obj, t))

    model.general_greedy()
    greedy_obj = model.objective_value
    print(f"Greedy objective: {greedy_obj}")

    model.set_param('callback', callback)
    print(f"Solving for {TIME_BUDGET}s single-threaded...")
    result = model.solve()

    print(f"Final objective: {result.objective}")
    print(f"Solve time: {result.solve_time:.0f}ms")
    print(f"Oracle calls: {result.oracle_calls}")
    print(f"Total improvements: {len(history)}")

    if history:
        # Print first 10 and last 10 improvements
        total = len(history)
        show = history[:10]
        if total > 20:
            show += [None]  # separator
            show += history[-10:]
        elif total > 10:
            show += history[10:]

        print(f"\n{'step':>5}  {'objective':>15}  {'time_s':>10}  {'delta':>10}")
        prev = greedy_obj
        idx = 0
        for item in show:
            if item is None:
                print(f"  ... ({total - 20} more improvements) ...")
                continue
            obj, t = item
            # Find actual index
            while history[idx] != item:
                prev = history[idx][0]
                idx += 1
            delta = obj - prev
            prev = obj
            print(f"{idx:>5}  {obj:>15.0f}  {t:>10.3f}  {delta:>+10.0f}")
            idx += 1

        total_gain = history[-1][0] - greedy_obj
        if total_gain > 0:
            print(f"\nFirst improvement at: {history[0][1]:.3f}s")
            print(f"Last improvement at:  {history[-1][1]:.3f}s")
            print(f"Total gain: {total_gain:+.0f} ({100*total_gain/greedy_obj:.1f}%)")
            for pct in [0.5, 0.9, 0.95, 0.99]:
                target = greedy_obj + pct * total_gain
                for obj, t in history:
                    if obj >= target:
                        print(f"  {pct*100:5.1f}% of gain by {t:.3f}s")
                        break
        else:
            print("No improvement over greedy!")
