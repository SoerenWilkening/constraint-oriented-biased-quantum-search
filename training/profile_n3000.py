#!/usr/bin/env python3
"""Run n=3000 knapsack instance for 60s single-threaded with history tracking."""
import sys
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cbqs import Model, MAXIMIZE


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


print("Building n=3000 knapsack instance...")
model = make_knapsack(3000)
print(f"Model built: {len(model.variables)} variables")

model.set_param('num_workers', 1)
model.set_param('stopping_time', 60.0)

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
print("Solving for 60s single-threaded...")
result = model.solve()

print(f"\nFinal objective: {result.objective}")
print(f"Solve time: {result.solve_time:.0f}ms")
print(f"Oracle calls: {result.oracle_calls}")
print(f"\nImprovement history ({len(history)} improvements):")
print(f"{'step':>5}  {'objective':>12}  {'time_s':>10}  {'delta':>10}")
prev = greedy_obj
for i, (obj, t) in enumerate(history):
    delta = obj - prev
    prev = obj
    print(f"{i:>5}  {obj:>12.0f}  {t:>10.3f}  {delta:>+10.0f}")

# Summary: when did improvements slow down?
if history:
    print(f"\nFirst improvement at: {history[0][1]:.3f}s")
    print(f"Last improvement at:  {history[-1][1]:.3f}s")
    total_gain = history[-1][0] - greedy_obj
    # Find when 50%, 90%, 99% of gain was achieved
    for pct in [0.5, 0.9, 0.95, 0.99]:
        target = greedy_obj + pct * total_gain
        for obj, t in history:
            if obj >= target:
                print(f"  {pct*100:5.1f}% of gain by {t:.3f}s")
                break
