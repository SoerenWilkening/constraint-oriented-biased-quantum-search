#!/usr/bin/env python3
"""bd a0w: the angle-precision CLIFF figure — objective and realized radius vs eps.

Two stacked panels per n, both x-axes the gridsynth accuracy `eps` (log, coarse
on the LEFT so the reader walks from cheap circuits to expensive ones), with the
Ross-Selinger T-count per rotation on a twin top axis:

  top    — median objective delta vs the exact-angle arm, % (the CLIFF), with the
           seed-noise floor shaded: inside the band, "degradation" is unmeasurable.
  bottom — the MECHANISM: realized opt-phase Hamming radius (from
           result.branch_diagnostics) against the analytic prediction
           r_q = n*sin^2(theta_q/2). Systematic rounding is a non-monotone
           LATTICE (collapse to 0 and inflation both occur); dithered rounding
           approaches r from ABOVE via the second-order bias.

Usage:  python -m benchmarks.plot_a0w_precision [--dirs d1 d2 ...] [--out FILE]
"""
import argparse, json, math, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks.run_a0w_precision_probe import arm_name
from cbqs.phase_params import angle_precision_bits, t_count_per_rotation

MODES = (("systematic", "one circuit reused (systematic)", "tab:red", "o", "-"),
         ("dithered", "per-variable synthesis (dithered)", "tab:blue", "s", "--"))


def _panel_data(summary, mode_key):
    m = summary["modes"][mode_key]
    eps, dobj, r_real, r_pred = [], [], [], []
    for e in sorted(summary["eps_grid"]):
        a = arm_name(e, m["dither"])
        c = m["cmp"].get(a)
        if c is None or c["median_pct"] is None:
            continue
        eps.append(e)
        dobj.append(c["median_pct"])
        r_real.append(m["realized_radius"].get(a))
        r_pred.append(m["predicted_radius"][a])
    return eps, dobj, r_real, r_pred


def plot(summaries, out_path):
    ncol = len(summaries)
    fig, axes = plt.subplots(2, ncol, figsize=(6.2 * ncol, 8.2), squeeze=False)
    for col, s in enumerate(summaries):
        n = s["N"]
        ax_o, ax_r = axes[0][col], axes[1][col]
        noise = s.get("seed_noise_pct")
        if noise:
            ax_o.axhspan(-abs(noise), abs(noise), color="0.85", zorder=0,
                         label=f"seed-noise floor ±{noise:.3f}%")
        ax_o.axhline(0, color="k", lw=0.8, zorder=1)
        for key, label, color, marker, ls in MODES:
            eps, dobj, r_real, r_pred = _panel_data(s, key)
            if not eps:
                continue
            ax_o.plot(eps, dobj, marker=marker, ls=ls, color=color, label=label)
            star = s["modes"][key]["eps_star"]
            if star:
                ax_o.axvline(star, color=color, ls=":", lw=1.4)
                ax_o.annotate(f"ε*={star:g}\nb*={angle_precision_bits(star):.1f}",
                              xy=(star, 0), xytext=(4, 6), textcoords="offset points",
                              color=color, fontsize=8, ha="left")
            ax_r.plot(eps, r_real, marker=marker, ls=ls, color=color,
                      label=f"{label} — realized")
            ax_r.plot(eps, r_pred, marker="", ls=":", color=color, alpha=0.7,
                      label=f"{label} — predicted n·sin²(θ_q/2)")
        exact_r = s.get("exact_radius_mean")
        if exact_r is not None:
            ax_r.axhline(exact_r, color="k", lw=0.9, ls="-",
                         label=f"exact-angle realized r = {exact_r:.2f}")
        for ax in (ax_o, ax_r):
            ax.set_xscale("log")
            ax.invert_xaxis()          # coarse (cheap) on the LEFT
            ax.grid(alpha=0.3)
        ax_o.set_title(f"n={n}   θ={s['theta_exact']:.4f} rad at r={s['r_opt']}   "
                       f"T(n)={s['T']}, {len(s['indices'])} inst × {len(s['seeds'])} seeds")
        ax_o.set_ylabel("median Δ objective vs exact angles (%)")
        ax_o.legend(fontsize=8, loc="lower left")
        ax_r.set_ylabel("realized opt-phase Hamming radius")
        ax_r.set_xlabel("gridsynth accuracy ε (rad) — coarser/cheaper to the left")
        ax_r.set_yscale("symlog", linthresh=1.0)
        ax_r.legend(fontsize=7, loc="upper left")
        top = ax_o.secondary_xaxis("top", functions=(lambda e: e, lambda e: e))
        top.set_xticks([e for e in s["eps_grid"]])
        top.set_xticklabels([f"{t_count_per_rotation(e):.0f}" for e in s["eps_grid"]],
                            fontsize=7)
        top.set_xlabel("Ross-Selinger T-gates per rotation  (~3·log₂(1/ε))", fontsize=8)
    fig.suptitle("bd a0w — angle-precision cliff: how coarse may the QTG's R_y(θᵢ) be?",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=140)
    print(f"wrote {out_path}")


def main(argv=None):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "artifacts", "m5_a0w_precision")
    p = argparse.ArgumentParser(description="bd a0w angle-precision cliff figure.")
    p.add_argument("--dirs", nargs="*", default=None,
                   help="probe out-dirs (default: every n*_m* under artifacts/m5_a0w_precision)")
    p.add_argument("--out", default=os.path.join(root, "angle_precision_cliff.png"))
    args = p.parse_args(argv)
    dirs = args.dirs or sorted(
        os.path.join(root, d) for d in os.listdir(root)
        if os.path.isfile(os.path.join(root, d, "summary.json")))
    summaries = [json.load(open(os.path.join(d, "summary.json"))) for d in dirs]
    summaries.sort(key=lambda s: s["N"])
    if not summaries:
        raise SystemExit("no summary.json found — run benchmarks.run_a0w_precision_probe first")
    plot(summaries, args.out)


if __name__ == "__main__":
    main()
