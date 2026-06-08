"""Tests for the M1 primal-integral fitness metric (bd 8an.2, NORTHSTAR §6/§8/§13).

Pure-function tests: no solve, no built extension — the metric operates on already-extracted
``result.history`` / ``result.final_incumbents`` plain-Python structures, so a lightweight stub
stands in for ``OptimizeResult``. Golden PI values are hand-computed in the module design and
re-derived in the comments here (CLAUDE.md §2.2 RED-GREEN: assert against known-correct numbers,
not "it runs"). The one real-data test is skipped unless ``CBQS_BENCHMARKS_DIR`` is set.
"""
import math
import os
import types

import pytest

from benchmarks.metric import (
    GAMMA_MAX,
    PI_EPS,
    EXPLORE_FLOOR_FRACTION,
    NOISE_MARGIN_K,
    LARGEST_N,
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
)


def _result(history=None, final_incumbents=None):
    """Minimal OptimizeResult stand-in (the metric only duck-types .history/.final_incumbents)."""
    return types.SimpleNamespace(
        history=list(history) if history is not None else [],
        final_incumbents=list(final_incumbents) if final_incumbents is not None else [],
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
