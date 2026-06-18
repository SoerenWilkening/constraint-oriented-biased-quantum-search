#!/usr/bin/env python3
"""benchmarks/run_m3_warm.py — the EXPLORATORY WARM M3 agent-loop driver (bd 8an.10).

The published CBQS (``iqs``) WARM-starts via ``general_greedy()`` (bd 8an.9); the cold
M3 (bd 884) optimized against a ``0^n`` cold start iqs never uses. This driver re-runs
M3 WARM (both A/B arms warm) against a freshly-solved warm default on the anchored
``n≤90`` strata, with the §13 discipline (capstone, CV+Holm, negative control, held-out
rescore) intact.

GENOME SCOPE — a corrected finding (bd 8an.10 run + review). The task's premise was that
a warm (feasible-from-oracle-0) start makes ``r_opt_sat`` + ``alpha_switch`` INERT, so
only ``{r_opt, θ}`` need searching. **That is empirically FALSE at n≤90:** the greedy
construction is FREQUENTLY INFEASIBLE (4/9 n=90 instances), so the solver DOES run
``opt_sat`` and the broad ``opt_sat_branching_radius`` + early ``opt_switch_oracles`` are
the DOMINANT drivers of the warm win (full cand_16 warm at n=90: §13 W=+9, +23% mean-PI;
the warm-live ``{r_opt,θ}`` subset: tie / −3%). So this driver searches the **FULL 5-gene
genome** by default; ``--warm-live-only`` restricts to ``WARM_SPEC`` (valid only where the
greedy start is always feasible — e.g. verified-feasible large-n, NOT n≤90).

Warm-specific machinery:

  1. **Warm solves** — every default/candidate/neg-control/rescore solve warm-starts
     (``run_sweep(warm=True)``; bd 8an.10 wiring). BOTH arms warm → matched A/B.
  2. **Warm anchor table** — the frozen ``default_PI`` is COLD, so it is REPLACED in an
     in-memory table by the freshly-solved WARM default's median PI
     (:func:`benchmarks.baselines.synthesize_warm_default_pi`); ``B_I`` (protocol-
     independent frontier) and ``L_I`` (cold first-feasible floor) are KEPT — both arms
     normalize against the SAME cold ``L_I`` so its warm/cold inconsistency cancels in the
     paired delta (the accepted EXPLORATORY gap). The capstone STILL holds: the warm
     default re-scores to exactly the synthesized warm ``default_PI`` (strict_xcheck).

EXPLORATORY: a FINAL/reproducible result still needs 8an.9 (re-FROZEN warm ``default_PI``
+ 'default := warm' governance). This driver discovers/ranks warm schedules; it does NOT
re-freeze anchors. See ``benchmarks/M3_WARM_FINDINGS.md``.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.run_m3_warm [--generations G]
      [--pop-size P] [--n-offspring K] [--n-init-random R] [--seed S]
      [--out-dir DIR] [--bench-root DIR] [--no-rescore] [--warm-live-only] [--max-per-size N]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks import baselines, m2, m3, m3_proposer, m3_select, metric  # noqa: E402
from benchmarks.run_m3 import (  # noqa: E402  (genome-agnostic helpers reused verbatim)
    SELECTION_SIZES, HOLDOUT_INSTANCES, RESCORE_SEEDS,
    selection_instances, _guard_candidate_genome, _fitness_dict,
)


# --------------------------------------------------------------------------- #
# Warm genome formatting (the 3-gene WARM_SPEC layout, bd 8an.10)
# --------------------------------------------------------------------------- #

def _fmt_warm_genome(genome):
    if genome is None:
        return "None"
    g = [float(x) for x in genome]
    feat = m3_proposer.FEATURES[int(min(len(m3_proposer.FEATURES) - 1, max(0, g[2])))][0]
    return f"(r_opt={g[0]:.2f}, theta_amp={g[1]:.2f}, feat={feat})"


def _warm_genome_dict(genome):
    if genome is None:
        return None
    g = [float(x) for x in genome]
    feat = m3_proposer.FEATURES[int(min(len(m3_proposer.FEATURES) - 1, max(0, g[2])))][0]
    return {"r_opt": g[0], "theta_amp": g[1], "theta_feature": feat}


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def _subset_per_size(instances, max_per_size):
    """Deterministically keep the first ``max_per_size`` (lowest-index) instances per size.

    A fast EXPLORATORY pass: each fold stays populated (all sizes kept) but the per-candidate
    solve cost (88 instances × 7 seeds ≈ 5 min) drops proportionally. The subset is fixed by
    (size, index) ordering, so the run stays reproducible and the config stamp records it."""
    if not max_per_size:
        return instances
    by_size = {}
    for (n, i) in sorted(instances):
        by_size.setdefault(n, []).append((n, i))
    out = []
    for n in sorted(by_size):
        out.extend(by_size[n][:max_per_size])
    return out


def run(*, out_dir, bench_root, seed, generations, pop_size, n_offspring,
        n_init_random, num_workers=None, do_rescore=True, max_per_size=None,
        warm_live_only=False, log=print):
    """Solve the WARM default once, synthesize the warm anchor table, run the warm
    population search, then the §13 selection (vs the warm default).

    GENOME SCOPE (bd 8an.10 — corrected by the empirical run): searches the FULL 5-gene
    genome by DEFAULT. The task's premise was that a warm (feasible-from-oracle-0) start makes
    ``r_opt_sat`` + ``alpha_switch`` inert, so only ``{r_opt, θ}`` (``WARM_SPEC``) need
    searching. That is EMPIRICALLY FALSE at n≤90: the greedy construction is FREQUENTLY
    INFEASIBLE (4/9 n=90 instances: 90_2/6/7/8), so the solver DOES run ``opt_sat`` and the
    broad ``opt_sat_branching_radius`` + early ``opt_switch_oracles`` are the DOMINANT drivers
    of the warm win (full cand_16 warm: §13 W=+9, +23% mean-PI at n=90; dropping them → tie
    /−3%). So the warm search must keep them. ``warm_live_only=True`` restricts to the 3-gene
    ``WARM_SPEC`` (valid ONLY where the greedy start is always feasible — e.g. verified-feasible
    large-n — NOT n≤90)."""
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    if warm_live_only:
        spec = m3_proposer.WARM_SPEC
        fmt_genome, genome_dict = _fmt_warm_genome, _warm_genome_dict
    else:
        spec = m3_proposer.COLD_SPEC          # full 5-gene — opt_sat/switch LIVE at n≤90
        from benchmarks.run_m3 import _fmt_genome, _genome_dict
        fmt_genome, genome_dict = _fmt_genome, _genome_dict
    frozen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "baselines_frozen.csv")
    frozen = baselines.load_frozen_baselines(frozen_path)
    instances = selection_instances(frozen)  # scoreable n≤90 (cold default_PI present == B_I/L_I ok)
    instances = _subset_per_size(instances, max_per_size)  # fast exploratory subset (bd 8an.10)
    seeds = baselines.DEFAULT_SEED_BANK
    log(f"[run_m3_warm] WARM exploratory M3 (bd 8an.10): {len(instances)} anchored "
        f"instances over sizes {SELECTION_SIZES}; seed bank {seeds}; rng seed {seed}; "
        f"genome={'WARM_SPEC (live-only)' if warm_live_only else 'FULL 5-gene'} {spec.genes}")

    # --- Config stamp (cross-run aliasing guard; warm flag makes the provenance explicit). ---
    run_cfg = {"seed": int(seed), "generations": int(generations),
               "pop_size": int(pop_size), "n_offspring": int(n_offspring),
               "n_init_random": int(n_init_random), "sizes": list(SELECTION_SIZES),
               "max_per_size": (int(max_per_size) if max_per_size else None),
               "n_instances": len(instances), "warm": True,
               "genome": ("warm_live" if warm_live_only else "full")}
    cfg_path = os.path.join(out_dir, "run_config.json")
    cand_root = os.path.join(out_dir, "candidates")
    if os.path.isdir(cand_root) and any(os.scandir(cand_root)):
        if not os.path.exists(cfg_path):
            raise SystemExit(
                f"[run_m3_warm] {cand_root} holds candidate run-sets but no run_config.json — "
                f"refusing to resume into an unknown state (out_dir aliasing risk). Use a fresh "
                f"--out-dir.")
        prev_cfg = json.load(open(cfg_path))
        if prev_cfg != run_cfg:
            raise SystemExit(
                f"[run_m3_warm] CONFIG MISMATCH: {out_dir} was built with {prev_cfg} but this run "
                f"asks for {run_cfg}. Resuming would alias a different schedule's run-set onto a "
                f"reused candidate id (landmine #4 / §2.1). Use a fresh --out-dir.")
    json.dump(run_cfg, open(cfg_path, "w"), indent=2)

    # ------------------------------------------------------------------ #
    # 1) WARM default run-set, solved ONCE (landmine #4), persisted + resumable.
    # ------------------------------------------------------------------ #
    default_dir = os.path.join(out_dir, "default")
    t0 = time.time()
    m2.run_sweep("m3warm_default", None, instances, out_dir=default_dir, seeds=seeds,
                 bench_root=bench_root, num_workers=num_workers, warm=True,
                 log=lambda *a: None)
    default_results = m2.load_run_set_dir(default_dir)
    log(f"[run_m3_warm] warm default run-set ready ({len(default_results)} instances, "
        f"{time.time() - t0:.0f}s)")

    # ------------------------------------------------------------------ #
    # 2) WARM anchor table: replace the (cold) frozen default_PI with the warm
    #    default's median PI; keep B_I/L_I. The §6 metric reads default_PI from THIS
    #    table as the authoritative gate reference (bd 8an.10).
    # ------------------------------------------------------------------ #
    warm_baselines = baselines.synthesize_warm_default_pi(frozen, default_results)
    n_warm_anchored = sum(1 for k in instances
                          if warm_baselines.get(k, {}).get("default_PI") is not None)
    log(f"[run_m3_warm] synthesized warm default_PI for {n_warm_anchored}/{len(instances)} "
        f"instances (B_I/L_I kept cold).")
    if n_warm_anchored == 0:
        raise SystemExit("[run_m3_warm] no instance got a warm default_PI — the warm default "
                         "is never reliably feasible? (cannot score). Aborting.")

    # ------------------------------------------------------------------ #
    # 3) CAPSTONE (landmine #2 / M1 lesson): default-vs-default strict-xcheck against
    #    the WARM table. The warm default re-scores to exactly the synthesized warm
    #    default_PI, so this MUST pass — a breach means the warm run-set and the warm
    #    table diverged (a coding bug), not a stale freeze.
    # ------------------------------------------------------------------ #
    try:
        cap = metric.score_verdict(default_results, default_results, warm_baselines,
                                   strict_xcheck=True, require_largest_n=False)
    except ValueError as exc:
        raise SystemExit(
            f"[run_m3_warm] CAPSTONE FAILED: warm default-vs-default strict-xcheck raised ({exc}). "
            f"The warm anchor table and the warm default run-set are inconsistent — a synthesis bug, "
            f"not a stale freeze. Refusing to score candidates against a poisoned reference.")
    if not cap["overall_pass"] or (cap.get("default_xcheck_failures") or []):
        raise SystemExit(
            f"[run_m3_warm] CAPSTONE FAILED: warm default-vs-default overall_pass="
            f"{cap['overall_pass']}, xcheck_failures={len(cap.get('default_xcheck_failures') or [])}.")
    log(f"[run_m3_warm] capstone OK: warm default-vs-default strict-xcheck exact "
        f"({len(cap['default_PI'])} warm-anchored instances).")

    # ------------------------------------------------------------------ #
    # 4) Evaluator: per-candidate out_dir isolation + DETERMINISTIC §10 gate +
    #    genome-stamp; WARM solves; scored vs the WARM table.
    # ------------------------------------------------------------------ #
    from benchmarks import candidate_gate
    genomes_dir = os.path.join(out_dir, "genomes")
    evaluated = {}

    def evaluator(candidate, *, out_dir, scale_check=True, gate_scale_ns=(100, 1000), **kw):
        cid = candidate.meta["id"]
        _guard_candidate_genome(genomes_dir, cid, candidate.genome)
        cand_dir = os.path.join(out_dir, cid)
        # §10 gate is start-agnostic (it measures the opt-radius LEVER's scale-invariance
        # on synthetic instances, a property of the schedule, not the warm/cold trajectory);
        # deterministic seeds=(1,) (bd cjz / 8an.4.4), then solve with scale_check=False.
        gate = candidate_gate.admit(candidate.factory, scale_ns=gate_scale_ns,
                                    scale_check=scale_check, seeds=(1,))
        if not gate.ok:
            ind = m3.Individual(candidate, m3.Fitness.gated_out(), verdict=None,
                                gate=gate, gated_out=True)
        else:
            ind = m3.evaluate_candidate(candidate, out_dir=cand_dir,
                                        scale_check=False, **kw)
            ind.gate = gate
        evaluated[cid] = ind
        tag = ("GATED " + "; ".join(gate.reasons)) if ind.gated_out else repr(ind.fitness)
        log(f"[run_m3_warm]   eval {cid} genome={fmt_genome(candidate.genome)} -> {tag}")
        return ind

    eval_kwargs = dict(
        default_results=default_results, baselines=warm_baselines,
        instances=instances, seeds=seeds, out_dir=cand_root, bench_root=bench_root,
        num_workers=num_workers, opt_sample_cap=0, scale_check=True, warm=True)

    # ------------------------------------------------------------------ #
    # 5) Init population = the spec's baseline genome + R random genomes.
    # ------------------------------------------------------------------ #
    init_pop = [m3.Candidate(
        factory=spec.to_factory(spec.baseline),
        genome=tuple(float(x) for x in spec.baseline),
        meta={"id": "init_default", "op": "seed"})]
    for i in range(n_init_random):
        g = m3_proposer.random_genome(rng, genes=spec.genes, bounds=spec.bounds)
        init_pop.append(m3.Candidate(
            factory=spec.to_factory(g),
            genome=tuple(float(x) for x in g),
            meta={"id": f"init_rand_{i}", "op": "seed"}))

    # ------------------------------------------------------------------ #
    # 6) Run the WARM population search (NORTHSTAR §10).
    # ------------------------------------------------------------------ #
    proposer = m3_proposer.ParametricProposer(
        n_offspring=n_offspring, sigma=m3_proposer.GENE_SIGMA, crossover_rate=0.3,
        id_prefix="cand", spec=spec)
    log(f"[run_m3_warm] evolve: pop_size={pop_size} generations={generations} "
        f"n_offspring={n_offspring} (init {len(init_pop)}) over {spec.genes}")
    t0 = time.time()
    result = m3.evolve(proposer, rng=rng, generations=generations, pop_size=pop_size,
                       init_population=init_pop, evaluator=evaluator,
                       eval_kwargs=eval_kwargs, min_genome_distance=0.0, log=log)
    log(f"[run_m3_warm] evolve done ({time.time() - t0:.0f}s, {len(evaluated)} candidates "
        f"evaluated). best {result.best.fitness!r} "
        f"genome={fmt_genome(result.best.candidate.genome)}")

    # ------------------------------------------------------------------ #
    # 7) §13 selection over the admitted family (CV + Holm FWER), vs the warm default.
    # ------------------------------------------------------------------ #
    admitted = {cid: ind for cid, ind in evaluated.items() if not ind.gated_out}
    candidate_results_by_id = {
        cid: m2.load_run_set_dir(os.path.join(cand_root, cid)) for cid in admitted}
    log(f"[run_m3_warm] selection over {len(candidate_results_by_id)} admitted candidates "
        f"(of {len(evaluated)} evaluated).")
    sel = m3_select.select_significant(
        candidate_results_by_id, default_results, warm_baselines,
        folds=m3_select.FOLDS, alpha=m3_select.ALPHA, strict_xcheck=True)
    log(f"[run_m3_warm] selection: {len(sel.survivors)} survivor(s) "
        f"(CV-pass AND Holm-reject): {sel.survivors}")

    # ------------------------------------------------------------------ #
    # 8) Negative control (§13): warm baseline-equivalent ({}) candidates solved WARM at
    #    the matched seed bank are byte-identical to the warm default -> no survivor.
    # ------------------------------------------------------------------ #
    nc_root = os.path.join(out_dir, "negcontrol")
    _nc = [0]

    def nc_candidate_solve(factory, inst, sds):
        i = _nc[0]
        _nc[0] += 1
        d = os.path.join(nc_root, f"nc_{i}")
        m2.run_sweep(f"negctl_{i}", factory, list(inst), out_dir=d, seeds=sds,
                     bench_root=bench_root, num_workers=num_workers, warm=True,
                     log=lambda *a: None)
        return m2.load_run_set_dir(d)

    neg_factories = {f"nc_{i}": m3_proposer.baseline_equivalent_factory() for i in range(3)}
    neg = m3_select.negative_control(
        neg_factories, default_results, warm_baselines,
        candidate_solve=nc_candidate_solve, candidate_instances=instances,
        candidate_seeds=seeds, folds=m3_select.FOLDS, alpha=m3_select.ALPHA)
    if neg.any_significant:
        raise SystemExit(
            f"[run_m3_warm] NEGATIVE CONTROL FAILED: a warm baseline-equivalent candidate was "
            f"flagged significant ({neg.selection.survivors}) — the multiplicity machine is leaking "
            f"type-I error (NORTHSTAR §13).")
    log(f"[run_m3_warm] negative control PASSED (no warm baseline-equivalent survivor).")

    # ------------------------------------------------------------------ #
    # 9) §13 final rescore (if a winner emerged) on the untouched n=100/150 holdout with
    #    NEW seeds 8..10, WARM. The warm holdout default_PI is synthesized from the
    #    freshly-solved warm default inside rescore_once (default_pi_synthesizer).
    # ------------------------------------------------------------------ #
    final = None
    winner_id = None
    if sel.survivors and do_rescore:
        winner_id = max(sel.survivors, key=lambda cid: admitted[cid].fitness)
        winner_factory = admitted[winner_id].candidate.factory
        log(f"[run_m3_warm] winner {winner_id} "
            f"genome={fmt_genome(admitted[winner_id].candidate.genome)} — rescoring WARM on "
            f"holdout {list(HOLDOUT_INSTANCES)} with new seeds {RESCORE_SEEDS}.")

        def default_solve(inst, sds):
            d = os.path.join(out_dir, "rescore_default")
            m2.run_sweep("rescore_default", None, list(inst), out_dir=d, seeds=sds,
                         bench_root=bench_root, num_workers=num_workers, warm=True,
                         log=lambda *a: None)
            return m2.load_run_set_dir(d)

        def candidate_solve(factory, inst, sds):
            d = os.path.join(out_dir, "rescore_winner")
            m2.run_sweep("rescore_winner", factory, list(inst), out_dir=d, seeds=sds,
                         bench_root=bench_root, num_workers=num_workers, warm=True,
                         log=lambda *a: None)
            return m2.load_run_set_dir(d)

        # NOTE (bd 8an.10 review): default_pi_synthesizer rebuilds the table from the
        # freshly-solved warm HOLDOUT default, so it nulls default_PI for the (absent)
        # selection keys. Harmless — rescore_once scores ONLY the holdout instances, whose
        # warm default_PI it has just synthesized; the nulled selection keys are never read.
        final = m3_select.rescore_once(
            winner_factory, warm_baselines, holdout_instances=list(HOLDOUT_INSTANCES),
            new_seeds=RESCORE_SEEDS, default_solve=default_solve,
            candidate_solve=candidate_solve, selection_keys=instances,
            default_pi_synthesizer=baselines.synthesize_warm_default_pi, strict_xcheck=True)
        log(f"[run_m3_warm] rescore: {final!r}")

    # ------------------------------------------------------------------ #
    # 10) Persist the §13 audit summary + print the selected schedule(s).
    # ------------------------------------------------------------------ #
    summary = _summarize(out_dir, seed, generations, pop_size, n_offspring, instances,
                         evaluated, result, sel, neg, final, winner_id, admitted,
                         warm_baselines, genome_dict, warm_live_only)
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    _print_report(log, summary)
    return summary


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def _summarize(out_dir, seed, generations, pop_size, n_offspring, instances,
               evaluated, result, sel, neg, final, winner_id, admitted, warm_baselines,
               genome_dict, warm_live_only):
    candidates = {}
    for cid, ind in evaluated.items():
        rec = sel.per_candidate.get(cid, {})
        candidates[cid] = {
            "genome": genome_dict(ind.candidate.genome),
            "op": ind.candidate.meta.get("op"),
            "parent": ind.candidate.meta.get("parent"),
            "gated_out": ind.gated_out,
            "gate_reasons": (ind.gate.reasons if ind.gate is not None else None),
            "fitness": (None if ind.gated_out else _fitness_dict(ind.fitness)),
            "cross_val": rec.get("cross_val"),
            "p_value": rec.get("p_value"),
            "p_adjusted": rec.get("p_adjusted"),
            "holm_reject": rec.get("reject"),
        }
    warm_default_pi = {f"{k[0]}_{k[1]}": warm_baselines[k]["default_PI"]
                       for k in instances if warm_baselines.get(k, {}).get("default_PI") is not None}
    return {
        "bead": "constraint-oriented-biased-quantum-search-8an.10",
        "protocol": "WARM (general_greedy; exploratory — cold L_I/B_I anchors, warm default_PI)",
        "config": {"seed": seed, "generations": generations, "pop_size": pop_size,
                   "n_offspring": n_offspring, "n_instances": len(instances),
                   "sizes": list(SELECTION_SIZES),
                   "genome": ("warm_live" if warm_live_only else "full"),
                   "folds": {k: sorted(v) for k, v in m3_select.FOLDS.items()},
                   "alpha": m3_select.ALPHA},
        "n_evaluated": len(evaluated),
        "n_admitted": len(admitted),
        "n_gated_out": sum(1 for i in evaluated.values() if i.gated_out),
        "warm_default_PI": warm_default_pi,
        "best_by_fitness": {
            "id": next((cid for cid, ind in evaluated.items() if ind is result.best), None),
            "gated_out": result.best.gated_out,
            "genome": genome_dict(result.best.candidate.genome),
            "fitness": _fitness_dict(result.best.fitness)},
        "survivors": sel.survivors,
        "winner_id": winner_id,
        "negative_control_passed": not neg.any_significant,
        "rescore": (None if final is None else {
            "passed": final.passed, "p_value": final.p_value,
            "holdout": [list(k) for k in final.holdout_instances],
            "new_seeds": list(final.new_seeds),
            "overall_pass": final.verdict["overall_pass"]}),
        "candidates": candidates,
    }


def _print_report(log, s):
    log("")
    log("=" * 72)
    log("WARM M3 RUN SUMMARY (bd 8an.10)")
    log("=" * 72)
    c = s["config"]
    log(f"protocol: {s['protocol']}")
    log(f"config: seed={c['seed']} gens={c['generations']} pop={c['pop_size']} "
        f"n_offspring={c['n_offspring']} | {c['n_instances']} instances over {c['sizes']}")
    log(f"genome scope: {c['genome']} ({'WARM_SPEC live-only' if c['genome']=='warm_live' else 'FULL 5-gene — opt_sat/switch LIVE at n<=90'})")
    log(f"evaluated={s['n_evaluated']} admitted={s['n_admitted']} gated_out={s['n_gated_out']}")
    b = s["best_by_fitness"]
    log(f"best-by-fitness: {b['id']} genome={b['genome']} fitness={b['fitness']}")
    log(f"negative control passed: {s['negative_control_passed']}")
    log("")
    if s["survivors"]:
        log(f"SELECTED WARM SCHEDULE(S) — CV-pass AND Holm-reject (FWER<= {c['alpha']}):")
        for cid in s["survivors"]:
            rec = s["candidates"][cid]
            tag = " <== WINNER" if cid == s["winner_id"] else ""
            log(f"  {cid}: genome={rec['genome']}  p={rec['p_value']:.4g} "
                f"p_adj={rec['p_adjusted']:.4g}{tag}")
        if s["rescore"] is not None:
            r = s["rescore"]
            log("")
            log(f"§13 WARM rescore on untouched holdout {r['holdout']} seeds {r['new_seeds']}: "
                f"passed={r['passed']} p={r['p_value']:.4g}")
    else:
        log("RESULT: NO warm candidate beat the warm default under all §6/§8 gates "
            "(Holm-controlled). The warm default is unbeaten on the anchored n<=90 strata.")
    log("=" * 72)


def main(argv=None):
    p = argparse.ArgumentParser(description="WARM exploratory M3 driver (bd 8an.10).")
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m3_run_warm_8an10"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seed", type=int, default=20260618)
    p.add_argument("--generations", type=int, default=6)
    p.add_argument("--pop-size", type=int, default=8)
    p.add_argument("--n-offspring", type=int, default=8)
    p.add_argument("--n-init-random", type=int, default=5)
    p.add_argument("--num-workers", type=int, default=None)
    p.add_argument("--max-per-size", type=int, default=None,
                   help="fast exploratory pass: keep only the first N (lowest-index) instances "
                        "per size (all folds still populated). Default: all (~88 instances).")
    p.add_argument("--no-rescore", dest="do_rescore", action="store_false",
                   help="skip the held-out warm rescore (the exploratory selection still runs).")
    p.add_argument("--warm-live-only", action="store_true",
                   help="search only the 3-gene warm-live space {r_opt, theta} (WARM_SPEC). "
                        "Default is the FULL 5-gene genome — at n<=90 the warm greedy is often "
                        "INFEASIBLE so opt_sat_radius/switch are LIVE and dominant (bd 8an.10).")
    p.set_defaults(do_rescore=True)
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required — the real Eq.29 "
                         "instances are needed to solve.")
    if args.num_workers is not None:
        print(f"[run_m3_warm] WARNING: --num-workers={args.num_workers} overrides the solver "
              f"default; both arms still share it, so the warm A/B stays matched.")
    run(out_dir=args.out_dir, bench_root=args.bench_root, seed=args.seed,
        generations=args.generations, pop_size=args.pop_size, n_offspring=args.n_offspring,
        n_init_random=args.n_init_random, num_workers=args.num_workers,
        do_rescore=args.do_rescore, max_per_size=args.max_per_size,
        warm_live_only=args.warm_live_only)


if __name__ == "__main__":
    main()
