#!/usr/bin/env python3
"""Run n=100 instance for 60s single-threaded with history tracking."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE

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


instance_path = (PROJECT_ROOT / "training" / "knapsack_instances" /
                 "n_100_c_10000000000_g_6_f_0.3_eps_1e-05_s_300" / "test_0.in")

model = load_knapsack_file(instance_path)
model.set_param('num_workers', 1)
model.set_param('stopping_time', 60.0)

# Track all improvements
history = []

def callback():
    obj = model.objective_value
    t = model.runtime
    if not history or (obj is not None and obj > history[-1][0]):
        history.append((obj, t))

model.general_greedy()
greedy_obj = model.objective_value
print(f"Greedy objective: {greedy_obj}")

model.set_param('callback', callback)
result = model.solve()

print(f"\nFinal objective: {result.objective}")
print(f"Solve time: {result.solve_time:.0f}ms")
print(f"Oracle calls: {result.oracle_calls}")
print(f"\nImprovement history ({len(history)} improvements):")
print(f"{'step':>5}  {'objective':>15}  {'time_s':>10}  {'delta':>10}")
for i, (obj, t) in enumerate(history):
    delta = obj - greedy_obj if i == 0 else obj - history[i-1][0]
    print(f"{i:>5}  {obj:>15.0f}  {t:>10.3f}  {delta:>+10.0f}")
