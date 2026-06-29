#!/usr/bin/env python3
"""bd 71e SCHEDULE PROBE — does a broad->tight SCHEDULE beat the best CONSTANT opt radius at n=3000?

This is the DECISIVE config-only test for bd 71e (M5 oracle-indexed radius schedule). The first probe
(benchmarks/run_71e_probe.py) showed a tighter CONSTANT opt radius beats a broad one at n=3000 (GO on
the existing static lever, NO core change) — but it could NOT distinguish "best constant radius is
small" from "a time-varying SCHEDULE beats the best constant", because all its arms ran a constant opt
radius with an early switch. Only the latter could justify the 71e core change. This probe isolates it.

The phase machine gives exactly ONE config-only knob to create a broad->tight STEP without a core
change: the exploit->explore SWITCH placement (opt_switch_oracles = round(alpha * T(n))). The opt_sat
phase runs at opt_sat_radius (broad), the opt phase at opt_branching_radius (tight); a LATER switch =>
a longer broad-early segment before the tight segment = a genuine 1-step schedule. So:

  A (best-constant-tight): opt_sat_r=8, opt_r=r*, EARLY switch (alpha=0.012, ~120 oracles broad) ->
                           tight almost immediately, i.e. ~constant tight opt radius.
  B (broad->tight step):   opt_sat_r=8, opt_r=r*, LATE  switch (alpha=0.15, ~1498 oracles broad) ->
                           a real broad-early / tight-late schedule.
  control:                 opt_sat_r=8, opt_r=8 (constant broad anchor; the first probe's control).

r* (the best constant tight radius) is found WITHIN this run by comparing two candidates at the bottom
of the monotone gradient (the first probe found r=2>4>8, optimum at/below the tested boundary): r=2.0
and r=1.5 (the realistic floor — bias=n/r-2 huge at r=1.5 => ~1-flip radius; below this the lever
saturates). r* = argmax over {A_r2, A_r1p5} of the seed-aggregated median obj@common vs control.

DECISIVE TEST: B_r* vs A_r* at obj@common (the faithful equal-min-oracle-depth read; obj@T is
wall-depth-confounded under the RUN POLICY cap). If B does NOT materially beat A (seed-robust, Holm) ->
a schedule buys nothing over the best constant -> DEFER 71e, ship r* via the existing static lever.
Only B >> A (and only after a SEPARATE Section-5 multi-worker nondeterminism audit of the oracle-index
axis — the first probe found that axis is itself nondeterministic run-to-run) would make the continuous
oracle-indexed C lever plausible (and it must then also beat this best config-only step schedule).

MULTI-SEED (3 seeds): the first probe was single-seed; p=0.00195 was the 2^-9 sign-only floor. Here we
report per-instance sign stability across seeds + an across-seed view, and aggregate per instance by
the median-over-seeds delta before the Wilcoxon over the 9 instances.

RUN POLICY: M=M_BIG + stopping_time wall cap. Resumable: each (instance, arm, seed) persists to JSON.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_71e_schedule_probe \
      [--n 3000] [--out-dir DIR] [--seeds 20260625,20260626,20260627] [--wall 900] \
      [--workers 4] [--indices 0,..,8] [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget, _holm, _boot_ci_median  # reuse stats core (§2.7)

M_BIG = 100_000_000
DEFAULT_INDICES = tuple(range(9))
DEFAULT_SEEDS = (20260625, 20260626, 20260627)
ALPHA_EARLY = 0.012          # ~constant tight (opt starts ~oracle 120)
ALPHA_LATE = 0.15            # broad->tight step (opt starts ~oracle round(0.15*T))
R_OPT_SAT = 8.0              # broad feasibility radius, shared by all arms
BASELINE_ARM = "control"

#: arm -> (opt_sat_radius, opt_radius, alpha_switch). The schedule lives in (opt_radius, alpha_switch).
ARM_SPEC = {
    "control": (R_OPT_SAT, R_OPT_SAT, ALPHA_EARLY),   # constant broad anchor
    "A_r2":    (R_OPT_SAT, 2.0,       ALPHA_EARLY),   # best-constant candidate (tight ~throughout opt)
    "A_r1p5":  (R_OPT_SAT, 1.5,       ALPHA_EARLY),   # tighter best-constant candidate
    "B_r2":    (R_OPT_SAT, 2.0,       ALPHA_LATE),    # broad->tight schedule at r=2
    "B_r1p5":  (R_OPT_SAT, 1.5,       ALPHA_LATE),    # broad->tight schedule at r=1.5
}
ARMS = ["control", "A_r2", "A_r1p5", "B_r2", "B_r1p5"]
A_OF = {2.0: "A_r2", 1.5: "A_r1p5"}     # constant arm for each r* candidate
B_OF = {2.0: "B_r2", 1.5: "B_r1p5"}     # schedule arm for each r* candidate
R_CANDS = (2.0, 1.5)


def _resolve(arm, n):
    r_sat, r_opt, alpha = ARM_SPEC[arm]
    return {
        "opt_sat_branching_radius": r_sat,
        "opt_branching_radius": r_opt,
        "opt_switch_oracles": int(round(alpha * metric.oracle_budget(n))),
    }


def solve_arm(arm, n, idx, seed, wall, workers, bench_root):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = _resolve(arm, n)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    m.set_param("M", M_BIG)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("stopping_time", float(wall))
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    t0 = time.time(); r = m.solve(); dt = time.time() - t0
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o) in (r.history or [])]
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed), "wall_s": dt, "params": resolved,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "greedy_feasible": bool(greedy_feasible), "history": hist}


# --------------------------------------------------------------------------- #
# Analysis: obj@common per (instance, seed); seed-aggregated paired stats
# --------------------------------------------------------------------------- #

def _obj_common_per_seed(recs, indices, seeds, T):
    """obj_at[(idx,seed,arm)] read at B(idx,seed)=min over arms of oracle_calls (capped at T) — the
    faithful equal-oracle-depth read for that matched-seed cell. Also returns the common budgets."""
    obj_at, budgets = {}, {}
    for idx in indices:
        for s in seeds:
            cell = {arm: recs.get((idx, arm, s)) for arm in ARMS}
            if any(r is None for r in cell.values()):
                continue
            B = min(min(int(r["oracle_calls"]) for r in cell.values()), T)
            budgets[(idx, s)] = B
            for arm, r in cell.items():
                obj_at[(idx, s, arm)] = obj_at_budget(r["history"], B)
    return obj_at, budgets


def _paired_seedagg(obj_at, indices, seeds, arm, baseline):
    """Per-instance (arm-baseline) delta aggregated over seeds by the MEDIAN; plus per-seed signs.
    A pair is kept only if every seed cell for both arms is feasible-at-B. Returns (pairs, perseed).
      pairs:   [(idx, median_delta_over_seeds)]
      perseed: {idx: [delta_seed0, delta_seed1, ...]}"""
    pairs, perseed = [], {}
    for idx in indices:
        ds = []
        for s in seeds:
            a, b = obj_at.get((idx, s, arm)), obj_at.get((idx, s, baseline))
            if a is None or b is None:
                ds = None; break
            ds.append(a - b)
        if not ds:
            continue
        perseed[idx] = ds
        pairs.append((idx, float(np.median(ds))))
    return pairs, perseed


def _wilcoxon_one_sided(deltas):
    if any(x != 0 for x in deltas):
        try:
            W, p = ss.wilcoxon(deltas, alternative="greater", zero_method="wilcox")
            return (float(W), float(p))
        except ValueError:
            return (None, 1.0)
    return (None, 1.0)


def _cmp(obj_at, indices, seeds, arm, baseline):
    """Full seed-aggregated comparison of `arm` vs `baseline`."""
    pairs, perseed = _paired_seedagg(obj_at, indices, seeds, arm, baseline)
    med = [d for _i, d in pairs]
    W, p = _wilcoxon_one_sided(med)
    # seed-robustness: per instance, do ALL seeds agree the delta is positive?
    sign_robust = {i: (all(x > 0 for x in perseed[i]), all(x < 0 for x in perseed[i])) for i in perseed}
    n_all_pos = sum(1 for i in sign_robust if sign_robust[i][0])
    n_all_neg = sum(1 for i in sign_robust if sign_robust[i][1])
    return {
        "arm": arm, "baseline": baseline, "n_pairs": len(pairs),
        "n_pos": sum(1 for d in med if d > 0), "n_neg": sum(1 for d in med if d < 0),
        "median_delta": (float(np.median(med)) if med else None),
        "median_pct": None,  # filled by caller (needs baseline level)
        "ci95_median_delta": (_boot_ci_median(med) if len(med) >= 3 else None),
        "wilcoxon_W": W, "p_value": p,
        "n_instances_all_seeds_pos": n_all_pos, "n_instances_all_seeds_neg": n_all_neg,
        "per_instance": [{"index": i, "median_delta": d, "per_seed": perseed[i]} for i, d in pairs],
    }


def _verdict(n, recs, indices, seeds, T):
    obj_at, budgets = _obj_common_per_seed(recs, indices, seeds, T)
    feas = {arm: sum(1 for idx in indices for s in seeds if obj_at.get((idx, s, arm)) is not None)
            for arm in ARMS}
    # 1) confirm each tight arm beats control (sanity / replication of probe 1, now multi-seed)
    vs_control = {arm: _cmp(obj_at, indices, seeds, arm, BASELINE_ARM)
                  for arm in ARMS if arm != BASELINE_ARM}
    # 2) pick r* = the constant (A) arm with the best seed-aggregated median vs control
    a_scores = {r: (vs_control[A_OF[r]]["median_delta"] or -1e30) for r in R_CANDS}
    r_star = max(R_CANDS, key=lambda r: a_scores[r])
    A_star, B_star = A_OF[r_star], B_OF[r_star]
    # 3) DECISIVE: schedule (B_r*) vs best-constant (A_r*)
    decisive = _cmp(obj_at, indices, seeds, B_star, A_star)
    decisive_holm = _holm({B_star: decisive["p_value"]}, alpha=0.05)
    # 4) also B_r* vs control (schedule vs broad anchor — secondary context)
    b_vs_control = vs_control[B_star]
    # SCHEDULE-GO iff B_r* beats A_r*: Holm-reject, positive median, AND seed-robust (every kept
    # instance's seeds agree positive => the schedule edge is not a single-seed coincidence).
    schedule_go = bool(decisive_holm[B_star]["reject"]
                       and (decisive["median_delta"] or 0) > 0
                       and decisive["n_instances_all_seeds_pos"] == decisive["n_pairs"]
                       and decisive["n_pairs"] >= 6)
    return {"bead": "constraint-oriented-biased-quantum-search-71e", "N": n, "T": T,
            "seeds": list(seeds), "indices": list(indices),
            "alpha_early": ALPHA_EARLY, "alpha_late": ALPHA_LATE, "arm_spec": ARM_SPEC,
            "feasible_cells": feas, "r_star": r_star, "A_star": A_star, "B_star": B_star,
            "vs_control": vs_control, "decisive_B_vs_A": decisive,
            "decisive_holm": decisive_holm, "B_vs_control": b_vs_control,
            "schedule_go": schedule_go,
            "common_budgets": {f"{i}_{s}": budgets.get((i, s)) for i in indices for s in seeds
                               if (i, s) in budgets}}


def run(*, n, out_dir, seeds, wall, workers, indices, bench_root, report_only=False, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    cfg = {"N": n, "seeds": list(seeds), "wall_s": float(wall), "workers": int(workers),
           "indices": list(indices), "M_BIG": M_BIG, "T": T, "arm_spec": ARM_SPEC}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "wall_s", "workers", "M_BIG"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[71e-sched] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — fresh --out-dir.")
    else:
        json.dump(cfg, open(cfg_path, "w"), indent=2)

    if not report_only:
        total = len(indices) * len(ARMS) * len(seeds); done = 0
        for idx in indices:
            for s in seeds:
                for arm in ARMS:
                    done += 1
                    rp = os.path.join(out_dir, f"{n}_{idx}__{arm}__s{s}.json")
                    if os.path.exists(rp):
                        log(f"[71e-sched] ({done}/{total}) skip {n}_{idx} {arm} s={s} (done)"); continue
                    rs, ro, al = ARM_SPEC[arm]
                    log(f"[71e-sched] ({done}/{total}) solve {n}_{idx} {arm} "
                        f"(opt_sat={rs},opt={ro},switch=round({al}*T)={int(round(al*T))}) s={s} wall={wall}s ...")
                    rec = solve_arm(arm, n, idx, s, wall, workers, bench_root)
                    json.dump(rec, open(rp, "w"))
                    log(f"[71e-sched]   -> obj@T={obj_at_budget(rec['history'],T)} feas={rec['feasible']} "
                        f"oracles={rec['oracle_calls']} wall={rec['wall_s']:.0f}s hist={len(rec['history'])}")

    recs = {}
    for idx in indices:
        for s in seeds:
            for arm in ARMS:
                rp = os.path.join(out_dir, f"{n}_{idx}__{arm}__s{s}.json")
                if os.path.exists(rp):
                    recs[(idx, arm, s)] = json.load(open(rp))
    summary = _verdict(n, recs, indices, seeds, T)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=2)
    _report(log, summary)
    return summary


def _report(log, s):
    log("\n" + "=" * 74)
    log(f"bd 71e SCHEDULE PROBE — n={s['N']}: does a broad->tight SCHEDULE beat the best CONSTANT radius?")
    log("=" * 74)
    log(f"N={s['N']} T(n)={s['T']} instances={s['indices']} seeds={s['seeds']}")
    log(f"early switch alpha={s['alpha_early']} (~constant tight)  late switch alpha={s['alpha_late']} (broad->tight)")
    log(f"feasible cells per arm (of {len(s['indices'])*len(s['seeds'])}): {s['feasible_cells']}")
    log("\n--- tight arms vs control (multi-seed; replicates probe 1) [obj@common] ---")
    for arm, c in s["vs_control"].items():
        md = c["median_delta"]
        log(f"[{arm:>7} vs control] pairs={c['n_pairs']} (+{c['n_pos']}/-{c['n_neg']}) "
            f"median Δ={md:+,.0f} p={c['p_value']:.4g} seeds-all-pos={c['n_instances_all_seeds_pos']}/{c['n_pairs']}"
            if md is not None else f"[{arm}] no pairs")
    log(f"\nr* (best constant) = {s['r_star']}  (A={s['A_star']}, B={s['B_star']})")
    d = s["decisive_B_vs_A"]; h = s["decisive_holm"][s["B_star"]]
    log(f"\n--- DECISIVE: {s['B_star']} (broad->tight) vs {s['A_star']} (best constant) [obj@common] ---")
    if d["median_delta"] is not None:
        log(f"  pairs={d['n_pairs']} (+{d['n_pos']}/-{d['n_neg']})  median Δ={d['median_delta']:+,.0f}  "
            f"CI95={d['ci95_median_delta']}")
        log(f"  Wilcoxon p={d['p_value']:.4g}  Holm thr={h['holm_threshold']:.4g} reject={h['reject']}")
        log(f"  seed-robust: instances all-seeds-positive={d['n_instances_all_seeds_pos']}/{d['n_pairs']}, "
            f"all-seeds-negative={d['n_instances_all_seeds_neg']}/{d['n_pairs']}")
        for pi in d["per_instance"]:
            log(f"     {s['N']}_{pi['index']}: medianΔ={pi['median_delta']:+,.0f}  per-seed={[f'{x:+,.0f}' for x in pi['per_seed']]}")
    bc = s["B_vs_control"]
    log(f"\n  (context) {s['B_star']} vs control: median Δ={bc['median_delta']:+,.0f} p={bc['p_value']:.4g}"
        if bc["median_delta"] is not None else "")
    log("")
    if s["schedule_go"]:
        log(f"71e SCHEDULE VERDICT: GO (schedule beats best constant). {s['B_star']} (broad->tight) beats "
            f"{s['A_star']} (best constant r={s['r_star']}) at obj@common — Holm-reject, positive median, "
            f"seed-robust. A time-varying radius adds value over the best constant => the continuous 71e C "
            f"lever is plausible. NEXT GATE before the core change: (1) §5 multi-worker nondeterminism audit "
            f"of the oracle-index axis; (2) the continuous lever must beat THIS best config-only step schedule.")
    else:
        log(f"71e SCHEDULE VERDICT: DEFER 71e. The broad->tight step ({s['B_star']}) does NOT beat the best "
            f"constant ({s['A_star']}, r={s['r_star']}) at obj@common (seed-robust). A schedule buys nothing "
            f"over the best constant radius => the oracle-indexed C lever is not justified. SHIP r*={s['r_star']} "
            f"via the existing static opt_branching_radius lever; close 71e as won't-do (constant suffices).")
    log("=" * 74)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd 71e schedule-proxy probe (B late-switch vs A best-constant).")
    p.add_argument("--n", type=int, default=3000)
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_71e_schedule"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    p.add_argument("--wall", type=float, default=900.0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None)
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    seeds = [int(x) for x in args.seeds.split(",")]
    run(n=args.n, out_dir=args.out_dir, seeds=seeds, wall=args.wall, workers=args.workers,
        indices=indices, bench_root=args.bench_root, report_only=args.report_only)


if __name__ == "__main__":
    main()
