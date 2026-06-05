"""End-to-end scale-invariance gate for the radius lever (bd 8an.1.7, M0g).

NORTHSTAR §9 generalization contract: on synthetic instances with matched
constraint-tightness, the realized Hamming-radius distribution (mean+variance)
and the free-decision fraction f(n) must be statistically indistinguishable
across n; f(n) drift is a rejection criterion.

This is the CI gate. It asserts the DISCRIMINATOR works — a scale-stable lever
is accepted and a drifting one is rejected — which is exactly how the §10
candidate gate uses it ("scale-invariance end-to-end test passes"):

  * POSITIVE control — the radius lever (bias = n/r − 2) over n∈{100,1000}:
    realized radius (mean+var) and f(n) are indistinguishable (small rel-spread).
  * NEGATIVE control — a fixed scalar bias (not n-scaled, NORTHSTAR §1.5
    "do not use it directly") over the same n: the realized radius drifts by
    nearly an order of magnitude and is correctly flagged. Without this, a
    too-loose gate would silently pass everything (§13 negative control).
  * SMALL-n drift control — n=10 vs n=1000 on the radius lever: the n=10
    small-n compression (f≈0.5, ~43% radius compression — squarely in §4's
    predicted 38–56% band) is correctly detected. n=10 is therefore used as a
    drift control, not asserted invariant (see bd 8an.1.7 finding; the full
    n∈{10,100,1000,3000} characterization lives in
    benchmarks/scale_invariance_characterization.py).

The full sweep + variance characterization is intentionally NOT a CI gate
(it solves n=3000); this gate stays fast (capped M, few instances/workers).
"""
import pytest

pytest.importorskip("cbqs")
pytest.importorskip("scipy")

from benchmarks.scale_invariance import collect_profiles, cross_n_summary
from benchmarks.synthetic_eq29 import tightness, CAP_TIGHTNESS, COV_TIGHTNESS

# --- indistinguishability bands (calibrated bd 8an.1.7) -------------------
# Positive control sits at ~0.03 (f, r_mean) and ~0.05 (r_var); the fixed-bias
# negative control sits at ~1.5 (r_mean). These bands separate them by >15x.
TOL_F = 0.10
TOL_RMEAN = 0.10
TOL_RVAR = 0.30

# Fast-gate solve config (the characterization script uses heavier settings).
RADIUS = 8.0
GATE_N = [100, 1000]
N_INSTANCES = 3
NUM_WORKERS = 4
M_CAP = 1200


@pytest.fixture(scope="module")
def positive_profiles():
    """Radius lever over the scale-stable regime — solved once, reused."""
    return collect_profiles(GATE_N, n_instances=N_INSTANCES, seeds=(0,),
                            radius=RADIUS, num_workers=NUM_WORKERS, M=M_CAP)


def test_matched_tightness_across_n():
    """The synthetic family is matched: capacity/covering tightness ratios equal
    the configured constants and are identical (up to integer RHS rounding) at
    every n. Guards against an accidental generator change that breaks the §9
    precondition that tightness is fixed across n (c1/Σw1, c2/Σw2 fixed)."""
    for n in [10, 100, 1000, 3000]:
        cap_t, cov_t = tightness(n)
        # Realized ratio = round(t·mass)/mass ≈ t; rounding error shrinks with n.
        assert cap_t == pytest.approx(CAP_TIGHTNESS, abs=0.05)
        assert cov_t == pytest.approx(COV_TIGHTNESS, abs=0.05)
    # Cross-n equality (the matched-family invariant), tight at large n.
    big = [tightness(n) for n in [1000, 3000]]
    assert big[0] == pytest.approx(big[1], abs=1e-3), \
        f"tightness drifted across large n: {big}"


def test_instances_reach_opt_phase(positive_profiles):
    """Every profiled instance must be feasible and generate opt-phase
    candidates, otherwise f(n)/radius are undefined and the gate is vacuous."""
    for n, profs in positive_profiles.items():
        for p in profs:
            assert p["feasible"], f"n={n} instance {p['index']} infeasible"
            assert p["opt_candidates"] > 0, \
                f"n={n} instance {p['index']} never entered opt phase"


def test_radius_lever_is_scale_invariant(positive_profiles):
    """POSITIVE control: realized radius (mean+var) and f(n) are indistinguishable
    across n for the radius lever (NORTHSTAR §9)."""
    f = cross_n_summary(positive_profiles, "f")
    rm = cross_n_summary(positive_profiles, "r_mean")
    rv = cross_n_summary(positive_profiles, "r_var")
    assert f["rel_spread"] <= TOL_F, f"f(n) drifted: {f}"
    assert rm["rel_spread"] <= TOL_RMEAN, f"radius mean drifted: {rm}"
    assert rv["rel_spread"] <= TOL_RVAR, f"radius variance drifted: {rv}"
    # Realized radius tracks the target r at every scale-stable n (≈ f(n)·r, and
    # f≈1 here): a coarse sanity bound that the lever isn't collapsed/blown up.
    for n, med in rm["per_n_median"].items():
        assert 0.6 * RADIUS <= med <= 1.4 * RADIUS, \
            f"n={n} realized radius {med:.2f} far from target {RADIUS}"


def test_fixed_bias_drift_is_detected():
    """NEGATIVE control: a fixed scalar bias (not n-scaled) makes the realized
    radius scale with n; the SAME check must reject it. Proves the gate has
    discriminating power (§13 negative control)."""
    profiles = collect_profiles(GATE_N, n_instances=2, seeds=(0,),
                                bias=4.0, num_workers=NUM_WORKERS, M=M_CAP)
    rm = cross_n_summary(profiles, "r_mean")
    assert rm["rel_spread"] > TOL_RMEAN, \
        f"fixed-bias radius drift was NOT detected (gate too loose): {rm}"


def test_small_n_compression_is_detected():
    """SMALL-n drift control: n=10 sits in the small-n compression regime
    (f≈0.5, ~43% radius compression). The gate must flag n=10-vs-large-n as
    drifting — this is the documented bd 8an.1.7 finding and the reason n=10 is
    a drift control, not an asserted-invariant size."""
    profiles = collect_profiles([10, 1000], n_instances=2, seeds=(0,),
                                radius=RADIUS, num_workers=NUM_WORKERS, M=M_CAP)
    f = cross_n_summary(profiles, "f")
    rm = cross_n_summary(profiles, "r_mean")
    assert (f["rel_spread"] > TOL_F) or (rm["rel_spread"] > TOL_RMEAN), \
        f"small-n compression was NOT detected: f={f}, r_mean={rm}"
    # The compression is specifically at the small size.
    assert f["per_n_median"][10] < f["per_n_median"][1000], \
        "expected lower free-decision fraction at n=10 (more forced decisions)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
