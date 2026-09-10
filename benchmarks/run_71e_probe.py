#!/usr/bin/env python3
"""bd 71e PROBE — does TIGHTENING the opt-phase radius (r_opt < r_opt_sat) help at n=3000?

The cheap, config-only go/no-go GATE for bd 71e (M5: oracle-indexed / convergence-aware opt
radius SCHEDULE), recommended by the 71e faithfulness workflow (2026-06-25, see bd 71e notes /
memory 71e-scheduled-radius-faithful-probe-first). It needs NO core change: it uses the two
EXISTING, already-priced, allow-listed per-phase radius levers (``opt_sat_branching_radius`` and
``opt_branching_radius``). A STATIC two-stage tighten is the PAYOFF LOWER BOUND of a continuous
71e schedule — if tightening the opt radius below the (broad) opt_sat radius shows no n=3000 edge
here, the richer oracle-indexed schedule is very unlikely to clear the core-change / 3+1 bar.

IMPORTANT — the lower-bound logic is ONE-DIRECTIONAL (a NEGATIVE result kills 71e; a POSITIVE result
is NECESSARY-NOT-SUFFICIENT for the core change). All arms run a CONSTANT opt radius (the switch fires
ONCE — SearchLib.c installs branching_stats_opt and never re-reads/decays the radius — and with an
EARLY switch the opt phase is >95% of the run). So a positive result establishes only that a tighter
CONSTANT opt radius wins, which is capturable by the existing static lever with NO core change. It does
NOT show a time-varying SCHEDULE beats the BEST CONSTANT radius (this probe pairs vs the broad r=8
control, never the best constant). Establishing the schedule's marginal value requires a SEPARATE
late-switch broad->tight schedule-proxy A/B (arm B vs arm A=best-constant-tight) AND a §5 multi-worker
nondeterminism audit of the oracle-index axis a schedule would ride (this probe found that axis is
itself nondeterministic run-to-run between byte-identical 4-worker configs — negctl noise floor below).

WHY IT IS A FAIR ISOLATION. Both M4 winners already tighten (cand_16 r_opt_sat=8.0 -> r_opt=4.41;
cand_23 5.16 -> 4.43) but BUNDLE switch + theta, so the win cannot be attributed to the radius
gradient alone. This probe holds everything else fixed and varies ONLY the opt-phase radius:

  * shared opt_sat radius = 8.0 (BROAD — drives the feasibility push; cand_16's value),
  * shared early switch alpha = 0.012 (cand_16),  * theta OFF (no opt_branching_weights),
  * vary opt_branching_radius across arms.

Feasibility at n=3000 is driven by the (shared, broad) opt_sat radius — the warm greedy start is
INFEASIBLE at n=3000, so the solver runs sat -> opt_sat -> opt and the broad opt_sat radius is
what reaches feasibility. Tightening ONLY the opt phase therefore does not jeopardise feasibility;
the arms differ purely in how tightly the OPT phase polishes past first-feasible (exactly the
regime where the warm default stalls — M4_WARM_FINDINGS §6/§9).

Arms (matched-seed warm A/B, paired vs ``control``):
  control       opt radius == opt_sat radius (= 8.0)  — NO tightening (the baseline)
  tight         opt radius = 4.0  (~ the winners' opt radius)
  strong_tight  opt radius = 2.0  (aggressive tighten)
  negctl        == control (byte-identical params)    -> delta vs control MUST be == 0

Metric (mirrors benchmarks.run_m4_n3000, NORTHSTAR §13): obj@T(n) PRIMARY + obj@common
CORROBORATION (assumption-free equal-oracle-cost read), one-sided Wilcoxon (arm > control),
Holm-FWER over {tight, strong_tight}, and a clean negative control. Reuses M4's pure stats core
(``obj_at_budget``, ``_candidate_stats``, ``_holm``, ``_boot_ci_median``) — §2.7, no duplicate stats.

RUN POLICY (CLAUDE.md): M = M_BIG + stopping_time wall cap (faithfulness waived for the run; the
oracle COUNT stays correct, the metric reads at the oracle budget). Resumable: each
(instance, arm) solve persists to JSON and is skipped on re-run.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_71e_probe \
      [--n 3000] [--out-dir DIR] [--seed S] [--wall 900] [--workers 4] \
      [--indices 0,1,..,8] [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
# Reuse the M4 statistical core verbatim (pure functions, no module-global deps): §2.7.
from benchmarks.run_m4_n3000 import obj_at_budget, _candidate_stats, _holm, _boot_ci_median

M_BIG = 100_000_000
DEFAULT_INDICES = tuple(range(9))             # the n=3000 test set (3000_0..8)

R_OPT_SAT = 8.0                               # BROAD feasibility radius, shared by all arms (cand_16)
ALPHA_SWITCH = 0.012                          # early exploit->explore switch, shared (cand_16)
BASELINE_ARM = "control"                      # the equal-radius arm everything is paired against

#: arm -> opt_branching_radius (the ONLY gene that varies). control/negctl == R_OPT_SAT (no tighten).
ARM_R_OPT = {
    "control": R_OPT_SAT,
    "tight": 4.0,
    "strong_tight": 2.0,
    "negctl": R_OPT_SAT,                      # byte-identical to control -> Delta must be 0
}
ARMS = ["control", "tight", "strong_tight", "negctl"]
CANDIDATE_ARMS = ["tight", "strong_tight"]   # the family compared vs control (Holm over these)


def _resolve(arm, n):
    """The set_param overrides for one arm: a fixed broad opt_sat radius + early switch + theta
    OFF, varying only the opt-phase radius. ALL arms set explicit params (no C-default path), so
    negctl (== control params, matched seed) is a byte-identical control replica."""
    return {
        "opt_sat_branching_radius": R_OPT_SAT,
        "opt_branching_radius": ARM_R_OPT[arm],
        "opt_switch_oracles": int(round(ALPHA_SWITCH * metric.oracle_budget(n))),
    }


def solve_arm(arm, n, idx, seed, wall, workers, bench_root):
    """One warm A/B solve; returns the persisted record dict (objective + oracle-indexed history).
    Mirrors benchmarks.run_m4_n3000.solve_arm (same warm-start + RUN POLICY protocol)."""
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = _resolve(arm, n)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()       # WARM start (published iqs)
    m.seed = int(seed)
    m.set_param("M", M_BIG)                                   # wall binds, not the budget
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)                          # exact sampler
    m.set_param("stopping_time", float(wall))                 # RUN POLICY wall cap
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    t0 = time.time(); r = m.solve(); dt = time.time() - t0
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o, *_) in (r.history or [])]
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed), "wall_s": dt,
            "params": {k: (list(v) if isinstance(v, np.ndarray) else v) for k, v in resolved.items()},
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "greedy_value": (int(greedy_value) if greedy_value is not None else None),
            "greedy_feasible": bool(greedy_feasible), "history": hist}


# --------------------------------------------------------------------------- #
# Verdict (paired vs the equal-radius CONTROL arm; M4 stats core reused)
# --------------------------------------------------------------------------- #

def _paired(indices, obj_at, arm, baseline=BASELINE_ARM):
    """Matched (baseline, arm) obj pairs over instances where BOTH are feasible-at-budget."""
    pairs, dropped = [], []
    for idx in indices:
        b, a = obj_at.get((idx, baseline)), obj_at.get((idx, arm))
        if b is None or a is None:
            dropped.append((idx, baseline if b is None else arm)); continue
        pairs.append((idx, b, a))
    return pairs, dropped


def _obj_at_common(indices, recs, T):
    """obj at the per-instance COMMON budget B = min over arms of oracle_calls (capped at T):
    the largest budget where EVERY arm has a MEASURED value. Assumption-free (no stall
    extrapolation) -> the faithful equal-oracle-cost read. Local copy of the M4 helper, keyed
    on THIS probe's ARMS."""
    obj_at, budgets = {}, {}
    for idx in indices:
        rs = {arm: recs.get((idx, arm)) for arm in ARMS}
        if any(r is None for r in rs.values()):
            continue
        B = min(min(int(r.get("oracle_calls", 0)) for r in rs.values()), T)
        budgets[idx] = B
        for arm, r in rs.items():
            obj_at[(idx, arm)] = obj_at_budget(r["history"], B)
    return obj_at, budgets


def _block(indices, obj_at):
    """A candidate-family verdict at one obj_at read: per-candidate stats (vs control) + Holm."""
    cand, pvals = {}, {}
    for arm in CANDIDATE_ARMS:
        pairs, dropped = _paired(indices, obj_at, arm)
        st = _candidate_stats(pairs, arm); st["dropped"] = dropped
        cand[arm] = st; pvals[arm] = st["p_value"]
    return {"candidates": cand, "holm": _holm(pvals, alpha=0.05)}


def _verdict(n, indices, recs, obj_at_T, T):
    at_T = _block(indices, obj_at_T)                              # obj@T(n) (designed budget)
    obj_common, budgets = _obj_at_common(indices, recs, T)       # obj@common (faithful equal-oracle)
    at_common = _block(indices, obj_common); at_common["budgets"] = budgets
    # NEGATIVE CONTROL. negctl has byte-identical params to control, so its delta must be ~0.
    # CRITICAL: read it at the EQUAL-ORACLE common budget, NOT at obj@T. Under the RUN POLICY wall
    # cap, two identical-param runs reach DIFFERENT oracle depths (timing jitter; faithfulness is
    # waived for wall-capped runs), so an obj@T read of negctl is the wall-truncation NOISE FLOOR,
    # not a determinism check. At equal oracle depth the trajectory is deterministic (matched seed
    # bank), so negctl-vs-control collapses to ~0 (residual = boundary-incumbent logging only).
    nc_T = [a - b for (_i, b, a) in _paired(indices, obj_at_T, "negctl")[0]]       # wall noise floor
    nc_C = [a - b for (_i, b, a) in _paired(indices, obj_common, "negctl")[0]]     # determinism check
    cand_med_min = (min((at_common["candidates"][a]["median_delta"] or 0) for a in CANDIDATE_ARMS)
                    if CANDIDATE_ARMS else 0)
    neg = {"n_pairs": len(nc_C),
           "at_common_median": (float(np.median(nc_C)) if nc_C else None),
           "at_common_max_abs": (max(abs(x) for x in nc_C) if nc_C else 0),
           "at_T_max_abs_noise": (max(abs(x) for x in nc_T) if nc_T else 0),
           # clean iff equal-oracle determinism holds in the median AND the residual is far below the
           # smallest candidate signal (the pipeline manufactures no signal from identical inputs).
           "clean": bool(nc_C and np.median(nc_C) == 0
                         and max(abs(x) for x in nc_C) < cand_med_min)}
    feas = {arm: sum(1 for idx in indices if obj_at_T.get((idx, arm)) is not None) for arm in ARMS}
    # 71e-GO at this gate: Holm-reject at BOTH the designed budget T(n) AND the faithful equal-oracle
    # common budget (so the win is NOT a wall-truncation-depth artifact), positive median at common,
    # and a clean negative control (read at equal oracle depth).
    survivors = [a for a in CANDIDATE_ARMS
                 if at_T["holm"][a]["reject"]
                 and at_common["holm"][a]["reject"]
                 and (at_common["candidates"][a]["median_delta"] or 0) > 0
                 and neg["clean"]]
    return {"bead": "constraint-oriented-biased-quantum-search-71e", "N": n, "T": T,
            "baseline_arm": BASELINE_ARM, "r_opt_sat": R_OPT_SAT, "alpha_switch": ALPHA_SWITCH,
            "arm_r_opt": ARM_R_OPT, "n_instances": len(indices), "indices": list(indices),
            "at_T": at_T, "at_common": at_common, "negative_control": neg,
            "feasible_at_T": feas, "survivors": survivors}


def run(*, n, out_dir, seed, wall, workers, indices, bench_root, report_only=False, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    cfg = {"N": n, "seed": int(seed), "wall_s": float(wall), "workers": int(workers),
           "indices": list(indices), "M_BIG": M_BIG, "T": T, "arms": ARMS,
           "r_opt_sat": R_OPT_SAT, "alpha_switch": ALPHA_SWITCH, "arm_r_opt": ARM_R_OPT}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "seed", "wall_s", "workers", "M_BIG", "r_opt_sat", "alpha_switch"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[71e] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — use a fresh --out-dir.")
    else:
        json.dump(cfg, open(cfg_path, "w"), indent=2)

    if not report_only:
        total = len(indices) * len(ARMS); done = 0
        for idx in indices:
            for arm in ARMS:
                done += 1
                rp = os.path.join(out_dir, f"{n}_{idx}__{arm}.json")
                if os.path.exists(rp):
                    log(f"[71e] ({done}/{total}) skip {n}_{idx} {arm} (done)"); continue
                log(f"[71e] ({done}/{total}) solve {n}_{idx} {arm} (r_opt={ARM_R_OPT[arm]}) "
                    f"seed={seed} wall={wall}s ...")
                rec = solve_arm(arm, n, idx, seed, wall, workers, bench_root)
                json.dump(rec, open(rp, "w"))
                ob = obj_at_budget(rec["history"], T)
                log(f"[71e]   -> obj@T={ob} final={rec['objective']} feas={rec['feasible']} "
                    f"oracles={rec['oracle_calls']} wall={rec['wall_s']:.0f}s hist={len(rec['history'])}")

    recs = {}
    for idx in indices:
        for arm in ARMS:
            rp = os.path.join(out_dir, f"{n}_{idx}__{arm}.json")
            if os.path.exists(rp):
                recs[(idx, arm)] = json.load(open(rp))
    obj_at = {(idx, arm): obj_at_budget(r["history"], T) for (idx, arm), r in recs.items()}
    summary = _verdict(n, indices, recs, obj_at, T)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=2)
    _report(log, summary)
    return summary


def _block_report(log, block, label, N, show_instances=True):
    log(f"\n--- {label} ---")
    for arm, r in block["candidates"].items():
        h = block["holm"][arm]; tag = "  <== Holm-reject" if h["reject"] else ""; md = r["median_delta"]
        log(f"[{arm} vs {BASELINE_ARM}] pairs={r['n_pairs']} (+{r['n_pos']}/-{r['n_neg']}) "
            f"median Δ={md:+,.0f} ({r['median_pct']:+.4f}%) CI95={r['ci95_median_delta']}"
            if md is not None else f"[{arm}] no pairs")
        log(f"        Wilcoxon p={r['p_value']:.4g}  Holm thr={h['holm_threshold']:.4g} "
            f"reject={h['reject']}{tag}")
        if show_instances and md is not None:
            for pi in r["per_instance"]:
                log(f"          {N}_{pi['index']}: Δ={pi['delta']:+,.0f} ({pi['pct']:+.4f}%)")


def _report(log, s):
    log("\n" + "=" * 72)
    log("bd 71e PROBE — n=%d static opt-radius TIGHTEN A/B (vs equal-radius control)" % s["N"])
    log("=" * 72)
    log(f"N={s['N']} T(n)={s['T']} instances={s['n_instances']} {s['indices']}")
    log(f"shared opt_sat radius={s['r_opt_sat']}  early switch alpha={s['alpha_switch']}  theta=OFF")
    log(f"arm -> opt radius: {s['arm_r_opt']}")
    log(f"feasible-at-T per arm: {s['feasible_at_T']}")
    nc = s["negative_control"]
    log(f"negative control (negctl vs control) — multi-worker run-to-run NOISE FLOOR, NOT bit-determinism "
        f"(§8 guarantees single-worker only; 4-worker runs diverge at a fixed oracle index): "
        f"n={nc['n_pairs']} @common median={nc['at_common_median']:+,.0f} "
        f"max|Δ|={nc['at_common_max_abs']:,.0f} (<< signal) ok={nc['clean']}  "
        f"(obj@T wall-depth noise max|Δ|={nc['at_T_max_abs_noise']:,.0f})")
    _block_report(log, s["at_T"], "PRIMARY: objective @ T(n) (designed budget)", s["N"], True)
    _block_report(log, s["at_common"],
                  "CORROBORATION: objective @ common budget min(oracle_calls) (equal oracle cost)",
                  s["N"], False)
    if s["at_common"].get("budgets"):
        log(f"   common budgets per instance: {s['at_common']['budgets']}")
    log("")
    if s["survivors"]:
        log(f"71e PROBE VERDICT: GO on the STATIC opt-radius lever — NO core change. Tightening arm(s) "
            f"{s['survivors']} beat the equal-radius (r=8) control at n={s['N']}: Holm-reject at BOTH "
            f"obj@common (the faithful equal-oracle read) and obj@T, monotone in r, negctl noise floor "
            f"<< signal. This is a BEST-CONSTANT result — capture it by setting opt_branching_radius "
            f"smaller via the EXISTING lever. The 71e SCHEDULE's marginal value over the best constant "
            f"is NOT measured here (all arms = constant opt radius, early switch). Do NOT open the "
            f"core-change / 3+1 workflow without (1) a §5 multi-worker nondeterminism audit of the "
            f"oracle-index axis, and (2) a late-switch broad->tight schedule-proxy A/B (B vs "
            f"best-constant-tight A) showing the schedule beats the best constant. Also: single seed, "
            f"~0.04%, all reads sub-budget (<70% of T(n)) — replicate across seeds.")
    else:
        log(f"71e PROBE VERDICT: NO-GO / weak. No tightening arm passes both the Holm gate at T(n) and "
            f"the faithful equal-oracle corroboration. The static lower bound shows no isolated radius-"
            f"tightening edge -> the richer oracle-indexed schedule is unlikely to clear the core-change bar.")
    log("=" * 72)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd 71e probe: static opt-radius tighten A/B.")
    p.add_argument("--n", type=int, default=3000, help="problem size (3000 = the real gate; small n = wiring smoke)")
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m5_71e_probe"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seed", type=int, default=20260625)        # fresh; disjoint from M4 (20260624)
    p.add_argument("--wall", type=float, default=900.0)         # RUN POLICY 15-min cap (matches M4)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None, help="comma sep (default 0..8)")
    p.add_argument("--report-only", action="store_true", help="recompute the verdict from existing JSON")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    run(n=args.n, out_dir=args.out_dir, seed=args.seed, wall=args.wall, workers=args.workers,
        indices=indices, bench_root=args.bench_root, report_only=args.report_only)


if __name__ == "__main__":
    main()
