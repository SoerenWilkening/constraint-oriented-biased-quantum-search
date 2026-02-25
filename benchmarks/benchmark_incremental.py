#!/usr/bin/env python3
"""Benchmark: incremental constraint evaluation in local_search.

Measures local_search wall-clock time across representative problem sizes.
Run on any commit to compare performance between incremental and full-recalc
evaluation paths.

Usage:
    python benchmarks/benchmark_incremental.py
"""
import time
import statistics
import random
import logging
import warnings

# Suppress history callback warnings during benchmark
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE


CONFIGS = [
    # (num_vars, num_constraints, label)
    (10, 5, "small-10"),
    (20, 10, "small-20"),
    (50, 25, "medium-50"),
    (100, 50, "medium-100"),
    (200, 100, "large-200"),
    (500, 200, "large-500"),
]

NUM_RUNS = 5
STOPPING_TIME = 2.0  # seconds per run (cap to keep benchmark reasonable)
DISTANCE = 1         # single-flip neighbourhood


def build_problem(num_vars, num_constraints, seed=42):
    """Build a random knapsack-style problem.

    Creates a Model with random linear constraints and a weighted-sum
    objective.  Uses the same pattern as benchmarks/test_bench_solver.py.
    """
    rng = random.Random(seed)
    m = Model()

    vars_dict = m.add_variables(num_vars)
    variables = [vars_dict[i] for i in range(num_vars)]

    # Random constraints: sparse linear inequalities
    for c in range(num_constraints):
        n_terms = min(rng.randint(2, max(3, num_vars // 5)), num_vars)
        var_indices = rng.sample(range(num_vars), n_terms)
        coeffs = [rng.randint(-5, 10) for _ in range(n_terms)]

        # Build expression term by term
        terms = [coeffs[j] * variables[var_indices[j]] for j in range(n_terms)]
        expr = terms[0]
        for term in terms[1:]:
            expr = expr + term

        rhs = rng.randint(num_vars // 4, num_vars * 2)
        m.add_constraint(expr <= rhs)

    # Objective: maximize weighted sum
    obj_terms = [rng.randint(1, 20) * variables[i] for i in range(num_vars)]
    obj = obj_terms[0]
    for term in obj_terms[1:]:
        obj = obj + term
    m.set_objective(obj, MAXIMIZE)

    m.close()
    m.set_param("stopping_time", STOPPING_TIME)
    m.set_param("distance", DISTANCE)

    return m


def benchmark_config(num_vars, num_constraints, label):
    """Run benchmark for one configuration."""
    times = []
    all_ok = True
    for run in range(NUM_RUNS):
        m = build_problem(num_vars, num_constraints, seed=42 + run)
        start = time.perf_counter()
        result = m.local_search()
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        # Correctness check: solver returned without crash and produced a solution
        if result is None or result.solution is None:
            all_ok = False

    median_time = statistics.median(times)
    return {
        "label": label,
        "num_vars": num_vars,
        "num_constraints": num_constraints,
        "median_s": median_time,
        "min_s": min(times),
        "max_s": max(times),
        "all_times": times,
        "all_ok": all_ok,
    }


def main():
    print("=" * 60)
    print("Incremental Evaluation Benchmark")
    print("=" * 60)
    print(f"Runs per config: {NUM_RUNS}")
    print(f"Stopping time:   {STOPPING_TIME}s")
    print(f"Distance:        {DISTANCE}")
    print()

    results = []
    for num_vars, num_constraints, label in CONFIGS:
        print(f"Running {label} ({num_vars} vars, {num_constraints} constraints)...")
        r = benchmark_config(num_vars, num_constraints, label)
        results.append(r)
        ok_str = "OK" if r["all_ok"] else "FAIL"
        print(
            f"  Median: {r['median_s']:.4f}s  "
            f"Range: [{r['min_s']:.4f}, {r['max_s']:.4f}]  "
            f"Correctness: {ok_str}"
        )

    # Print markdown table
    print()
    print("## Results (Markdown)")
    print()
    print(
        "| Config | Variables | Constraints | Median (s) | Min (s) | Max (s) | Correct |"
    )
    print(
        "|--------|-----------|-------------|------------|---------|---------|---------|"
    )
    for r in results:
        ok = "Yes" if r["all_ok"] else "No"
        print(
            f"| {r['label']} | {r['num_vars']} | {r['num_constraints']} | "
            f"{r['median_s']:.4f} | {r['min_s']:.4f} | {r['max_s']:.4f} | {ok} |"
        )

    return results


if __name__ == "__main__":
    main()
