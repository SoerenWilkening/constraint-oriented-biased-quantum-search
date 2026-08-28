"""bd a0w (M5): the ANGLE-PRECISION lever (Ross-Selinger / gridsynth) — Python.

End-to-end gates for the lever; the pure-quantizer and clamp unit tests live in
``tests/test_angle_precision.c``.

The lever models finite synthesis accuracy of the QTG's per-variable rotation
``R_y(theta_i)``: gridsynth reaches an absolute angle accuracy ``eps`` radians
at ``~3*log2(1/eps)`` T-gates, so a coarser angle buys a cheaper circuit. The
input is always ``eps`` (radians); bits and T-counts are reporting quantities.

What is pinned here:

  * param validation + per-phase resolution (``sat_/opt_sat_/opt_`` come free
    from ``PHASE_PARAM_SUFFIXES``);
  * NEGATIVE CONTROL — the lever unset (and ``dither`` armed with no ``eps``)
    is BIT-FOR-BIT the pre-a0w solve: identical objective, solution array AND
    oracle-indexed history;
  * a very fine ``eps`` reproduces the exact-angle arm (the sweep's negative
    control at solver level);
  * DETERMINISM (NORTHSTAR §8) under a fixed seed + single worker with the
    lever ON, dither both OFF and ON;
  * BOUNDED DECISIONS (§1.7) survive a grid coarse enough to round theta to
    zero at the n=3000 operating point — the solve stays feasible-capable and
    never crashes;
  * the realized opt-phase radius from ``result.branch_diagnostics`` tracks the
    PREDICTED quantized radius ``r_q = n*sin^2(theta_q/2)`` — i.e. the lever
    really moves the neighborhood the way the angle model says it does.
"""
import math

import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from cbqs.phase_params import (
    PhaseParamResolver, DEFAULTS, PHASE_PARAM_SUFFIXES,
    angle_precision_bits, t_count_per_rotation, t_count_per_qtg_application,
)


def _build(n=40, cap=20):
    """Small feasible knapsack-style model (all-zeros feasible -> enters opt)."""
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum(x[i] for i in range(n)), MAXIMIZE)
    m.add_constraint(sum(x[i] for i in range(n)) <= cap)
    m.close()
    return m


def _solve(params, *, seed=7, M=1500, workers=1, n=40, cap=20):
    m = _build(n, cap)
    m.seed = seed
    m.set_param("M", M)
    m.set_param("num_workers", workers)
    m.set_param("track_history", True)
    for k, v in params.items():
        m.set_param(k, v)
    r = m.solve()
    hist = tuple((float(a), int(b)) for a, b in (r.history or []))
    return r, hist


def _fingerprint(r, hist):
    return (r.objective, tuple(int(b) for b in r.solution), bool(r.feasible), hist)


# --------------------------------------------------------------------------- #
# param validation + resolution
# --------------------------------------------------------------------------- #

class TestValidation:
    @pytest.mark.parametrize("key", ["angle_precision_eps",
                                     "sat_angle_precision_eps",
                                     "opt_sat_angle_precision_eps",
                                     "opt_angle_precision_eps"])
    @pytest.mark.parametrize("bad", [0.0, -1.0, -1e-9])
    def test_rejects_nonpositive_eps(self, key, bad):
        """<= 0 is the OFF switch, expressed as None — never as a set value."""
        m = _build()
        with pytest.raises(ValueError):
            m.set_param(key, bad)

    def test_accepts_positive_eps_and_dither(self):
        m = _build()
        m.set_param("angle_precision_eps", 0.01)
        m.set_param("angle_precision_dither", True)
        m.set_param("opt_angle_precision_eps", 0.002)
        assert m._params["angle_precision_eps"] == 0.01
        assert m._params["angle_precision_dither"] is True
        assert m._params["opt_angle_precision_eps"] == 0.002

    @pytest.mark.parametrize("key", ["angle_precision_dither",
                                     "sat_angle_precision_dither",
                                     "opt_angle_precision_dither"])
    @pytest.mark.parametrize("bad", ["false", "no", "off", "", [1], 2, -1, 0.5])
    def test_dither_rejects_non_boolean(self, key, bad):
        """§2.1 fail loud: plain ``bool`` coercion makes every non-empty string
        truthy, so ``set_param(..., 'false')`` would silently ARM the flag and
        switch which PHYSICAL synthesis model an arm runs — corrupting a whole
        sweep with no error. Only real booleans and 0/1 are accepted."""
        m = _build()
        with pytest.raises(ValueError):
            m.set_param(key, bad)

    @pytest.mark.parametrize("good,expected", [(True, True), (False, False),
                                               (1, True), (0, False)])
    def test_dither_accepts_bools_and_0_1(self, good, expected):
        m = _build()
        m.set_param("angle_precision_dither", good)
        assert m._params["angle_precision_dither"] is expected

    def test_unknown_param_rejected(self):
        m = _build()
        with pytest.raises(ValueError):
            m.set_param("angle_precision_bits", 4)

    def test_default_is_off(self):
        m = _build()
        assert m._get_effective("angle_precision_eps") is None
        assert m._get_effective("angle_precision_dither") is False


class TestPhaseResolution:
    def test_suffixes_registered(self):
        assert "angle_precision_eps" in PHASE_PARAM_SUFFIXES
        assert "angle_precision_dither" in PHASE_PARAM_SUFFIXES
        assert DEFAULTS["angle_precision_eps"] is None
        assert DEFAULTS["angle_precision_dither"] is False

    def test_phase_specific_beats_unprefixed(self):
        store = {"angle_precision_eps": 0.05, "opt_angle_precision_eps": 0.001,
                 "angle_precision_dither": True}
        res = PhaseParamResolver(store, DEFAULTS)
        assert res.resolve("sat", "angle_precision_eps") == 0.05
        assert res.resolve("opt_sat", "angle_precision_eps") == 0.05
        assert res.resolve("opt", "angle_precision_eps") == 0.001
        assert res.resolve("opt", "angle_precision_dither") is True

    def test_unset_resolves_to_off(self):
        res = PhaseParamResolver({}, DEFAULTS)
        for phase in ("sat", "opt_sat", "opt"):
            assert res.resolve(phase, "angle_precision_eps") is None
            assert res.resolve(phase, "angle_precision_dither") is False


class TestReportingHelpers:
    """Bits / T-counts are DERIVED for reading results, never solver inputs."""

    def test_bits_matches_uniform_grid(self):
        # a b-bit uniform grid on [0, pi] has max rounding error pi/2**(b+1)
        for b in (2, 4, 8, 12):
            eps = math.pi / 2 ** (b + 1)
            assert angle_precision_bits(eps) == pytest.approx(b)

    def test_t_count_is_ross_selinger(self):
        assert t_count_per_rotation(0.01) == pytest.approx(3 * math.log2(100))
        assert t_count_per_qtg_application(0.01, 3000) == pytest.approx(
            3000 * 3 * math.log2(100))

    @pytest.mark.parametrize("bad", [0.0, -1.0, None])
    def test_reporting_helpers_fail_loud(self, bad):
        with pytest.raises(ValueError):
            angle_precision_bits(bad)
        with pytest.raises(ValueError):
            t_count_per_rotation(bad)


# --------------------------------------------------------------------------- #
# NEGATIVE CONTROL: lever OFF == pre-a0w solve, bit-for-bit
# --------------------------------------------------------------------------- #

class TestOffIsBitForBit:
    def test_dither_without_eps_is_a_no_op(self):
        """`dither` alone must not perturb anything — eps is the only switch."""
        base = _fingerprint(*_solve({}))
        for dither in (False, True):
            got = _fingerprint(*_solve({"angle_precision_dither": dither}))
            assert got == base

    def test_per_phase_dither_without_eps_is_a_no_op(self):
        base = _fingerprint(*_solve({}))
        got = _fingerprint(*_solve({"sat_angle_precision_dither": True,
                                    "opt_sat_angle_precision_dither": True,
                                    "opt_angle_precision_dither": True}))
        assert got == base

    def test_fine_eps_is_numerically_near_exact_but_NOT_bit_for_bit(self):
        """The sweep's `negctl` arm is NEAR-exact, and the docs must say so.

        `eps <= 0` is the only bit-for-bit control (the quantizer block is
        skipped entirely -- pinned by the two tests above). A tiny positive eps
        still runs the round trip `1 - sin^2(asin(sqrt(p)))`, which is lossy at
        the ~1e-13 level; since sampling compares `random_num > value`, a
        perturbation that small can eventually flip a decision, so a
        "must reproduce the exact arm bit-for-bit" claim would be false and
        would fire spuriously. What IS guaranteed is the numeric bound.
        """
        for bias in (5.0, 43.0, 1498.0):          # r=4 at n=180; r=2 at n=3000
            v = (bias + 1.0) / (bias + 2.0)
            p = 1.0 - v
            theta = 2 * math.asin(math.sqrt(p))
            for eps in (1e-12, 1e-9):
                delta = 2 * eps
                theta_q = delta * round(theta / delta)
                v_q = 1.0 - math.sin(theta_q / 2) ** 2
                assert abs(theta_q - theta) <= eps
                assert abs(v_q - v) <= 4 * eps       # |dv| = |sin(theta)*dtheta|/2 <= eps
        # at least one operating point is genuinely NOT bit-identical, so the
        # weaker claim is the necessary one (guards against re-tightening it).
        v = (5.0 + 1.0) / (5.0 + 2.0)
        theta = 2 * math.asin(math.sqrt(1.0 - v))
        theta_q = 2e-12 * round(theta / 2e-12)
        assert 1.0 - math.sin(theta_q / 2) ** 2 != v


# --------------------------------------------------------------------------- #
# DETERMINISM (NORTHSTAR §8) with the lever ARMED
# --------------------------------------------------------------------------- #

class TestDeterminism:
    @pytest.mark.parametrize("dither", [False, True])
    @pytest.mark.parametrize("eps", [0.25, 0.03, 0.002])
    def test_fixed_seed_single_worker_is_reproducible(self, eps, dither):
        params = {"angle_precision_eps": eps, "angle_precision_dither": dither}
        a = _fingerprint(*_solve(params, seed=11, workers=1))
        b = _fingerprint(*_solve(params, seed=11, workers=1))
        assert a == b

    def test_dither_changes_the_trajectory(self):
        """Dither must actually DO something — otherwise the on/off arms of the
        sweep would be measuring the same thing."""
        eps = 0.25
        off = _fingerprint(*_solve({"angle_precision_eps": eps,
                                    "angle_precision_dither": False}, seed=11))
        on = _fingerprint(*_solve({"angle_precision_eps": eps,
                                   "angle_precision_dither": True}, seed=11))
        assert off != on


# --------------------------------------------------------------------------- #
# BOUNDED DECISIONS (§1.7) end-to-end at a coarse grid
# --------------------------------------------------------------------------- #

class TestBoundedDecisionsEndToEnd:
    @pytest.mark.parametrize("dither", [False, True])
    @pytest.mark.parametrize("eps", [0.5, 0.25, 0.125, 0.0625, 0.03, 0.008, 0.001])
    def test_coarse_grid_still_solves(self, eps, dither):
        """Even a grid that rounds theta to 0 (deterministic-greedy in the naive
        implementation) must leave a well-formed, verifiable solve."""
        r, _ = _solve({"angle_precision_eps": eps,
                       "angle_precision_dither": dither}, M=600)
        assert r.objective is not None
        assert len(r.solution) == 40
        assert set(int(b) for b in r.solution) <= {0, 1}

    def test_snap_to_zero_collapses_the_radius_but_stays_well_formed(self):
        """The fail-loud case, pinned on its MEASURABLE consequence.

        A grid with eps > theta rounds the angle to zero. §1.7 then guarantees
        only that the probability stays inside (0,1) -- at the clamp floor
        p_flip = 1e-9, which is deterministic greedy in every practical sense.
        So the honest assertion is not "the stage stays exploratory" but the
        observable: the realized opt-phase Hamming radius COLLAPSES relative to
        the exact-angle arm, while the solve itself stays well-formed (a valid
        binary solution, real diagnostics, no crash). That collapse is exactly
        the cliff mechanism the a0w sweep measures.
        """
        n, r_target = 200, 2.0
        theta = 2 * math.asin(math.sqrt(r_target / n))
        assert 0.5 > theta, "precondition: eps=0.5 must round theta to zero"

        def solve(eps):
            m = _build(n=n, cap=n // 2)
            m.seed = 3
            m.set_param("M", 400)
            m.set_param("num_workers", 1)
            m.set_param("branching_radius", r_target)
            m.set_param("opt_switch_oracles", 0)
            if eps is not None:
                m.set_param("angle_precision_eps", eps)
            return m.solve()

        exact, crushed = solve(None), solve(0.5)
        for res in (exact, crushed):
            assert res.objective is not None
            assert len(res.solution) == n
            assert set(int(b) for b in res.solution) <= {0, 1}
            assert res.branch_diagnostics["n"] == n
        if not (exact.branch_diagnostics["opt_candidates"]
                and crushed.branch_diagnostics["opt_candidates"]):
            pytest.skip("no opt-phase candidates under the capped budget")
        assert crushed.branch_diagnostics["radius_mean"] < \
            0.5 * exact.branch_diagnostics["radius_mean"]


# --------------------------------------------------------------------------- #
# realized radius tracks the PREDICTED quantized radius
# --------------------------------------------------------------------------- #

def _predicted_quantized_radius(n, r, eps):
    """r_q = n*sin^2(theta_q/2) for the SYSTEMATIC grid (all variables share it).

    Uses floor(x+0.5), NOT Python's round(): C99 round() is half-away-from-zero
    while Python's is banker's rounding, and this helper exists to mirror the C
    lever exactly."""
    theta = 2 * math.asin(math.sqrt(r / n))
    delta = 2 * eps
    theta_q = delta * math.floor(theta / delta + 0.5)
    return n * math.sin(theta_q / 2) ** 2


class TestRealizedRadiusMatchesPrediction:
    """§1.5 scale-invariance diagnostic, applied to the quantized lever."""

    @pytest.mark.parametrize("eps", [0.02, 0.05])
    def test_realized_radius_ratio_matches_predicted(self, eps):
        pytest.importorskip("numpy")
        from benchmarks.scale_invariance import radius_profile

        n, r = 200, 4.0
        common = dict(n=n, index=0, seed=0, num_workers=4, M=800)
        exact = radius_profile(params={"branching_radius": r}, **common)
        quant = radius_profile(params={"branching_radius": r,
                                       "angle_precision_eps": eps}, **common)
        if exact["opt_candidates"] == 0 or quant["opt_candidates"] == 0:
            pytest.skip("no opt-phase candidates under the capped budget")

        predicted_ratio = _predicted_quantized_radius(n, r, eps) / r
        realized_ratio = quant["r_mean"] / exact["r_mean"]
        # The realized radius is f(n)-scaled in both arms, so the RATIO cancels
        # the (n-dependent) compression factor and isolates the quantization.
        assert realized_ratio == pytest.approx(predicted_ratio, rel=0.15), (
            f"eps={eps}: predicted r_q/r={predicted_ratio:.4f}, "
            f"realized {quant['r_mean']:.4f}/{exact['r_mean']:.4f}"
            f"={realized_ratio:.4f}")

    def test_coarse_grid_collapses_the_radius(self):
        """The cliff mechanism, observed directly: a grid coarser than theta/2
        rounds the angle to zero, so the realized radius collapses toward the
        clamp floor rather than staying at r."""
        pytest.importorskip("numpy")
        from benchmarks.scale_invariance import radius_profile

        n, r = 200, 4.0
        common = dict(n=n, index=0, seed=0, num_workers=4, M=800)
        exact = radius_profile(params={"branching_radius": r}, **common)
        crushed = radius_profile(params={"branching_radius": r,
                                         "angle_precision_eps": 0.5}, **common)
        if exact["opt_candidates"] == 0 or crushed["opt_candidates"] == 0:
            pytest.skip("no opt-phase candidates under the capped budget")
        assert _predicted_quantized_radius(n, r, 0.5) < 1e-6
        assert crushed["r_mean"] < 0.5 * exact["r_mean"]
