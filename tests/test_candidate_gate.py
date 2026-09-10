"""Tests for the M3 candidate pre-scoring gate (benchmarks/candidate_gate.py, bd 8an.4.2).

The gate composes the NORTHSTAR §10 pre-scoring checks into one ``admit(candidate)``.
Its decision logic is PURE over resolved params / a scale-invariance summary, so the
allow-list and the pass/fail decisions are unit-tested with no solve (the bulk here);
the solve-based summary producer is smoke-tested only when the C extension is present.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import candidate_gate as cg  # noqa: E402
from benchmarks.candidate_gate import (  # noqa: E402
    LEGAL_LEVER_PARAMS,
    admit,
    check_param_allowlist,
    check_radius_realization,
    check_scale_invariance,
)


# --------------------------------------------------------------------------- #
# (i) param / lever allow-list — pure, the no-free-relabel / equal-T(n) check.
# --------------------------------------------------------------------------- #

def test_legal_lever_params_cover_phase_prefixed_and_switch():
    # the 6 phase-aware levers × {unprefixed, sat_, opt_sat_, opt_} + the switch
    assert "opt_branching_radius" in LEGAL_LEVER_PARAMS
    assert "branching_radius" in LEGAL_LEVER_PARAMS
    assert "opt_sat_branching_radius" in LEGAL_LEVER_PARAMS
    assert "opt_branching_weights" in LEGAL_LEVER_PARAMS
    assert "opt_variable_priorities" in LEGAL_LEVER_PARAMS
    assert "opt_switch_oracles" in LEGAL_LEVER_PARAMS


def test_angle_precision_is_excluded_from_the_lever_surface():
    """bd a0w: the angle-precision lever must NOT be candidate-settable (§1.1).

    ``LEGAL_LEVER_PARAMS`` is derived from ``phase_params.DEFAULTS`` so it cannot
    drift from the C param surface — but that derivation is a TRAPDOOR: any new
    phase suffix silently becomes candidate-settable. ``angle_precision_eps``
    moves cost on the Ross-Selinger **T-count-per-oracle** axis, which the
    equal-``T(n)`` ORACLE A/B does not price. A tuned candidate could therefore
    buy objective with unpriced circuit cost — exactly the "no free relabel"
    breach §1.1 forbids. It stays a HARNESS-level knob, like ``M`` and
    ``opt_sample_cap``, and belongs in ``_FAITHFULNESS_BREACH_PARAMS``.
    """
    leaked = sorted(k for k in LEGAL_LEVER_PARAMS if "angle_precision" in k)
    assert leaked == [], f"angle-precision leaked into the lever surface: {leaked}"
    # 6 lever suffixes x {unprefixed, sat_, opt_sat_, opt_} + opt_switch_oracles
    assert len(LEGAL_LEVER_PARAMS) == 25


def test_angle_precision_is_rejected_as_a_faithfulness_breach():
    ok, reasons = check_param_allowlist({"opt_branching_radius": 2.0,
                                         "opt_angle_precision_eps": 0.5})
    assert not ok
    assert any("opt_angle_precision_eps" in r for r in reasons)
    assert any("T-count" in r or "T-gate" in r for r in reasons), reasons


def test_flat_import_fallback_lever_surface_matches_the_package_one():
    """The ImportError fallback DEFAULTS must enumerate the SAME lever suffixes
    as cbqs.phase_params, or a flat-layout run gets a different legal set."""
    from cbqs.phase_params import DEFAULTS as PKG_DEFAULTS
    assert set(cg._FALLBACK_DEFAULTS) == set(PKG_DEFAULTS)


def test_allowlist_accepts_pure_radius_switch_schedule():
    ok, reasons = check_param_allowlist(
        {"opt_sat_branching_radius": 2.0, "opt_branching_radius": 6.0,
         "opt_switch_oracles": 0})
    assert ok and reasons == []


def test_allowlist_rejects_budget_override_as_faithfulness_breach():
    # overriding M breaks equal-T(n) pricing (NORTHSTAR §5) — must be a named breach
    ok, reasons = check_param_allowlist({"opt_branching_radius": 6.0, "M": 999})
    assert not ok
    assert any("M" in r and "faithfulness" in r.lower() for r in reasons)


def test_allowlist_rejects_cost_model_params():
    for bad in ("num_workers", "opt_sample_cap", "depth_look_ahead",
                "look_ahead_factor"):
        ok, reasons = check_param_allowlist({"opt_branching_radius": 6.0, bad: 4})
        assert not ok, bad
        assert any(bad in r for r in reasons), bad


def test_allowlist_rejects_unknown_param():
    ok, reasons = check_param_allowlist({"opt_branching_radius": 6.0, "nonsense": 1})
    assert not ok
    assert any("nonsense" in r for r in reasons)


# --------------------------------------------------------------------------- #
# (iii) scale-invariance decision — pure over a summary dict; anti-vacuous.
# --------------------------------------------------------------------------- #

def _summary(r_spread=0.03, f_spread=0.03, coverage=None):
    return {
        "r_mean": {"rel_spread": r_spread, "per_n_median": {100: 6.0, 1000: 6.0}},
        "f": {"rel_spread": f_spread, "per_n_median": {100: 0.9, 1000: 0.9}},
        "coverage": coverage or {100: 1.0, 1000: 1.0},
    }


def test_scale_invariance_accepts_stable_radius():
    ok, reasons = check_scale_invariance(_summary(0.03, 0.03))
    assert ok and reasons == []


def test_scale_invariance_rejects_radius_drift():
    ok, reasons = check_scale_invariance(_summary(r_spread=0.9, f_spread=0.03))
    assert not ok
    assert any("radius" in r.lower() for r in reasons)


def test_scale_invariance_rejects_free_fraction_drift():
    ok, reasons = check_scale_invariance(_summary(r_spread=0.03, f_spread=0.5))
    assert not ok
    assert any("f(n)" in r or "free" in r.lower() for r in reasons)


def test_scale_invariance_is_not_vacuous_on_infeasibility():
    # landmine #12: a candidate that makes instances infeasible yields no opt
    # profiles -> rel_spread could read clean over the surviving points. Low
    # feasibility coverage must FAIL, not silently pass by absence of data.
    ok, reasons = check_scale_invariance(
        _summary(0.0, 0.0, coverage={100: 1.0, 1000: 0.1}))
    assert not ok
    assert any("coverage" in r.lower() for r in reasons)


def test_scale_invariance_rejects_nan_spread():
    ok, reasons = check_scale_invariance(_summary(r_spread=float("inf")))
    assert not ok


# --------------------------------------------------------------------------- #
# (iv) θ radius-neutrality / lever fidelity — realized opt radius ≈ target r.
# --------------------------------------------------------------------------- #

def test_radius_realization_accepts_on_target():
    # realized r_mean ≈ target radius at every scale-stable n (θ did not shift it)
    summary = _summary()
    ok, reasons = check_radius_realization(summary, target_by_n={100: 6.0, 1000: 6.0})
    assert ok and reasons == []


def test_radius_realization_flags_theta_radius_shift():
    # θ pushed realized radius to ~9 while the scalar set r=6 -> not radius-neutral
    summary = _summary()
    summary["r_mean"]["per_n_median"] = {100: 9.0, 1000: 9.0}
    ok, reasons = check_radius_realization(summary, target_by_n={100: 6.0, 1000: 6.0})
    assert not ok
    assert any("realiz" in r.lower() or "target" in r.lower() for r in reasons)


def test_radius_realization_skips_when_no_target():
    # candidate left the opt radius at the default (no explicit target) -> the
    # fidelity check is skipped (cross-n scale-invariance still applies).
    ok, reasons = check_radius_realization(_summary(), target_by_n={})
    assert ok and reasons == []


# --------------------------------------------------------------------------- #
# admit() composition — pure-path (scale_check off / injected summary).
# --------------------------------------------------------------------------- #

def _radius_factory(n, c1, c2, c3):
    return {"opt_sat_branching_radius": 2.0, "opt_branching_radius": 6.0,
            "opt_switch_oracles": 0}


def test_admit_param_only_path_passes(monkeypatch):
    # scale_check=False exercises just the pure allow-list path (no solve)
    res = admit(_radius_factory, scale_check=False)
    assert res.ok
    assert res.reasons == []
    assert "opt_branching_radius" in res.params


def test_admit_rejects_budget_override_without_solving(monkeypatch):
    bad = lambda n, c1, c2, c3: {"opt_branching_radius": 6.0, "M": 5}
    res = admit(bad, scale_check=False)
    assert not res.ok
    assert any("param-allowlist" in r for r in res.reasons)


def test_admit_with_injected_scale_summary_composes_all_checks():
    # inject a clean summary -> full gate passes without any solve
    res = admit(_radius_factory, scale_summary=_summary(0.03, 0.03))
    assert res.ok, res.reasons


def test_admit_with_injected_failing_summary_reports_scale_reason():
    res = admit(_radius_factory, scale_summary=_summary(r_spread=0.9))
    assert not res.ok
    assert any("scale-invariance" in r for r in res.reasons)


def test_admit_aggregates_param_and_scale_reasons():
    bad = lambda n, c1, c2, c3: {"opt_branching_radius": 6.0, "num_workers": 2}
    res = admit(bad, scale_summary=_summary(r_spread=0.9))
    assert not res.ok
    assert any("param-allowlist" in r for r in res.reasons)
    assert any("scale-invariance" in r for r in res.reasons)


# --------------------------------------------------------------------------- #
# Solve-based smoke test — only with the C extension (mirrors test_scale_invariance).
# --------------------------------------------------------------------------- #

def test_radius_profile_accepts_params_dict():
    pytest.importorskip("cbqs")
    pytest.importorskip("scipy")
    from benchmarks.scale_invariance import radius_profile
    # a resolved per-phase params dict reaches the solver and produces an opt profile
    prof = radius_profile(100, index=0, seed=1,
                          params={"opt_branching_radius": 6.0},
                          num_workers=4, M=1500)
    assert prof["n"] == 100
    assert prof["opt_candidates"] >= 0
    assert prof["r_mean"] is None or math.isfinite(prof["r_mean"])
