#!/usr/bin/env python3
"""bd kyg — conditional analysis: the opt_sat radius lever ONLY acts where the warm greedy start is
INFEASIBLE (so the opt_sat / feasibility-push phase actually runs). On greedy-feasible instances the
phase machine jumps straight to opt and opt_sat_branching_radius is provably inert (Δ≡0 vs C_r2). So the
all-instance median dilutes the signal with exact zeros; the correct read conditions on greedy-infeasible
instances. This script computes greedy feasibility per instance and scores an opt_sat sweep on that subset.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.kyg_conditional --n 90 \
      --dir benchmarks/artifacts/m5_kyg/n90_optsat [--seeds ...]
"""
import argparse, json, os, sys
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget

DEFAULT_SEEDS = (20260630, 20260701, 20260702)


def greedy_feasibility(n, indices, bench_root):
    out = {}
    for idx in indices:
        c1, c2, c3 = load_eq29(n, idx, bench_root)
        m = build_model(c1, c2, c3, vectorized=True)
        _gv, gf = m.general_greedy()
        out[idx] = bool(gf)
    return out


def load_cell(d, n, idx, arm, s):
    p = os.path.join(d, f"{n}_{idx}__{arm}__s{s}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def sweep(n, d, indices, seeds, arms, bench_root, T):
    feas = greedy_feasibility(n, indices, bench_root)
    infeas = [i for i in indices if not feas[i]]
    feasible = [i for i in indices if feas[i]]
    print(f"\nn={n}: greedy INFEASIBLE (opt_sat runs) = {infeas}   "
          f"greedy-feasible (opt_sat inert) = {feasible}")
    print(f"read: obj@common per-pair vs C_r2 (baseline opt_sat=8), median-over-seeds, faithful M=T(n)={T}")
    print(f"{'arm':>9} | {'median Δ (ALL 9)':>17} | {'median Δ (infeasible-greedy)':>28} | "
          f"sign(inf) | p(inf, greater)")
    for arm in arms:
        if arm == "C_r2":
            continue
        # per-instance median-over-seeds Δ vs C_r2 at per-pair common budget
        med_all, med_inf, perinst = [], [], {}
        for idx in indices:
            ds = []
            ok = True
            for s in seeds:
                ra, rb = load_cell(d, n, idx, arm, s), load_cell(d, n, idx, "C_r2", s)
                if ra is None or rb is None:
                    ok = False; break
                B = min(int(ra["oracle_calls"]), int(rb["oracle_calls"]), T)
                a, b = obj_at_budget(ra["history"], B), obj_at_budget(rb["history"], B)
                if a is None or b is None:
                    ok = False; break
                ds.append(a - b)
            if not ok:
                continue
            md = float(np.median(ds)); perinst[idx] = md
            med_all.append(md)
            if idx in infeas:
                med_inf.append(md)
        pos = sum(1 for i in infeas if perinst.get(i, 0) > 0)
        neg = sum(1 for i in infeas if perinst.get(i, 0) < 0)
        p = 1.0
        if any(x != 0 for x in med_inf):
            try:
                _W, p = ss.wilcoxon(med_inf, alternative="greater", zero_method="wilcox"); p = float(p)
            except ValueError:
                p = 1.0
        ma = float(np.median(med_all)) if med_all else float("nan")
        mi = float(np.median(med_inf)) if med_inf else float("nan")
        print(f"{arm:>9} | {ma:>+17,.0f} | {mi:>+28,.0f} | {pos:>4}+/{neg}- | {p:.4g}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    ap.add_argument("--indices", default=",".join(str(i) for i in range(9)))
    ap.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    a = ap.parse_args(argv)
    seeds = [int(x) for x in a.seeds.split(",")]
    indices = [int(x) for x in a.indices.split(",")]
    T = metric.oracle_budget(a.n)
    cfg = json.load(open(os.path.join(a.dir, "run_config.json")))
    arms = [x for x in cfg["arms"] if x.startswith("optsat")]
    sweep(a.n, a.dir, indices, seeds, arms, a.bench_root, T)


if __name__ == "__main__":
    main()
