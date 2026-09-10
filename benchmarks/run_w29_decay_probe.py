#!/usr/bin/env python3
"""bd w29 (M5 / 71e): DIRECT-MEASUREMENT A/B of the continuous opt-radius DECAY lever.

Settles the original 71e question by DIRECT MEASUREMENT (not the config-only proxy that closed
71e won't-do): does an opt-phase radius that tightens CONTINUOUSLY with convergence beat the best
CONSTANT opt radius (r*~2) at n=3000? The real lever (a between-round classical write of the
opt-phase state-prep angle, inner sampler byte-unchanged — bd w29 / solver_ctx opt_radius_schedule)
is now built, so the within-opt decay the phase machine could NOT express config-only is measurable.

ARMS (all share opt_sat_radius=8 broad-feasibility + the SAME early exploit->explore switch so the
ONLY difference is the opt-phase radius trajectory; the decay is keyed on total_oracles/T(n) in
[0,1], NORTHSTAR §1.5):
  A_r2          : best CONSTANT tight radius r*=2 (static opt_branching_radius; schedule OFF).
  neg_r2        : schedule r_start==r_end==2 — degenerates to the constant lever. At SINGLE worker
                  it reproduces A_r2 BIT-FOR-BIT (proven in tests/test_opt_radius_schedule.{c,py});
                  at the A/B's multi-worker setting its delta vs A_r2 is the empirical §5 oracle-axis
                  NOISE FLOOR (the decisive |D-A| must materially exceed it).
  D_4to2        : continuous decay r_start=4 -> r_end=2, gamma=1 (linear).
  D_8to2        : continuous decay r_start=8 -> r_end=2, gamma=1 (linear; broadest early contrast).
  D_8to2_steep  : continuous decay r_start=8 -> r_end=2, gamma=2 (tightens EARLY).

DECISIVE TEST: each D arm vs A_r2 at obj@common (the faithful equal-min-oracle-depth read; obj@T is
wall-depth-confounded under the RUN POLICY cap), aggregated per instance by the median-over-seeds
delta, one-sided Wilcoxon over instances, Holm-corrected over the D family, with per-seed
sign-robustness. KEEP the C lever ONLY if the best D BEATS A_r2 materially + seed-robustly AND the
edge exceeds the neg_r2 noise floor; otherwise REVERT and confirm 71e won't-do BY DIRECT MEASUREMENT.

RUN POLICY: M=M_BIG + stopping_time wall cap (900-1800s). Resumable: each (instance, arm, seed)
persists to JSON; --report-only re-aggregates without solving.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_w29_decay_probe \
      [--n 3000] [--out-dir DIR] [--seeds 20260630,20260701,20260702] [--wall 900] \
      [--workers 4] [--indices 0,..,8] [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget, _holm, _boot_ci_median  # proven stats core (§2.7)

M_BIG = 100_000_000
DEFAULT_INDICES = tuple(range(9))
DEFAULT_SEEDS = (20260630, 20260701, 20260702)
ALPHA_SWITCH = 0.012          # early exploit->explore switch (~constant; opt starts ~oracle 120)
R_OPT_SAT = 8.0               # broad feasibility radius, shared by every arm
R_STAR = 2.0                  # the best constant tight radius (71e probe found r*=2)
BASELINE_ARM = "A_r2"

#: arm -> resolved param dict. A_r2 is the constant baseline; neg_r2 is the bit-for-bit/noise-floor
#: control; D_* are the real continuous decays. All share opt_sat_radius + switch (isolated lever).
def _resolve(arm, n):
    switch = int(round(ALPHA_SWITCH * metric.oracle_budget(n)))
    base = {"opt_sat_branching_radius": R_OPT_SAT, "opt_switch_oracles": switch}
    if arm == "A_r2":
        return {**base, "opt_branching_radius": R_STAR}
    if arm == "neg_r2":
        return {**base, "opt_branching_radius": R_STAR,
                "opt_radius_schedule_r_start": R_STAR, "opt_radius_schedule_r_end": R_STAR,
                "opt_radius_schedule_gamma": 1.0}
    if arm == "D_4to2":
        return {**base, "opt_radius_schedule_r_start": 4.0, "opt_radius_schedule_r_end": 2.0,
                "opt_radius_schedule_gamma": 1.0}
    if arm == "D_8to2":
        return {**base, "opt_radius_schedule_r_start": 8.0, "opt_radius_schedule_r_end": 2.0,
                "opt_radius_schedule_gamma": 1.0}
    if arm == "D_8to2_steep":
        return {**base, "opt_radius_schedule_r_start": 8.0, "opt_radius_schedule_r_end": 2.0,
                "opt_radius_schedule_gamma": 2.0}
    raise ValueError(f"unknown arm {arm}")


ARMS = ["A_r2", "neg_r2", "D_4to2", "D_8to2", "D_8to2_steep"]
D_ARMS = ["D_4to2", "D_8to2", "D_8to2_steep"]   # the real-decay family (Holm over these)


def solve_arm(arm, n, idx, seed, wall, workers, bench_root, budget_mult=None):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = _resolve(arm, n)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    # Two modes. WALL (budget_mult is None): the n>=1000 RUN POLICY — M=T(n) + wall
    # cap; obj@common is the faithful read (obj@T is wall-depth-confounded). NB M
    # MUST be T(n), NOT M_BIG: the opt-radius schedule keys on total_oracles/mod->M,
    # so M_BIG would pin the schedule at r_start (ratio~0). The wall is the early
    # terminator. FAITHFUL (budget_mult set, for the small-n insight sweep):
    # terminate on the ORACLE budget M = round(mult * T(n)) with NO wall cap
    # (stopping_time=-1) — fast + REPRODUCIBLE at small n (no wall-truncation noise).
    if budget_mult is not None:
        m.set_param("M", int(round(budget_mult * metric.oracle_budget(n))))
        m.set_param("stopping_time", -1.0)
    else:
        m.set_param("M", int(metric.oracle_budget(n)))
        m.set_param("stopping_time", float(wall))
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    t0 = time.time(); r = m.solve(); dt = time.time() - t0
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o, *_) in (r.history or [])]
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed), "wall_s": dt, "params": resolved,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "greedy_feasible": bool(greedy_feasible), "history": hist}


# --------------------------------------------------------------------------- #
# Analysis: obj@common per (instance, seed); seed-aggregated paired stats
# --------------------------------------------------------------------------- #

def _obj_common_per_seed(recs, indices, seeds, T):
    """obj_at[(idx,seed,arm)] read at B(idx,seed) = min over arms of oracle_calls (capped at T) —
    the faithful equal-oracle-depth read for that matched-seed cell."""
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
    """Per-instance (arm-baseline) delta aggregated over seeds by the MEDIAN; plus per-seed signs."""
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
    pairs, perseed = _paired_seedagg(obj_at, indices, seeds, arm, baseline)
    med = [d for _i, d in pairs]
    W, p = _wilcoxon_one_sided(med)
    sign_robust = {i: (all(x > 0 for x in perseed[i]), all(x < 0 for x in perseed[i])) for i in perseed}
    return {
        "arm": arm, "baseline": baseline, "n_pairs": len(pairs),
        "n_pos": sum(1 for d in med if d > 0), "n_neg": sum(1 for d in med if d < 0),
        "median_delta": (float(np.median(med)) if med else None),
        "ci95_median_delta": (_boot_ci_median(med) if len(med) >= 3 else None),
        "wilcoxon_W": W, "p_value": p,
        "n_instances_all_seeds_pos": sum(1 for i in sign_robust if sign_robust[i][0]),
        "n_instances_all_seeds_neg": sum(1 for i in sign_robust if sign_robust[i][1]),
        "per_instance": [{"index": i, "median_delta": d, "per_seed": perseed[i]} for i, d in pairs],
    }


def _verdict(n, recs, indices, seeds, T):
    obj_at, budgets = _obj_common_per_seed(recs, indices, seeds, T)
    feas = {arm: sum(1 for idx in indices for s in seeds if obj_at.get((idx, s, arm)) is not None)
            for arm in ARMS}
    # noise floor: neg_r2 vs A_r2 (schedule==constant; nonzero only via the multi-worker §5 race)
    noise = _cmp(obj_at, indices, seeds, "neg_r2", BASELINE_ARM)
    noise_floor = abs(noise["median_delta"]) if noise["median_delta"] is not None else None
    # each real-decay arm vs the best constant
    vs_const = {arm: _cmp(obj_at, indices, seeds, arm, BASELINE_ARM) for arm in D_ARMS}
    holm = _holm({arm: vs_const[arm]["p_value"] for arm in D_ARMS}, alpha=0.05)
    # pick the best decay arm by seed-aggregated median delta vs A_r2
    best_arm = max(D_ARMS, key=lambda a: (vs_const[a]["median_delta"] or -1e30))
    best = vs_const[best_arm]
    beats_noise = (noise_floor is not None and best["median_delta"] is not None
                   and best["median_delta"] > noise_floor)
    # KEEP iff the best decay: Holm-rejects, positive seed-robust median, n_pairs>=6, beats noise.
    keep_lever = bool(holm[best_arm]["reject"]
                      and (best["median_delta"] or 0) > 0
                      and best["n_instances_all_seeds_pos"] == best["n_pairs"]
                      and best["n_pairs"] >= 6
                      and beats_noise)
    return {"bead": "constraint-oriented-biased-quantum-search-w29", "N": n, "T": T,
            "seeds": list(seeds), "indices": list(indices), "alpha_switch": ALPHA_SWITCH,
            "r_opt_sat": R_OPT_SAT, "r_star": R_STAR, "feasible_cells": feas,
            "noise_floor_neg_vs_A": noise, "noise_floor": noise_floor,
            "decays_vs_constant": vs_const, "holm": holm, "best_decay_arm": best_arm,
            "best_decay": best, "best_beats_noise_floor": beats_noise, "keep_lever": keep_lever,
            "common_budgets": {f"{i}_{s}": budgets.get((i, s)) for i in indices for s in seeds
                               if (i, s) in budgets}}


def run(*, n, out_dir, seeds, wall, workers, indices, bench_root, budget_mult=None,
        report_only=False, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    mode = "faithful" if budget_mult is not None else "wall"
    cfg = {"N": n, "seeds": list(seeds), "wall_s": float(wall), "workers": int(workers),
           "indices": list(indices), "M_BIG": M_BIG, "T": T, "arms": ARMS, "mode": mode,
           "budget_mult": budget_mult, "alpha_switch": ALPHA_SWITCH,
           "r_opt_sat": R_OPT_SAT, "r_star": R_STAR}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "workers", "mode", "budget_mult"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[w29] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — fresh --out-dir.")
        if mode == "wall" and prev.get("wall_s") != cfg["wall_s"]:
            raise SystemExit(f"[w29] CONFIG MISMATCH on wall_s — fresh --out-dir.")
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
                        log(f"[w29] ({done}/{total}) skip {n}_{idx} {arm} s={s} (done)"); continue
                    _budget = (f"M={int(round(budget_mult*metric.oracle_budget(n)))}(={budget_mult}xT)"
                               if budget_mult is not None else f"wall={wall}s")
                    log(f"[w29] ({done}/{total}) solve {n}_{idx} {arm} s={s} {_budget} ...")
                    rec = solve_arm(arm, n, idx, s, wall, workers, bench_root, budget_mult=budget_mult)
                    json.dump(rec, open(rp, "w"))
                    log(f"[w29]   -> obj@T={obj_at_budget(rec['history'],T)} feas={rec['feasible']} "
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
    log("\n" + "=" * 78)
    log(f"bd w29 DECAY A/B — n={s['N']}: does a CONTINUOUS opt-radius decay beat the best CONSTANT r*={s['r_star']}?")
    log("=" * 78)
    log(f"N={s['N']} T(n)={s['T']} instances={s['indices']} seeds={s['seeds']} (workers in run_config)")
    log(f"feasible cells per arm (of {len(s['indices'])*len(s['seeds'])}): {s['feasible_cells']}")
    nf = s["noise_floor_neg_vs_A"]
    log(f"\n--- noise floor: neg_r2 (schedule 2->2) vs A_r2 (constant r=2) [obj@common] ---")
    if nf["median_delta"] is not None:
        log(f"  median Δ={nf['median_delta']:+,.0f}  (|floor|={s['noise_floor']:,.0f})  "
            f"all-seeds-pos={nf['n_instances_all_seeds_pos']}/{nf['n_pairs']} "
            f"all-seeds-neg={nf['n_instances_all_seeds_neg']}/{nf['n_pairs']}")
    log(f"\n--- each continuous decay vs A_r2 (constant r=2) [obj@common] ---")
    for arm in D_ARMS:
        c = s["decays_vs_constant"][arm]; h = s["holm"][arm]
        if c["median_delta"] is None:
            log(f"  [{arm}] no pairs"); continue
        log(f"  [{arm:>13}] pairs={c['n_pairs']} (+{c['n_pos']}/-{c['n_neg']}) median Δ={c['median_delta']:+,.0f} "
            f"CI95={c['ci95_median_delta']} p={c['p_value']:.4g} Holm-reject={h['reject']} "
            f"seeds-all-pos={c['n_instances_all_seeds_pos']}/{c['n_pairs']}")
    b = s["best_decay"]
    log(f"\nbest decay arm = {s['best_decay_arm']} (median Δ={b['median_delta']:+,.0f} vs A_r2); "
        f"beats noise floor = {s['best_beats_noise_floor']}")
    log("")
    if s["keep_lever"]:
        log(f"w29 VERDICT: KEEP the C lever. The continuous decay ({s['best_decay_arm']}) BEATS the best "
            f"constant r*={s['r_star']} at n={s['N']} — Holm-reject, positive seed-robust median, edge "
            f"exceeds the multi-worker noise floor. A radius that tightens with convergence adds real value "
            f"over the best constant => the 71e core lever is justified BY DIRECT MEASUREMENT.")
    else:
        log(f"w29 VERDICT: REVERT the C lever. No continuous decay beats the best constant r*={s['r_star']} "
            f"at n={s['N']} (seed-robust, above the noise floor). A within-opt decay buys nothing over the "
            f"best constant => 71e is confirmed WON'T-DO BY DIRECT MEASUREMENT (not just proxy inference). "
            f"Ship r*={s['r_star']} via the existing static opt_branching_radius lever.")
    log("=" * 78)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd w29 continuous opt-radius decay A/B (D vs best-constant r*).")
    p.add_argument("--n", type=int, default=3000)
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_w29_decay"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    p.add_argument("--wall", type=float, default=900.0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None)
    p.add_argument("--budget-mult", type=float, default=None,
                   help="FAITHFUL mode (small-n insight): terminate on M=round(mult*T(n)) oracles, "
                        "NO wall cap (reproducible, no wall-noise). Omit for the n=3000 wall mode.")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    seeds = [int(x) for x in args.seeds.split(",")]
    run(n=args.n, out_dir=args.out_dir, seeds=seeds, wall=args.wall, workers=args.workers,
        indices=indices, bench_root=args.bench_root, budget_mult=args.budget_mult,
        report_only=args.report_only)


if __name__ == "__main__":
    main()
