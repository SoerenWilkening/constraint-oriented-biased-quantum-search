"""Tests for the WARM re-scope of M3 (bd 8an.10).

Stub-based — no C extension, no real solves (mirrors tests/test_m3_proposer.py and
tests/test_m3_select.py). Covers:

* the warm proposer (``m3_proposer.WARM_SPEC`` / ``warm_genome_to_factory``) — the
  re-scope to the warm-LIVE lever space (opt radius + θ ONLY; the inert
  ``opt_sat_branching_radius`` / ``opt_switch_oracles`` are never emitted);
* the warm anchor synthesizer (``baselines.synthesize_warm_default_pi``) and its
  consistency property (the warm default re-scores to exactly the synthesized
  ``default_PI`` → ``score_verdict`` strict_xcheck passes — the warm capstone);
* the ``rescore_once`` ``default_pi_synthesizer`` hook (cold path unchanged).

The faithfulness firewall (§1.4 feature allow-list, §1.6 legal-lever-only output,
§1.1 no inert-dim confound) is the central thing under test.
"""
import math
import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import baselines, m3, m3_proposer as P, metric, m3_select as S  # noqa: E402
from benchmarks.candidate_gate import LEGAL_LEVER_PARAMS, _FAITHFULNESS_BREACH_PARAMS  # noqa: E402
from benchmarks.synthetic_eq29 import make_matrices  # noqa: E402
from benchmarks.m3 import Candidate, Fitness  # noqa: E402


# --------------------------------------------------------------------------- #
# Warm genome layout — a strict subset of the cold genome (the inert dims dropped).
# --------------------------------------------------------------------------- #

def test_warm_genes_are_the_live_subset():
    assert P.WARM_GENES == ("r_opt", "theta_amp", "theta_feature")
    # the two warm-INERT cold genes (cand_16's dominant cold levers) are NOT searched.
    assert "r_opt_sat" not in P.WARM_GENES
    assert "alpha_switch" not in P.WARM_GENES
    # every warm gene is a real cold gene with the SAME bounds (no silent re-bounding).
    for g in P.WARM_GENES:
        assert g in P.GENES
        assert P.WARM_GENE_BOUNDS[g] == P.GENE_BOUNDS[g]
    assert len(P.WARM_BASELINE_GENOME) == len(P.WARM_GENES)


# --------------------------------------------------------------------------- #
# warm_genome_to_factory — emits ONLY the warm-live opt-phase levers.
# --------------------------------------------------------------------------- #

def test_warm_factory_omits_inert_levers_and_emits_only_legal_ones():
    # The re-scope (bd 8an.10 / §1.1): a warm candidate differs from the warm default
    # ONLY in the live opt levers — never opt_sat_branching_radius / opt_switch_oracles.
    rng = np.random.default_rng(0)
    seen = set()
    for _ in range(300):
        g = P.random_genome(rng, genes=P.WARM_GENES, bounds=P.WARM_GENE_BOUNDS)
        factory = P.warm_genome_to_factory(g)
        for n in (10, 40, 90, 100, 1000):
            c1, c2, c3 = make_matrices(n, 0)
            params = factory(n, c1, c2, c3)
            seen |= set(params)
            assert set(params) <= set(LEGAL_LEVER_PARAMS)
            assert set(params).isdisjoint(_FAITHFULNESS_BREACH_PARAMS)
            assert "opt_sat_branching_radius" not in params   # INERT under warm — omitted
            assert "opt_switch_oracles" not in params         # INERT under warm — omitted
            assert "opt_variable_priorities" not in params    # order lever held out
    # opt radius is always emitted; weights only when θ active; nothing else ever.
    assert "opt_branching_radius" in seen
    assert seen <= {"opt_branching_radius", "opt_branching_weights"}


def test_warm_theta_off_emits_only_radius():
    c1, c2, c3 = make_matrices(40, 0)
    # θ amp 0 -> radius only
    f0 = P.warm_genome_to_factory([4.0, 0.0, 1.0])
    assert set(f0(40, c1, c2, c3)) == {"opt_branching_radius"}
    # feature 'none' (index 0) -> radius only even with amp>0
    f1 = P.warm_genome_to_factory([4.0, 0.5, 0.0])
    assert set(f1(40, c1, c2, c3)) == {"opt_branching_radius"}


def test_warm_theta_bounded_and_opt_phase_only():
    f = P.warm_genome_to_factory([4.0, 0.5, 1.0])  # amp=0.5, feature=pii_z
    c1, c2, c3 = make_matrices(50, 0)
    params = f(50, c1, c2, c3)
    w = params["opt_branching_weights"]
    assert len(w) == 50
    assert float(np.max(np.abs(w))) <= 0.5 + 1e-12
    assert not any(k.endswith("branching_weights") and k != "opt_branching_weights"
                   for k in params)


def test_warm_radius_matches_cold_radius_lever():
    # the warm opt radius is the SAME lever value the cold genome would emit for the
    # same r_opt — the re-scope drops dims, it does not change the radius semantics.
    c1, c2, c3 = make_matrices(60, 0)
    warm = P.warm_genome_to_factory([5.3, 0.0, 0.0])(60, c1, c2, c3)
    cold = P.genome_to_factory([4.0, 5.3, 0.1, 0.0, 0.0])(60, c1, c2, c3)
    assert warm["opt_branching_radius"] == cold["opt_branching_radius"] == 5.3


def test_warm_factory_fails_loud_when_radius_not_below_n():
    f = P.warm_genome_to_factory([8.0, 0.0, 0.0])
    c1, c2, c3 = make_matrices(8, 0)  # n=8 < r=8
    with pytest.raises(ValueError):
        f(8, c1, c2, c3)


# --------------------------------------------------------------------------- #
# Warm genome ops (clamp/random/mutate/crossover) over the 3-gene layout.
# --------------------------------------------------------------------------- #

def test_warm_clamp_random_mutate_crossover_stay_in_bounds_and_length():
    rng = np.random.default_rng(2)
    kw = dict(genes=P.WARM_GENES, bounds=P.WARM_GENE_BOUNDS)
    g = P.random_genome(rng, **kw)
    assert g.shape == (3,)
    for _ in range(200):
        g = P.mutate(g, rng, sigma=2.0, **kw)  # big sigma to push against bounds
        assert g.shape == (3,)
        for i, name in enumerate(P.WARM_GENES):
            lo, hi = P.WARM_GENE_BOUNDS[name]
            assert lo <= g[i] <= hi
    child = P.crossover(P.random_genome(rng, **kw), P.random_genome(rng, **kw), rng, **kw)
    assert child.shape == (3,)


def test_warm_clamp_rejects_wrong_length():
    with pytest.raises(ValueError):
        P.clamp_genome([1.0, 2.0], genes=P.WARM_GENES, bounds=P.WARM_GENE_BOUNDS)
    with pytest.raises(ValueError):  # a 5-gene cold vector is wrong for the warm spec
        P.clamp_genome([4.0, 4.0, 0.1, 0.0, 0.0], genes=P.WARM_GENES,
                       bounds=P.WARM_GENE_BOUNDS)


# --------------------------------------------------------------------------- #
# WARM_SPEC behind the ParametricProposer / evolve seam.
# --------------------------------------------------------------------------- #

def test_warm_spec_proposer_emits_three_gene_warm_candidates():
    prop = P.ParametricProposer(n_offspring=6, spec=P.WARM_SPEC)
    seed_pop = [m3.Individual(
        candidate=Candidate(P.warm_genome_to_factory(P.WARM_BASELINE_GENOME),
                            genome=tuple(P.WARM_BASELINE_GENOME)),
        fitness=Fitness(True, 0, 0.0, -0.3, 1.0))]
    offspring = prop(seed_pop, np.random.default_rng(0))
    assert len(offspring) == 6
    assert len({c.meta["id"] for c in offspring}) == 6
    c1, c2, c3 = make_matrices(40, 0)
    for c in offspring:
        assert len(c.genome) == 3
        params = c.factory(40, c1, c2, c3)
        assert "opt_sat_branching_radius" not in params
        assert "opt_switch_oracles" not in params
        assert "opt_branching_radius" in params


def test_warm_spec_proposer_is_deterministic_under_fixed_rng():
    def run():
        pop = [Candidate(P.warm_genome_to_factory(g), genome=tuple(g), meta={"id": f"s{i}"})
               for i, g in enumerate([P.WARM_BASELINE_GENOME, np.array([6.0, 0.2, 1.0]),
                                      np.array([3.0, 0.4, 2.0])])]
        seeded = [m3.Individual(c, Fitness(True, 0, -float(np.linalg.norm(c.genome)), -0.3, 1.0))
                  for c in pop]
        prop = P.ParametricProposer(n_offspring=5, spec=P.WARM_SPEC)
        return [tuple(round(x, 9) for x in c.genome)
                for c in prop(seeded, np.random.default_rng(42))]
    assert run() == run()


def test_cold_proposer_default_spec_unchanged():
    # regression guard: the default ParametricProposer is STILL the cold 5-gene path.
    prop = P.ParametricProposer(n_offspring=3)
    assert prop.spec is P.COLD_SPEC
    seed_pop = [m3.Individual(
        candidate=Candidate(P.genome_to_factory(P.BASELINE_GENOME),
                            genome=tuple(P.BASELINE_GENOME)),
        fitness=Fitness(True, 0, 0.0, -0.3, 1.0))]
    for c in prop(seed_pop, np.random.default_rng(0)):
        assert len(c.genome) == 5


# --------------------------------------------------------------------------- #
# warm_repair_history — the warm "feasible from oracle 0" trajectory repair.
# --------------------------------------------------------------------------- #

def test_warm_repair_empty_history_with_feasible_final():
    # greedy lands optimal, no worker improves -> empty history. Repair to the best
    # feasible final held at oracle 0 (else compute_primal_integral reads it as +inf).
    r = types.SimpleNamespace(history=[], seed=1,
                              final_incumbents=[(990.0, True), (980.0, True), (0.0, False)])
    h = baselines.warm_repair_history(r)
    assert h == [(990.0, 0)] and r.history == [(990.0, 0)]
    # and it now scores as feasible (finite PI), not +inf.
    pi = metric.compute_primal_integral(r.history, _B_I, _L_I, metric.oracle_budget(10))
    assert math.isfinite(pi)


def test_warm_repair_does_not_backfill_nonempty_history():
    # bd 8an.10 review: a non-empty warm history is LEFT VERBATIM (no oracle-0 backdate).
    # Backdating over-credited [0,first_stamp) with the first-improvement value and was wrong
    # when the greedy start was infeasible (then [0,first_stamp) is genuinely pre-feasible).
    r = types.SimpleNamespace(history=[(900.0, 5), (950.0, 40)], seed=1,
                              final_incumbents=[(950.0, True)])
    baselines.warm_repair_history(r)
    assert r.history == [(900.0, 5), (950.0, 40)]   # unchanged — cold γ=1 plateau kept
    metric.compute_primal_integral(r.history, _B_I, _L_I, metric.oracle_budget(10))


def test_warm_repair_preserves_infeasible_greedy_pre_feasible_plateau():
    # bd 8an.10 review (CONFIRMED high finding): the warm greedy start is NOT always feasible
    # (initial_state_preparation can leave an infeasible state). On such a run the solver
    # reaches feasibility only at oracle k>0, history[0] is the GENUINE first-feasible incumbent
    # at k, and [0,k) is a legitimate pre-feasible γ=1 plateau (identical to a cold run). The
    # old backfill backdated history[0] to oracle 0 and ERASED that plateau (verified on 60_0:
    # [(897,4),...] -> wrongly [(897,0),(897,4),...]). The fix must leave it verbatim.
    r = types.SimpleNamespace(history=[(897.0, 4), (902.0, 6)], seed=1,
                              final_incumbents=[(902.0, True)])
    baselines.warm_repair_history(r)
    assert r.history == [(897.0, 4), (902.0, 6)]   # γ=1 plateau on [0,4) preserved
    assert r.history[0][1] == 4                     # NOT backdated to oracle 0


def test_warm_repair_leaves_genuinely_infeasible_empty():
    # empty history AND no feasible final = genuinely never feasible -> stays +inf.
    r = types.SimpleNamespace(history=[], seed=1, final_incumbents=[(0.0, False)])
    assert baselines.warm_repair_history(r) == []
    assert metric.compute_primal_integral(r.history, _B_I, _L_I, 1200) == float("inf")


def test_warm_repair_noop_when_history_already_starts_at_zero():
    r = types.SimpleNamespace(history=[(900.0, 0), (950.0, 5)], seed=1,
                              final_incumbents=[(950.0, True)])
    baselines.warm_repair_history(r)
    assert r.history == [(900.0, 0), (950.0, 5)]  # unchanged


# --------------------------------------------------------------------------- #
# 8an.9 FAITHFUL warm history: the TRUE greedy value at oracle 0. The greedy
# value+feasibility are captured between general_greedy() and solve() (returned by
# Model.general_greedy) and passed in explicitly — superseding the EXPLORATORY
# empty-history-only repair (the "deferred to 8an.9 FINAL path" in the docstring).
# --------------------------------------------------------------------------- #

def test_warm_repair_seeds_feasible_greedy_value_at_oracle_zero():
    # A FEASIBLE greedy start is the true best-of-P at oracle 0 (all workers copy the SAME
    # deterministic greedy state). Prepend (greedy_value, 0) ahead of the first logged
    # improvement — which is strictly better than the greedy value, so the curve stays monotone.
    r = types.SimpleNamespace(history=[(900.0, 5), (950.0, 40)], seed=1,
                              final_incumbents=[(950.0, True)])
    h = baselines.warm_repair_history(r, greedy_value=820.0, greedy_feasible=True)
    assert h == [(820.0, 0), (900.0, 5), (950.0, 40)]
    assert r.history == [(820.0, 0), (900.0, 5), (950.0, 40)]


def test_warm_repair_empty_history_uses_feasible_greedy_value():
    # empty history + feasible greedy -> anchor the greedy value itself at oracle 0
    # (== max(feasible finals) here, but read from the captured greedy value, not the finals).
    r = types.SimpleNamespace(history=[], seed=1,
                              final_incumbents=[(990.0, True), (980.0, True)])
    h = baselines.warm_repair_history(r, greedy_value=990.0, greedy_feasible=True)
    assert h == [(990.0, 0)] and r.history == [(990.0, 0)]


def test_warm_repair_infeasible_greedy_left_verbatim_even_with_value():
    # INFEASIBLE greedy start: [0, first_feasible) is a genuine pre-feasible γ=1 plateau
    # (identical to a cold run) — NEVER seed oracle 0, regardless of any captured value.
    r = types.SimpleNamespace(history=[(897.0, 4), (902.0, 6)], seed=1,
                              final_incumbents=[(902.0, True)])
    h = baselines.warm_repair_history(r, greedy_value=None, greedy_feasible=False)
    assert h == [(897.0, 4), (902.0, 6)]
    assert r.history[0][1] == 4   # not backdated to oracle 0


def test_warm_repair_feasible_greedy_already_at_zero_no_double_seed():
    # history already anchored at oracle 0 -> do NOT prepend a second oracle-0 entry.
    r = types.SimpleNamespace(history=[(820.0, 0), (900.0, 5)], seed=1,
                              final_incumbents=[(900.0, True)])
    h = baselines.warm_repair_history(r, greedy_value=820.0, greedy_feasible=True)
    assert h == [(820.0, 0), (900.0, 5)]


def test_warm_repair_infeasible_greedy_empty_history_stays_infeasible():
    # infeasible greedy + no worker ever feasible -> empty -> +inf (a real feasibility loss).
    r = types.SimpleNamespace(history=[], seed=1, final_incumbents=[(0.0, False)])
    h = baselines.warm_repair_history(r, greedy_value=None, greedy_feasible=False)
    assert h == []
    assert metric.compute_primal_integral(r.history, _B_I, _L_I, 1200) == float("inf")


# --------------------------------------------------------------------------- #
# Warm anchor synthesizer + the warm capstone (end-to-end vs the REAL metric).
# --------------------------------------------------------------------------- #

_B_I, _L_I = 1000.0, 100.0
_SIZES = (10, 20, 30, 40, 50, 60, 70, 80, 90)
_IDXS = (0, 1)
_SEEDS = (1, 2, 3)
#: warm default outcome per instance (near-frontier; distinct so the spread is positive).
_WVALS = {(n, i): (900.0 if i == 0 else 850.0) for n in _SIZES for i in _IDXS}


def _res(value, n, seed, feasible=True):
    if not feasible:
        return types.SimpleNamespace(history=[], final_incumbents=[(value, False)], seed=seed)
    return types.SimpleNamespace(history=[(value, 3)],
                                 final_incumbents=[(value, True), (value - 20, True)], seed=seed)


def _warm_default_runset():
    return {(n, i): [_res(_WVALS[(n, i)], n, s) for s in _SEEDS]
            for n in _SIZES for i in _IDXS}


def _frozen_table_cold():
    # mimics the frozen baselines: B_I/L_I present, a COLD default_PI present (a value we
    # must REPLACE), default_cap 0. plus a non-scoreable row (L_I >= B_I) to test the guard.
    table = {}
    for n in _SIZES:
        for i in _IDXS:
            table[(n, i)] = {"B_I": _B_I, "L_I": _L_I, "default_PI": 0.42, "default_cap": 0}
    table[(90, 9)] = {"B_I": 100.0, "L_I": 200.0, "default_PI": None, "default_cap": 0}  # L>=B
    return table


def test_synthesize_warm_replaces_default_pi_keeps_bi_li():
    frozen = _frozen_table_cold()
    warm_runs = _warm_default_runset()
    warm = baselines.synthesize_warm_default_pi(frozen, warm_runs)
    # B_I/L_I untouched; default_PI replaced by the warm median PI (NOT the cold 0.42).
    for key in warm_runs:
        assert warm[key]["B_I"] == _B_I and warm[key]["L_I"] == _L_I
        expect = metric._reduce_seed_bank_pi(warm_runs[key], key[0], _B_I, _L_I)
        assert warm[key]["default_PI"] == pytest.approx(expect)
        assert warm[key]["default_PI"] != 0.42
    # input not mutated
    assert frozen[(10, 0)]["default_PI"] == 0.42


def test_synthesize_warm_nulls_missing_and_non_scoreable():
    frozen = _frozen_table_cold()
    warm_runs = _warm_default_runset()
    del warm_runs[(10, 0)]                       # no warm run for this instance
    warm = baselines.synthesize_warm_default_pi(frozen, warm_runs)
    assert warm[(10, 0)]["default_PI"] is None   # never serve a stale cold value
    assert warm[(90, 9)]["default_PI"] is None   # L_I >= B_I (non-scoreable)


def test_warm_capstone_passes_strict_xcheck():
    # the run_m3_warm capstone: warm default-vs-default against the warm table re-scores
    # EXACTLY to the synthesized warm default_PI -> strict_xcheck passes, overall tie-pass.
    frozen = _frozen_table_cold()
    warm_runs = _warm_default_runset()
    warm = baselines.synthesize_warm_default_pi(frozen, warm_runs)
    verdict = metric.score_verdict(warm_runs, warm_runs, warm,
                                   strict_xcheck=True, require_largest_n=False)
    assert verdict["overall_pass"] is True
    assert verdict["default_xcheck_failures"] == []


def test_warm_candidate_win_scores_against_warm_default():
    # a warm candidate that strictly beats the warm default on every instance is a §6.6
    # win vs the WARM table (proves the comparison is warm-vs-warm, not warm-vs-cold).
    frozen = _frozen_table_cold()
    warm_runs = _warm_default_runset()
    warm = baselines.synthesize_warm_default_pi(frozen, warm_runs)
    cand = {(n, i): [_res(990.0, n, s) for s in _SEEDS] for n in _SIZES for i in _IDXS}
    verdict = metric.score_verdict(cand, warm_runs, warm,
                                   strict_xcheck=True, require_largest_n=False)
    # candidate closer to B_I=1000 than the warm default -> lower (better) PI everywhere.
    assert all(verdict["candidate_PI"][k] < verdict["default_PI"][k] for k in cand)


# --------------------------------------------------------------------------- #
# rescore_once default_pi_synthesizer hook.
# --------------------------------------------------------------------------- #

# 2 instances per holdout size (distinct default values) so default_pi_spreads has a
# positive per-n spread — mirrors the real HOLDOUT (n=100 / n=150 each have 2 instances).
_HOLDOUT = [(100, 0), (100, 2), (150, 0), (150, 1)]
_HDV = {(100, 0): 900.0, (100, 2): 880.0, (150, 0): 910.0, (150, 1): 870.0}


def test_rescore_once_synthesizer_hook_refreshes_holdout_anchor():
    # warm rescore: the holdout default_PI is synthesized from the freshly-solved warm
    # default INSIDE rescore_once, so strict_xcheck=True is satisfiable on warm runs.
    frozen = {k: {"B_I": _B_I, "L_I": _L_I, "default_PI": None, "default_cap": 0}
              for k in _HOLDOUT}
    seen = {"synth": 0}

    def default_solve(inst, seeds):
        return {k: [_res(_HDV[k], k[0], s) for s in seeds] for k in inst}

    def candidate_solve(factory, inst, seeds):
        return {k: [_res(_HDV[k] + 50.0, k[0], s) for s in seeds] for k in inst}

    def synth(table, default_rs):
        seen["synth"] += 1
        return baselines.synthesize_warm_default_pi(table, default_rs)

    final = S.rescore_once(
        lambda n, c1, c2, c3: {"opt_branching_radius": 5.0}, frozen,
        holdout_instances=_HOLDOUT, new_seeds=(8, 9, 10),
        default_solve=default_solve, candidate_solve=candidate_solve,
        selection_keys=[(10, 0), (90, 0)],
        default_pi_synthesizer=synth, strict_xcheck=True)
    assert seen["synth"] == 1
    assert final.passed is True       # candidate beats the warm default toward B_I=1000
    # the holdout default_PI was the SYNTHESIZED warm value, not the (None) frozen one.
    assert all(final.verdict["default_PI"][k] is not None for k in _HOLDOUT)


def test_rescore_once_cold_path_unchanged_without_synthesizer():
    # synthesizer=None (default) keeps the cold behavior: the frozen default_PI is used.
    frozen = {}
    for k in _HOLDOUT:
        dpi = metric.score_instance(_res(_HDV[k], k[0], 8), k[0], _B_I, _L_I)["PI"]
        frozen[k] = {"B_I": _B_I, "L_I": _L_I, "default_PI": dpi, "default_cap": 0}

    def default_solve(inst, seeds):
        return {k: [_res(_HDV[k], k[0], s) for s in seeds] for k in inst}

    def candidate_solve(factory, inst, seeds):
        return {k: [_res(_HDV[k] + 50.0, k[0], s) for s in seeds] for k in inst}

    final = S.rescore_once(
        lambda n, c1, c2, c3: {"opt_branching_radius": 5.0}, frozen,
        holdout_instances=_HOLDOUT, new_seeds=(8, 9, 10),
        default_solve=default_solve, candidate_solve=candidate_solve,
        selection_keys=[(10, 0)])  # no synthesizer, strict_xcheck defaults False
    for k in _HOLDOUT:
        exp = metric.score_instance(_res(_HDV[k], k[0], 8), k[0], _B_I, _L_I)["PI"]
        assert final.verdict["default_PI"][k] == pytest.approx(exp)
