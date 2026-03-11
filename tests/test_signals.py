"""
Unit tests for cbqs.ml.signals -- training signal computation.

Tests AUC (trapezoidal integration of incumbent curve), weighted combination
signal, and the signal factory.
"""

import pytest

from cbqs.ml.signals import compute_auc, compute_weighted, make_signal
from cbqs.result import OptimizeResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_result(**overrides):
    """Create an OptimizeResult with sensible defaults, overridden by kwargs."""
    defaults = dict(
        solution=[1, 0, 1, 0],
        objective=42.0,
        feasible=True,
        solve_time=100.0,
        preprocessing_time=50.0,
        iterations=5000,
        oracle_calls=250,
        history=[(38.0, 0.005), (42.0, 0.020)],
        verified=True,
        violations=None,
        num_threads=4,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


# ===================================================================
# AUC Computation
# ===================================================================


class TestComputeAUC:
    """Tests for compute_auc -- trapezoidal integration of incumbent curve."""

    def test_auc_single_point(self):
        """One incumbent entry: area = value * total_time."""
        history = [(10.0, 0.0)]
        total_time = 5.0
        auc = compute_auc(history, total_time)
        assert auc == pytest.approx(10.0 * 5.0)

    def test_auc_two_points(self):
        """Two points: trapezoidal integration.

        History: value=2.0 at t=0, value=6.0 at t=4. Total time=4.
        Area = 2.0 * 0 (initial to first point, t=0) + trap(0->4, 2->6) = 0
        Actually: from t=0 value=2, at t=4 value=6, total_time=4.
        Area under step+trap: from t=0 to t=4 with value starting at 2 then
        jumping to 6 at t=4. The incumbent holds value 2 from t=0 to t=4,
        then value 6 from t=4 to t=4 (no more time).
        AUC = 2.0 * (4 - 0) + 6.0 * (4 - 4) = 8.0

        Wait -- the trapezoidal rule on the incumbent curve means:
        We hold the previous incumbent value until a new one arrives.
        So from t=0 to t=4, the value is 2.0 (area = 2*4 = 8).
        At t=4, value jumps to 6.0 but total_time=4, so no more area.
        Total = 8.0.
        """
        history = [(2.0, 0.0), (6.0, 4.0)]
        auc = compute_auc(history, total_time=4.0)
        assert auc == pytest.approx(8.0)

    def test_auc_monotone_improving(self):
        """Increasing objective over time.

        History: (0, 0.0), (5, 1.0), (10, 3.0). Total time = 5.
        Area = 0 * (1-0) + 5 * (3-1) + 10 * (5-3)
             = 0 + 10 + 20 = 30
        """
        history = [(0.0, 0.0), (5.0, 1.0), (10.0, 3.0)]
        auc = compute_auc(history, total_time=5.0)
        assert auc == pytest.approx(30.0)

    def test_auc_empty_history(self):
        """Empty history returns 0."""
        auc = compute_auc([], total_time=10.0)
        assert auc == pytest.approx(0.0)

    def test_auc_normalized_by_time(self):
        """AUC / total_time gives average quality.

        Constant incumbent of 7.0 for 10 seconds.
        AUC = 70, AUC / 10 = 7.0 = average.
        """
        history = [(7.0, 0.0)]
        total_time = 10.0
        auc = compute_auc(history, total_time)
        avg = auc / total_time
        assert avg == pytest.approx(7.0)

    def test_auc_negative_objectives(self):
        """AUC works with negative objective values.

        History: (-10, 0.0), (-3, 2.0). Total time = 4.
        Area = -10 * (2-0) + -3 * (4-2) = -20 + -6 = -26
        """
        history = [(-10.0, 0.0), (-3.0, 2.0)]
        auc = compute_auc(history, total_time=4.0)
        assert auc == pytest.approx(-26.0)

    def test_auc_with_one_history_entry(self):
        """Single entry at non-zero time: area from that time to total_time.

        History: (5.0, 2.0). Total time = 6.
        Area = 5.0 * (6 - 2) = 20.0
        """
        history = [(5.0, 2.0)]
        auc = compute_auc(history, total_time=6.0)
        assert auc == pytest.approx(20.0)


# ===================================================================
# Weighted Combination
# ===================================================================


class TestComputeWeighted:
    """Tests for compute_weighted -- objective - lambda * time."""

    def test_weighted_basic(self):
        """score = obj - lambda * time."""
        score = compute_weighted(objective=100.0, time_to_best=5.0, lam=2.0,
                                 feasible=True)
        assert score == pytest.approx(100.0 - 2.0 * 5.0)

    def test_weighted_lambda_zero_equals_obj(self):
        """lambda=0 means pure objective score."""
        score = compute_weighted(objective=50.0, time_to_best=999.0, lam=0.0,
                                 feasible=True)
        assert score == pytest.approx(50.0)

    def test_weighted_high_lambda_penalizes_slow(self):
        """Slow solutions scored lower with high lambda."""
        fast = compute_weighted(objective=100.0, time_to_best=1.0, lam=10.0,
                                feasible=True)
        slow = compute_weighted(objective=100.0, time_to_best=10.0, lam=10.0,
                                feasible=True)
        assert fast > slow

    def test_weighted_infeasible_penalty(self):
        """Infeasible solution gets large negative score."""
        score = compute_weighted(objective=100.0, time_to_best=1.0, lam=1.0,
                                 feasible=False)
        assert score == pytest.approx(-1e6)

    def test_weighted_with_zero_time(self):
        """Zero time: score = objective."""
        score = compute_weighted(objective=75.0, time_to_best=0.0, lam=5.0,
                                 feasible=True)
        assert score == pytest.approx(75.0)

    def test_weighted_custom_infeasible_penalty(self):
        """Custom infeasible penalty value."""
        score = compute_weighted(objective=100.0, time_to_best=1.0, lam=1.0,
                                 feasible=False, infeasible_penalty=-500.0)
        assert score == pytest.approx(-500.0)


# ===================================================================
# Signal Factory
# ===================================================================


class TestMakeSignal:
    """Tests for make_signal -- factory returning scoring functions."""

    def test_signal_factory_auc(self):
        """Factory returns callable that computes AUC from a result."""
        signal_fn = make_signal('auc')
        result = _make_result(
            history=[(10.0, 0.0), (20.0, 1.0)],
            solve_time=2000.0,  # 2000 ms = 2 seconds
        )
        score = signal_fn(result)
        # AUC: 10 * (1-0) + 20 * (2-1) = 10 + 20 = 30
        assert score == pytest.approx(30.0)

    def test_signal_factory_weighted(self):
        """Factory returns callable that computes weighted from a result."""
        signal_fn = make_signal('weighted', lam=2.0)
        result = _make_result(
            objective=50.0,
            feasible=True,
            history=[(30.0, 0.5), (50.0, 1.5)],
            solve_time=3000.0,  # 3 seconds total
        )
        # time_to_best = last history entry time = 1.5s
        # score = 50 - 2 * 1.5 = 47.0
        score = signal_fn(result)
        assert score == pytest.approx(47.0)

    def test_signal_factory_unknown_raises(self):
        """Unknown signal name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown signal"):
            make_signal('unknown_signal')

    def test_signal_factory_auc_empty_history(self):
        """AUC signal with empty history returns 0."""
        signal_fn = make_signal('auc')
        result = _make_result(history=[], solve_time=1000.0)
        score = signal_fn(result)
        assert score == pytest.approx(0.0)

    def test_signal_factory_weighted_infeasible(self):
        """Weighted signal with infeasible result returns penalty."""
        signal_fn = make_signal('weighted', lam=1.0)
        result = _make_result(feasible=False, objective=100.0,
                              history=[(100.0, 0.5)], solve_time=1000.0)
        score = signal_fn(result)
        assert score == pytest.approx(-1e6)
