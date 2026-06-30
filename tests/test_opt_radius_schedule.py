"""bd w29 (M5 / 71e): continuous oracle-indexed opt-radius DECAY lever — Python.

End-to-end faithfulness gates for the lever (the C-level pure-evaluator + ctg
bit-for-bit tests live in tests/test_opt_radius_schedule.c):

  * param validation (set-time domain guards);
  * NEGATIVE CONTROL — a schedule degenerating to a constant (r_start==r_end==r*)
    reproduces the STATIC opt_branching_radius=r* arm BIT-FOR-BIT (identical
    objective AND identical oracle-indexed history), single worker / fixed seed;
  * single-worker determinism with the schedule armed;
  * LIVENESS — a real decay (r_start != r_end) drives a feasible solve whose
    realized opt-phase radius sits strictly between the two endpoints (the hook
    fired and the radius varied across rounds);
  * SCALE-INVARIANCE — the scheduled lever's realized radius (mean/var) and f(n)
    are indistinguishable across n (keyed on the T(n)-normalized oracle fraction,
    NORTHSTAR §1.5), mirroring the static-radius positive control.
"""
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE


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


# --------------------------------------------------------------------------- #
# param validation
# --------------------------------------------------------------------------- #

class TestValidation:
    @pytest.mark.parametrize("key", ["opt_radius_schedule_r_start",
                                     "opt_radius_schedule_r_end",
                                     "opt_radius_schedule_gamma"])
    @pytest.mark.parametrize("bad", [0.0, -1.0, -0.001])
    def test_rejects_nonpositive(self, key, bad):
        m = _build()
        with pytest.raises(ValueError):
            m.set_param(key, bad)

    def test_accepts_positive(self):
        m = _build()
        m.set_param("opt_radius_schedule_r_start", 8.0)
        m.set_param("opt_radius_schedule_r_end", 2.0)
        m.set_param("opt_radius_schedule_gamma", 2.5)
        assert m._params["opt_radius_schedule_r_start"] == 8.0
        assert m._params["opt_radius_schedule_r_end"] == 2.0
        assert m._params["opt_radius_schedule_gamma"] == 2.5

    def test_unknown_schedule_param_rejected(self):
        m = _build()
        with pytest.raises(ValueError):
            m.set_param("opt_radius_schedule_bogus", 1.0)


# --------------------------------------------------------------------------- #
# NEGATIVE CONTROL: schedule(r_start==r_end==r*) == static opt radius r*, bit-for-bit
# --------------------------------------------------------------------------- #

class TestNegativeControlBitForBit:
    @pytest.mark.parametrize("seed", [1, 7, 42, 2024])
    @pytest.mark.parametrize("r_star", [2.0, 4.0])
    def test_degenerate_schedule_matches_static(self, seed, r_star):
        """A schedule with r_start==r_end==r* must reproduce the static
        opt_branching_radius=r* arm EXACTLY (objective + full oracle-indexed
        history), proving 'schedule degenerates to constant' bit-for-bit."""
        r_static, h_static = _solve({"opt_branching_radius": r_star}, seed=seed)
        r_deg, h_deg = _solve(
            {"opt_branching_radius": r_star,
             "opt_radius_schedule_r_start": r_star,
             "opt_radius_schedule_r_end": r_star}, seed=seed)
        assert r_static.objective == r_deg.objective
        assert r_static.feasible == r_deg.feasible
        assert h_static == h_deg, "degenerate schedule diverged from static arm"

    def test_degenerate_schedule_gamma_invariant(self):
        """With r_start==r_end the shape exponent gamma is irrelevant: any gamma
        reproduces the same constant trajectory bit-for-bit."""
        _r0, h0 = _solve(
            {"opt_branching_radius": 2.0,
             "opt_radius_schedule_r_start": 2.0, "opt_radius_schedule_r_end": 2.0,
             "opt_radius_schedule_gamma": 1.0}, seed=11)
        _r1, h1 = _solve(
            {"opt_branching_radius": 2.0,
             "opt_radius_schedule_r_start": 2.0, "opt_radius_schedule_r_end": 2.0,
             "opt_radius_schedule_gamma": 5.0}, seed=11)
        assert h0 == h1


# --------------------------------------------------------------------------- #
# determinism with the schedule armed
# --------------------------------------------------------------------------- #

class TestDeterminism:
    @pytest.mark.parametrize("gamma", [1.0, 0.5, 2.0])
    def test_same_seed_same_trajectory(self, gamma):
        sched = {"opt_radius_schedule_r_start": 8.0,
                 "opt_radius_schedule_r_end": 2.0,
                 "opt_radius_schedule_gamma": gamma}
        _r1, h1 = _solve(sched, seed=99)
        _r2, h2 = _solve(sched, seed=99)
        assert h1 == h2, "schedule must be deterministic under a fixed seed (single worker)"


# --------------------------------------------------------------------------- #
# LIVENESS: a real decay varies the realized opt radius between endpoints
# --------------------------------------------------------------------------- #

class TestLiveness:
    def test_decay_is_scheduled_between_endpoints(self):
        """Solve a synthetic instance with a decay schedule and confirm the
        realized opt-phase radius (from branch_diagnostics) sits strictly between
        r_end and r_start — i.e. the radius genuinely varied across rounds (it is
        neither pinned at the broad start nor the tight end)."""
        from benchmarks.scale_invariance import radius_profile
        p = radius_profile(
            1000, index=0, seed=0,
            params={"opt_radius_schedule_r_start": 8.0,
                    "opt_radius_schedule_r_end": 2.0},
            num_workers=4, M=1200)
        assert p["feasible"]
        assert p["opt_candidates"] > 0
        # Time-averaged realized radius is an interior value (broad start +
        # tight end). Bounds are generous to stay non-flaky but still exclude
        # "pinned at an endpoint".
        assert 2.0 < p["r_mean"] < 8.0, f"realized r_mean {p['r_mean']} not interior"

    def test_decay_differs_from_broad_constant(self):
        """The decay schedule's realized radius must differ from the broad
        constant (r=8) — guards against the hook being a silent no-op."""
        from benchmarks.scale_invariance import radius_profile
        decay = radius_profile(
            1000, index=0, seed=0,
            params={"opt_radius_schedule_r_start": 8.0,
                    "opt_radius_schedule_r_end": 2.0},
            num_workers=4, M=1200)
        const = radius_profile(1000, index=0, seed=0, radius=8.0,
                               num_workers=4, M=1200)
        assert decay["r_mean"] < const["r_mean"] - 0.5, \
            "decay 8->2 should tighten the realized radius vs constant r=8"


# --------------------------------------------------------------------------- #
# SCALE-INVARIANCE of the scheduled lever (NORTHSTAR §9, criterion 4)
# --------------------------------------------------------------------------- #

class TestScaleInvariance:
    # Same indistinguishability bands as the static positive control
    # (tests/test_scale_invariance.py): the scheduled lever is keyed on the
    # T(n)-normalized oracle fraction, so its realized-radius PROFILE is the same
    # function of normalized progress at every n => the aggregate is invariant.
    TOL_F = 0.10
    TOL_RMEAN = 0.10
    TOL_RVAR = 0.30

    def test_scheduled_lever_is_scale_invariant(self):
        pytest.importorskip("scipy")
        from benchmarks.scale_invariance import collect_profiles, cross_n_summary
        sched = {"opt_radius_schedule_r_start": 8.0, "opt_radius_schedule_r_end": 2.0}
        profs = collect_profiles([100, 1000], n_instances=3, seeds=(0,),
                                 params=sched, num_workers=4, M=1200)
        for n, ps in profs.items():
            for p in ps:
                assert p["feasible"] and p["opt_candidates"] > 0, \
                    f"n={n} instance {p['index']} never profiled the opt phase"
        f = cross_n_summary(profs, "f")
        rm = cross_n_summary(profs, "r_mean")
        rv = cross_n_summary(profs, "r_var")
        assert f["rel_spread"] <= self.TOL_F, f"f(n) drifted: {f}"
        assert rm["rel_spread"] <= self.TOL_RMEAN, f"scheduled radius mean drifted: {rm}"
        assert rv["rel_spread"] <= self.TOL_RVAR, f"scheduled radius var drifted: {rv}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
