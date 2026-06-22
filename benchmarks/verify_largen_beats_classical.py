#!/usr/bin/env python3
"""Verify: warm CBQS beats classical SOTA at n>=1000 (bd 8an.11).

For each probed n>=1000 instance:
  1. run warm CBQS (general_greedy warm start + solve), best-of-portfolio over seeds;
  2. INDEPENDENTLY audit the returned solution from the raw c1/c2/c3 (NOT the solver's
     verify flag): recompute objective + BOTH constraints per the Eq.29 semantics
     (eq29_loader docstring) and confirm feasible + objective-consistent;
  3. compare the (independently-recomputed) objective to B_I (classical-only SOTA:
     gurobi/hexaly/simanneal) and to the published iqs (CBQS).

RUN POLICY: stopping_time=1800s safety cap on every solve (binds only at n=3000;
n=1000 converges under T(1000)=2176 in ~2min). Output: a per-instance verdict table.
"""
import csv, glob, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import baselines
from benchmarks.eq29_loader import load_eq29, build_model, eq29_rhs

BENCH = os.environ["CBQS_BENCHMARKS_DIR"]
PLOTS = os.path.join(BENCH, "Paper_general_constraints", "plots")
N1000 = [(1000, i) for i in range(9)]          # all anchored n=1000
N3000 = [(3000, i) for i in range(3)]          # sample at the largest scale
SEEDS_SMALL = (1, 2, 3)                          # n=1000: best-of-3 (each best-of-portfolio)
SEEDS_LARGE = (1,)                               # n=3000: single (expensive)
CAP_S = 1800


def published_objectives():
    """Best objective per (n,index) by method family from the benchmark CSVs.

    Returns {(n,i): {'B_I_classical': float, 'B_I_method': str, 'iqs': float}}.
    Classical = gurobi/hexaly/simanneal (== baselines.BI_METHODS, the B_I source);
    iqs = published CBQS (excluded from B_I). Dual *-bound / *-modeling-time skipped."""
    classical = {}
    iqs = {}
    cls_method = {}
    for f in sorted(glob.glob(os.path.join(PLOTS, "*.csv"))):
        with open(f) as fh:
            rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
        if not rows:
            continue
        hdr = rows[0]
        try:
            si, ii, mi = hdr.index("size"), hdr.index("index"), hdr.index("method")
            oi = hdr.index("obj") if "obj" in hdr else 2
        except ValueError:
            continue
        for r in rows[1:]:
            try:
                key = (int(r[si]), int(r[ii])); m = r[mi].strip().lower(); o = float(r[oi])
            except (ValueError, IndexError):
                continue
            if m in baselines.BI_METHODS:
                if o > classical.get(key, float("-inf")):
                    classical[key] = o; cls_method[key] = m
            elif m == "iqs":
                iqs[key] = max(iqs.get(key, float("-inf")), o)
    return {k: {"B_I_classical": classical.get(k), "B_I_method": cls_method.get(k),
                "iqs": iqs.get(k)} for k in set(classical) | set(iqs)}


def independent_audit(x, c1, c2, c3):
    """Recompute objective + feasibility from raw matrices (Eq.29). x in {0,1}^n,
    in the read_instance (efficiency-sorted, lower-tri) variable order. Returns
    (objective:int, feasible:bool, le_lhs, le_rhs, ge_lhs, ge_rhs)."""
    x = np.asarray(x, dtype=np.int64).reshape(-1)
    c1 = np.asarray(c1, dtype=np.int64); c2 = np.asarray(c2, dtype=np.int64); c3 = np.asarray(c3, dtype=np.int64)
    # use python-int accumulation via object dtype only if needed; values ~1e10 fit int64
    obj = int(x @ (c1 @ x))
    le_lhs = int(x @ ((2 * c3) @ x)); ge_lhs = int(x @ ((2 * c2) @ x))
    le_rhs, ge_rhs = eq29_rhs(c2, c3)
    feasible = (le_lhs <= le_rhs) and (ge_lhs >= ge_rhs)
    return obj, feasible, le_lhs, le_rhs, ge_lhs, ge_rhs


def run_one(n, idx, seeds):
    c1, c2, c3 = load_eq29(n, idx, BENCH)
    best = None
    for s in seeds:
        m = build_model(c1, c2, c3, vectorized=True)
        gv, gf = m.general_greedy()
        m.seed = int(s)
        m.set_param("M", -1)
        m.set_param("verify", True)
        m.set_param("opt_sample_cap", 0)
        m.set_param("stopping_time", CAP_S)
        t0 = time.time(); r = m.solve(); dt = time.time() - t0
        if r.solution is None or not getattr(r, "feasible", False):
            continue
        obj, feas, le_l, le_r, ge_l, ge_r = independent_audit(r.solution, c1, c2, c3)
        rec = {"seed": s, "dt": dt, "solver_obj": r.objective, "solver_feasible": r.feasible,
               "audit_obj": obj, "audit_feasible": feas, "obj_match": (obj == r.objective),
               "le_l": le_l, "le_r": le_r, "ge_l": ge_l, "ge_r": ge_r,
               "greedy_value": gv, "greedy_feasible": gf}
        if best is None or (feas and obj > best["audit_obj"]):
            best = rec
    return best


def main():
    pub = published_objectives()
    print(f"{'inst':>8} {'CBQS(audit)':>14} {'feas':>4} {'B_I(cls)':>14} {'meth':>8} "
          f"{'iqs(pub)':>14} {'vs B_I':>10} {'vs iqs':>10} {'objOK':>5}")
    rows = []
    for (n, idx), seeds in [(k, SEEDS_SMALL) for k in N1000] + [(k, SEEDS_LARGE) for k in N3000]:
        rec = run_one(n, idx, seeds)
        p = pub.get((n, idx), {})
        BI = p.get("B_I_classical"); iqs = p.get("iqs"); meth = p.get("B_I_method") or "?"
        if rec is None:
            print(f"{f'{n}_{idx}':>8} {'NO FEASIBLE':>14}"); rows.append((n, idx, None)); continue
        o = rec["audit_obj"]
        dBI = o - BI if BI else float("nan")
        diq = o - iqs if iqs else float("nan")
        print(f"{f'{n}_{idx}':>8} {o:>14} {str(rec['audit_feasible']):>4} "
              f"{(BI or 0):>14.0f} {meth:>8} {(iqs or 0):>14.0f} "
              f"{dBI:>+10.0f} {diq:>+10.0f} {str(rec['obj_match']):>5}")
        rows.append((n, idx, {**rec, "B_I": BI, "B_I_method": meth, "iqs": iqs, "dBI": dBI, "diq": diq}))
        sys.stdout.flush()
    # summary
    print("\n=== SUMMARY ===")
    for n in (1000, 3000):
        sub = [r for r in rows if r[0] == n and r[2] is not None]
        beat_BI = sum(1 for _, _, d in sub if d["audit_feasible"] and d["B_I"] and d["audit_obj"] > d["B_I"])
        beat_iqs = sum(1 for _, _, d in sub if d["audit_feasible"] and d["iqs"] and d["audit_obj"] > d["iqs"])
        objok = sum(1 for _, _, d in sub if d["obj_match"])
        feasok = sum(1 for _, _, d in sub if d["audit_feasible"])
        tot = len([r for r in rows if r[0] == n])
        print(f"n={n}: {len(sub)}/{tot} solved | feasible(audit) {feasok}/{len(sub)} | "
              f"obj-consistent {objok}/{len(sub)} | beat B_I(classical) {beat_BI}/{len(sub)} | "
              f"beat iqs(published) {beat_iqs}/{len(sub)}")


if __name__ == "__main__":
    main()
