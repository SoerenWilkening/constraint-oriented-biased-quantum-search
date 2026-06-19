#!/usr/bin/env python3
"""benchmarks/run_m3.py — the REAL M3 agent-loop driver (bd 884, NORTHSTAR §10/§13).

No CLI existed for the M3 population search; this is that driver. It copies the
:func:`benchmarks.m3.evolve` wiring from ``tests/test_m3.py`` (which uses a FAKE
evaluator) but swaps in the REAL :func:`benchmarks.m3.evaluate_candidate` — gate →
equal-``T(n)`` solve → ``score_verdict`` → fitness — over the anchored ``n≤90``
strata, then runs the §13 selection discipline (cross-validation + Holm FWER +
negative control + final rescore).

M3 is UN-GATED at this range: ``default_PI`` + the §8.3 floor are frozen for
``n=10..90`` (commit 355676d). The ``stopping_time`` wall cap (9211b21) is DORMANT
at ``n≤90`` (solves are ms-to-sec ≪ any cap), so the existing baseline is VALID —
this driver does NOT re-freeze anchors. It DOES solve the default ONCE up front to
get the live run-set the floor/strict-xcheck need (landmine #4: never re-solve the
default per candidate).

Landmines honored (CLAUDE.md §5 / NORTHSTAR §10/§13):
  #1 equal-T(n) A/B   — every solve runs at M=-1 (real T(n)); the candidate and the
                        default are priced at the SAME oracle budget (§1.1/§5).
  #2 fail-loud        — score_verdict raises propagate (corrupt input ≠ "lost"); the
                        default-vs-default strict-xcheck capstone is asserted BEFORE
                        any candidate solve (the M1 lesson — it caught two P1 repro
                        bugs the green suite missed).
  #3 §1.4 allow-list  — the genome→factory emits only LEGAL_LEVER_PARAMS by
                        construction; candidate_gate.admit (scale_check=True) is the
                        pre-scoring firewall (rejects scale-drifting levers at n≥100).
  #4 default ONCE     — default_results is solved once and replayed for every
                        candidate AND reused (restricted) as the negative-control
                        reference.
  out_dir isolation   — run_sweep names instance files ``n_index`` only, so a SHARED
                        out_dir would alias candidate B's run-set to candidate A's via
                        resume=True. Each candidate gets its OWN subdir.

Reproducible (bd 8an.4.4): all stochasticity flows through one seeded numpy
Generator; every solve is at the matched seed bank (1..7) with the solver default
worker count (= the freeze recipe). variable_order is HELD OUT (8an.8 cliff).

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.run_m3 [--generations G]
      [--pop-size P] [--n-offspring K] [--n-init-random R] [--seed S]
      [--out-dir DIR] [--bench-root DIR]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks import baselines, m2, m3, m3_proposer, m3_select, metric  # noqa: E402


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: Anchored selection strata (bd 884). 80_0 is dropped (never-feasible — no
#: default_PI) and excluded automatically by the default_PI-present filter.
SELECTION_SIZES = (10, 20, 30, 40, 50, 60, 70, 80, 90)

#: §13 held-out rescore set: faithful (cap=0) frozen anchors OUTSIDE the n≤90
#: selection folds, so genuinely untouched. Used only for the final single rescore.
HOLDOUT_INSTANCES = ((100, 0), (100, 2), (150, 0), (150, 1))

#: §13 NEW seeds for the final rescore — disjoint from the selection bank (1..7),
#: all ≥ 1 (bd cjz). The rescore is the only place new seeds appear.
RESCORE_SEEDS = (8, 9, 10)


def selection_instances(baselines_table, sizes=SELECTION_SIZES):
    """The (n, index) rows with a frozen ``default_PI`` at the selection sizes.

    A missing/None ``default_PI`` (never-feasible 80_0, or an absent B_I row like
    90_3) is excluded — those have no anchor to score against (§6)."""
    keys = [k for k in sorted(baselines_table)
            if k[0] in set(sizes) and baselines_table[k].get("default_PI") is not None]
    if not keys:
        raise ValueError(f"no anchored instances with default_PI at sizes {sizes}")
    return keys


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def run(*, out_dir, bench_root, seed, generations, pop_size, n_offspring,
        n_init_random, num_workers=None, log=print):
    """Solve the default once, run the population search, then the §13 selection."""
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    frozen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "baselines_frozen.csv")
    baselines_table = baselines.load_frozen_baselines(frozen_path)
    # bd 8an.9: the canonical baselines_frozen.csv is now WARM (general_greedy start). This is the
    # COLD M3 driver: it solves cold candidates, which cannot reproduce the warm anchors, so its own
    # default-vs-default strict_xcheck capstone below would breach. Fail loud early with a pointer
    # rather than a cryptic re-score error (§2.1).
    if any(r.get("protocol") == "warm"
           for r in baselines_table.values() if r.get("default_PI") is not None):
        raise SystemExit(
            "[run_m3] baselines_frozen.csv is WARM (bd 8an.9) but this is the COLD M3 driver. Use "
            "benchmarks/run_m3_warm.py (the canonical warm driver). To reproduce the archived cold "
            "M3, restore benchmarks/baselines_frozen_cold.csv over baselines_frozen.csv first.")
    instances = selection_instances(baselines_table)
    seeds = baselines.DEFAULT_SEED_BANK
    log(f"[run_m3] {len(instances)} anchored instances over sizes {SELECTION_SIZES}; "
        f"seed bank {seeds}; rng seed {seed}")

    # --- Config stamp (fail-loud cross-run aliasing guard, CLAUDE.md §2.1). The
    #     candidate ids are POSITIONAL (cand_0, cand_1, …) and the genome behind
    #     each id is fixed by (seed, pop, gens, n_offspring, n_init_random). A
    #     re-run with a DIFFERENT config to the SAME out_dir would, via run_sweep
    #     resume=True, alias a different schedule's run-set onto a reused id. So a
    #     resume MUST match the original config exactly; anything else aborts. ---
    run_cfg = {"seed": int(seed), "generations": int(generations),
               "pop_size": int(pop_size), "n_offspring": int(n_offspring),
               "n_init_random": int(n_init_random), "sizes": list(SELECTION_SIZES)}
    cfg_path = os.path.join(out_dir, "run_config.json")
    cand_root = os.path.join(out_dir, "candidates")
    if os.path.isdir(cand_root) and any(os.scandir(cand_root)):
        if not os.path.exists(cfg_path):
            raise SystemExit(
                f"[run_m3] {cand_root} holds candidate run-sets but no run_config.json "
                f"records their provenance — refusing to resume into an unknown state "
                f"(out_dir aliasing risk). Use a fresh --out-dir.")
        prev_cfg = json.load(open(cfg_path))
        if prev_cfg != run_cfg:
            raise SystemExit(
                f"[run_m3] CONFIG MISMATCH: {out_dir} was built with {prev_cfg} but this "
                f"run asks for {run_cfg}. Resuming would alias a different schedule's "
                f"run-set onto a reused candidate id (landmine #4 / §2.1). Use a fresh "
                f"--out-dir.")
    json.dump(run_cfg, open(cfg_path, "w"), indent=2)

    # ------------------------------------------------------------------ #
    # 1) Default run-set, solved ONCE (landmine #4), persisted + resumable.
    # ------------------------------------------------------------------ #
    default_dir = os.path.join(out_dir, "default")
    t0 = time.time()
    m2.run_sweep("m3_default", None, instances, out_dir=default_dir, seeds=seeds,
                 bench_root=bench_root, num_workers=num_workers, log=lambda *a: None)
    default_results = m2.load_run_set_dir(default_dir)
    log(f"[run_m3] default run-set ready ({len(default_results)} instances, "
        f"{time.time() - t0:.0f}s)")

    # ------------------------------------------------------------------ #
    # 2) CAPSTONE (landmine #2 / M1 lesson): default-vs-default strict-xcheck
    #    MUST be exact before a single candidate is solved. A breach means the
    #    live default drifted from the frozen anchors (stale freeze / core change)
    #    — abort rather than score every candidate against a poisoned reference.
    # ------------------------------------------------------------------ #
    try:
        cap = metric.score_verdict(default_results, default_results, baselines_table,
                                   strict_xcheck=True, require_largest_n=False)
    except ValueError as exc:
        # strict_xcheck RAISES the instant the live default diverges from the frozen
        # default_PI (metric.py); convert that into a curated abort (the M1 lesson).
        raise SystemExit(
            f"[run_m3] CAPSTONE FAILED: default-vs-default strict-xcheck raised — the "
            f"live default drifted from the frozen anchors ({exc}). Refusing to score "
            f"candidates against a poisoned reference (NORTHSTAR §13 / M1 lesson).")
    if not cap["overall_pass"] or (cap.get("default_xcheck_failures") or []):
        raise SystemExit(
            f"[run_m3] CAPSTONE FAILED: default-vs-default overall_pass="
            f"{cap['overall_pass']}, xcheck_failures="
            f"{len(cap.get('default_xcheck_failures') or [])}. Refusing to score "
            f"candidates against a poisoned reference (NORTHSTAR §13 / M1 lesson).")
    log(f"[run_m3] capstone OK: default-vs-default strict-xcheck exact "
        f"({len(cap['default_PI'])} anchored instances).")

    # ------------------------------------------------------------------ #
    # 3) Evaluator wrapper: per-candidate out_dir isolation + DETERMINISTIC §10
    #    gate + genome-stamp + family registry.
    # ------------------------------------------------------------------ #
    from benchmarks import candidate_gate
    genomes_dir = os.path.join(out_dir, "genomes")
    evaluated = {}  # id -> m3.Individual (the full multiple-comparison family)

    def evaluator(candidate, *, out_dir, scale_check=True, gate_scale_ns=(100, 1000),
                  **kw):
        cid = candidate.meta["id"]
        _guard_candidate_genome(genomes_dir, cid, candidate.genome)
        cand_dir = os.path.join(out_dir, cid)
        # §10 gate, DETERMINISTIC: candidate_gate.admit defaults to seeds=(0,) ==
        # entropy-seeded synthetic solves (bd cjz), which makes the admit/reject
        # decision non-reproducible (bd 8an.4.4). Pin a non-entropy seed; then solve
        # with scale_check=False so evaluate_candidate does NOT re-run the
        # (non-deterministic) internal scale gate. The synthetic instance is
        # deterministic given (n,index), so seeds=(1,) fully fixes the gate.
        gate = candidate_gate.admit(candidate.factory, scale_ns=gate_scale_ns,
                                    scale_check=scale_check, seeds=(1,))
        if not gate.ok:
            ind = m3.Individual(candidate, m3.Fitness.gated_out(), verdict=None,
                                gate=gate, gated_out=True)
        else:
            ind = m3.evaluate_candidate(candidate, out_dir=cand_dir,
                                        scale_check=False, **kw)
            ind.gate = gate  # attach the full deterministic gate for the §13 audit
        evaluated[cid] = ind
        tag = ("GATED " + "; ".join(gate.reasons)) if ind.gated_out else repr(ind.fitness)
        log(f"[run_m3]   eval {cid} genome={_fmt_genome(candidate.genome)} -> {tag}")
        return ind

    eval_kwargs = dict(
        default_results=default_results, baselines=baselines_table,
        instances=instances, seeds=seeds, out_dir=cand_root, bench_root=bench_root,
        num_workers=num_workers, opt_sample_cap=0, scale_check=True)

    # ------------------------------------------------------------------ #
    # 4) Init population = default genome + R random genomes (bd 884 step 3).
    # ------------------------------------------------------------------ #
    init_pop = [m3.Candidate(
        factory=m3_proposer.genome_to_factory(m3_proposer.BASELINE_GENOME),
        genome=tuple(float(x) for x in m3_proposer.BASELINE_GENOME),
        meta={"id": "init_default", "op": "seed"})]
    for i in range(n_init_random):
        g = m3_proposer.random_genome(rng)
        init_pop.append(m3.Candidate(
            factory=m3_proposer.genome_to_factory(g),
            genome=tuple(float(x) for x in g),
            meta={"id": f"init_rand_{i}", "op": "seed"}))

    # ------------------------------------------------------------------ #
    # 5) Run the population search (NORTHSTAR §10).
    # ------------------------------------------------------------------ #
    proposer = m3_proposer.ParametricProposer(
        n_offspring=n_offspring, sigma=m3_proposer.GENE_SIGMA,
        crossover_rate=0.3, id_prefix="cand")
    log(f"[run_m3] evolve: pop_size={pop_size} generations={generations} "
        f"n_offspring={n_offspring} (init {len(init_pop)})")
    t0 = time.time()
    result = m3.evolve(proposer, rng=rng, generations=generations, pop_size=pop_size,
                       init_population=init_pop, evaluator=evaluator,
                       eval_kwargs=eval_kwargs, min_genome_distance=0.0, log=log)
    log(f"[run_m3] evolve done ({time.time() - t0:.0f}s, {len(evaluated)} candidates "
        f"evaluated). best {result.best.fitness!r} "
        f"genome={_fmt_genome(result.best.candidate.genome)}")

    # ------------------------------------------------------------------ #
    # 6) §13 selection over the FULL admitted family (CV + Holm FWER).
    # ------------------------------------------------------------------ #
    admitted = {cid: ind for cid, ind in evaluated.items() if not ind.gated_out}
    candidate_results_by_id = {
        cid: m2.load_run_set_dir(os.path.join(cand_root, cid)) for cid in admitted}
    log(f"[run_m3] selection over {len(candidate_results_by_id)} admitted candidates "
        f"(of {len(evaluated)} evaluated).")
    sel = m3_select.select_significant(
        candidate_results_by_id, default_results, baselines_table,
        folds=m3_select.FOLDS, alpha=m3_select.ALPHA, strict_xcheck=True)
    log(f"[run_m3] selection: {len(sel.survivors)} survivor(s) "
        f"(CV-pass AND Holm-reject): {sel.survivors}")

    # ------------------------------------------------------------------ #
    # 7) Negative control (§13 type-I check): baseline-equivalent candidates
    #    solved at the matched seed bank must yield NO survivor.
    # ------------------------------------------------------------------ #
    nc_root = os.path.join(out_dir, "negcontrol")
    _nc = [0]

    def nc_candidate_solve(factory, inst, sds):
        i = _nc[0]
        _nc[0] += 1
        d = os.path.join(nc_root, f"nc_{i}")
        m2.run_sweep(f"negctl_{i}", factory, list(inst), out_dir=d, seeds=sds,
                     bench_root=bench_root, num_workers=num_workers, log=lambda *a: None)
        return m2.load_run_set_dir(d)

    neg_factories = {f"nc_{i}": m3_proposer.baseline_equivalent_factory()
                     for i in range(3)}
    neg = m3_select.negative_control(
        neg_factories, default_results, baselines_table,
        candidate_solve=nc_candidate_solve, candidate_instances=instances,
        candidate_seeds=seeds, folds=m3_select.FOLDS, alpha=m3_select.ALPHA)
    if neg.any_significant:
        raise SystemExit(
            f"[run_m3] NEGATIVE CONTROL FAILED: a baseline-equivalent candidate was "
            f"flagged significant ({neg.selection.survivors}) — the multiplicity "
            f"machine is leaking type-I error (NORTHSTAR §13). Refusing to report a "
            f"selection from a miscalibrated pipeline.")
    log(f"[run_m3] negative control PASSED (no baseline-equivalent survivor).")

    # ------------------------------------------------------------------ #
    # 8) §13 final rescore (only if a winner emerged) on the untouched n=100/150
    #    holdout with NEW seeds 8..10.
    # ------------------------------------------------------------------ #
    final = None
    winner_id = None
    if sel.survivors:
        winner_id = max(sel.survivors, key=lambda cid: admitted[cid].fitness)
        winner_factory = admitted[winner_id].candidate.factory
        log(f"[run_m3] winner {winner_id} "
            f"genome={_fmt_genome(admitted[winner_id].candidate.genome)} — rescoring "
            f"on holdout {list(HOLDOUT_INSTANCES)} with new seeds {RESCORE_SEEDS}.")

        def default_solve(inst, sds):
            d = os.path.join(out_dir, "rescore_default")
            m2.run_sweep("rescore_default", None, list(inst), out_dir=d, seeds=sds,
                         bench_root=bench_root, num_workers=num_workers, log=lambda *a: None)
            return m2.load_run_set_dir(d)

        def candidate_solve(factory, inst, sds):
            d = os.path.join(out_dir, "rescore_winner")
            m2.run_sweep("rescore_winner", factory, list(inst), out_dir=d, seeds=sds,
                         bench_root=bench_root, num_workers=num_workers, log=lambda *a: None)
            return m2.load_run_set_dir(d)

        final = m3_select.rescore_once(
            winner_factory, baselines_table, holdout_instances=list(HOLDOUT_INSTANCES),
            new_seeds=RESCORE_SEEDS, default_solve=default_solve,
            candidate_solve=candidate_solve, selection_keys=instances)
        log(f"[run_m3] rescore: {final!r}")

    # ------------------------------------------------------------------ #
    # 9) Persist the §13 audit summary + print the selected schedule(s).
    # ------------------------------------------------------------------ #
    summary = _summarize(out_dir, seed, generations, pop_size, n_offspring,
                         instances, evaluated, result, sel, neg, final, winner_id,
                         admitted)
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    _print_report(log, summary)
    return summary


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #

def _guard_candidate_genome(genomes_dir, cid, genome):
    """Stamp each candidate id's genome in a SIBLING dir (never inside the run-set
    subdir — load_run_set_dir would parse a stray .json as an instance file). On a
    resumed run, ASSERT the on-disk genome matches before run_sweep's resume=True
    reuses the cached run-set — defends against any residual out_dir aliasing even
    if the config stamp is bypassed (CLAUDE.md §2.1 fail-loud / landmine #4)."""
    os.makedirs(genomes_dir, exist_ok=True)
    stamp = os.path.join(genomes_dir, f"{cid}.json")
    g = [round(float(x), 12) for x in (genome or ())]
    if os.path.exists(stamp):
        prev = [round(float(x), 12) for x in json.load(open(stamp))]
        if prev != g:
            raise SystemExit(
                f"[run_m3] OUT_DIR ALIASING: candidate id {cid!r} previously held "
                f"genome {prev} but now decodes to {g}. Resuming would score the wrong "
                f"schedule's run-set (landmine #4 / §2.1). Use a fresh --out-dir.")
    else:
        json.dump(g, open(stamp, "w"))


def _fmt_genome(genome):
    if genome is None:
        return "None"
    names = m3_proposer.GENES
    g = [float(x) for x in genome]
    feat = m3_proposer.FEATURES[int(min(len(m3_proposer.FEATURES) - 1, max(0, g[4])))][0]
    return (f"(r_opt_sat={g[0]:.2f}, r_opt={g[1]:.2f}, alpha={g[2]:.3f}, "
            f"theta_amp={g[3]:.2f}, feat={feat})")


def _genome_dict(genome):
    if genome is None:
        return None
    g = [float(x) for x in genome]
    feat = m3_proposer.FEATURES[int(min(len(m3_proposer.FEATURES) - 1, max(0, g[4])))][0]
    return {"r_opt_sat": g[0], "r_opt": g[1], "alpha_switch": g[2],
            "theta_amp": g[3], "theta_feature": feat}


def _fitness_dict(fit):
    return {"passes_gate": fit.passes_gate,
            "lost_feasibility_total": fit.lost_feasibility_total,
            "pi_rank": fit.pi_rank, "pi_median": fit.pi_median,
            "floor_fraction": fit.floor_fraction}


def _summarize(out_dir, seed, generations, pop_size, n_offspring, instances,
               evaluated, result, sel, neg, final, winner_id, admitted):
    candidates = {}
    for cid, ind in evaluated.items():
        rec = sel.per_candidate.get(cid, {})
        candidates[cid] = {
            "genome": _genome_dict(ind.candidate.genome),
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
    return {
        "bead": "constraint-oriented-biased-quantum-search-884",
        "config": {"seed": seed, "generations": generations, "pop_size": pop_size,
                   "n_offspring": n_offspring, "n_instances": len(instances),
                   "sizes": list(SELECTION_SIZES), "folds": {k: sorted(v) for k, v in
                                                             m3_select.FOLDS.items()},
                   "alpha": m3_select.ALPHA},
        "n_evaluated": len(evaluated),
        "n_admitted": len(admitted),
        "n_gated_out": sum(1 for i in evaluated.values() if i.gated_out),
        "best_by_fitness": {
            "id": next((cid for cid, ind in evaluated.items()
                        if ind is result.best), None),
            "gated_out": result.best.gated_out,
            "gate_reasons": (result.best.gate.reasons
                             if result.best.gate is not None else None),
            "genome": _genome_dict(result.best.candidate.genome),
            "fitness": _fitness_dict(result.best.fitness)},
        "survivors": sel.survivors,
        "winner_id": winner_id,
        "negative_control_passed": not neg.any_significant,
        "negative_control_note": (
            "Baseline-equivalent factories ({}) solved at the SAME matched seed bank "
            "as the frozen default produce byte-identical run-sets, hence exact-zero "
            "paired deltas -> candidate_pvalue short-circuits to p=1.0 (all_zero) and "
            "Holm rejects nothing. This is the §13 control the matched-seed metric "
            "admits (a different-seed null would violate score_verdict's matched-seed "
            "invariant); it verifies the pipeline never fabricates a winner from a "
            "null schedule, but does NOT stress the FWER machinery with noise."),
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
    log("M3 RUN SUMMARY (bd 884)")
    log("=" * 72)
    c = s["config"]
    log(f"config: seed={c['seed']} gens={c['generations']} pop={c['pop_size']} "
        f"n_offspring={c['n_offspring']} | {c['n_instances']} instances over {c['sizes']}")
    log(f"evaluated={s['n_evaluated']} admitted={s['n_admitted']} "
        f"gated_out={s['n_gated_out']}")
    b = s["best_by_fitness"]
    gflag = "  [GATED-OUT: no admitted candidate!]" if b.get("gated_out") else ""
    log(f"best-by-fitness: {b['id']} genome={b['genome']} fitness={b['fitness']}{gflag}")
    log(f"negative control passed: {s['negative_control_passed']} "
        f"(exact-zero baseline-equiv control — see summary.json note)")
    log("")
    if s["survivors"]:
        log(f"SELECTED SCHEDULE(S) — CV-pass AND Holm-reject (FWER<= {c['alpha']}):")
        for cid in s["survivors"]:
            rec = s["candidates"][cid]
            tag = " <== WINNER" if cid == s["winner_id"] else ""
            log(f"  {cid}: genome={rec['genome']}  p={rec['p_value']:.4g} "
                f"p_adj={rec['p_adjusted']:.4g}{tag}")
        if s["rescore"] is not None:
            r = s["rescore"]
            log("")
            log(f"§13 rescore on untouched holdout {r['holdout']} seeds {r['new_seeds']}: "
                f"passed={r['passed']} p={r['p_value']:.4g}")
    else:
        log("RESULT: NO candidate beat the default under all §6/§8 gates "
            "(Holm-controlled). This is a clean 'no winner' — the default is "
            "unbeaten on the anchored n<=90 strata at the searched budget.")
    log("=" * 72)


def main(argv=None):
    p = argparse.ArgumentParser(description="M3 agent-loop driver (bd 884).")
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "m3_run_884"))
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seed", type=int, default=20260615)
    p.add_argument("--generations", type=int, default=6)
    p.add_argument("--pop-size", type=int, default=8)
    p.add_argument("--n-offspring", type=int, default=8)
    p.add_argument("--n-init-random", type=int, default=5)
    p.add_argument("--num-workers", type=int, default=None)
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required — the "
                         "real Eq.29 instances are needed to solve.")
    if args.num_workers is not None:
        print(f"[run_m3] WARNING: --num-workers={args.num_workers} overrides the solver "
              f"default. The frozen anchors were frozen at the solver-default worker "
              f"count, so a different count will change best-of-portfolio and almost "
              f"certainly FAIL the capstone strict-xcheck. Proceeding as requested.")
    run(out_dir=args.out_dir, bench_root=args.bench_root, seed=args.seed,
        generations=args.generations, pop_size=args.pop_size,
        n_offspring=args.n_offspring, n_init_random=args.n_init_random,
        num_workers=args.num_workers)


if __name__ == "__main__":
    main()
