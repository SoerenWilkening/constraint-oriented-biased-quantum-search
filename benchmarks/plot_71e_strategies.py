#!/usr/bin/env python3
"""bd 71e — comparison plot of strategies on ONE n=3000 instance under a 5-minute wall cap.

Runs the key schedules head-to-head on a single Eq.29 n=3000 instance with a 300 s (5-min) wall cap
and plots the best-of-portfolio objective vs ORACLE COUNT (the faithful project cost axis — the 5-min
cap simply bounds how far each trajectory extends). Strategies:

  default                    the published warm CBQS default ({} overrides; C default schedule)
  cand_16 (M4 winner)        the M4 agent-discovered schedule (genome GENOME_WINNER)
  cand_23 (parsimonious)     the M4 parsimonious winner (GENOME_PARSIMONIOUS)
  broad r=8 (control)        opt_sat=8, opt=8, early switch (the 71e control)
  best constant r=2          opt_sat=8, opt=2, early switch (the 71e static win; r*~2)
  schedule broad->tight r=2  opt_sat=8, opt=2, LATE switch a=0.15 (the rejected 71e schedule proxy)

Histories are oracle-indexed (value, oracle); there are no per-incumbent wall timestamps, so the x
axis is oracles and the title notes the 5-min cap. Resumable: each strategy persists to JSON.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.plot_71e_strategies \
      [--n 3000] [--instance 0] [--wall 300] [--workers 4] [--seed 20260625] [--out-dir DIR] [--plot-only]
"""
import argparse, json, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines, m3_proposer
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.plot_m3_n90 import GENOME_WINNER, GENOME_PARSIMONIOUS

M_BIG = 100_000_000


def _const(opt_sat, opt, alpha):
    def f(n, c1, c2, c3):
        return {"opt_sat_branching_radius": opt_sat, "opt_branching_radius": opt,
                "opt_switch_oracles": int(round(alpha * metric.oracle_budget(n)))}
    return f


#: ordered (key, label, factory) — factory(n,c1,c2,c3)->set_param overrides ({} = C default)
STRATEGIES = [
    ("default",      "default",                   lambda n, c1, c2, c3: {}),
    ("cand16",       "cand_16 (M4 winner)",       m3_proposer.genome_to_factory(GENOME_WINNER)),
    ("cand23",       "cand_23 (parsimonious)",    m3_proposer.genome_to_factory(GENOME_PARSIMONIOUS)),
    ("broad_r8",     "broad r=8 (control)",       _const(8.0, 8.0, 0.012)),
    ("const_r2",     "best constant r=2",         _const(8.0, 2.0, 0.012)),
    ("sched_r2",     "schedule broad->tight r=2", _const(8.0, 2.0, 0.15)),
]


def solve(key, factory, n, idx, seed, wall, workers, bench_root):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    overrides = factory(n, c1, c2, c3)
    m = build_model(c1, c2, c3, vectorized=True)
    gv, gf = m.general_greedy()
    m.seed = int(seed)
    m.set_param("M", M_BIG)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("stopping_time", float(wall))
    m.set_param("track_history", True)
    for k, v in overrides.items():
        m.set_param(k, v)
    t0 = time.time(); r = m.solve(); dt = time.time() - t0
    baselines.warm_repair_history(r, greedy_value=gv, greedy_feasible=gf)
    hist = [[float(v), int(o)] for (v, o) in (r.history or [])]
    safe_over = {k: (np.asarray(v).tolist() if isinstance(v, np.ndarray) else v)
                 for k, v in overrides.items()}   # opt_branching_weights is an ndarray (theta active)
    return {"key": key, "n": n, "index": idx, "seed": int(seed), "wall_s": dt, "overrides": safe_over,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "greedy_feasible": bool(gf), "history": hist}


def _running_max(hist):
    """(oracles, running-max objective) as monotone step arrays from the feasible-only history."""
    xs, ys, best = [], [], None
    for v, o in sorted(hist, key=lambda t: t[1]):
        best = v if best is None else max(best, v)
        xs.append(o); ys.append(best)
    return xs, ys


def make_plot(records, n, idx, wall, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = {"default": "#888888", "cand16": "#1f77b4", "cand23": "#17becf",
              "broad_r8": "#d62728", "const_r2": "#2ca02c", "sched_r2": "#ff7f0e"}
    styles = {"sched_r2": "--", "broad_r8": ":"}
    finals = []
    for key, label, _f in STRATEGIES:
        rec = records.get(key)
        if rec is None or not rec["history"]:
            continue
        xs, ys = _running_max(rec["history"])
        ax.step(xs, ys, where="post", label=label, color=colors.get(key), lw=2.2,
                linestyle=styles.get(key, "-"), alpha=0.95)
        ax.scatter([xs[-1]], [ys[-1]], color=colors.get(key), s=28, zorder=5)
        finals.append((label, ys[-1], xs[-1], rec["oracle_calls"], rec["wall_s"]))

    ax.set_xscale("log")
    ax.set_xlabel("oracle calls (2j+1 charged per Grover round; the faithful cost axis)")
    ax.set_ylabel("best-of-portfolio objective (feasible incumbent)")
    ax.set_title(f"bd 71e — strategy comparison on Eq.29 {n}_{idx} under a 5-min ({int(wall)} s) wall cap\n"
                 f"best constant r=2 vs the broad->tight schedule vs default / M4 winners "
                 f"(warm start, {records[STRATEGIES[0][0]]['seed'] if records else ''} seed, 4 workers)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v/1e9:.4f}e9"))
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.93)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    print(f"[plot] wrote {out_png}")
    print("\n=== final best-of-portfolio objective at the 5-min cap (sorted) ===")
    base = next((f for f in finals if f[0] == "default"), None)
    for label, y, xlast, oc, w in sorted(finals, key=lambda t: -t[1]):
        rel = f"  ({100*(y-base[1])/base[1]:+.4f}% vs default)" if base else ""
        print(f"  {label:<28} obj={y:,.0f}{rel}  @oracle={xlast}  total_oracles={oc}  wall={w:.0f}s")


def main(argv=None):
    p = argparse.ArgumentParser(description="bd 71e strategy comparison plot (5-min cap, one n=3000 instance).")
    p.add_argument("--n", type=int, default=3000)
    p.add_argument("--instance", type=int, default=0)
    p.add_argument("--wall", type=float, default=300.0)         # 5-minute cutoff
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260625)
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_71e_compare"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--plot-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    os.makedirs(args.out_dir, exist_ok=True)
    records = {}
    for i, (key, label, factory) in enumerate(STRATEGIES, 1):
        rp = os.path.join(args.out_dir, f"{args.n}_{args.instance}__{key}__s{args.seed}.json")
        if os.path.exists(rp):
            records[key] = json.load(open(rp))
            print(f"[71e-cmp] ({i}/{len(STRATEGIES)}) skip {label} (done)")
            continue
        if args.plot_only:
            continue
        print(f"[71e-cmp] ({i}/{len(STRATEGIES)}) solve {label} on {args.n}_{args.instance} wall={args.wall}s ...")
        rec = solve(key, factory, args.n, args.instance, args.seed, args.wall, args.workers, args.bench_root)
        with open(rp, "w") as fh:        # context manager => no partial file on a later crash
            json.dump(rec, fh)
        records[key] = rec
        print(f"[71e-cmp]   -> final obj={rec['objective']} feas={rec['feasible']} "
              f"oracles={rec['oracle_calls']} wall={rec['wall_s']:.0f}s hist={len(rec['history'])}")
    out_png = os.path.join(args.out_dir, f"compare_{args.n}_{args.instance}_5min.png")
    make_plot(records, args.n, args.instance, args.wall, out_png)


if __name__ == "__main__":
    main()
