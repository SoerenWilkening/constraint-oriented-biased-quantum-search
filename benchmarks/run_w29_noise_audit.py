#!/usr/bin/env python3
"""bd w29.3 (PREREQUISITE): §5 multi-worker nondeterminism audit of the oracle-index axis.

The continuous opt-radius decay A/B (run_w29_decay_probe) reads obj@common — the best-of-portfolio
objective at a matched oracle depth. That axis is NOT perfectly reproducible under the multi-worker
RUN POLICY: the per-worker oracle stamp (ctx->oracle_count) and per-worker value (ctx->callback_value)
are race-free (M0d/4uf), BUT the wall-clock cap (stopping_time) truncates each worker at a
TIMING-DEPENDENT round, so the same (seed, config) reaches different per-worker oracle depths run to
run — a machine-dependent trajectory the RUN POLICY explicitly accepts. The 71e probes saw this as
byte-identical 4-worker configs diverging at a fixed oracle index.

The decay lever RIDES this axis, so before trusting the A/B we must confirm the NOISE FLOOR (run-to-run
obj@common variation of a FIXED config) is small relative to plausible lever effects (the 71e static
radius finding was ~0.04-0.05% at obj@common). This audit measures it directly:

  (1) SINGLE-WORKER determinism: 1 worker, oracle-budget termination (NO wall cap), schedule armed,
      repeated -> the oracle-indexed history must be BIT-FOR-BIT identical (the lever cannot break the
      §8 single-worker determinism baseline).
  (2) MULTI-WORKER + WALL-CAP noise floor: the A/B settings (4 workers, wall cap), a FIXED config,
      same seed, R repeats -> pairwise obj@common divergence. Reported absolute and as % of the median
      objective. This is the floor the A/B's |D-A| must exceed.
  (3) SCHEDULE==CONSTANT under the race: neg(schedule r*->r*) vs static(r*) at the A/B settings ->
      their divergence must be WITHIN the same floor (the schedule adds no extra nondeterminism).

Pair this with: TSan thread_safety (tests/run_sanitizers.sh) + the grep confirmation that the ctg
schedule hook writes ONLY the per-worker ctx->branching_stats_opt.bias (no new shared mod-> write).

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_w29_noise_audit \
      [--n 1000] [--indices 0,1,2] [--seed 20260630] [--repeats 3] [--workers 4] [--wall 120] \
      [--out-dir DIR]
"""
import argparse, json, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget

R_OPT_SAT = 8.0
R_STAR = 2.0
ALPHA_SWITCH = 0.012
M_BIG = 100_000_000


def _solve(n, idx, seed, *, params, workers, wall, bench_root, cap_oracles=None):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    m.set_param("M", cap_oracles if cap_oracles is not None else M_BIG)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("stopping_time", float(wall) if wall and wall > 0 else -1)
    m.set_param("track_history", True)
    for k, v in params.items():
        m.set_param(k, v)
    r = m.solve()
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o, *_) in (r.history or [])]
    return {"objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls), "history": hist}


def _arm_params(arm, n):
    switch = int(round(ALPHA_SWITCH * metric.oracle_budget(n)))
    base = {"opt_sat_branching_radius": R_OPT_SAT, "opt_switch_oracles": switch}
    if arm == "static_r2":
        return {**base, "opt_branching_radius": R_STAR}
    if arm == "neg_r2":
        return {**base, "opt_branching_radius": R_STAR,
                "opt_radius_schedule_r_start": R_STAR, "opt_radius_schedule_r_end": R_STAR}
    if arm == "decay_8to2":
        return {**base, "opt_radius_schedule_r_start": 8.0, "opt_radius_schedule_r_end": 2.0}
    raise ValueError(arm)


def run(*, n, indices, seed, repeats, workers, wall, bench_root, out_dir, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    report = {"N": n, "T": T, "indices": list(indices), "seed": seed, "repeats": repeats,
              "workers": workers, "wall_s": wall}

    # (1) single-worker determinism (oracle-budget termination, no wall cap), decay armed.
    log("\n[w29.3] (1) single-worker bit-for-bit determinism (decay 8->2, no wall cap, M=T) ...")
    single = []
    for rep in range(2):
        rec = _solve(n, indices[0], seed, params=_arm_params("decay_8to2", n),
                     workers=1, wall=-1, bench_root=bench_root, cap_oracles=T)
        single.append(tuple((v, o) for v, o in rec["history"]))
    single_bitforbit = (single[0] == single[1])
    report["single_worker_bit_for_bit"] = single_bitforbit
    log(f"[w29.3]   single-worker history identical across 2 repeats: {single_bitforbit} "
        f"(len {len(single[0])} vs {len(single[1])})")

    # (2) multi-worker + wall-cap noise floor on a FIXED config (static_r2), same seed, R repeats.
    log(f"\n[w29.3] (2) multi-worker noise floor: static_r2, {workers}w, wall={wall}s, "
        f"seed={seed}, {repeats} repeats, indices={list(indices)} ...")
    floor = {}
    for idx in indices:
        reps = []
        for rep in range(repeats):
            t0 = time.time()
            rec = _solve(n, idx, seed, params=_arm_params("static_r2", n),
                         workers=workers, wall=wall, bench_root=bench_root)
            reps.append(rec)
            log(f"[w29.3]   {n}_{idx} rep{rep}: obj@T={obj_at_budget(rec['history'],T)} "
                f"oracles={rec['oracle_calls']} wall={time.time()-t0:.0f}s")
        # obj@common across the repeats: read each repeat at the min oracle depth over repeats
        B = min(min(int(r["oracle_calls"]) for r in reps), T)
        vals = [obj_at_budget(r["history"], B) for r in reps]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            spread = max(vals) - min(vals)
            med = float(np.median(vals))
            floor[idx] = {"common_budget": B, "obj_at_common": vals, "spread": spread,
                          "median": med, "spread_pct": (100.0 * spread / med if med else None)}
            log(f"[w29.3]   {n}_{idx} noise floor: spread={spread:,.0f} over {vals} @B={B} "
                f"({floor[idx]['spread_pct']:.4f}% of median)")
    report["noise_floor_static"] = floor

    # (3) schedule==constant under the race: neg_r2 vs static_r2 (same seed, A/B settings).
    log(f"\n[w29.3] (3) schedule==constant under the race: neg_r2 vs static_r2, {workers}w, wall={wall}s ...")
    sched_vs_static = {}
    for idx in indices:
        neg = _solve(n, idx, seed, params=_arm_params("neg_r2", n),
                     workers=workers, wall=wall, bench_root=bench_root)
        stat = _solve(n, idx, seed, params=_arm_params("static_r2", n),
                      workers=workers, wall=wall, bench_root=bench_root)
        B = min(int(neg["oracle_calls"]), int(stat["oracle_calls"]), T)
        a, b = obj_at_budget(neg["history"], B), obj_at_budget(stat["history"], B)
        if a is not None and b is not None:
            sched_vs_static[idx] = {"common_budget": B, "neg": a, "static": b, "delta": a - b}
            log(f"[w29.3]   {n}_{idx} neg-static Δ={a-b:+,.0f} @B={B}")
    report["schedule_vs_constant_race"] = sched_vs_static

    # Summary verdict
    spreads = [v["spread"] for v in floor.values()]
    spread_pcts = [v["spread_pct"] for v in floor.values() if v["spread_pct"] is not None]
    sched_deltas = [abs(v["delta"]) for v in sched_vs_static.values()]
    report["summary"] = {
        "single_worker_bit_for_bit": single_bitforbit,
        "noise_floor_max_spread": (max(spreads) if spreads else None),
        "noise_floor_median_spread_pct": (float(np.median(spread_pcts)) if spread_pcts else None),
        "noise_floor_max_spread_pct": (max(spread_pcts) if spread_pcts else None),
        "schedule_vs_constant_max_abs_delta": (max(sched_deltas) if sched_deltas else None),
    }
    json.dump(report, open(os.path.join(out_dir, "noise_audit.json"), "w"), indent=2)
    _report(log, report)
    return report


def _report(log, r):
    s = r["summary"]
    log("\n" + "=" * 74)
    log(f"bd w29.3 §5 oracle-axis nondeterminism audit — n={r['N']} ({r['workers']}w, wall={r['wall_s']}s)")
    log("=" * 74)
    log(f"(1) single-worker bit-for-bit determinism (decay armed): {s['single_worker_bit_for_bit']}")
    log(f"(2) multi-worker noise floor: max spread={s['noise_floor_max_spread']:,} "
        f"(median {s['noise_floor_median_spread_pct']:.4f}% / max {s['noise_floor_max_spread_pct']:.4f}% of obj)"
        if s["noise_floor_max_spread"] is not None else "(2) no noise-floor pairs")
    log(f"(3) schedule==constant under the race: max |Δ|={s['schedule_vs_constant_max_abs_delta']:,}"
        if s["schedule_vs_constant_max_abs_delta"] is not None else "(3) no schedule-vs-constant pairs")
    log("\nINTERPRETATION: the A/B (run_w29_decay_probe) is decidable iff the lever effect |D-A| can")
    log("exceed this floor. The 71e static-radius edge was ~0.04-0.05% at obj@common. If the noise")
    log("floor %% above is COMPARABLE to that, the A/B cannot distinguish lever from race noise at")
    log("these settings — raise --wall, add seeds, or fall back to a single-worker A/B.")
    log("=" * 74)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd w29.3 §5 oracle-axis nondeterminism audit.")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--indices", default="0,1,2")
    p.add_argument("--seed", type=int, default=20260630)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--wall", type=float, default=120.0)
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_w29_noise_audit"))
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    indices = [int(x) for x in args.indices.split(",")]
    run(n=args.n, indices=indices, seed=args.seed, repeats=args.repeats, workers=args.workers,
        wall=args.wall, bench_root=args.bench_root, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
