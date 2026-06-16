#!/usr/bin/env python3
"""benchmarks/plot_m3_n90.py — objective-over-time, M3 findings vs the CBQS default
on the anchored n=90 Eq.29 instances (bd 884 follow-up; user request 2026-06-16).

WHAT IT SHOWS
-------------
The M3 finding (``benchmarks/M3_RUN_884_FINDINGS.md``) is that a **radius+switch**
schedule beats the CBQS default on the anchored ``n≤90`` strata, the dominant lever
being ``opt_switch_oracles`` (switch to the explore phase ~5–8× earlier). This driver
re-solves the 9 anchored ``n=90`` instances under three schedules and plots the
**best-of-portfolio objective vs cumulative oracle calls** (``result.history`` — the
oracle-indexed, M0e running-max trajectory). Oracles are the faithful cost axis (the
"time"); at ``n=90`` the budget ``T(90) = (90/32)² + 1200 = 1207``.

SCHEDULES
---------
* ``default``      — the CBQS default (empty param dict == close()'s n/4 bias path).
* ``m3_winner``    — cand_16, the highest-fitness §13 survivor
                     (r_opt_sat=8.0, r_opt=4.41, α_switch=0.012, θ=0.29·z(p_ii)).
* ``m3_parsimonious`` — cand_23, the θ-OFF cluster representative
                     (r_opt_sat=5.16, r_opt=4.43, α_switch=0.0, θ off) — the robust
                     recommendation ("the cluster, not the point, is the finding").

FAITHFULNESS / RUN POLICY
-------------------------
Exactly the M3 A/B recipe: equal-``T(n)`` (M=-1 both arms), exact sampler
(opt_sample_cap=0), matched seed bank (1..7), solver-default worker count,
``variable_order`` held out. Per the CLAUDE.md RUN POLICY a wall cap
``stopping_time = 1800`` s is set on every solve; at ``n=90`` it is DORMANT (~0.2 s
< cap), which the CAPSTONE proves: the recomputed default median-PI must reproduce
the frozen ``default_PI`` anchor bit-for-bit (it would not if the cap bound or the
setup drifted). Fail-loud if it doesn't (CLAUDE.md §2.1 / M1 lesson).

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.plot_m3_n90 [--out-dir DIR]
"""
import argparse
import json
import math
import os
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmarks import baselines, m2, m3_proposer, metric  # noqa: E402
from benchmarks.eq29_loader import build_model, load_eq29  # noqa: E402

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
N = 90
SEEDS = baselines.DEFAULT_SEED_BANK            # (1..7), the frozen-anchor bank
STOPPING_TIME = 1800                           # RUN POLICY wall cap (dormant at n=90)

# Exact §13 survivor genomes (from artifacts/m3_run_884/summary.json). Genome layout:
# [r_opt_sat, r_opt, alpha_switch, theta_amp, theta_feature_index]; pii_z == index 1.
GENOME_WINNER = [8.0, 4.409916944894315, 0.012044790907040026,
                 0.28884412462871306, 1.0]                       # cand_16
GENOME_PARSIMONIOUS = [5.164074159795587, 4.428165071164998, 0.0,
                       0.34053296197047567, 0.0]                 # cand_23 (theta_feature='none')

SCHEDULES = {
    "default": {},
    "m3_winner": m3_proposer.genome_to_factory(GENOME_WINNER),
    "m3_parsimonious": m3_proposer.genome_to_factory(GENOME_PARSIMONIOUS),
}
SCHEDULE_LABELS = {
    "default": "CBQS default",
    "m3_winner": "M3 winner (cand_16: r=8/4.4, α=0.012, θ=z(pₙ))",
    "m3_parsimonious": "M3 parsimonious (cand_23: r=5.2/4.4, α=0, θ off)",
}
SCHEDULE_COLORS = {"default": "#666666", "m3_winner": "#1f77b4",
                   "m3_parsimonious": "#2ca02c"}


# --------------------------------------------------------------------------- #
# Solving (mirrors m2.run_candidate_seed_bank, + the RUN POLICY wall cap)
# --------------------------------------------------------------------------- #
def solve_seed_bank(n, index, params_or_factory, bench_root):
    """Solve one instance once per master seed at the faithful M3 A/B recipe.

    Identical to :func:`benchmarks.m2.run_candidate_seed_bank` (M=-1 real T(n),
    exact sampler, vectorized build, fail-loud seed guard) plus the RUN POLICY
    ``stopping_time`` wall cap. Returns the list of OptimizeResults."""
    bad = [s for s in SEEDS if int(s) <= 0]
    if bad:
        raise ValueError(f"seed bank has non-positive seeds {bad!r} (seed 0 == entropy, "
                         f"non-reproducible — use >= 1; bd cjz).")
    c1, c2, c3 = load_eq29(n, index, bench_root)
    resolved = m2.resolve_params(params_or_factory, n, c1, c2, c3)
    out = []
    for seed in SEEDS:
        m = build_model(c1, c2, c3, vectorized=True)
        m.seed = int(seed)
        m.set_param("M", -1)                       # real T(n) == equal-T(n) A/B (§1.1)
        m.set_param("verify", True)
        m.set_param("opt_sample_cap", 0)           # exact sampler (no approximation)
        m.set_param("stopping_time", STOPPING_TIME)  # RUN POLICY; dormant at n=90
        for key, value in resolved.items():
            m.set_param(key, value)
        out.append(m.solve())
    return out, resolved


# --------------------------------------------------------------------------- #
# Trajectory math
# --------------------------------------------------------------------------- #
def step_eval(history, grid, floor):
    """Right-continuous best-objective step function on *grid* (oracle axis).

    ``history`` is the FEASIBLE-only running-max ``[(value, oracle), ...]``. Before
    the first feasible incumbent the best is the floor ``L_I`` (γ=1 region, matching
    metric.compute_primal_integral's pre-feasible convention). Oracle stamps are
    clipped to the grid's max (the metric clips overshoot to T_I)."""
    best = np.full(len(grid), float(floor), dtype=float)
    for value, oracle in history:
        best[grid >= oracle] = float(value)
    return best


def median_trajectory(histories, grid, floor):
    """Median over seeds of the per-seed best-objective step functions."""
    stack = np.vstack([step_eval(h, grid, floor) for h in histories])
    return np.median(stack, axis=0), stack


def gamma_curve(best_values, B_I, D_I):
    """Bounded signed primal gap γ over a best-objective array (metric.gamma)."""
    return np.array([metric.gamma(float(b), B_I, D_I) for b in best_values])


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run(out_dir, bench_root):
    os.makedirs(out_dir, exist_ok=True)
    frozen = baselines.load_frozen_baselines(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines_frozen.csv"))
    instances = sorted(idx for (sz, idx) in frozen
                       if sz == N and frozen[(sz, idx)].get("default_PI") is not None)
    T = metric.oracle_budget(N)
    grid = np.arange(0, T + 1)
    print(f"[plot_m3_n90] n={N}: {len(instances)} anchored instances {instances}; "
          f"T(n)={T}; seeds {SEEDS}; schedules {list(SCHEDULES)}")

    data = {}        # data[index][sched] = {histories, resolved, B_I, L_I, median_PI}
    capstone_fail = []
    t_start = time.time()
    for index in instances:
        anchor = frozen[(N, index)]
        B_I, L_I = float(anchor["B_I"]), float(anchor["L_I"])
        data[index] = {"B_I": B_I, "L_I": L_I, "schedules": {}}
        for sched, pf in SCHEDULES.items():
            t0 = time.time()
            results, resolved = solve_seed_bank(N, index, pf, bench_root)
            histories = [[(float(v), int(o)) for (v, o) in (r.history or [])]
                         for r in results]
            pis = [metric.compute_primal_integral(r.history, B_I, L_I, T) for r in results]
            med_pi = statistics.median(pis)
            data[index]["schedules"][sched] = {
                "histories": histories,
                "resolved": {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                             for k, v in resolved.items()},
                "per_seed_PI": pis, "median_PI": med_pi,
                "final_obj_median": float(np.median([r.objective for r in results])),
            }
            print(f"  {N}_{index} {sched:16s} median_PI={med_pi:.4f} "
                  f"final_obj(med)={np.median([r.objective for r in results]):.0f} "
                  f"({time.time()-t0:.1f}s)")
        # CAPSTONE: recomputed default median-PI must reproduce the frozen anchor
        # bit-for-bit (proves faithful setup AND that stopping_time is dormant).
        rec = data[index]["schedules"]["default"]["median_PI"]
        froz = float(anchor["default_PI"])
        if not math.isclose(rec, froz, rel_tol=1e-9, abs_tol=1e-9):
            capstone_fail.append((index, rec, froz))
    if capstone_fail:
        raise SystemExit(
            "[plot_m3_n90] CAPSTONE FAILED — recomputed default median-PI does not "
            f"reproduce the frozen default_PI (setup drift or a binding wall cap): "
            f"{capstone_fail}. Refusing to plot against a poisoned reference (§2.1).")
    print(f"[plot_m3_n90] CAPSTONE OK: default reproduces all {len(instances)} frozen "
          f"default_PI anchors ({time.time()-t_start:.0f}s total).")

    _save_data(out_dir, data, instances, T)
    _plot(out_dir, data, instances, grid, T)
    _print_summary(data, instances)
    return data


def _save_data(out_dir, data, instances, T):
    path = os.path.join(out_dir, "m3_n90_trajectories.json")
    with open(path, "w") as fh:
        json.dump({"n": N, "T": T, "seeds": list(SEEDS), "instances": instances,
                   "genomes": {"m3_winner": GENOME_WINNER,
                               "m3_parsimonious": GENOME_PARSIMONIOUS},
                   "data": {str(i): data[i] for i in instances}}, fh, indent=1)
    print(f"[plot_m3_n90] raw trajectories -> {path}")


def _print_summary(data, instances):
    print("\n" + "=" * 78)
    print("MEDIAN PRIMAL INTEGRAL (lower = better) — n=90, per instance")
    print("=" * 78)
    hdr = f"{'inst':>6} | " + " | ".join(f"{s:>16}" for s in SCHEDULES)
    print(hdr); print("-" * len(hdr))
    agg = {s: [] for s in SCHEDULES}
    for i in instances:
        row = f"90_{i:<3} | "
        for s in SCHEDULES:
            pi = data[i]["schedules"][s]["median_PI"]
            agg[s].append(pi)
            row += f"{pi:>16.4f} | "
        print(row.rstrip(" |") + " |")
    print("-" * len(hdr))
    mrow = f"{'MEAN':>6} | "
    for s in SCHEDULES:
        mrow += f"{statistics.mean(agg[s]):>16.4f} | "
    print(mrow.rstrip(" |") + " |")
    base = statistics.mean(agg["default"])
    print()
    for s in SCHEDULES:
        if s == "default":
            continue
        m = statistics.mean(agg[s])
        print(f"  {s:16s}: mean PI {m:.4f}  vs default {base:.4f}  "
              f"-> {100*(base-m)/abs(base):+.1f}% PI reduction "
              f"({'better' if m < base else 'worse'})")
    print("=" * 78)


# --------------------------------------------------------------------------- #
# Plot
# --------------------------------------------------------------------------- #
def _plot(out_dir, data, instances, grid, T):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    D_by_inst = {i: metric.d_i(data[i]["B_I"], data[i]["L_I"]) for i in instances}

    # ---- Figure 1: per-instance objective-over-oracles (3x3 grid). ----
    ncol = 3
    nrow = int(math.ceil(len(instances) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(15, 4.2 * nrow), squeeze=False)
    for ax_i, index in enumerate(instances):
        ax = axes[ax_i // ncol][ax_i % ncol]
        B_I, L_I = data[index]["B_I"], data[index]["L_I"]
        for sched in SCHEDULES:
            hs = data[index]["schedules"][sched]["histories"]
            med, stack = median_trajectory(hs, grid, L_I)
            c = SCHEDULE_COLORS[sched]
            for row in stack:                       # thin per-seed portfolio spread
                ax.plot(grid, row, color=c, alpha=0.10, lw=0.6)
            ax.plot(grid, med, color=c, lw=2.0,
                    label=f"{sched} (PI={data[index]['schedules'][sched]['median_PI']:.3f})")
        ax.axhline(B_I, ls="--", color="k", lw=1.0, alpha=0.7)
        ax.axhline(L_I, ls=":", color="k", lw=1.0, alpha=0.5)
        ax.set_title(f"90_{index}   B_I={B_I:.0f} (hexaly)", fontsize=10)
        ax.set_xlabel("cumulative oracle calls  (faithful cost axis)")
        ax.set_ylabel("best-of-portfolio objective")
        ax.set_xlim(0, T)
        ax.set_ylim(L_I - 0.03 * (B_I - L_I), B_I + 0.04 * (B_I - L_I))
        ax.legend(fontsize=7, loc="lower right")
        ax.grid(alpha=0.25)
    for k in range(len(instances), nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")
    fig.suptitle("CBQS objective over oracle budget — M3 findings vs default, "
                 f"n=90 Eq.29 (median over seeds {SEEDS}; dashed=B_I target, dotted=L_I floor)",
                 fontsize=13, y=0.998)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    p1 = os.path.join(out_dir, "m3_n90_objective_over_time.png")
    fig.savefig(p1, dpi=130); plt.close(fig)

    # ---- Figure 2: aggregate normalized primal gap γ over oracles. ----
    fig2, ax = plt.subplots(figsize=(10, 6))
    for sched in SCHEDULES:
        per_inst = []
        for index in instances:
            hs = data[index]["schedules"][sched]["histories"]
            med, _ = median_trajectory(hs, grid, data[index]["L_I"])
            per_inst.append(gamma_curve(med, data[index]["B_I"], D_by_inst[index]))
        mean_gamma = np.mean(np.vstack(per_inst), axis=0)
        auc = float(np.trapz(mean_gamma, grid) / T)   # ≈ aggregate PI
        ax.plot(grid, mean_gamma, color=SCHEDULE_COLORS[sched], lw=2.2,
                label=f"{SCHEDULE_LABELS[sched]}  (∫γ/T ≈ {auc:.3f})")
    ax.axhline(0.0, ls="--", color="k", lw=1.0, alpha=0.6)
    ax.set_xlabel("cumulative oracle calls  (faithful cost axis; T(90)=1207)")
    ax.set_ylabel("normalized primal gap  γ = (B_I − best)/D_I   (lower = better)")
    ax.set_title("Aggregate primal gap over oracle budget — n=90 (mean over 9 instances, "
                 "median over seeds)\nArea under curve ≈ primal integral; γ=0 reaches the "
                 "classical frontier B_I", fontsize=11)
    ax.set_xlim(0, T)
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(alpha=0.3)
    fig2.tight_layout()
    p2 = os.path.join(out_dir, "m3_n90_primal_gap_aggregate.png")
    fig2.savefig(p2, dpi=130); plt.close(fig2)
    print(f"[plot_m3_n90] figures -> {p1}\n                       {p2}")


def main(argv=None):
    p = argparse.ArgumentParser(description="objective-over-time, M3 vs default, n=90.")
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "m3_n90"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    run(args.out_dir, args.bench_root)


if __name__ == "__main__":
    main()
