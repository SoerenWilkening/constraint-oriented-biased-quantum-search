#!/usr/bin/env python3
"""benchmarks/plot_w29_grow_n3000.py — objective-over-oracles for the bd w29 n=3000 grow probe.

Visualises the SAVED w29 grow-probe trajectories at n=3000 instance 0 (900s wall) for the four
arms (CBQS default, constant r=2, constant r=2+theta, cand_16's constant r=4.41+theta, and the
GROW r=2->4.41+theta schedule), on the faithful oracle-cost axis (best-of-portfolio objective vs
cumulative oracle calls — the M0e oracle-indexed running-max history). Mirrors plot_m4_n3000.py.

The 4 w29 arms are read from benchmarks/artifacts/m5_w29_grow/n3000_wall900/3000_0__{arm}__s{seed}.json
(seed 20260630); the CBQS default is reused from the committed M4 capstone artifact
benchmarks/artifacts/m4_n3000/3000_0__default.json (seed 20260624 — the default stalls at
first-feasible structurally, so the cross-seed reuse is illustrative, NOT a matched-seed claim).

Usage:
  python -m benchmarks.plot_w29_grow_n3000 [--index 0] [--seed 20260630]
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

T = 9989  # T(3000) = (3000/32)^2 + 1200
W29_DIR = "benchmarks/artifacts/m5_w29_grow/n3000_wall900"
M4_DIR = "benchmarks/artifacts/m4_n3000"

# arm -> (style). Order = legend order (default first, then tight->broad configs, grow last).
STYLE = {
    "default":       dict(color="#444444", label="CBQS default (bias=n/4; stalls at first-feasible)"),
    "C_r2":          dict(color="#2ca02c", label="constant r=2 (bare best radius)"),
    "C_r2_theta":    dict(color="#9467bd", label="constant r=2 + θ=z(pᵢᵢ)·0.29"),
    "K_const4.41":   dict(color="#d62728", label="cand_16: constant r=4.41 + θ"),
    "K_grow2to4.41": dict(color="#1f77b4", label="GROW r=2→4.41 + θ  (refine-then-explore)"),
}
ARMS = list(STYLE.keys())


def _load(arm, index, seed):
    if arm == "default":
        path = os.path.join(M4_DIR, f"3000_{index}__default.json")
    else:
        path = os.path.join(W29_DIR, f"3000_{index}__{arm}__s{seed}.json")
    with open(path) as f:
        return json.load(f)


def plot_single(index, seed):
    recs = {arm: _load(arm, index, seed) for arm in ARMS}
    default_final = recs["default"]["history"][-1][0]
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    for arm in ARMS:
        h = recs[arm]["history"]
        if not h:
            continue
        xs = [o for (_, o) in h] + [T]
        ys = [v for (v, _) in h] + [h[-1][0]]
        lw = 2.2 if arm == "K_grow2to4.41" else 1.7
        ax.plot(xs, ys, drawstyle="steps-post", lw=lw, **STYLE[arm])
        ax.plot([h[-1][1]], [h[-1][0]], "o", color=STYLE[arm]["color"], ms=5)
    ax.axhline(default_final, color="#444444", ls=":", lw=0.9, alpha=0.7)
    ax.axvline(T, color="grey", ls="--", lw=0.9, alpha=0.6)
    ax.annotate(f"T(n)={T}", xy=(T, default_final), xytext=(-4, 6),
                textcoords="offset points", ha="right", fontsize=8, color="grey")
    ax.set_xscale("log")
    ax.set_xlabel("cumulative oracle calls  (the faithful cost axis)")
    ax.set_ylabel("best-of-portfolio objective")
    ax.set_title(f"n=3000 instance {index} — objective vs oracles (bd w29 grow probe, 900s wall)\n"
                 "default stalls at first-feasible; growing r=2→4.41+θ climbs highest "
                 "(single instance — directional)")
    ax.ticklabel_format(axis="y", style="plain")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.92)
    ax.grid(True, which="both", ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(W29_DIR, f"obj_over_oracles_w29_3000_{index}.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)

    # text summary: obj@common (matched min-oracle-depth across the non-default arms) + final
    from benchmarks.run_m4_n3000 import obj_at_budget
    nd = [a for a in ARMS if a != "default"]
    B = min(int(recs[a]["oracle_calls"]) for a in nd)
    base = obj_at_budget(recs["C_r2"]["history"], B)
    print(f"\nn=3000 instance {index} (900s wall) — obj@common (B={B}) Δ vs C_r2, and final:")
    for arm in ARMS:
        o = obj_at_budget(recs[arm]["history"], min(B, int(recs[arm]["oracle_calls"])))
        fin = recs[arm]["history"][-1][0] if recs[arm]["history"] else None
        d = (o - base) if (o is not None) else None
        print(f"  {arm:<14} obj@common={o:,.0f}  Δ_vs_C_r2={d:+,.0f}" if d is not None
              else f"  {arm:<14} (no feasible incumbent)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260630)
    args = ap.parse_args()
    out = plot_single(args.index, args.seed)
    print("\nwrote:", out)


if __name__ == "__main__":
    main()
