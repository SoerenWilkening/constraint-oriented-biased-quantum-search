#!/usr/bin/env python3
"""bd kyg — visualize the opt_sat-radius SEED VARIANCE (the basin-lottery finding).

Reads the faithful opt_sat sweeps and plots, vs the C_r2 baseline (opt_sat=8), the per-(instance,seed)
obj@common deltas — so the huge per-run spread (±500k at n=90 → ±2.7M at n=500) and its dissolution with
scale are directly inspectable. Every point is one (instance, seed) cell; boxes show median/IQR.

Figures (saved to benchmarks/artifacts/m5_kyg/figures/):
  1. kyg_optsat_variance.png    — opt_sat radius sweep, one panel per n; Δ% vs C_r2, all cells + box.
  2. kyg_optsat6_lottery.png    — per-instance Δ% for optsat6, one panel per n, colored by seed.
  3. kyg_dissolution.png        — median Δ% (+ bootstrap CI) vs n for a few radii: the signal dissolving.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.plot_kyg_variance
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_kyg")
FIG = os.path.join(ART, "figures")

# (n, dir, seeds, radii available) — the faithful opt_sat sweeps
SWEEPS = [
    (60,  os.path.join(ART, "n60_optsat"), [20260630, 20260701, 20260702], [2, 3, 4, 5, 6, 7]),
    (90,  os.path.join(ART, "n90_optsat_5seed"), [20260630, 20260701, 20260702, 20260703, 20260704],
     [2, 3, 4, 5, 5.5, 6, 6.5, 7]),
    (150, os.path.join(ART, "n150_bridge"), [20260630, 20260701, 20260702], [2, 4, 5, 6, 7]),
    (500, os.path.join(ART, "n500_bridge"), [20260630, 20260701, 20260702], [2, 4, 5, 6, 7]),
]
CROSS_RADII = [2, 4, 5, 6, 7]   # radii present at every n (for cross-scale panels)


def _arm(r):
    return f"optsat{int(r) if float(r).is_integer() else r}"


def greedy_infeasible(n, bench_root):
    out = []
    for idx in range(9):
        c1, c2, c3 = load_eq29(n, idx, bench_root)
        m = build_model(c1, c2, c3, vectorized=True)
        if not m.general_greedy()[1]:
            out.append(idx)
    return out


def cell_deltas_pct(n, d, seeds, radius, infeas):
    """List of (idx, seed, delta_pct) for one opt_sat radius vs C_r2, obj@common per-pair, on
    greedy-infeasible instances (where opt_sat actually runs)."""
    T = metric.oracle_budget(n)
    arm = _arm(radius)
    out = []
    for idx in infeas:
        for s in seeds:
            pa = os.path.join(d, f"{n}_{idx}__{arm}__s{s}.json")
            pb = os.path.join(d, f"{n}_{idx}__C_r2__s{s}.json")
            if not (os.path.exists(pa) and os.path.exists(pb)):
                continue
            ra, rb = json.load(open(pa)), json.load(open(pb))
            B = min(int(ra["oracle_calls"]), int(rb["oracle_calls"]), T)
            a, b = obj_at_budget(ra["history"], B), obj_at_budget(rb["history"], B)
            if a is None or b is None or b == 0:
                continue
            out.append((idx, s, 100.0 * (a - b) / b))
    return out


def _boot_ci(vals, B=3000):
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(20260701)
    arr = np.asarray(vals, float)
    meds = [np.median(rng.choice(arr, size=len(arr), replace=True)) for _ in range(B)]
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def fig_variance(bench_root):
    fig, axes = plt.subplots(1, len(SWEEPS), figsize=(5 * len(SWEEPS), 5.2), squeeze=False)
    for ax, (n, d, seeds, radii) in zip(axes[0], SWEEPS):
        infeas = greedy_infeasible(n, bench_root)
        data, labels = [], []
        for r in radii:
            vals = [dp for (_i, _s, dp) in cell_deltas_pct(n, d, seeds, r, infeas)]
            data.append(vals); labels.append(str(r))
        # box (median/IQR) + jittered points
        bp = ax.boxplot(data, positions=range(len(data)), widths=0.55, showfliers=False,
                        medianprops=dict(color="crimson", lw=2), patch_artist=True,
                        boxprops=dict(facecolor="#e8eef7", edgecolor="#4477aa"))
        for i, vals in enumerate(data):
            x = np.full(len(vals), i) + (np.random.default_rng(i).uniform(-0.16, 0.16, len(vals)))
            ax.scatter(x, vals, s=22, alpha=0.7, color="#33668a", edgecolor="white", linewidth=0.4, zorder=3)
        ax.axhline(0, color="black", lw=1, ls="--", alpha=0.7)
        ax.set_title(f"n={n}  ({len(infeas)}/9 greedy-infeasible, {len(seeds)} seeds)")
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
        ax.set_xlabel("opt_sat radius  (baseline C_r2 = 8)")
        ax.set_ylabel("Δ objective vs opt_sat=8  (% at obj@common)")
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("kyg — opt_sat radius sweep: the win is a SEED-VARIANCE BASIN LOTTERY\n"
                 "each point = one (instance, seed); red = median. Spread grows with n; median ≈ 0 by n=500.",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p = os.path.join(FIG, "kyg_optsat_variance.png"); fig.savefig(p, dpi=130); plt.close(fig)
    return p


def fig_lottery(bench_root, radius=6):
    fig, axes = plt.subplots(1, len(SWEEPS), figsize=(5 * len(SWEEPS), 5.0), squeeze=False)
    for ax, (n, d, seeds, radii) in zip(axes[0], SWEEPS):
        infeas = greedy_infeasible(n, bench_root)
        cells = cell_deltas_pct(n, d, seeds, radius, infeas)
        colors = plt.cm.viridis(np.linspace(0, 0.9, len(seeds)))
        smap = {s: colors[i] for i, s in enumerate(seeds)}
        for (idx, s, dp) in cells:
            xi = infeas.index(idx)
            ax.scatter(xi + (list(seeds).index(s) - len(seeds) / 2) * 0.12, dp,
                       color=smap[s], s=42, edgecolor="black", linewidth=0.4, zorder=3)
        ax.axhline(0, color="black", lw=1, ls="--", alpha=0.7)
        ax.set_title(f"n={n}  optsat{radius} vs opt_sat=8")
        ax.set_xticks(range(len(infeas))); ax.set_xticklabels(infeas)
        ax.set_xlabel("instance (greedy-infeasible)")
        ax.set_ylabel("Δ objective vs opt_sat=8 (%)")
        ax.grid(axis="y", alpha=0.3)
    handles = [plt.Line2D([0], [0], marker="o", ls="", color=plt.cm.viridis(i / max(1, len(SWEEPS[0][2]) - 1)),
                          label=f"seed {s}") for i, s in enumerate(SWEEPS[0][2])]
    axes[0][-1].legend(handles=handles, fontsize=7, title="seed", loc="best")
    fig.suptitle(f"kyg — per-instance seed spread for optsat{radius}: same instance swings ±sign across seeds\n"
                 "(the median-over-seeds 'sign-consistency' is a thin lottery, not a systematic win)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    p = os.path.join(FIG, f"kyg_optsat{radius}_lottery.png"); fig.savefig(p, dpi=130); plt.close(fig)
    return p


def fig_dissolution(bench_root):
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ns = [n for (n, _d, _s, _r) in SWEEPS]
    for r in CROSS_RADII:
        meds, los, his = [], [], []
        for (n, d, seeds, radii) in SWEEPS:
            infeas = greedy_infeasible(n, bench_root)
            vals = [dp for (_i, _s, dp) in cell_deltas_pct(n, d, seeds, r, infeas)]
            meds.append(np.median(vals) if vals else np.nan)
            lo, hi = _boot_ci(vals); los.append(lo); his.append(hi)
        ax.plot(ns, meds, marker="o", label=f"optsat{r}")
        ax.fill_between(ns, los, his, alpha=0.12)
    ax.axhline(0, color="black", lw=1, ls="--")
    ax.set_ylim(-0.15, 0.15)   # focus on the median-lean trend; n=60 CI band clips (outlier-driven)
    ax.set_xscale("log"); ax.set_xticks(ns); ax.set_xticklabels([str(n) for n in ns])
    ax.set_xlabel("n (log)"); ax.set_ylabel("median Δ% vs opt_sat=8 (bootstrap 95% CI band; y clipped ±0.15)")
    ax.set_title("kyg — the opt_sat signal APPEARS then DISSOLVES with scale\n"
                 "median lean shrinks toward 0; CI straddles 0 by n=500 (basin variance dominates)", fontsize=11)
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    p = os.path.join(FIG, "kyg_dissolution.png"); fig.savefig(p, dpi=130); plt.close(fig)
    return p


def main():
    bench_root = os.environ.get("CBQS_BENCHMARKS_DIR")
    if not bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR required (greedy-feasibility needs the instances).")
    os.makedirs(FIG, exist_ok=True)
    p1 = fig_variance(bench_root)
    p2 = fig_lottery(bench_root, radius=6)
    p3 = fig_dissolution(bench_root)
    print("wrote:")
    for p in (p1, p2, p3):
        print(" ", p)


if __name__ == "__main__":
    main()
