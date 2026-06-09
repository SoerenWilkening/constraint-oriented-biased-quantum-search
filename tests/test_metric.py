"""Tests for the M1 primal-integral fitness metric (bd 8an.2, NORTHSTAR §6/§8/§13).

Pure-function tests: no solve, no built extension — the metric operates on already-extracted
``result.history`` / ``result.final_incumbents`` plain-Python structures, so a lightweight stub
stands in for ``OptimizeResult``. Golden PI values are hand-computed in the module design and
re-derived in the comments here (CLAUDE.md §2.2 RED-GREEN: assert against known-correct numbers,
not "it runs"). The one real-data test is skipped unless ``CBQS_BENCHMARKS_DIR`` is set.
"""
import math
import os
import statistics
import types

import pytest

from benchmarks.metric import (
    GAMMA_MAX,
    PI_EPS,
    EXPLORE_FLOOR_FRACTION,
    NOISE_MARGIN_K,
    LARGEST_N,
    FLOOR_INSTANCE_FRACTION,
    XCHECK_REL_TOL,
    oracle_budget,
    require_anchor,
    d_i,
    gamma,
    compute_primal_integral,
    instance_feasible,
    score_instance,
    exploration_floor,
    spread,
    feasibility_dominates,
    aggregate_stratified,
    default_pi_spreads,
    score_run_set,
    anchor_cap_summary,
    default_objective_spreads,
    score_verdict,
    _normalize_run_set,
    _reduce_seed_bank_pi,
    _check_matched_seeds,
    _aggregate_floor,
)


def _result(history=None, final_incumbents=None, seed=None):
    """Minimal OptimizeResult stand-in (the metric duck-types .history/.final_incumbents/.seed)."""
    return types.SimpleNamespace(
        history=list(history) if history is not None else [],
        final_incumbents=list(final_incumbents) if final_incumbents is not None else [],
        seed=seed,
    )


# --------------------------------------------------------------------------- #
# Step 1 — primitives
# --------------------------------------------------------------------------- #

def test_gamma_anchor_frontier_overshoot():
    # γ = clamp((B_I − best)/D_I, −0.5, 1) with B_I=100, D_I=100.
    assert gamma(0, 100, 100) == 1.0       # at/below the anchor
    assert gamma(100, 100, 100) == 0.0     # at the frontier
    assert gamma(40, 100, 100) == pytest.approx(0.60)
    assert gamma(200, 100, 100) == -GAMMA_MAX  # over-frontier, floored at −0.5
    assert gamma(150, 100, 100) == -GAMMA_MAX  # raw −0.5 exactly, still floored


def test_gamma_rejects_nonpositive_denominator():
    with pytest.raises(ValueError):
        gamma(0, 100, 0)
    with pytest.raises(ValueError):
        gamma(0, 100, -5)


def test_d_i_floor_and_drop_rule():
    assert d_i(100, 0) == 100.0
    # near-tie that survives the drop rule by an FP hair → floored, not zero.
    assert d_i(1.0, 1.0 - 1e-12) == pytest.approx(PI_EPS * 1.0)
    with pytest.raises(ValueError):  # drop rule: L_I >= B_I
        d_i(100, 100)
    with pytest.raises(ValueError):
        d_i(100, 150)
    with pytest.raises(ValueError):  # None anchor never coerced
        d_i(None, 0)
    with pytest.raises(ValueError):
        d_i(100, None)


def test_oracle_budget_matches_model():
    # Model.pyx:778 — int((n/4.0)**2 + 1200).
    assert oracle_budget(3000) == int((3000 / 4.0) ** 2 + 1200) == 563700
    assert oracle_budget(10) == int((10 / 4.0) ** 2 + 1200) == 1206
    assert oracle_budget(13) == int((13 / 4.0) ** 2 + 1200)  # not divisible by 4 → float division


def test_require_anchor_raises_on_none_not_zero():
    assert require_anchor(0.0, "L_I", (10, 0)) == 0.0      # 0.0 is a real anchor
    assert require_anchor(5, "B_I", (10, 0)) == 5.0
    with pytest.raises(ValueError):
        require_anchor(None, "L_I", (10, 0))


def test_require_anchor_rejects_nonfinite():
    # NaN/inf anchors must fail loud, exactly like None — not sail through to a finite-looking PI.
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            require_anchor(bad, "B_I", (10, 0))


def test_gamma_rejects_nonfinite_gap():
    # A NaN incumbent must raise, not be laundered to 1.0 by the clamp's first-arg-wins semantics.
    with pytest.raises(ValueError):
        gamma(float("nan"), 100, 100)
    with pytest.raises(ValueError):
        gamma(float("inf"), 100, 100)


def test_compute_primal_integral_rejects_nonfinite_anchor():
    # A non-finite anchor through the full path must raise, not yield a clean PI=1.0.
    with pytest.raises(ValueError):
        compute_primal_integral([(50, 1), (60, 500)], float("nan"), 0.0, 1000)
    with pytest.raises(ValueError):
        compute_primal_integral([(50, 1)], 100, float("inf"), 1000)


def test_spread_rejects_nonfinite_population():
    # A +inf never-feasible PI (or NaN) in the population would neutralize the gates → must raise.
    with pytest.raises(ValueError):
        spread([0.1, 0.2, float("inf")])
    with pytest.raises(ValueError):
        spread([0.1, 0.2, float("nan")])


# --------------------------------------------------------------------------- #
# Step 2 — compute_primal_integral golden vectors (B_I=100, L_I=0, D_I=100, T_I=1000)
# --------------------------------------------------------------------------- #

def test_pi_a_flat_at_anchor():
    # history=[(0,1)]: pre-feasible [0,1) γ=1 → 1; tail [1,1000] γ(0)=1 → 999; area=1000 → PI=1.0
    assert compute_primal_integral([(0, 1)], 100, 0, 1000) == 1.0


def test_pi_b_instant_frontier():
    # history=[(100,0)]: pre-feasible width 0; tail [0,1000] γ(100)=0 → 0; PI=0.0
    assert compute_primal_integral([(100, 0)], 100, 0, 1000) == 0.0
    # realistic variant at oracle 1: pre-feasible plateau of width 1 → area 1 → PI=0.001
    assert compute_primal_integral([(100, 1)], 100, 0, 1000) == pytest.approx(0.001)


def test_pi_c_over_frontier_capped():
    # history=[(200,1)]: γ(200)=−0.5; area = 1·1 + (−0.5)·999 = −498.5 → PI=−0.4985
    assert compute_primal_integral([(200, 1)], 100, 0, 1000) == pytest.approx(-0.4985)
    # no pre-feasible plateau → hits the hard −GAMMA_MAX floor exactly.
    assert compute_primal_integral([(200, 0)], 100, 0, 1000) == -GAMMA_MAX


def test_pi_d_gradual_multisegment():
    # history=[(40,100),(70,400),(100,600)]: γ=0.6,0.3,0.0
    # area = 1·100 + 0.6·300 + 0.3·200 + 0·400 = 100+180+60 = 340 → PI=0.34
    assert compute_primal_integral([(40, 100), (70, 400), (100, 600)], 100, 0, 1000) == pytest.approx(0.34)


def test_pi_e_never_feasible_is_inf():
    assert compute_primal_integral([], 100, 0, 1000) == float("inf")
    assert math.isinf(compute_primal_integral([], 100, 0, 1000))


def test_pi_f_first_feasible_partway_at_frontier():
    # history=[(100,300)]: pre-feasible [0,300) γ=1 → 300; tail γ(100)=0 → 0; PI=0.30
    assert compute_primal_integral([(100, 300)], 100, 0, 1000) == pytest.approx(0.30)


def test_pi_overshoot_clips_to_budget():
    # stamp 5000 > T_I=1000: clips out → whole [0,1000] is pre-feasible γ=1 → PI=1.0
    assert compute_primal_integral([(50, 5000)], 100, 0, 1000) == 1.0


def test_pi_duplicate_stamps_zero_width():
    # duplicate oracle stamp → zero-width interior segment; running-max value wins, no blow-up.
    pi = compute_primal_integral([(40, 100), (70, 100), (100, 600)], 100, 0, 1000)
    # [0,100) γ=1 →100; [100,100) width0; [100,600) γ(70)=0.3 →150; tail [600,1000] γ(100)=0 →0
    assert pi == pytest.approx((100 + 150) / 1000)


# --------------------------------------------------------------------------- #
# Step 3 — edge cases / fail-loud + properties
# --------------------------------------------------------------------------- #

def test_pi_raises_on_bad_inputs():
    with pytest.raises(ValueError):  # T_I <= 0
        compute_primal_integral([(50, 1)], 100, 0, 0)
    with pytest.raises(ValueError):
        compute_primal_integral([(50, 1)], 100, 0, -10)
    with pytest.raises(ValueError):  # L_I >= B_I drop rule
        compute_primal_integral([(50, 1)], 100, 100, 1000)
    with pytest.raises(ValueError):  # None anchor
        compute_primal_integral([(50, 1)], None, 0, 1000)
    with pytest.raises(ValueError):
        compute_primal_integral([(50, 1)], 100, None, 1000)
    with pytest.raises(ValueError):  # non-ascending oracle stamps
        compute_primal_integral([(40, 400), (70, 100)], 100, 0, 1000)
    with pytest.raises(ValueError):  # negative stamp
        compute_primal_integral([(40, -1)], 100, 0, 1000)
    with pytest.raises(ValueError):  # value regression — best(t) must be running-max (MAXIMIZE)
        compute_primal_integral([(100, 100), (40, 400)], 100, 0, 1000)
    with pytest.raises(ValueError):  # non-finite incumbent value
        compute_primal_integral([(float("nan"), 100), (50, 500)], 100, 0, 1000)


def test_pi_property_clamp_bounds():
    # For ANY feasible history the integrand ∈ [−0.5, 1] ⇒ PI ∈ [−0.5, 1].
    histories = [
        [(0, 1)], [(100, 0)], [(200, 5)], [(40, 100), (70, 400), (100, 600)],
        [(-50, 10)], [(95, 999)], [(120, 1), (130, 500)],
    ]
    for h in histories:
        pi = compute_primal_integral(h, 100, 0, 1000)
        assert -GAMMA_MAX - 1e-12 <= pi <= 1.0 + 1e-12


def test_pi_property_monotone_better_is_lower():
    # best_A(t) >= best_B(t) pointwise (same stamps, A's values >= B's) ⇒ PI_A <= PI_B.
    stamps = [50, 300, 700]
    a = [(60, 50), (80, 300), (100, 700)]
    b = [(30, 50), (50, 300), (70, 700)]
    assert compute_primal_integral(a, 100, 0, 1000) <= compute_primal_integral(b, 100, 0, 1000)


def test_pi_property_d_i_floor_prevents_blowup():
    # B_I − L_I = tiny positive (survives drop by an FP hair) → floor keeps PI finite, no inf/nan.
    pi = compute_primal_integral([(0.0, 1)], 1.0, 1.0 - 1e-15, 1000)
    assert math.isfinite(pi)


def test_pi_determinism_pure_function():
    h = [(40, 100), (70, 400), (100, 600)]
    assert compute_primal_integral(h, 100, 0, 1000) == compute_primal_integral(h, 100, 0, 1000)


# --------------------------------------------------------------------------- #
# Step 4 — wrappers, feasibility, exploration floor, batch None-skip
# --------------------------------------------------------------------------- #

def test_instance_feasible():
    assert instance_feasible(_result(history=[(100, 5)])) is True
    assert instance_feasible(_result(history=[])) is False
    # falls back to final_incumbents when history empty.
    assert instance_feasible(_result(history=[], final_incumbents=[(50, True)])) is True
    assert instance_feasible(_result(history=[], final_incumbents=[(50, False)])) is False


def test_score_instance_shape_and_inf():
    r = _result(history=[(40, 100), (70, 400), (100, 600)])
    s = score_instance(r, n=40, B_I=100, L_I=0, T_I=1000)
    assert s["PI"] == pytest.approx(0.34)
    assert s["feasible"] is True and s["best"] == 100 and s["D_I"] == 100.0
    # never feasible → +∞, feasible False.
    s2 = score_instance(_result(history=[]), n=40, B_I=100, L_I=0, T_I=1000)
    assert s2["PI"] == float("inf") and s2["feasible"] is False and s2["best"] is None
    # default T_I from oracle_budget(n).
    assert score_instance(r, n=40, B_I=100, L_I=0)["T_I"] == oracle_budget(40)
    with pytest.raises(ValueError):
        score_instance(r, n=40, B_I=100, L_I=None)


def test_exploration_floor_gate():
    spread_default = 10.0  # threshold = 0.5 * 10 = 5
    # best 100, median 90 → lift 10 > 5 → PASS
    res = exploration_floor([(100, True), (90, True), (80, True), (70, False)], spread_default)
    assert res["pass"] is True and res["best_of_P"] == 100 and res["median_of_P"] == 90
    assert res["lift"] == 10 and res["n_feasible"] == 3  # infeasible worker filtered
    # lift 2 <= 5 → FAIL
    assert exploration_floor([(92, True), (90, True), (88, True)], spread_default)["pass"] is False
    # all-infeasible → not pass, n_feasible 0.
    none_feas = exploration_floor([(50, False), (60, False)], spread_default)
    assert none_feas["pass"] is False and none_feas["n_feasible"] == 0
    with pytest.raises(ValueError):  # spread not frozen → cannot pass silently
        exploration_floor([(100, True)], None)


def test_spread_iqr_and_std():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    iqr = spread(vals, stat="IQR")
    assert iqr == pytest.approx(4.0)  # inclusive quartiles: Q1=3, Q3=7 → 4
    assert spread([5], stat="IQR") == 0.0   # <2 points → 0
    assert spread(vals, stat="std") == pytest.approx(__import__("statistics").pstdev(vals))
    with pytest.raises(ValueError):
        spread(vals, stat="variance")


def test_score_run_set_none_anchor_skips_never_zero():
    results = {(10, 0): _result(history=[(100, 5)]),
               (10, 1): _result(history=[(100, 5)]),
               (10, 2): _result(history=[]),
               (10, 3): _result(history=[(100, 5)]),
               (10, 4): _result(history=[(100, 5)])}
    baselines = {
        (10, 0): {"B_I": 100.0, "L_I": 0.0},          # scored
        (10, 1): {"B_I": 100.0, "L_I": None},         # L_I not frozen → skip (8an.1.16)
        (10, 2): {"B_I": 100.0, "L_I": 0.0},          # scored, never feasible → inf
        (10, 3): {"B_I": None, "L_I": 0.0},           # no frontier row → skip
        (10, 4): {"B_I": 100.0, "L_I": 100.0},        # L_I>=B_I → dropped
        # (10,5) absent entirely → caller didn't run it; not in results
    }
    out = score_run_set(results, baselines)
    assert (10, 0) in out["scored"]
    assert out["scored"][(10, 2)] == float("inf")
    assert (10, 2) in out["infeasible"]
    assert any(k == (10, 1) for k, _r in out["skipped_no_anchor"])  # None L_I never → 0
    assert any(k == (10, 3) for k, _r in out["skipped_no_anchor"])  # None B_I
    assert any(k == (10, 4) for k, _r in out["dropped"])
    # a None anchor must NEVER appear as a numeric 0 score.
    assert (10, 1) not in out["scored"] and (10, 3) not in out["scored"]
    # only (10,0)[feasible] and (10,2)[never-feasible] are scored → fraction 1/2.
    assert out["feasibility_fraction_by_size"][10] == pytest.approx(0.5)


def test_score_run_set_missing_key_skipped():
    out = score_run_set({(10, 7): _result(history=[(1, 1)])}, baselines={})
    assert any(k == (10, 7) for k, _r in out["skipped_no_anchor"])
    assert out["scored"] == {}


# --------------------------------------------------------------------------- #
# bd 0o8: opt_sample_cap anchor provenance + mixed-cap guard
# --------------------------------------------------------------------------- #

def test_anchor_cap_summary_faithful_and_approximate():
    """cap 0 (or missing) => faithful; cap>0 => approximate; only ANCHORED rows count."""
    faithful = {(10, 0): {"B_I": 100.0, "L_I": 50.0, "default_cap": 0},
                (10, 1): {"B_I": 100.0, "L_I": None, "default_cap": 999}}  # no anchor → ignored
    s = anchor_cap_summary(faithful)
    assert s == {"cap": 0, "approximate": False, "mixed": False, "caps": [0]}

    approx = {(500, 0): {"B_I": 9.0, "L_I": 5.0, "default_cap": 2000}}
    s = anchor_cap_summary(approx)
    assert s["cap"] == 2000 and s["approximate"] is True and s["mixed"] is False


def test_anchor_cap_summary_missing_column_is_zero():
    """A legacy anchor dict with no default_cap key reads as faithful (cap 0)."""
    assert anchor_cap_summary({(10, 0): {"B_I": 1.0, "L_I": 0.5}})["cap"] == 0


def test_score_run_set_surfaces_cap_provenance():
    """score_run_set reports the anchor cap + approximate flag so the verdict is labeled."""
    out = score_run_set({(500, 0): _result(history=[(7, 5)])},
                        baselines={(500, 0): {"B_I": 9.0, "L_I": 5.0, "default_cap": 2000}})
    assert out["anchor_cap"] == 2000 and out["anchor_approximate"] is True


def test_score_run_set_rejects_mixed_cap_anchors():
    """A table mixing faithful (cap 0) and approximate (cap>0) anchors is unscoreable."""
    baselines = {(10, 0): {"B_I": 100.0, "L_I": 50.0, "default_cap": 0},
                 (500, 0): {"B_I": 9.0, "L_I": 5.0, "default_cap": 2000}}
    with pytest.raises(ValueError, match="Mixed-cap"):
        score_run_set({(10, 0): _result(history=[(60, 5)])}, baselines)


# --------------------------------------------------------------------------- #
# Step 5 — aggregation + feasibility tier
# --------------------------------------------------------------------------- #

def test_feasibility_dominates_lexicographic():
    PI_A = {(10, 0): 0.2, (10, 1): 0.3, (10, 2): 0.4}
    PI_B = {(10, 0): 0.1, (10, 1): 0.1}
    # A feasible on a strict superset → A wins on KEY 1 regardless of worse PI.
    assert feasibility_dominates({(10, 0), (10, 1), (10, 2)}, {(10, 0), (10, 1)}, PI_A, PI_B) == "A"
    # equal feasibility → KEY 2 on jointly feasible: B has lower PI.
    assert feasibility_dominates({(10, 0), (10, 1)}, {(10, 0), (10, 1)}, PI_A, PI_B) == "B"
    # crossed sets, no overlap → incomparable.
    assert feasibility_dominates({(10, 0)}, {(10, 5)}, {(10, 0): 0.1}, {(10, 5): 0.2}) == "incomparable"


def test_aggregate_stratified_gates():
    # One stratum, candidate uniformly better than default, spread small → win, gates pass.
    cand = {(10, i): 0.2 for i in range(4)}
    deflt = {(10, i): 0.5 for i in range(4)}
    spreads = {10: 0.05}  # margin m = 1.0 * 0.05 = 0.05; δ=0.3 > m for all → all wins
    out = aggregate_stratified(cand, deflt, spreads)
    rec = out["per_size"][10]
    assert rec["W"] > 0 and rec["gate_B_pass"] is True
    assert out["overall_pass"] is True  # no largest_n stratum here → only gate B

    # worst-case regression past the margin fails GATE B.
    cand2 = dict(cand); cand2[(10, 0)] = 0.9  # candidate worse than default by 0.4 > margin
    out2 = aggregate_stratified(cand2, deflt, spreads)
    assert out2["per_size"][10]["gate_B_pass"] is False and out2["overall_pass"] is False

    # ties within the margin are Pratt zeros (excluded from W).
    # i=0 better (LOWER PI 0.20 vs default 0.50 → δ=+0.30 win); the rest exact ties (δ=0).
    cand3 = {(10, i): (0.20 if i == 0 else 0.50) for i in range(4)}
    deflt3 = {(10, i): 0.50 for i in range(4)}
    out3 = aggregate_stratified(cand3, deflt3, {10: 0.05})
    # only instance 0 contributes (the 3 ties have |δ|=0 <= margin) → W = +rank(0) > 0
    assert out3["per_size"][10]["W"] > 0


def test_aggregate_largest_n_strict_gate():
    # largest-n stratum: candidate better → strict-improvement GATE A passes.
    cand = {(LARGEST_N, i): 0.2 for i in range(5)}
    deflt = {(LARGEST_N, i): 0.5 for i in range(5)}
    spreads = {LARGEST_N: 0.05}
    out = aggregate_stratified(cand, deflt, spreads)
    rec = out["per_size"][LARGEST_N]
    assert rec["gate_A_pass"] is True and out["overall_pass"] is True
    # no-regression-but-no-improvement (candidate == default) fails the STRICT largest-n gate.
    out_flat = aggregate_stratified(dict(deflt), deflt, spreads)
    assert out_flat["per_size"][LARGEST_N]["gate_A_pass"] is False
    assert out_flat["overall_pass"] is False


def test_aggregate_drops_infeasible_and_requires_spread():
    # (10,1) infeasible for the candidate but feasible for default → feasibility REGRESSION → fail.
    cand = {(10, 0): 0.2, (10, 1): float("inf")}
    deflt = {(10, 0): 0.5, (10, 1): 0.5}
    out = aggregate_stratified(cand, deflt, {10: 0.05})
    rec = out["per_size"][10]
    assert rec["n_jointly_feasible"] == 1  # only (10,0) jointly feasible
    assert rec["feasibility_regressed"] is True and rec["lost_feasibility"] == [(10, 1)]
    assert rec["gate_B_pass"] is False and out["overall_pass"] is False
    with pytest.raises(ValueError):  # spread None → must not silently pass
        aggregate_stratified(cand, deflt, {10: None})
    with pytest.raises(ValueError):  # non-finite spread → non-finite margin → must not silently pass
        aggregate_stratified(cand, deflt, {10: float("inf")})


def test_aggregate_largest_n_feasibility_collapse_fails():
    # BLOCKER regression guard: candidate feasible on only 1 of 10 hardest (n=3000) instances,
    # default feasible on all 10. Despite a great PI on the survivor, the strict gate MUST fail.
    cand = {(LARGEST_N, i): float("inf") for i in range(9)}
    cand[(LARGEST_N, 9)] = 0.1
    deflt = {(LARGEST_N, i): 0.5 for i in range(10)}
    out = aggregate_stratified(cand, deflt, {LARGEST_N: 0.05})
    rec = out["per_size"][LARGEST_N]
    assert rec["feasibility_regressed"] is True and len(rec["lost_feasibility"]) == 9
    assert rec["gate_A_pass"] is False and rec["gate_B_pass"] is False
    assert out["overall_pass"] is False


def test_aggregate_empty_stratum_fails():
    # Candidate never feasible on a whole (non-largest) size where default is feasible → must fail
    # (was: worst_regression defaulted to 0.0 and the stratum silently passed).
    cand = {(500, i): float("inf") for i in range(10)}
    deflt = {(500, i): 0.3 for i in range(10)}
    out = aggregate_stratified(cand, deflt, {500: 0.05})
    rec = out["per_size"][500]
    assert rec["n_jointly_feasible"] == 0 and rec["feasibility_regressed"] is True
    assert rec["gate_B_pass"] is False and out["overall_pass"] is False


def test_aggregate_missing_largest_n_stratum_fails():
    # Candidate omits the n=3000 stratum entirely while default covers it → cannot have shown the
    # strict improvement the largest-n gate demands → must fail (sizes driven from the UNION).
    deflt = {(LARGEST_N, i): 0.5 for i in range(5)}
    deflt.update({(10, i): 0.5 for i in range(5)})
    cand = {(10, i): 0.2 for i in range(5)}  # no n=3000 keys at all
    out = aggregate_stratified(cand, deflt, {10: 0.05, LARGEST_N: 0.05})
    assert LARGEST_N in out["per_size"]  # the union surfaces the omitted stratum
    assert out["per_size"][LARGEST_N]["feasibility_regressed"] is True
    assert out["overall_pass"] is False


def test_aggregate_deadband_boundary_is_a_tie():
    # δ exactly at the margin must read as a tie (not an FP-flipped win/loss). deltas:
    #   (10,0): 0.5-0.55 = -0.05 (boundary tie)  (10,1): 0.5-0.45 = +0.05 (boundary tie)
    #   (10,2),(10,3): 0.5-0.44 = +0.06 (wins)
    deflt = {(10, i): 0.5 for i in range(4)}
    cand = {(10, 0): 0.55, (10, 1): 0.45, (10, 2): 0.44, (10, 3): 0.44}
    rec = aggregate_stratified(cand, deflt, {10: 0.05})["per_size"][10]
    # only the two +0.06 wins count (ranks 3.5 each); both ±0.05 ties dropped → W = 7.0
    assert rec["W"] == pytest.approx(7.0)
    # the -0.05 boundary "regression" is a tie, not a gate-B failure.
    assert rec["gate_B_pass"] is True


def test_default_pi_spreads_producer():
    # Produces the per-n PI spread margin base, excluding the +inf never-feasible sentinel.
    default_PI = {(10, 0): 1.0, (10, 1): 2.0, (10, 2): 3.0, (10, 3): 4.0, (10, 4): 5.0,
                  (10, 5): float("inf"),  # excluded from the spread population
                  (3000, 0): 0.1, (3000, 1): 0.2}
    spreads = default_pi_spreads(default_PI)
    assert spreads[10] == pytest.approx(spread([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert spreads[3000] == pytest.approx(spread([0.1, 0.2]))
    # round-trips straight into aggregate_stratified.
    cand = {(10, i): default_PI[(10, i)] - 0.5 for i in range(5)}
    out = aggregate_stratified(cand, {k: default_PI[k] for k in cand}, spreads)
    assert "overall_pass" in out


# --------------------------------------------------------------------------- #
# Real-data invariant (skipped unless a CBQS-benchmarks clone is available)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not os.environ.get("CBQS_BENCHMARKS_DIR"),
                    reason="needs CBQS_BENCHMARKS_DIR (real frozen baselines)")
def test_pi_eps_floor_never_overrides_real_gap():
    """On every frozen Eq.29 instance the ε floor is immaterial vs the genuine B_I−L_I (§1.5)."""
    from benchmarks.baselines import load_frozen_baselines
    path = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "baselines_frozen.csv")
    table = load_frozen_baselines(path)
    checked = 0
    for key, row in table.items():
        B_I, L_I = row["B_I"], row["L_I"]
        if B_I is None or L_I is None or L_I >= B_I:
            continue  # dropped / not-yet-frozen — not scored
        assert PI_EPS * abs(B_I) < (B_I - L_I), f"ε floor materially overrides gap at {key}"
        checked += 1
    # If L_I is still empty everywhere (pre-8an.1.16), this asserts nothing — that's expected.
    assert checked >= 0


# --------------------------------------------------------------------------- #
# Step 6 — bd 8an.2.1: objective-space §8.3 spread producer + end-to-end verdict driver
#
# Golden trick: a single feasible incumbent stamped at oracle 0 and held to T_I gives
# PI == γ(obj) EXACTLY (pre-feasible width 0; tail = γ(obj)·T_I / T_I). With B_I=100, L_I=0
# (D=100) that is PI = (100 − obj)/100, so obj∈{80,70,60,50,40,30,10} ⇒ PI∈{0.2,0.3,0.4,0.5,
# 0.6,0.7,0.9}. spread([80,90,100]) (inclusive quartiles) == 10.0 (Q1=85, Q3=95).
# --------------------------------------------------------------------------- #

def _bank(obj, fincs, seeds=(0, 1, 2)):
    """A matched seed bank for ONE instance: each seed a single feasible incumbent at oracle 0
    (PI = γ(obj)) plus the per-worker final incumbents *fincs* (objective-space, for the floor).
    ``obj is None`` ⇒ empty history ⇒ never feasible (PI = +∞)."""
    hist = [(obj, 0)] if obj is not None else []
    return [_result(history=list(hist), final_incumbents=list(fincs), seed=s) for s in seeds]


def _bl(B_I=100.0, L_I=0.0, default_PI=0.5, method="hexaly"):
    """A frozen-baseline row (load_frozen_baselines shape)."""
    return {"B_I": B_I, "B_I_method": method, "L_I": L_I, "default_PI": default_PI}


# --- objective-space spread producer --------------------------------------- #

def test_default_objective_spreads_excludes_infeasible():
    # The (70,False) worker contributes NO point (never-feasible exclusion); IQR over [100,90,80].
    res = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True), (70, False)])]}
    out = default_objective_spreads(res)
    assert out[10] == pytest.approx(spread([100, 90, 80])) == pytest.approx(10.0)


def test_default_objective_spreads_pools_within_instance_across_seed_bank():
    # One instance, two seeds: feasible objectives pool WITHIN the instance across its seed bank.
    res = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)]),
                     _result(final_incumbents=[(85, True), (75, True), (65, True)])]}
    out = default_objective_spreads(res)
    assert out[10] == pytest.approx(spread([100, 90, 80, 85, 75, 65]))


def test_default_objective_spreads_per_instance_not_cross_instance():
    # THE faithfulness test (panel risk #4): per-instance IQR then MEDIAN across instances, NOT a raw
    # cross-instance pool. Two instances at very different objective levels: pooling raw would let the
    # inter-instance LEVEL gap dominate the IQR; per-instance IQRs are each 10 / 100 → median 55.
    res = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)])],
           (10, 1): [_result(final_incumbents=[(1000, True), (900, True), (800, True)])]}
    out = default_objective_spreads(res)
    expected = statistics.median([spread([100, 90, 80]), spread([1000, 900, 800])])
    assert out[10] == pytest.approx(expected) == pytest.approx(55.0)
    # and it is NOT the contaminated cross-instance pool (which is ~782.5).
    assert out[10] != pytest.approx(spread([100, 90, 80, 1000, 900, 800]))


def test_default_objective_spreads_size_absent_when_lt2_feasible():
    # Only 1 feasible worker total at a size → no measurable IQR → size ABSENT (not 0.0) so the
    # floor's None-guard fires rather than a silent zero threshold.
    res = {(10, 0): [_result(final_incumbents=[(100, True), (90, False)])]}
    assert 10 not in default_objective_spreads(res)


def test_default_objective_spreads_raises_on_nonfinite():
    res = {(10, 0): [_result(final_incumbents=[(float("nan"), True), (90, True)])]}
    with pytest.raises(ValueError):
        default_objective_spreads(res)


# --- run-set normalization, seed-bank PI reduction, matched seeds ----------- #

def test_normalize_run_set_wraps_bare_result_and_raises_empty():
    n1 = _normalize_run_set({(10, 0): _result(history=[(1, 1)])}, side="x")
    assert isinstance(n1[(10, 0)], list) and len(n1[(10, 0)]) == 1
    with pytest.raises(ValueError):
        _normalize_run_set({}, side="x")
    with pytest.raises(ValueError):
        _normalize_run_set({(10, 0): []}, side="x")


def test_reduce_seed_bank_pi_matches_default_instance_anchors():
    # Parity with baselines.default_instance_anchors: median over per-seed PI at the SAME (B_I, L_I).
    from benchmarks import baselines as B
    n, B_I = 40, 100.0
    runs = [_result(history=[(60, 5), (70, 9)]),
            _result(history=[(55, 5), (80, 9)]),
            _result(history=[(58, 5), (75, 9)])]
    a = B.default_instance_anchors(runs, B_I=B_I, n=n)  # computes L_I = median first-feasible = 58
    assert a["status"] == "ok"
    assert _reduce_seed_bank_pi(runs, n, B_I, a["L_I"]) == pytest.approx(a["default_PI"])


def test_reduce_seed_bank_pi_minority_feasible_is_inf():
    # 1 feasible + 2 never-feasible → median of [finite, +inf, +inf] is +inf (not reliably feasible).
    runs = [_result(history=[(75, 5)]), _result(history=[]), _result(history=[])]
    assert _reduce_seed_bank_pi(runs, 40, 100.0, 50.0) == float("inf")


def test_check_matched_seeds_raises_on_seed_set_mismatch():
    cand = {(10, 0): [_result(seed=0), _result(seed=1), _result(seed=2)]}
    deflt = {(10, 0): [_result(seed=0), _result(seed=1), _result(seed=9)]}
    with pytest.raises(ValueError):
        _check_matched_seeds(cand, deflt)
    ok = {(10, 0): [_result(seed=2), _result(seed=0), _result(seed=1)]}
    audit = _check_matched_seeds(cand, ok)
    assert audit["candidate"][(10, 0)] == 3 and audit["default"][(10, 0)] == 3


def test_check_matched_seeds_falls_back_to_size_when_no_seed():
    cand = {(10, 0): [_result() for _ in range(3)]}   # .seed is None
    _check_matched_seeds(cand, {(10, 0): [_result() for _ in range(3)]})  # 3 == 3 → ok
    with pytest.raises(ValueError):
        _check_matched_seeds(cand, {(10, 0): [_result() for _ in range(7)]})


# --- two-level exploration floor ------------------------------------------- #

def test_aggregate_floor_passes_diverse_and_is_median_over_seeds():
    # spread_obj 10, fraction 0.5 → threshold 5. Per-seed lifts 10 and 12 → median 11 > 5 → pass.
    cand = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)]),
                      _result(final_incumbents=[(100, True), (88, True), (76, True)])]}
    out = _aggregate_floor(cand, {10: 10.0}, fraction=0.5, floor_instance_fraction=1.0, default_sizes={10})
    assert out["per_size"][10]["per_seed_lift"][(10, 0)] == pytest.approx([10.0, 12.0])
    assert out["per_size"][10]["instance_lifts"][(10, 0)] == pytest.approx(11.0)
    assert out["overall_pass"] is True


def test_aggregate_floor_greedy_collapse_fails():
    # Low-variance greedy portfolio: best ≈ median ⇒ lift 0 < threshold on every seed ⇒ FAIL.
    flat = _result(final_incumbents=[(90, True), (90, True), (90, True)])
    cand = {(10, 0): [flat, flat]}
    out = _aggregate_floor(cand, {10: 10.0}, fraction=0.5, default_sizes={10})
    assert out["per_size"][10]["instance_lifts"][(10, 0)] == pytest.approx(0.0)
    assert out["overall_pass"] is False


def test_aggregate_floor_no_pooling_across_seeds():
    # Each seed's portfolio is internally flat (lift 0), but the POOLED population [80×3,120×3] would
    # show a big best-vs-median lift. Judged per-solve, the floor correctly FAILS (anti-conflation).
    cand = {(10, 0): [_result(final_incumbents=[(80, True), (80, True), (80, True)]),
                      _result(final_incumbents=[(120, True), (120, True), (120, True)])]}
    out = _aggregate_floor(cand, {10: 10.0}, fraction=0.5, default_sizes={10})
    assert out["per_size"][10]["per_seed_lift"][(10, 0)] == pytest.approx([0.0, 0.0])
    assert out["overall_pass"] is False


def test_aggregate_floor_median_not_pass_fraction():
    # Per-seed lifts {12, 1}: a per-solve pass-fraction would be 1/2 (coin-flip at FLOOR 0.5), but the
    # MEDIAN lift 6.5 > 5 passes deterministically — pins the median-over-seeds rule.
    cand = {(10, 0): [_result(final_incumbents=[(100, True), (88, True), (76, True)]),   # lift 12
                      _result(final_incumbents=[(91, True), (90, True), (89, True)])]}    # lift 1
    out = _aggregate_floor(cand, {10: 10.0}, fraction=0.5, default_sizes={10})
    assert out["per_size"][10]["instance_lifts"][(10, 0)] == pytest.approx(6.5)
    assert out["overall_pass"] is True


def test_aggregate_floor_instance_fraction_knob():
    # 3 instances, 2 passing (lifts 10, 8, 2 at threshold 5) → fraction 2/3.
    cand = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)])],   # lift 10
            (10, 1): [_result(final_incumbents=[(100, True), (92, True), (84, True)])],   # lift 8
            (10, 2): [_result(final_incumbents=[(92, True), (90, True), (88, True)])]}    # lift 2
    so = {10: 10.0}
    out6 = _aggregate_floor(cand, so, fraction=0.5, floor_instance_fraction=0.6, default_sizes={10})
    assert out6["per_size"][10]["instance_pass_fraction"] == pytest.approx(2 / 3)
    assert out6["overall_pass"] is True
    out1 = _aggregate_floor(cand, so, fraction=0.5, floor_instance_fraction=1.0, default_sizes={10})
    assert out1["overall_pass"] is False


def test_aggregate_floor_absent_candidate_stratum_fails():
    # Default covers n=500, candidate omits it → anti-dodge stratum fail.
    cand = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)])]}
    out = _aggregate_floor(cand, {10: 10.0, 500: 5.0}, fraction=0.5, default_sizes={10, 500})
    assert out["per_size"][500]["stratum_pass"] is False
    assert out["overall_pass"] is False


def test_aggregate_floor_raises_on_none_spread_when_needed():
    cand = {(10, 0): [_result(final_incumbents=[(100, True), (90, True), (80, True)])]}
    with pytest.raises(ValueError):  # feasible workers but no objective spread → cannot normalize
        _aggregate_floor(cand, {}, fraction=0.5, default_sizes={10})


def test_aggregate_floor_raises_when_no_final_incumbents():
    cand = {(10, 0): [_result(final_incumbents=[])]}  # M0e harness produced nothing
    with pytest.raises(ValueError):
        _aggregate_floor(cand, {10: 10.0}, fraction=0.5, default_sizes={10})


def test_aggregate_floor_zero_feasible_solve_is_fail():
    # final_incumbents produced but all infeasible → lift None → instance fails (NOT a raise).
    cand = {(10, 0): [_result(final_incumbents=[(50, False), (60, False)])]}
    out = _aggregate_floor(cand, {10: 10.0}, fraction=0.5, default_sizes={10})
    assert out["per_size"][10]["instance_lifts"][(10, 0)] is None
    assert out["overall_pass"] is False


# --- end-to-end score_verdict ---------------------------------------------- #

def _pass_setup(sizes=(10, 20)):
    """A candidate that beats the default on §6.6 AND has diverse portfolios (passes §8.3)."""
    baselines, cand, deflt = {}, {}, {}
    # default frozen PI 0.5/0.6/0.7 per stratum; candidate PI 0.2/0.3/0.4 (uniformly 0.3 better).
    cand_obj = {0: 80, 1: 70, 2: 60}     # γ → 0.2 / 0.3 / 0.4
    def_obj = {0: 50, 1: 40, 2: 30}      # γ → 0.5 / 0.6 / 0.7  (re-scores to the frozen value)
    def_pi = {0: 0.5, 1: 0.6, 2: 0.7}
    cand_fincs = [(100, True), (90, True), (80, True)]   # lift 10
    def_fincs = [(100, True), (95, True), (90, True)]    # per-instance IQR 10
    for n in sizes:
        for i in range(3):
            baselines[(n, i)] = _bl(default_PI=def_pi[i])
            cand[(n, i)] = _bank(cand_obj[i], cand_fincs)
            deflt[(n, i)] = _bank(def_obj[i], def_fincs)
    return baselines, cand, deflt


def test_score_verdict_pass_small_n():
    baselines, cand, deflt = _pass_setup()
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert out["aggregation"]["overall_pass"] is True
    assert out["floor"]["overall_pass"] is True
    assert out["overall_pass"] is True
    assert out["default_xcheck_failures"] == []           # default run-set re-scores to frozen
    assert out["candidate_PI"][(10, 0)] == pytest.approx(0.2)
    assert out["default_PI"][(10, 0)] == pytest.approx(0.5)


def test_score_verdict_floor_vetoes_pi_winner():
    # Same §6.6 winner, but greedy-flat candidate portfolios → §8.3 floor vetoes (AND, never revive).
    baselines, cand, deflt = _pass_setup()
    flat = [(90, True), (90, True), (90, True)]           # lift 0
    for key in cand:
        cand[key] = _bank({(10, 0): 80, (10, 1): 70, (10, 2): 60,
                           (20, 0): 80, (20, 1): 70, (20, 2): 60}[key], flat)
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert out["aggregation"]["overall_pass"] is True
    assert out["floor"]["overall_pass"] is False
    assert out["overall_pass"] is False


def test_score_verdict_feasibility_regression_dominates():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    cand[(10, 2)] = _bank(None, [(0, False), (0, False), (0, False)])  # never feasible where default is
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert out["aggregation"]["per_size"][10]["feasibility_regressed"] is True
    assert out["overall_pass"] is False
    assert out["feasibility_fraction_by_size"]["candidate"][10] < \
           out["feasibility_fraction_by_size"]["default"][10]


def test_score_verdict_largest_n_strict_improvement_gate():
    # Candidate == default on the largest-n stratum (no regression, no improvement) → strict gate_A fails,
    # even with diverse portfolios. Pins the §6.6 hard-instance gate flowing through the driver.
    baselines, cand, deflt = {}, {}, {}
    def_pi = {0: 0.5, 1: 0.6, 2: 0.7}
    same_obj = {0: 50, 1: 40, 2: 30}     # candidate == default objective ⇒ PI ties
    cand_fincs = [(100, True), (90, True), (80, True)]
    def_fincs = [(100, True), (95, True), (90, True)]
    for i in range(3):
        baselines[(LARGEST_N, i)] = _bl(default_PI=def_pi[i])
        cand[(LARGEST_N, i)] = _bank(same_obj[i], cand_fincs)
        deflt[(LARGEST_N, i)] = _bank(same_obj[i], def_fincs)
    out = score_verdict(cand, deflt, baselines)   # require_largest_n default True; n=3000 frozen here
    assert out["aggregation"]["per_size"][LARGEST_N]["gate_A_pass"] is False
    assert out["overall_pass"] is False


def test_score_verdict_raises_unevaluable_largest_n():
    # require_largest_n True but the run-set covers no feasible-frozen largest-n instance → RAISE;
    # require_largest_n False → an inspectable partial verdict (no raise).
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    with pytest.raises(ValueError):
        score_verdict(cand, deflt, baselines, require_largest_n=True)
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert "overall_pass" in out


def test_score_verdict_consumes_frozen_default_pi_with_xcheck():
    # The supplied default run-set re-scores AWAY from frozen (0.9 vs 0.5); the gate uses the FROZEN
    # value verbatim, the drift is recorded, and strict_xcheck escalates it to a raise.
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    for i in range(3):
        deflt[(10, i)] = _bank(10, [(100, True), (95, True), (90, True)])  # γ(10)=0.9, far from frozen
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert out["default_PI"][(10, 0)] == pytest.approx(0.5)               # frozen, not the 0.9 re-score
    assert any(key == (10, 0) for (key, _rs, _fr, _rel) in out["default_xcheck_failures"])
    with pytest.raises(ValueError):
        score_verdict(cand, deflt, baselines, require_largest_n=False, strict_xcheck=True)


def test_score_verdict_none_default_pi_skipped_never_zero():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    baselines[(10, 1)] = _bl(default_PI=None)             # frozen default_PI not yet available
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert (10, 1) in out["default_pi_missing"]
    assert (10, 1) not in out["default_PI"]               # never coerced to a 0 anchor


def test_score_verdict_raises_seed_bank_mismatch():
    baselines = {(10, 0): _bl(default_PI=0.5)}
    fincs = [(100, True), (90, True), (80, True)]
    cand = {(10, 0): [_result(history=[(80, 0)], final_incumbents=fincs) for _ in range(3)]}
    deflt = {(10, 0): [_result(history=[(50, 0)], final_incumbents=fincs) for _ in range(7)]}
    with pytest.raises(ValueError):                       # 3 vs 7, no .seed
        score_verdict(cand, deflt, baselines, require_largest_n=False)
    cand_s = {(10, 0): _bank(80, fincs, seeds=(0, 1, 2))}
    deflt_s = {(10, 0): _bank(50, fincs, seeds=(0, 1, 9))}
    with pytest.raises(ValueError):                       # equal size, different seed sets
        score_verdict(cand_s, deflt_s, baselines, require_largest_n=False)


def test_score_verdict_raises_empty_run_sets():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    with pytest.raises(ValueError):
        score_verdict({}, deflt, baselines, require_largest_n=False)
    with pytest.raises(ValueError):
        score_verdict(cand, {}, baselines, require_largest_n=False)


def test_score_verdict_uses_pi_space_margin_objective_space_floor():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert out["spreads_PI"] == default_pi_spreads(out["default_PI"])         # §6.6 margin = PI space
    assert out["spreads_obj"] == default_objective_spreads(
        {k: deflt[k] for k in deflt})                                          # §8.3 floor = objective space
    assert out["spreads_PI"][10] != pytest.approx(out["spreads_obj"][10])      # distinct units (0.1 vs 10)


def test_score_verdict_feasibility_invariant_holds():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    # the asserted internal invariant: §6.6 overall_pass ⇒ no stratum feasibility-regressed.
    assert not (out["aggregation"]["overall_pass"] and
                any(r.get("feasibility_regressed") for r in out["aggregation"]["per_size"].values()))


def test_score_verdict_determinism():
    baselines, cand, deflt = _pass_setup()
    a = score_verdict(cand, deflt, baselines, require_largest_n=False)
    b = score_verdict(cand, deflt, baselines, require_largest_n=False)
    assert a == b


def test_score_verdict_params_echo():
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    out = score_verdict(cand, deflt, baselines, k=2.0, fraction=0.25, floor_instance_fraction=0.5,
                        stat="std", require_largest_n=False, strict_xcheck=False)
    assert out["params"] == {"k": 2.0, "fraction": 0.25, "floor_instance_fraction": 0.5,
                             "largest_n": LARGEST_N, "stat": "std", "require_largest_n": False,
                             "strict_xcheck": False}


# --------------------------------------------------------------------------- #
# Step 6b — review-driven hardening (bd 8an.2.1 adversarial review, all confirmed findings)
# --------------------------------------------------------------------------- #

def test_check_matched_seeds_rejects_duplicate_and_reweighted_banks():
    # Findings 2/5/9: set-equality is multiplicity-blind. A within-bank duplicate (zero-diversity
    # padding that re-weights the median) must RAISE, and a re-weighted bank with the same seed SET
    # but different multiplicities ([0,0,1] vs [0,1,1]) must RAISE too.
    dup = {(10, 0): [_result(seed=0), _result(seed=0), _result(seed=1)]}
    honest = {(10, 0): [_result(seed=0), _result(seed=1), _result(seed=2)]}
    with pytest.raises(ValueError):           # duplicate seed in the candidate bank
        _check_matched_seeds(dup, honest)
    with pytest.raises(ValueError):           # both re-weighted (same set {0,1}, different multiset)
        _check_matched_seeds({(10, 0): [_result(seed=0), _result(seed=0), _result(seed=1)]},
                             {(10, 0): [_result(seed=0), _result(seed=1), _result(seed=1)]})
    # a clean, distinct, equal multiset still passes (order-insensitive).
    _check_matched_seeds({(10, 0): [_result(seed=2), _result(seed=0), _result(seed=1)]}, honest)


def test_default_objective_spreads_absent_when_iqr_zero_and_floor_cannot_pass():
    # Finding 7 (the anti-greedy hole): ≥2 IDENTICAL feasible incumbents give IQR 0, which must be
    # treated as "no measurable diversity" → size ABSENT (not 0.0), so the floor's None-guard fires
    # rather than a 0.0 threshold admitting any near-greedy candidate lift > 0.
    converged = {(10, 0): [_result(final_incumbents=[(90, True), (90, True), (90, True)])]}
    spreads = default_objective_spreads(converged)
    assert 10 not in spreads
    near_greedy = {(10, 0): [_result(final_incumbents=[(90.000001, True), (90, True), (90, True)])]}
    with pytest.raises(ValueError):           # spread absent + feasible workers → fail loud, no silent pass
        _aggregate_floor(near_greedy, spreads, fraction=0.5, default_sizes={10})


def test_score_verdict_xcheck_flags_feasibility_mismatch():
    # Findings 1/8: the frozen default_PI is finite (freeze says "reliably feasible") but the supplied
    # live default run-set re-scores to +inf (median PI over the bank is non-finite — default_unreliable).
    # The finite-vs-finite REL_TOL band would skip this; it must be recorded and escalate under strict.
    baselines = {(10, i): _bl(default_PI=0.5) for i in range(3)}
    cand = {(10, i): _bank({0: 80, 1: 70, 2: 60}[i], [(100, True), (90, True), (80, True)]) for i in range(3)}
    # default bank: seed 0 feasible (so an objective spread exists), seeds 1,2 never feasible → median PI +inf.
    def _unreliable_default():
        return [_result(history=[(50, 0)], final_incumbents=[(100, True), (90, True), (80, True)], seed=0),
                _result(history=[], final_incumbents=[(0, False), (0, False), (0, False)], seed=1),
                _result(history=[], final_incumbents=[(0, False), (0, False), (0, False)], seed=2)]
    deflt = {(10, i): _unreliable_default() for i in range(3)}
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)
    fails = {key for (key, _rs, _fr, _rel) in out["default_xcheck_failures"]}
    assert (10, 0) in fails                              # finite-frozen vs +inf-live recorded
    assert out["default_PI"][(10, 0)] == pytest.approx(0.5)   # frozen still authoritative for the gate
    with pytest.raises(ValueError):
        score_verdict(cand, deflt, baselines, require_largest_n=False, strict_xcheck=True)


def test_score_verdict_partial_freeze_stratum_recorded_not_raised():
    # Finding 4: a stratum with frozen B_I/L_I present but default_PI None (the default_unreliable freeze
    # state) must be RECORDED in default_pi_missing and excluded from the comparison — NOT raise mid-verdict.
    baselines, cand, deflt = _pass_setup(sizes=(10,))
    baselines[(3000, 0)] = _bl(default_PI=None)          # L_I/B_I present, default_PI withheld
    cand[(3000, 0)] = _bank(80, [(100, True), (90, True), (80, True)])
    deflt[(3000, 0)] = _bank(50, [(100, True), (95, True), (90, True)])
    out = score_verdict(cand, deflt, baselines, require_largest_n=False)   # must not raise
    assert (3000, 0) in out["default_pi_missing"]
    assert (3000, 0) not in out["candidate_PI"]          # excluded — no default anchor to compare
    assert (3000, 0) not in out["default_PI"]            # never coerced to a 0 anchor
    assert "overall_pass" in out
