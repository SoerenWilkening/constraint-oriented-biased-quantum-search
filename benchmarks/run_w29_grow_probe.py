#!/usr/bin/env python3
"""bd w29 follow-up: the OPPOSITE schedule direction — GROW tight->broad (refine-then-explore).

The decay probe (broad->tight) LOST to the best constant and worsened with headroom. This tests the
inverse hypothesis (user-proposed): with a WARM start, a TIGHT radius early refines/consolidates the
near-optimal warm solution, then BROADENING late escapes local optima — "refine-then-explore", the
inverse of the falsified "explore-then-exploit" decay. Target endpoint = the M4 winner cand_16's opt
radius r=4.41 (NB cand_16's 4.41 is theta-COUPLED: with theta=z(p_ii)*0.288 it won at n=3000, whereas
the bare-radius optimum from the 71e probe is r~2). So we resolve the tension empirically.

Same FAITHFUL methodology as the decay probe (oracle-budget termination, NO wall cap => reproducible,
zero wall-noise; neg==constant exactly). Two regimes, both sharing opt_sat=8 + cand_16's early switch:
  RADIUS-ONLY (theta OFF, directly comparable to the decay probe):
    C_r2 / C_r4.41 / C_r6   — constant sweep (locate the best constant r* on these instances)
    G_2to4.41               — GROW 2 -> 4.41 (linear); the user's hypothesis
    G_2to4.41_steep         — GROW 2 -> 4.41, gamma=2 (reach 4.41 EARLY)
    neg_2to2                — GROW 2 -> 2 == constant r=2 (bit-for-bit harness check)
  CAND_16 REGIME (theta = z(p_ii)*0.288 ON, the actual M4 winner):
    K_const4.41             — cand_16 EXACT (constant opt r=4.41 + theta)
    K_grow2to4.41           — cand_16 but the opt radius GROWS 2 -> 4.41 (+ theta)

DECISIVE reads (obj@common best-of-portfolio, median-over-seeds, Wilcoxon+Holm, per-seed sign):
  * G_2to4.41 vs C_r4.41        — does growing INTO 4.41 beat SITTING at 4.41 (radius-only)?
  * G_2to4.41 vs best-constant  — does growing beat the best constant at all?
  * K_grow2to4.41 vs K_const4.41 — does growing beat constant IN cand_16's winning regime?

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_w29_grow_probe \
      [--n 90] [--budget-mult 1.0] [--indices 0..8] [--seeds ...] [--workers 4] [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.m3_proposer import genome_to_factory
from benchmarks.run_m4_n3000 import obj_at_budget, _holm, _boot_ci_median  # proven stats core (§2.7)

CAND16 = (8.0, 4.409916944894315, 0.012044790907040026, 0.28884412462871306, 1.5)  # M4 winner genome
R_OPT_SAT = 8.0
ALPHA = 0.012044790907040026   # cand_16 early switch
R4 = 4.409916944894315         # cand_16 opt radius
DEFAULT_INDICES = tuple(range(9))
DEFAULT_SEEDS = (20260630, 20260701, 20260702)
M_BIG = 100_000_000

ARMS = ["C_r2", "C_r4.41", "C_r6", "G_2to4.41", "G_2to4.41_steep", "neg_2to2",
        "K_const4.41", "K_grow2to4.41",
        # bd w29 decomposition (does the best config = constant r=2 + theta, no schedule?):
        "C_r2_theta", "C_r3_theta",
        # CBQS default (bias=n/4) for the comparison figure:
        "default"]
CONST_ARMS = ["C_r2", "C_r4.41", "C_r6"]


def _base(n):
    return {"opt_sat_branching_radius": R_OPT_SAT,
            "opt_switch_oracles": int(round(ALPHA * metric.oracle_budget(n)))}


def arm_params(arm, n, c1, c2, c3):
    if arm == "default":  return {}     # CBQS default: close() auto-sets bias=n/4, switch=0.1*M
    if arm == "C_r2":     return {**_base(n), "opt_branching_radius": 2.0}
    if arm == "C_r4.41":  return {**_base(n), "opt_branching_radius": R4}
    if arm == "C_r6":     return {**_base(n), "opt_branching_radius": 6.0}
    if arm == "G_2to4.41":
        return {**_base(n), "opt_radius_schedule_r_start": 2.0, "opt_radius_schedule_r_end": R4}
    if arm == "G_2to4.41_steep":
        return {**_base(n), "opt_radius_schedule_r_start": 2.0, "opt_radius_schedule_r_end": R4,
                "opt_radius_schedule_gamma": 2.0}
    if arm == "neg_2to2":
        return {**_base(n), "opt_branching_radius": 2.0,
                "opt_radius_schedule_r_start": 2.0, "opt_radius_schedule_r_end": 2.0}
    if arm == "K_const4.41":
        return dict(genome_to_factory(CAND16)(n, c1, c2, c3))     # cand_16 exact (theta ON)
    if arm == "K_grow2to4.41":
        p = dict(genome_to_factory(CAND16)(n, c1, c2, c3))         # keep theta + opt_sat + switch
        p["opt_radius_schedule_r_start"] = 2.0; p["opt_radius_schedule_r_end"] = R4
        return p
    # Decomposition: cand_16's theta (z(p_ii)*0.288) at the BARE-optimal radius (constant, no
    # schedule). If this beats both bare C_r2 and K_grow, the "schedule" edge was just theta at the
    # right radius — ship a constant r=2 + theta, no lever.
    if arm == "C_r2_theta":
        return dict(genome_to_factory((R_OPT_SAT, 2.0, ALPHA, CAND16[3], CAND16[4]))(n, c1, c2, c3))
    if arm == "C_r3_theta":
        return dict(genome_to_factory((R_OPT_SAT, 3.0, ALPHA, CAND16[3], CAND16[4]))(n, c1, c2, c3))
    raise ValueError(arm)


def solve_arm(arm, n, idx, seed, budget_mult, workers, bench_root, wall=None):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = arm_params(arm, n, c1, c2, c3)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    if wall and wall > 0:
        # WALL mode (n>=1000 RUN POLICY): M=T(n) (NOT M_BIG!) so the schedule keys correctly on
        # total_oracles/mod->M = total/T(n) in [0,1] — with M_BIG the ratio is ~0 and the schedule
        # is PINNED at r_start (never moves). The wall cap is the early terminator (mid-round
        # deadline interrupts giant O(n*j^2) rounds); obj@common is the faithful read.
        m.set_param("M", int(metric.oracle_budget(n)))
        m.set_param("stopping_time", float(wall))
    else:
        # FAITHFUL mode (small-n): oracle-budget termination, reproducible (no wall noise).
        m.set_param("M", int(round(budget_mult * metric.oracle_budget(n))))
        m.set_param("stopping_time", -1.0)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    r = m.solve()
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o, *_) in (r.history or [])]
    # resolved may carry a numpy weights array; store only its presence/scale (JSON-safe)
    rps = {k: (float(v) if np.isscalar(v) else f"<vec[{len(v)}]>") for k, v in resolved.items()}
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed), "params": rps,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls), "history": hist}


# --------------------------- analysis (generic over ARMS) --------------------------- #

def _obj_common(recs, indices, seeds, T):
    obj_at = {}
    for idx in indices:
        for s in seeds:
            cell = {arm: recs.get((idx, arm, s)) for arm in ARMS}
            if any(r is None for r in cell.values()):
                continue
            B = min(min(int(r["oracle_calls"]) for r in cell.values()), T)
            for arm, r in cell.items():
                obj_at[(idx, s, arm)] = obj_at_budget(r["history"], B)
    return obj_at


def _cmp(obj_at, indices, seeds, arm, baseline):
    pairs, perseed = [], {}
    for idx in indices:
        ds = []
        for s in seeds:
            a, b = obj_at.get((idx, s, arm)), obj_at.get((idx, s, baseline))
            if a is None or b is None:
                ds = None; break
            ds.append(a - b)
        if ds is None:
            continue
        perseed[idx] = ds
        pairs.append((idx, float(np.median(ds))))
    med = [d for _i, d in pairs]
    W = p = None
    if any(x != 0 for x in med):
        try:
            W, p = ss.wilcoxon(med, alternative="greater", zero_method="wilcox"); W, p = float(W), float(p)
        except ValueError:
            p = 1.0
    else:
        p = 1.0
    allpos = sum(1 for i in perseed if all(x > 0 for x in perseed[i]))
    allneg = sum(1 for i in perseed if all(x < 0 for x in perseed[i]))
    return {"arm": arm, "baseline": baseline, "n_pairs": len(pairs),
            "n_pos": sum(1 for d in med if d > 0), "n_neg": sum(1 for d in med if d < 0),
            "median_delta": (float(np.median(med)) if med else None),
            "ci95": (_boot_ci_median(med) if len(med) >= 3 else None),
            "p_value": p, "all_seeds_pos": allpos, "all_seeds_neg": allneg,
            "per_instance": [{"index": i, "median_delta": d, "per_seed": perseed[i]} for i, d in pairs]}


def _verdict(n, recs, indices, seeds, T):
    obj_at = _obj_common(recs, indices, seeds, T)
    feas = {arm: sum(1 for idx in indices for s in seeds if obj_at.get((idx, s, arm)) is not None)
            for arm in ARMS}
    # constant sweep: each C arm vs C_r2 (locate the best constant on these instances)
    const_vs_r2 = {a: _cmp(obj_at, indices, seeds, a, "C_r2") for a in ("C_r4.41", "C_r6")}
    best_const = "C_r2"
    best_val = 0.0
    for a in ("C_r4.41", "C_r6"):
        d = const_vs_r2[a]["median_delta"] or 0.0
        if d > best_val:
            best_val, best_const = d, a
    # decisive growing comparisons
    grow_vs_4 = _cmp(obj_at, indices, seeds, "G_2to4.41", "C_r4.41")     # grow-into-4.41 vs sit-at-4.41
    grow_vs_best = _cmp(obj_at, indices, seeds, "G_2to4.41", best_const)  # grow vs best constant
    grow_steep_vs_4 = _cmp(obj_at, indices, seeds, "G_2to4.41_steep", "C_r4.41")
    k_grow_vs_const = _cmp(obj_at, indices, seeds, "K_grow2to4.41", "K_const4.41")  # cand_16 regime
    neg = _cmp(obj_at, indices, seeds, "neg_2to2", "C_r2")               # harness: must be 0
    fam = {"G_2to4.41": grow_vs_best["p_value"], "G_2to4.41_steep": grow_steep_vs_4["p_value"],
           "K_grow2to4.41": k_grow_vs_const["p_value"]}
    holm = _holm(fam, alpha=0.05)
    grow_wins = bool(holm["G_2to4.41"]["reject"] and (grow_vs_best["median_delta"] or 0) > 0
                     and grow_vs_best["all_seeds_pos"] == grow_vs_best["n_pairs"]
                     and grow_vs_best["n_pairs"] >= 6)
    k_grow_wins = bool(holm["K_grow2to4.41"]["reject"] and (k_grow_vs_const["median_delta"] or 0) > 0
                       and k_grow_vs_const["all_seeds_pos"] == k_grow_vs_const["n_pairs"]
                       and k_grow_vs_const["n_pairs"] >= 6)
    return {"bead": "constraint-oriented-biased-quantum-search-w29", "N": n, "T": T,
            "seeds": list(seeds), "indices": list(indices), "feasible_cells": feas,
            "const_vs_r2": const_vs_r2, "best_const": best_const,
            "grow_vs_C4.41": grow_vs_4, "grow_vs_best_const": grow_vs_best,
            "grow_steep_vs_C4.41": grow_steep_vs_4, "K_grow_vs_K_const": k_grow_vs_const,
            "neg_vs_C2": neg, "holm": holm,
            "grow_beats_best_const": grow_wins, "k_grow_beats_k_const": k_grow_wins}


def run(*, n, out_dir, seeds, budget_mult, workers, indices, bench_root, wall=None,
        report_only=False, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    mode = "wall" if (wall and wall > 0) else "faithful"
    cfg = {"N": n, "seeds": list(seeds), "budget_mult": budget_mult, "workers": int(workers),
           "indices": list(indices), "arms": ARMS, "mode": mode, "wall_s": (float(wall) if wall else None)}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "workers", "mode"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[w29-grow] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — fresh --out-dir.")
        if mode == "wall" and prev.get("wall_s") != cfg["wall_s"]:
            raise SystemExit(f"[w29-grow] CONFIG MISMATCH on wall_s — fresh --out-dir.")
        if mode == "faithful" and prev.get("budget_mult") != cfg["budget_mult"]:
            raise SystemExit(f"[w29-grow] CONFIG MISMATCH on budget_mult — fresh --out-dir.")
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
                        log(f"[w29-grow] ({done}/{total}) skip {n}_{idx} {arm} s={s}"); continue
                    t0 = time.time()
                    rec = solve_arm(arm, n, idx, s, budget_mult, workers, bench_root, wall=wall)
                    json.dump(rec, open(rp, "w"))
                    log(f"[w29-grow] ({done}/{total}) {n}_{idx} {arm} s={s}: obj@T={obj_at_budget(rec['history'],T)} "
                        f"feas={rec['feasible']} oracles={rec['oracle_calls']} {time.time()-t0:.1f}s")

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
    log("\n" + "=" * 80)
    log(f"bd w29 GROW probe — n={s['N']}: does GROWING tight->broad (refine-then-explore) beat the constant?")
    log("=" * 80)
    log(f"N={s['N']} T(n)={s['T']} instances={s['indices']} seeds={s['seeds']}")
    log(f"feasible cells per arm (of {len(s['indices'])*len(s['seeds'])}): {s['feasible_cells']}")
    log(f"\n--- constant sweep (vs C_r2; locate best constant) [obj@common] ---")
    for a in ("C_r4.41", "C_r6"):
        c = s["const_vs_r2"][a]
        log(f"  {a:>9} vs C_r2: median Δ={c['median_delta']:+,.0f} (+{c['n_pos']}/-{c['n_neg']}) p={c['p_value']:.4g}"
            if c["median_delta"] is not None else f"  {a}: no pairs")
    log(f"  => best constant on these instances: {s['best_const']}")

    def line(tag, c):
        if c["median_delta"] is None:
            log(f"  {tag}: no pairs"); return
        log(f"  {tag}: median Δ={c['median_delta']:+,.0f} (+{c['n_pos']}/-{c['n_neg']} of {c['n_pairs']}) "
            f"CI95={c['ci95']} p={c['p_value']:.4g} all-seeds-pos={c['all_seeds_pos']}/{c['n_pairs']} "
            f"all-seeds-neg={c['all_seeds_neg']}/{c['n_pairs']}")
    log(f"\n--- DECISIVE: growing tight->broad [obj@common] ---")
    line("G_2to4.41  vs C_r4.41 (grow-into vs sit-at)", s["grow_vs_C4.41"])
    line(f"G_2to4.41  vs {s['best_const']} (best const) ", s["grow_vs_best_const"])
    line("G_2to4.41_steep vs C_r4.41                  ", s["grow_steep_vs_C4.41"])
    line("K_grow2to4.41 vs K_const4.41 (cand_16 regime)", s["K_grow_vs_K_const"])
    line("neg_2to2 vs C_r2 (HARNESS, must be 0)        ", s["neg_vs_C2"])
    log("")
    if s["grow_beats_best_const"] or s["k_grow_beats_k_const"]:
        log(f"w29 GROW VERDICT: SIGNAL — growing tight->broad beats the constant "
            f"(radius-only={s['grow_beats_best_const']}, cand_16-regime={s['k_grow_beats_k_const']}). "
            f"The refine-then-explore direction has merit; warrants a wall-capped n=3000 confirmation.")
    else:
        log(f"w29 GROW VERDICT: NULL/NEGATIVE — growing tight->broad does NOT beat the constant "
            f"(seed-robust, Holm). Neither schedule direction (decay nor grow) beats the best constant => "
            f"the static radius is the right lever; 71e/w29 won't-do stands by direct measurement.")
    log("=" * 80)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd w29 grow (tight->broad) probe vs constant.")
    p.add_argument("--n", type=int, default=90)
    p.add_argument("--budget-mult", type=float, default=1.0)
    p.add_argument("--wall", type=float, default=None,
                   help="WALL mode (n>=1000): huge M + this wall-clock cap (s); obj@common read. "
                        "Omit for FAITHFUL small-n mode (M=budget_mult*T(n), no wall).")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None)
    p.add_argument("--arms", default=None,
                   help="comma-separated subset of arms to SOLVE+score (default all). "
                        "Absent arms' comparisons report as None (no crash).")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    if args.arms:
        global ARMS
        sub = [a.strip() for a in args.arms.split(",")]
        unknown = [a for a in sub if a not in ARMS]
        if unknown:
            raise SystemExit(f"unknown arm(s): {unknown}; known: {ARMS}")
        ARMS = sub
    tag = (f"n{args.n}_wall{int(args.wall)}" if args.wall else f"n{args.n}_m{args.budget_mult}")
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "artifacts", "m5_w29_grow", tag)
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    seeds = [int(x) for x in args.seeds.split(",")]
    run(n=args.n, out_dir=out_dir, seeds=seeds, budget_mult=args.budget_mult, workers=args.workers,
        indices=indices, bench_root=args.bench_root, wall=args.wall, report_only=args.report_only)


if __name__ == "__main__":
    main()
