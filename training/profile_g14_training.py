#!/usr/bin/env python3
"""Profile g=14 instances (n=300-600) for 30s single-threaded.
Check if they're suitable for training: do they keep improving past 1s?"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE

INSTANCES_DIR = PROJECT_ROOT / "training" / "knapsack_instances"
SIZES = [300, 350, 400, 450, 500, 550, 600]
TIME_BUDGET = 30.0


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


print(f"{'n':>4}  {'greedy':>15}  {'final':>15}  {'gain':>10}  {'gain%':>7}  "
      f"{'#impr':>6}  {'last_t':>7}  {'t50%':>7}  {'t90%':>7}  {'t99%':>7}")
print("-" * 110)

for n in SIZES:
    dirname = f"n_{n}_c_10000000000_g_14_f_0.3_eps_1e-05_s_300"
    path = INSTANCES_DIR / dirname / "test_0.in"
    if not path.exists():
        print(f"{n:>4}  MISSING")
        continue

    model = load_knapsack_file(path)
    model.set_param('num_workers', 1)
    model.set_param('stopping_time', TIME_BUDGET)

    history = []

    def callback(h=history, m=model):
        obj = m.objective_value
        t = m.runtime
        if not h or (obj is not None and obj > h[-1][0]):
            h.append((obj, t))

    model.general_greedy()
    greedy_obj = model.objective_value or 0

    model.set_param('callback', callback)
    result = model.solve()

    final_obj = result.objective or 0
    total_gain = final_obj - greedy_obj

    if history and total_gain > 0:
        last_t = history[-1][1]
        pct_times = {}
        for pct in [0.5, 0.9, 0.99]:
            target = greedy_obj + pct * total_gain
            for obj, t in history:
                if obj >= target:
                    pct_times[pct] = t
                    break
            else:
                pct_times[pct] = float('inf')

        gain_pct = 100 * total_gain / greedy_obj if greedy_obj else 0
        print(f"{n:>4}  {greedy_obj:>15.0f}  {final_obj:>15.0f}  {total_gain:>+10.0f}  "
              f"{gain_pct:>6.3f}%  {len(history):>6}  {last_t:>7.2f}  "
              f"{pct_times[0.5]:>7.2f}  {pct_times[0.9]:>7.2f}  {pct_times[0.99]:>7.02f}")
    else:
        print(f"{n:>4}  {greedy_obj:>15.0f}  {final_obj:>15.0f}  {total_gain:>+10.0f}  "
              f"  0.000%  {len(history):>6}  {'N/A':>7}  {'N/A':>7}  {'N/A':>7}  {'N/A':>7}")
