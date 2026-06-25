#!/usr/bin/env python3
"""benchmarks/plot_m4_n3000.py — objective-over-oracles for the n=3000 M4 instances.

Reads the SAVED M4 A/B artifacts (``benchmarks/artifacts/m4_n3000/3000_{i}__{arm}.json``)
and plots the best-of-portfolio objective vs cumulative oracle calls (``history`` — the
oracle-indexed, M0e running-max trajectory) for the default vs the discovered schedules
cand_16 / cand_23. Oracles are the faithful cost axis (the "time"); no solver, clone, or
re-run needed — it visualises the committed verdict (NORTHSTAR_CAPSTONE.md §1).

Modes:
  --mode single  [--index 0]   one instance, absolute objective (default)
  --mode grid                  3x3 grid of all 9 instances, absolute objective
  --mode average               mean gain vs each instance's own default, across 9 instances
  --mode all                   produces grid + average + index 0

Usage:
  python -m benchmarks.plot_m4_n3000 --mode all
"""
import argparse
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ARMS = ["default", "cand_16", "cand_23"]
N_INSTANCES = 9
STYLE = {
    "default":  dict(color="#444444", label="CBQS default"),
    "cand_16":  dict(color="#1f77b4", label="cand_16 (M3 winner: r=8/4.4, α=0.012, θ=z(pᵢᵢ))"),
    "cand_23":  dict(color="#d62728", label="cand_23 (parsimonious: r=5.2/4.4, α=0, θ off)"),
}


def _load(out_dir, index, arm):
    with open(os.path.join(out_dir, f"3000_{index}__{arm}.json")) as f:
        return json.load(f)


def _read_T(out_dir):
    with open(os.path.join(out_dir, "summary.json")) as f:
        return int(json.load(f)["T"])


def step_eval(history, grid):
    """Running-max objective at each oracle in *grid*; NaN before first feasible.
    history is feasible-only, oracle-ascending, values non-decreasing (M0e merge)."""
    oracles = np.array([o for (_, o) in history], dtype=float)
    vals = np.array([v for (v, _) in history], dtype=float)
    idx = np.searchsorted(oracles, grid, side="right") - 1
    out = np.where(idx >= 0, vals[np.clip(idx, 0, len(vals) - 1)], np.nan)
    return out


# --------------------------------------------------------------------------- #
def plot_single(out_dir, index, T):
    recs = {arm: _load(out_dir, index, arm) for arm in ARMS}
    default_final = recs["default"]["history"][-1][0]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for arm in ARMS:
        h = recs[arm]["history"]
        xs = [o for (_, o) in h] + [T]
        ys = [v for (v, _) in h] + [h[-1][0]]
        ax.plot(xs, ys, drawstyle="steps-post", lw=1.8, **STYLE[arm])
        ax.plot([h[-1][1]], [h[-1][0]], "o", color=STYLE[arm]["color"], ms=5)
    ax.axhline(default_final, color="#444444", ls=":", lw=0.9, alpha=0.7)
    ax.axvline(T, color="grey", ls="--", lw=0.9, alpha=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("cumulative oracle calls  (the faithful cost axis)")
    ax.set_ylabel("best-of-portfolio objective")
    ax.set_title(f"n=3000 instance {index} — objective vs oracles (M4 A/B)\n"
                 "default stalls at first-feasible; discovered schedules cross it and climb")
    ax.ticklabel_format(axis="y", style="plain")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(True, which="both", ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(out_dir, f"obj_over_oracles_3000_{index}.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_grid(out_dir, T):
    fig, axes = plt.subplots(3, 3, figsize=(15, 11), sharex=True)
    for i in range(N_INSTANCES):
        ax = axes[i // 3][i % 3]
        recs = {arm: _load(out_dir, i, arm) for arm in ARMS}
        dflt = recs["default"]["history"][-1][0]
        for arm in ARMS:
            h = recs[arm]["history"]
            xs = [o for (_, o) in h] + [T]
            ys = [v for (v, _) in h] + [h[-1][0]]
            ax.plot(xs, ys, drawstyle="steps-post", lw=1.4, color=STYLE[arm]["color"])
        ax.axhline(dflt, color="#444444", ls=":", lw=0.8, alpha=0.7)
        ax.set_xscale("log")
        d16 = recs["cand_16"]["history"][-1][0] - dflt
        d23 = recs["cand_23"]["history"][-1][0] - dflt
        ax.set_title(f"3000_{i}  (cand_16 +{d16/1e6:.1f}M, cand_23 +{d23/1e6:.1f}M)", fontsize=9)
        ax.ticklabel_format(axis="y", style="plain")
        ax.tick_params(labelsize=7)
        ax.grid(True, which="both", ls=":", alpha=0.3)
    for ax in axes[2]:
        ax.set_xlabel("cumulative oracle calls", fontsize=8)
    for r in range(3):
        axes[r][0].set_ylabel("objective", fontsize=8)
    handles = [plt.Line2D([], [], color=STYLE[a]["color"], lw=2, label=STYLE[a]["label"]) for a in ARMS]
    fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=9, framealpha=0.9)
    fig.suptitle("n=3000 — objective vs oracles, all 9 M4 instances (default stalls; cand_16/cand_23 climb)",
                 y=0.995, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(out_dir, "obj_over_oracles_3000_all.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_average(out_dir, T):
    grid = np.unique(np.round(np.logspace(np.log10(40), np.log10(T), 400)).astype(int))
    # per-instance gain relative to that instance's OWN default obj@T
    gains = {arm: [] for arm in ARMS}
    for i in range(N_INSTANCES):
        recs = {arm: _load(out_dir, i, arm) for arm in ARMS}
        dbase = step_eval(recs["default"]["history"], grid)
        dbase_final = recs["default"]["history"][-1][0]   # default stall = its obj@T
        for arm in ARMS:
            g = step_eval(recs[arm]["history"], grid) - dbase_final
            gains[arm].append(g)
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    for arm in ARMS:
        stack = np.vstack(gains[arm]) / 1e6                 # millions
        mean = np.nanmean(stack, axis=0)
        std = np.nanstd(stack, axis=0)
        n_ok = np.sum(~np.isnan(stack), axis=0)
        m = n_ok >= 3                                       # only where >=3 instances feasible
        ax.plot(grid[m], mean[m], lw=2.0, color=STYLE[arm]["color"], label=STYLE[arm]["label"])
        if arm != "default":
            ax.fill_between(grid[m], (mean - std)[m], (mean + std)[m],
                            color=STYLE[arm]["color"], alpha=0.15)
    ax.axhline(0, color="#444444", ls=":", lw=1.0, alpha=0.8)
    ax.axvline(T, color="grey", ls="--", lw=0.9, alpha=0.6)
    ax.annotate(f"T(n)={T}", xy=(T, 0), xytext=(-4, 6), textcoords="offset points",
                ha="right", fontsize=8, color="grey")
    ax.set_xscale("log")
    ax.set_xlabel("cumulative oracle calls  (the faithful cost axis)")
    ax.set_ylabel("mean objective gain vs default  (millions, ±1σ across instances)")
    ax.set_title("n=3000 — mean objective gain vs default across 9 M4 instances\n"
                 "candidates start below default, cross ~oracle 200, climb to ~+19–20M @ T(n)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(True, which="both", ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(out_dir, "obj_gain_vs_default_3000_average.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)

    # text summary: mean gain @ T
    print(f"\nn=3000 mean gain vs default @ T(n)={T} (across {N_INSTANCES} instances):")
    for arm in ["cand_16", "cand_23"]:
        finals = np.array([g[-1] for g in gains[arm]])      # gain at the last grid point (= obj@T)
        print(f"  {arm:<9} mean +{finals.mean()/1e6:6.2f}M   median +{np.median(finals)/1e6:6.2f}M   "
              f"min +{finals.min()/1e6:5.2f}M   max +{finals.max()/1e6:6.2f}M   (all {np.sum(finals>0)}/9 > 0)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "grid", "average", "all"], default="single")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--out-dir", default="benchmarks/artifacts/m4_n3000")
    args = ap.parse_args()
    T = _read_T(args.out_dir)
    written = []
    if args.mode in ("single", "all"):
        written.append(plot_single(args.out_dir, args.index, T))
    if args.mode in ("grid", "all"):
        written.append(plot_grid(args.out_dir, T))
    if args.mode in ("average", "all"):
        written.append(plot_average(args.out_dir, T))
    print("\nwrote:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main()
