#!/usr/bin/env python3
"""M4 — generalization to n=3000 via a DIRECT objective A/B (bd 8an.11, NORTHSTAR §12/§13).

The B_I-anchored primal-integral verdict is DEGENERATE at n≥1000 (warm CBQS meets/beats the
classical frontier B_I → L_I≥B_I; see M3_WARM_FINDINGS.md §9/§10). So M4 scores the discovered
schedule(s) against the warm default by the DIRECT objective at the faithful oracle budget
T(n)=9989, read from the best-of-portfolio oracle-indexed history (the project cost axis;
mirrors logs/m4_spot/compare_n3000_warm_history.py, scaled to the full test set).

Why objective-at-T(n) and not final/wall objective: under M=M_BIG a stalled DEFAULT eventually
"catches up" via a single giant Grover round at ~4300×T(n) (the j-clamp-off artifact, faithfully
counted but sim-deadline-truncated). Reading the history STEP at oracle≤T(n) excludes that
over-budget artifact, so the comparison is at the faithful budget on both arms.

Design (§13): per instance, a matched-seed warm A/B — default vs cand_16 (M3 winner) vs cand_23
(parsimonious) vs a baseline-equivalent NEGATIVE CONTROL ({} → identical to default). Pairing is
over the 9 untouched n=3000 instances (fresh seed, disjoint from the n≤90 selection banks). Verdict:
one-sided Wilcoxon signed-rank (candidate > default) per candidate, Holm-FWER over the candidate
family, median Δ + %, and the negative control (must be Δ≡0 / non-significant).

RUN POLICY: M=M_BIG + stopping_time wall cap (faithfulness waived for the run; the oracle COUNT
stays correct, the metric reads at T(n)). Resumable: each (instance,arm,seed) solve persists to
JSON and is skipped on re-run.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_m4_n3000 \
      [--out-dir DIR] [--seed S] [--wall 900] [--workers 4] [--indices 0,1,..,8] [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, m3_proposer
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.plot_m3_n90 import GENOME_WINNER, GENOME_PARSIMONIOUS

N = 3000
M_BIG = 100_000_000
DEFAULT_INDICES = tuple(range(9))            # the untouched n=3000 test set (3000_0..8)
CANDIDATES = {                                # arm label -> schedule (factory or params)
    "cand_16": m3_proposer.genome_to_factory(GENOME_WINNER),
    "cand_23": m3_proposer.genome_to_factory(GENOME_PARSIMONIOUS),
}
ARMS = ["default", "cand_16", "cand_23", "negctl"]   # negctl = baseline-equivalent ({})


def _resolve(arm, n, c1, c2, c3):
    """The set_param overrides for one arm (empty for default/negctl = the C default schedule)."""
    if arm in ("default", "negctl"):
        return {}
    return CANDIDATES[arm](n, c1, c2, c3)


def solve_arm(arm, idx, seed, wall, workers, bench_root):
    """One warm A/B solve; returns the persisted record dict (objective + oracle-indexed history)."""
    c1, c2, c3 = load_eq29(N, idx, bench_root)
    resolved = _resolve(arm, N, c1, c2, c3)
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
    from benchmarks import baselines
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o, *_) in (r.history or [])]
    return {"arm": arm, "index": idx, "seed": int(seed), "wall_s": dt,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "greedy_value": (int(greedy_value) if greedy_value is not None else None),
            "greedy_feasible": bool(greedy_feasible), "history": hist}


def obj_at_budget(history, T):
    """Best-of-portfolio objective at oracle budget T: the running-max value among history
    entries with oracle ≤ T (a step function; history is feasible-only, oracle-ascending).
    None if no feasible incumbent by T (a feasibility loss at the budget)."""
    vals = [v for (v, o, *_) in history if o <= T]
    return max(vals) if vals else None


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def run(*, out_dir, seed, wall, workers, indices, bench_root, report_only=False, log=print):
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(N)
    cfg = {"N": N, "seed": int(seed), "wall_s": float(wall), "workers": int(workers),
           "indices": list(indices), "M_BIG": M_BIG, "T": T, "arms": ARMS}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        # seed/wall/workers/M_BIG define a solve; a mismatch would alias different runs onto reused ids.
        for k in ("N", "seed", "wall_s", "workers", "M_BIG"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[m4] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — use a fresh --out-dir.")
    else:
        json.dump(cfg, open(cfg_path, "w"), indent=2)

    # ---- 1) solve every (index, arm) once, resumably ----
    if not report_only:
        total = len(indices) * len(ARMS)
        done = 0
        for idx in indices:
            for arm in ARMS:
                done += 1
                rp = os.path.join(out_dir, f"{N}_{idx}__{arm}.json")
                if os.path.exists(rp):
                    log(f"[m4] ({done}/{total}) skip {N}_{idx} {arm} (done)")
                    continue
                log(f"[m4] ({done}/{total}) solve {N}_{idx} {arm} seed={seed} wall={wall}s ...")
                rec = solve_arm(arm, idx, seed, wall, workers, bench_root)
                json.dump(rec, open(rp, "w"))
                ob = obj_at_budget(rec["history"], T)
                log(f"[m4]   -> obj@T={ob} final={rec['objective']} feas={rec['feasible']} "
                    f"oracles={rec['oracle_calls']} wall={rec['wall_s']:.0f}s hist={len(rec['history'])}")

    # ---- 2) load all, compute obj@T(n) per (index, arm) ----
    recs = {}
    for idx in indices:
        for arm in ARMS:
            rp = os.path.join(out_dir, f"{N}_{idx}__{arm}.json")
            if os.path.exists(rp):
                recs[(idx, arm)] = json.load(open(rp))
    obj_at = {(idx, arm): obj_at_budget(r["history"], T) for (idx, arm), r in recs.items()}

    # ---- 3) §13 verdict: paired Wilcoxon (candidate > default) + Holm + neg control ----
    summary = _verdict(indices, recs, obj_at, T)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=2)
    _report(log, summary)
    return summary


def _paired(indices, obj_at, arm):
    """Matched (default, arm) obj@T pairs over instances where BOTH are feasible-at-T."""
    pairs, dropped = [], []
    for idx in indices:
        d, a = obj_at.get((idx, "default")), obj_at.get((idx, arm))
        if d is None or a is None:
            dropped.append((idx, "default" if d is None else arm)); continue
        pairs.append((idx, d, a))
    return pairs, dropped


def _obj_at_common(indices, recs, T):
    """obj at the per-instance COMMON budget B = min over arms of `oracle_calls` (capped at T):
    the largest oracle budget where EVERY arm has a MEASURED value (it actually ran those oracles
    — a stall just adds no history entry). Assumption-free (no stall extrapolation), so this is the
    faithful equal-oracle-cost read; conservative for a still-climbing candidate (the default is the
    bottleneck). Returns (obj_at dict, {idx: B})."""
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


def _candidate_stats(pairs, arm):
    """Per-candidate paired stats vs default: deltas, one-sided Wilcoxon (cand>default), median+CI."""
    deltas = [a - d for (_i, d, a) in pairs]
    pcts = [100.0 * (a - d) / d for (_i, d, a) in pairs]
    if any(x != 0 for x in deltas):
        try:
            W, p = ss.wilcoxon(deltas, alternative="greater", zero_method="wilcox")
        except ValueError:
            W, p = None, 1.0
    else:
        W, p = None, 1.0
    return {"n_pairs": len(pairs), "n_pos": sum(1 for x in deltas if x > 0),
            "n_neg": sum(1 for x in deltas if x < 0),
            "median_delta": (float(np.median(deltas)) if deltas else None),
            "median_pct": (float(np.median(pcts)) if pcts else None),
            "ci95_median_delta": (_boot_ci_median(deltas) if len(deltas) >= 3 else None),
            "wilcoxon_W": (float(W) if W is not None else None), "p_value": float(p),
            "per_instance": [{"index": i, "default": d, arm: a, "delta": a - d,
                              "pct": 100.0 * (a - d) / d} for (i, d, a) in pairs]}


def _block(indices, obj_at):
    """A full candidate-family verdict at one obj_at read: per-candidate stats + Holm-FWER."""
    cand, pvals = {}, {}
    for arm in CANDIDATES:
        pairs, dropped = _paired(indices, obj_at, arm)
        st = _candidate_stats(pairs, arm); st["dropped"] = dropped
        cand[arm] = st; pvals[arm] = st["p_value"]
    return {"candidates": cand, "holm": _holm(pvals, alpha=0.05)}


def _verdict(indices, recs, obj_at_T, T):
    # PRIMARY: obj@T(n) — the designed faithful budget. The default is read as its stalled value
    # (it does not improve in [reached, T]; per-run stall + §6: default flat until ~43M oracles).
    at_T = _block(indices, obj_at_T)
    # CORROBORATION: obj@common — assumption-free equal-oracle-cost read (min oracle_calls/arm).
    obj_common, budgets = _obj_at_common(indices, recs, T)
    at_common = _block(indices, obj_common)
    at_common["budgets"] = budgets
    # negative control: (negctl - default) obj@T must be ≡0 (identical schedule, matched seed).
    nc_pairs, nc_dropped = _paired(indices, obj_at_T, "negctl")
    nc_deltas = [a - d for (_i, d, a) in nc_pairs]
    neg = {"n_pairs": len(nc_pairs), "dropped": nc_dropped,
           "all_zero": all(x == 0 for x in nc_deltas),
           "max_abs_delta": (max(abs(x) for x in nc_deltas) if nc_deltas else 0)}
    feas = {arm: sum(1 for idx in indices if obj_at_T.get((idx, arm)) is not None) for arm in ARMS}
    # M4-PASS: Holm-reject at the designed budget T AND a positive median at the faithful common
    # budget (the win is not a wall/oracle-count artifact) AND the negative control is clean.
    survivors = [a for a in CANDIDATES
                 if at_T["holm"][a]["reject"]
                 and (at_common["candidates"][a]["median_delta"] or 0) > 0
                 and neg["all_zero"]]
    return {"bead": "constraint-oriented-biased-quantum-search-8an.11", "N": N, "T": T,
            "n_instances": len(indices), "indices": list(indices),
            "at_T": at_T, "at_common": at_common, "negative_control": neg,
            "feasible_at_T": feas, "survivors": survivors}


def _boot_ci_median(deltas, B=2000):
    rng = np.random.default_rng(20260624)          # fixed → reproducible CI
    arr = np.asarray(deltas, dtype=float)
    meds = [float(np.median(rng.choice(arr, size=len(arr), replace=True))) for _ in range(B)]
    return [float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))]


def _holm(pvals, alpha):
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out = {}
    prev_reject = True
    for rank, (arm, p) in enumerate(items):
        thresh = alpha / (m - rank)
        reject = prev_reject and (p <= thresh)
        out[arm] = {"p_value": p, "holm_threshold": thresh, "reject": reject, "rank": rank}
        prev_reject = reject
    return out


def _block_report(log, block, label, N, show_instances=True):
    log(f"\n--- {label} ---")
    for arm, r in block["candidates"].items():
        h = block["holm"][arm]
        tag = "  <== Holm-reject" if h["reject"] else ""
        md = r["median_delta"]
        log(f"[{arm}] pairs={r['n_pairs']} (+{r['n_pos']}/-{r['n_neg']}) "
            f"median Δ={md:+,.0f} ({r['median_pct']:+.4f}%) CI95={r['ci95_median_delta']}"
            if md is not None else f"[{arm}] no pairs")
        log(f"        Wilcoxon p={r['p_value']:.4g}  Holm thr={h['holm_threshold']:.4g} "
            f"reject={h['reject']}{tag}")
        if show_instances:
            for pi in r["per_instance"]:
                log(f"          {N}_{pi['index']}: Δ={pi['delta']:+,.0f} ({pi['pct']:+.4f}%)")


def _report(log, s):
    log("\n" + "=" * 72)
    log("M4 — n=3000 DIRECT OBJECTIVE A/B (bd 8an.11)")
    log("=" * 72)
    log(f"N={s['N']} T(n)={s['T']} instances={s['n_instances']} {s['indices']}")
    log(f"feasible-at-T per arm: {s['feasible_at_T']}")
    nc = s["negative_control"]
    log(f"negative control (baseline-equiv vs default): n={nc['n_pairs']} all_zero={nc['all_zero']} "
        f"max|Δ|={nc['max_abs_delta']}")
    _block_report(log, s["at_T"], "PRIMARY: objective @ T(n) (designed budget; default read as stalled)",
                  s["N"], show_instances=True)
    _block_report(log, s["at_common"],
                  "CORROBORATION: objective @ common budget min(oracle_calls) (assumption-free, equal oracle cost)",
                  s["N"], show_instances=False)
    if s["at_common"].get("budgets"):
        log(f"   common budgets per instance: {s['at_common']['budgets']}")
    log("")
    if s["survivors"]:
        log(f"M4 VERDICT: schedule(s) {s['survivors']} BEAT the warm default at n=3000 — Holm-FWER≤0.05 "
            f"at the designed budget T(n) AND a positive median at the faithful equal-oracle budget, "
            f"negative control clean. Generalization CONFIRMED.")
    else:
        log("M4 VERDICT: NO schedule passes both the designed-budget Holm gate and the faithful "
            "equal-oracle corroboration. Generalization NOT established.")
    log("=" * 72)


def main(argv=None):
    p = argparse.ArgumentParser(description="M4 n=3000 direct objective A/B (bd 8an.11).")
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m4_n3000"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seed", type=int, default=20260624)        # fresh: disjoint from selection banks
    p.add_argument("--wall", type=float, default=900.0)         # RUN POLICY 15-min cap
    p.add_argument("--workers", type=int, default=4)            # matches the §6 spot harness
    p.add_argument("--indices", default=None, help="comma sep (default 0..8)")
    p.add_argument("--report-only", action="store_true", help="recompute the verdict from existing JSON")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    run(out_dir=args.out_dir, seed=args.seed, wall=args.wall, workers=args.workers,
        indices=indices, bench_root=args.bench_root, report_only=args.report_only)


if __name__ == "__main__":
    main()
