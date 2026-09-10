"""Tests for M3 cross-validation + multiplicity control (benchmarks/m3_select.py, bd 8an.4.5).

Two test styles, mirroring the repo convention:

* PURE statistics over canned ``score_verdict`` dicts and p-value tables (the
  Wilcoxon unit, Holm-Bonferroni, the deadband) — no solve, no metric integration.
* END-TO-END over lightweight stub run-sets that the REAL
  :func:`benchmarks.metric.score_verdict` accepts (``types.SimpleNamespace`` with
  ``history`` / ``final_incumbents`` / ``seed``, plain-dict baselines) — exercises
  restrict -> score -> CV -> select wiring against the actual metric. No C extension.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import metric, m3_select as S  # noqa: E402


# --------------------------------------------------------------------------- #
# Folds — the authoritative bd-8an.4 split (contract, mirrors test_selection_sizes).
# --------------------------------------------------------------------------- #

def test_folds_match_the_bd_8an4_decision_and_are_disjoint():
    assert S.FOLDS["train"] == frozenset({10, 20, 30, 40, 50})
    assert S.FOLDS["validate"] == frozenset({60, 70, 80, 90})
    assert S.FOLDS["train"].isdisjoint(S.FOLDS["validate"])  # disjoint folds (§9)
    # both folds live within the anchored n=10..90 strata (n=100 too few, n>=500 pending 0o8)
    assert all(10 <= n <= 90 for n in S.FOLDS["train"] | S.FOLDS["validate"])


def test_restrict_run_set_filters_to_fold_sizes():
    rs = {(10, 0): "a", (20, 0): "b", (60, 0): "c"}
    assert set(S.restrict_run_set(rs, {10, 20})) == {(10, 0), (20, 0)}


def test_restrict_run_set_raises_on_empty_fold():
    with pytest.raises(ValueError):
        S.restrict_run_set({(60, 0): "x"}, {10, 20})  # no key in the fold -> fail loud


# --------------------------------------------------------------------------- #
# The §13 Wilcoxon unit — pure over canned score_verdict dicts.
# --------------------------------------------------------------------------- #

def _verdict(cand_pi, def_pi, spreads, k=1.0):
    return {"candidate_PI": dict(cand_pi), "default_PI": dict(def_pi),
            "spreads_PI": dict(spreads), "params": {"k": k}}


def test_candidate_pvalue_clear_win_is_significant():
    # 6 instances, candidate strictly better, all deltas beyond the margin -> p = 0.5^6.
    v = _verdict({(10, i): 0.10 for i in range(6)},
                 {(10, i): 0.50 for i in range(6)}, {10: 0.05})
    st = S.candidate_pvalue(v)
    assert st.n_effective == 6 and st.n_zeros == 0
    assert st.p_value == pytest.approx(0.5 ** 6)


def test_candidate_pvalue_all_within_margin_is_p1_all_zero():
    # |delta| <= m -> every delta zeroed -> deterministic p=1.0 (scipy would NaN/warn).
    v = _verdict({(10, i): 0.50 for i in range(6)},
                 {(10, i): 0.51 for i in range(6)}, {10: 1.0})
    st = S.candidate_pvalue(v)
    assert st.all_zero is True and st.p_value == 1.0 and st.n_effective == 0


def test_candidate_pvalue_clear_loss_not_significant_one_sided():
    v = _verdict({(10, i): 0.90 for i in range(6)},
                 {(10, i): 0.10 for i in range(6)}, {10: 0.05})
    assert S.candidate_pvalue(v).p_value == pytest.approx(1.0, abs=1e-6)


def test_candidate_pvalue_excludes_and_counts_nonfinite():
    # a +inf (never-feasible) candidate PI is EXCLUDED from the test and counted —
    # scipy would silently mis-rank a -inf delta as an ordinary loss (the landmine).
    v = _verdict({(10, 0): float("inf"), (10, 1): 0.1, (10, 2): 0.1, (10, 3): 0.1},
                 {(10, 0): 0.5, (10, 1): 0.5, (10, 2): 0.5, (10, 3): 0.5}, {10: 0.05})
    st = S.candidate_pvalue(v)
    assert st.n_excluded_nonfinite == 1 and st.n_effective == 3
    assert st.p_value == pytest.approx(0.5 ** 3)


def test_candidate_pvalue_deadband_zeroes_within_margin_only():
    # one delta inside the margin (zeroed), the rest outside (counted).
    v = _verdict({(10, 0): 0.49, (10, 1): 0.1, (10, 2): 0.1, (10, 3): 0.1, (10, 4): 0.1},
                 {(10, 0): 0.50, (10, 1): 0.5, (10, 2): 0.5, (10, 3): 0.5, (10, 4): 0.5},
                 {10: 0.05})  # margin = 0.05; delta_0 = 0.01 <= 0.05 -> zeroed
    st = S.candidate_pvalue(v)
    assert st.n_zeros == 1 and st.n_effective == 4


def test_candidate_pvalue_raises_on_missing_spread():
    # a jointly-feasible size absent from spreads_PI is a corrupt verdict — fail loud
    # (the §6.6 gate raises on this; the §13 unit must agree, not fall back to margin 0).
    v = _verdict({(10, 0): 0.1, (10, 1): 0.1}, {(10, 0): 0.5, (10, 1): 0.5}, spreads={})
    with pytest.raises(ValueError):
        S.candidate_pvalue(v)


def test_candidate_pvalue_uses_same_J_as_the_gate():
    # J = jointly-PRESENT keys. A candidate-only or default-only key is not paired.
    v = _verdict({(10, 0): 0.1, (10, 1): 0.1, (10, 9): 0.1},   # (10,9) candidate-only
                 {(10, 0): 0.5, (10, 1): 0.5, (10, 8): 0.5}, {10: 0.05})  # (10,8) default-only
    st = S.candidate_pvalue(v)
    assert st.n_effective == 2  # only (10,0),(10,1) are jointly present


# --------------------------------------------------------------------------- #
# Holm-Bonferroni FWER control — pure.
# --------------------------------------------------------------------------- #

def test_holm_rejects_only_small_enough_p_step_down():
    # m=5: smallest must clear alpha/5 = 0.01; step-down stops at first failure.
    out = S.holm_bonferroni({"a": 0.001, "b": 0.02, "c": 0.5, "d": 0.6, "e": 0.7})
    assert out["a"].reject is True       # 0.001 <= 0.05/5 = 0.01
    assert out["b"].reject is False      # 0.02 > 0.05/4 = 0.0125 -> stop
    assert all(not out[k].reject for k in ("c", "d", "e"))


def test_holm_step_down_blocks_later_rejection_after_a_gap():
    # m=4, alpha=0.05; sorted p = [0.001, 0.02, 0.03, 0.04]. 'b'=0.02 fails its
    # threshold 0.05/3=0.0167 -> step-down stop. 'd'=0.04 would clear alpha=0.05 on
    # its own but is BLOCKED by the earlier non-rejection (the Holm step-down rule).
    out = S.holm_bonferroni({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.04})
    assert out["a"].reject is True       # 0.001 <= 0.05/4 = 0.0125
    assert out["b"].reject is False      # 0.02 > 0.05/3 = 0.0167 -> stop
    assert out["c"].reject is False and out["d"].reject is False  # blocked despite d<=alpha


def test_holm_adjusted_p_is_monotone_and_clamped():
    out = S.holm_bonferroni({"a": 0.02, "b": 0.03, "c": 0.04})
    adj = [out[k].p_adjusted for k in ("a", "b", "c")]
    assert adj == sorted(adj)            # non-decreasing
    assert all(0.0 <= p <= 1.0 for p in adj)


def test_holm_empty_family():
    assert S.holm_bonferroni({}) == {}


def test_holm_controls_fwer_on_pure_noise():
    # 20 candidates whose p-values are ~uniform(0,1): at alpha=0.05 Holm should
    # almost never reject (this fixed draw rejects none) — the FWER guarantee.
    import numpy as np
    rng = np.random.default_rng(0)
    pvals = {f"c{i}": float(rng.uniform()) for i in range(20)}
    out = S.holm_bonferroni(pvals, alpha=0.05)
    assert sum(d.reject for d in out.values()) == 0


# --------------------------------------------------------------------------- #
# End-to-end over stub run-sets the REAL score_verdict accepts.
# --------------------------------------------------------------------------- #

_B_I, _L_I = 1000.0, 0.0
_SEEDS = (1, 2, 3)
#: small custom folds (2 sizes each, 2 instances/size) — keeps stub run-sets tiny
#: while preserving the >=2-instances-per-stratum spread requirement.
_FOLDS = {"train": frozenset({10, 20}), "validate": frozenset({30, 40})}
_SIZES = [10, 20, 30, 40]
_IDXS = [0, 1]
#: distinct default values per index so default_pi_spreads has a positive spread.
_DVALS = {(n, i): (500.0 if i == 0 else 600.0) for n in _SIZES for i in _IDXS}


def _res(value, n, seed, feasible=True):
    if not feasible:
        return types.SimpleNamespace(history=[], final_incumbents=[(value, False)], seed=seed)
    return types.SimpleNamespace(history=[(value, 5)],
                                 final_incumbents=[(value, True), (value - 50, True)], seed=seed)


def _default_and_baselines():
    default, baselines = {}, {}
    for n in _SIZES:
        for i in _IDXS:
            dv = _DVALS[(n, i)]
            runs = [_res(dv, n, s) for s in _SEEDS]
            default[(n, i)] = runs
            # default_PI = the run-set's own re-scored PI (identical across the matched
            # seeds) so strict_xcheck=True is satisfiable on the stub.
            dpi = metric.score_instance(runs[0], n, _B_I, _L_I)["PI"]
            baselines[(n, i)] = {"B_I": _B_I, "L_I": _L_I, "default_PI": dpi, "default_cap": 0}
    return default, baselines


def _candidate(value_fn, *, feasible_fn=lambda n, i: True):
    return {(n, i): [_res(value_fn(n, i), n, s, feasible=feasible_fn(n, i)) for s in _SEEDS]
            for n in _SIZES for i in _IDXS}


def test_cross_validate_winner_passes_both_folds():
    cand = _candidate(lambda n, i: 950.0)   # beats every default (<=600)
    deflt, base = _default_and_baselines()
    cv = S.cross_validate(cand, deflt, base, folds=_FOLDS, strict_xcheck=True)
    assert cv.passed is True
    assert all(v["overall_pass"] for v in cv.per_fold.values())


def test_cross_validate_fails_when_a_single_fold_regresses_feasibility():
    # candidate is a clear win EXCEPT it loses feasibility on one train instance ->
    # the train fold fails (§6 item 5 feasibility tier) -> AND across folds is False.
    cand = _candidate(lambda n, i: 950.0,
                      feasible_fn=lambda n, i: not (n == 10 and i == 0))
    deflt, base = _default_and_baselines()
    cv = S.cross_validate(cand, deflt, base, folds=_FOLDS, strict_xcheck=True)
    assert cv.passed is False
    assert cv.per_fold["train"]["overall_pass"] is False
    assert cv.per_fold["validate"]["overall_pass"] is True  # validate fold unaffected


def test_cross_validate_tie_passes_cv_without_a_win():
    # a baseline-equivalent candidate (ties the default) does NOT regress -> passes CV,
    # but it is not a significant win (the multiplicity layer must catch that).
    deflt, base = _default_and_baselines()
    cand = _candidate(lambda n, i: _DVALS[(n, i)])
    cv = S.cross_validate(cand, deflt, base, folds=_FOLDS, strict_xcheck=True)
    assert cv.passed is True
    union = frozenset(_SIZES)
    v = S.score_fold(cand, deflt, base, union, strict_xcheck=True)
    assert S.candidate_pvalue(v).p_value == 1.0


def test_cross_validate_raises_on_empty_folds():
    deflt, base = _default_and_baselines()
    cand = _candidate(lambda n, i: 950.0)
    with pytest.raises(ValueError):
        S.cross_validate(cand, deflt, base, folds={}, strict_xcheck=False)


def test_cross_validate_raises_on_unanchored_fold():
    # a fold whose instances are present in the run-sets but carry NO frozen anchor
    # scores nothing (empty default_PI) — must fail loud, not pass vacuously.
    cand = {(10, 0): [_res(950.0, 10, s) for s in _SEEDS]}
    deflt = {(10, 0): [_res(500.0, 10, s) for s in _SEEDS]}
    with pytest.raises(ValueError):
        S.cross_validate(cand, deflt, baselines={}, folds={"only": frozenset({10})},
                         strict_xcheck=False)


def test_strict_xcheck_raises_on_stale_freeze():
    # default_PI in the table disagrees with the supplied default run-set -> strict
    # xcheck RAISES (the M1 capstone guard), and is tolerated when strict_xcheck=False.
    deflt, base = _default_and_baselines()
    for entry in base.values():
        entry["default_PI"] = entry["default_PI"] + 0.5  # corrupt the freeze
    cand = _candidate(lambda n, i: 950.0)
    with pytest.raises(ValueError):
        S.cross_validate(cand, deflt, base, folds=_FOLDS, strict_xcheck=True)
    cv = S.cross_validate(cand, deflt, base, folds=_FOLDS, strict_xcheck=False)
    assert isinstance(cv.passed, bool)  # no raise


# --------------------------------------------------------------------------- #
# select_significant — CV + multiplicity over a population.
# --------------------------------------------------------------------------- #

def test_select_significant_promotes_only_the_significant_winner():
    deflt, base = _default_and_baselines()
    pop = {
        "winner": _candidate(lambda n, i: 950.0),               # clear win (p=0.5^8)
        "tie_a": _candidate(lambda n, i: _DVALS[(n, i)]),       # baseline-equivalent
        "tie_b": _candidate(lambda n, i: _DVALS[(n, i)]),
        "tie_c": _candidate(lambda n, i: _DVALS[(n, i)]),
    }
    sel = S.select_significant(pop, deflt, base, folds=_FOLDS, strict_xcheck=True)
    assert sel.survivors == ["winner"]
    assert sel.per_candidate["winner"]["reject"] is True
    for tie in ("tie_a", "tie_b", "tie_c"):
        assert sel.per_candidate[tie]["cross_val"] is True   # ties pass CV
        assert sel.per_candidate[tie]["reject"] is False     # but not a significant win


def test_cv_failing_candidate_spends_no_alpha():
    # a candidate that fails CV is never tested -> the Holm family is exactly the
    # CV-passing set, so a CV-failure does not inflate the correction divisor.
    deflt, base = _default_and_baselines()
    pop = {
        "winner": _candidate(lambda n, i: 950.0),
        "loser": _candidate(lambda n, i: 950.0,
                            feasible_fn=lambda n, i: not (n == 10 and i == 0)),  # fails CV
    }
    sel = S.select_significant(pop, deflt, base, folds=_FOLDS, strict_xcheck=True)
    assert sel.per_candidate["loser"]["cross_val"] is False
    assert sel.per_candidate["loser"]["p_value"] is None   # never tested
    assert "loser" not in sel.holm                          # not in the Holm family
    assert sel.survivors == ["winner"]                      # m=1 -> winner clears alpha/1


# --------------------------------------------------------------------------- #
# Final rescore (§13 once, new seeds, untouched holdout).
# --------------------------------------------------------------------------- #

def test_rescore_once_runs_on_holdout_with_injected_solves():
    deflt, base = _default_and_baselines()
    # holdout: brand-new instances + new seeds, both disjoint from selection.
    holdout = [(50, 0), (50, 1)]
    #: distinct default values per holdout instance so the n=50 stratum has a
    #: positive default PI spread (an all-equal stratum is unevaluable, raises).
    holdout_dval = {(50, 0): 550.0, (50, 1): 650.0}
    for k in holdout:
        runs = [_res(holdout_dval[k], k[0], s) for s in (8, 9)]
        # extend the baseline table for the holdout instances
        base[k] = {"B_I": _B_I, "L_I": _L_I,
                   "default_PI": metric.score_instance(runs[0], k[0], _B_I, _L_I)["PI"],
                   "default_cap": 0}

    calls = {"default": None, "candidate": None}

    def default_solve(instances, seeds):
        calls["default"] = (tuple(instances), tuple(seeds))
        return {k: [_res(holdout_dval[k], k[0], s) for s in seeds] for k in instances}

    def candidate_solve(factory, instances, seeds):
        calls["candidate"] = (tuple(instances), tuple(seeds))
        return {k: [_res(980.0, k[0], s) for s in seeds] for k in instances}  # winner

    fv = S.rescore_once(lambda n, c1, c2, c3: {}, base, holdout_instances=holdout,
                        new_seeds=(8, 9), default_solve=default_solve,
                        candidate_solve=candidate_solve,
                        selection_seeds=(1, 2, 3), selection_keys=list(deflt))
    assert calls["default"][1] == (8, 9) and calls["candidate"][1] == (8, 9)
    assert fv.passed is True and fv.p_value < 0.5   # a held-out win
    assert fv.new_seeds == (8, 9)


def test_rescore_once_blocks_seed_leakage():
    with pytest.raises(ValueError):       # new seed overlaps the selection bank
        S.rescore_once(lambda *a: {}, {}, holdout_instances=[(50, 0)], new_seeds=(2,),
                       default_solve=lambda *a: {}, candidate_solve=lambda *a: {},
                       selection_seeds=(1, 2, 3), selection_keys=[(10, 0)])


def test_rescore_once_blocks_instance_leakage():
    with pytest.raises(ValueError):       # holdout instance overlaps the selection set
        S.rescore_once(lambda *a: {}, {}, holdout_instances=[(10, 0)], new_seeds=(8,),
                       default_solve=lambda *a: {}, candidate_solve=lambda *a: {},
                       selection_seeds=(1, 2, 3), selection_keys=[(10, 0)])


def test_rescore_once_rejects_nonpositive_seeds():
    with pytest.raises(ValueError):
        S.rescore_once(lambda *a: {}, {}, holdout_instances=[(50, 0)], new_seeds=(0,),
                       default_solve=lambda *a: {}, candidate_solve=lambda *a: {},
                       selection_seeds=(1, 2, 3), selection_keys=[(10, 0)])


def test_rescore_once_requires_nonempty_selection_keys():
    # the §13 untouched-holdout guard must not be silently bypassable by an empty
    # (or omitted) selection_keys — it RAISES (valid new seeds, so it reaches it).
    with pytest.raises(ValueError):
        S.rescore_once(lambda *a: {}, {}, holdout_instances=[(50, 0)], new_seeds=(8,),
                       default_solve=lambda *a: {}, candidate_solve=lambda *a: {},
                       selection_seeds=(1, 2, 3), selection_keys=[])


# --------------------------------------------------------------------------- #
# Negative control (§13 / §1.3 type-I check).
# --------------------------------------------------------------------------- #

def test_negative_control_yields_no_significant_win():
    deflt, base = _default_and_baselines()

    def candidate_solve(factory, instances, seeds):
        # baseline-equivalent: re-use the default run-set restricted to the instances
        # (same seeds) -> deltas are exactly the seed-matched default vs itself.
        return {k: deflt[k] for k in instances}

    factories = {f"nc{i}": __import__("benchmarks.m3_proposer", fromlist=["baseline_equivalent_factory"]).baseline_equivalent_factory()
                 for i in range(4)}
    nc = S.negative_control(factories, deflt, base, candidate_solve=candidate_solve,
                            candidate_instances=list(deflt), candidate_seeds=_SEEDS,
                            folds=_FOLDS, strict_xcheck=True)
    assert nc.any_significant is False
    assert nc.selection.survivors == []


def test_negative_control_has_power_a_real_win_would_trip_it():
    # sanity: the control is not trivially always-False. If the injected solve
    # returned a genuine winner, the SAME pipeline would flag it (FWER-leak detector).
    deflt, base = _default_and_baselines()

    def winning_solve(factory, instances, seeds):
        return {k: [_res(950.0, k[0], s) for s in seeds] for k in instances}

    nc = S.negative_control({"plant": lambda *a: {}}, deflt, base,
                            candidate_solve=winning_solve, candidate_instances=list(deflt),
                            candidate_seeds=_SEEDS, folds=_FOLDS, strict_xcheck=True)
    assert nc.any_significant is True
