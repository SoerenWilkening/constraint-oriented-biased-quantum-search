"""
Unit tests for M22: exploration signal + constrained sampling.

Tests make_exploration_signal() in cbqs.ml.signals and constrained_*_params()
functions in cbqs.ml.data_collection.
"""

import numpy as np
import pytest

from cbqs.ml.signals import make_exploration_signal
from cbqs.ml.data_collection import (
    constrained_sat_params,
    constrained_opt_sat_params,
    constrained_opt_only_params,
)
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
# Exploration Signal
# ===================================================================


class TestExplorationSignal:
    """Tests for make_exploration_signal -- objective-first, time tiebreaker."""

    def test_exploration_signal_ranks_by_objective_first(self):
        """Higher objective always gets higher score, regardless of time."""
        signal_fn = make_exploration_signal()
        # Better objective but slower
        better_obj = _make_result(objective=100.0,
                                  history=[(100.0, 5.0)],
                                  solve_time=10000.0)
        # Worse objective but faster
        worse_obj = _make_result(objective=50.0,
                                 history=[(50.0, 0.1)],
                                 solve_time=10000.0)
        assert signal_fn(better_obj) > signal_fn(worse_obj)

    def test_exploration_signal_tiebreaks_by_time(self):
        """Equal objective: faster time-to-best gets higher score."""
        signal_fn = make_exploration_signal()
        fast = _make_result(objective=100.0,
                            history=[(100.0, 0.5)],
                            solve_time=10000.0)
        slow = _make_result(objective=100.0,
                            history=[(100.0, 5.0)],
                            solve_time=10000.0)
        assert signal_fn(fast) > signal_fn(slow)

    def test_exploration_signal_equal_obj_prefers_faster(self):
        """With same objective, the tiebreaker should differentiate."""
        signal_fn = make_exploration_signal()
        fast = _make_result(objective=42.0,
                            history=[(42.0, 0.01)],
                            solve_time=1000.0)
        slow = _make_result(objective=42.0,
                            history=[(42.0, 0.99)],
                            solve_time=1000.0)
        score_fast = signal_fn(fast)
        score_slow = signal_fn(slow)
        assert score_fast > score_slow

    def test_exploration_signal_better_obj_always_wins(self):
        """Even a tiny objective improvement beats any time difference."""
        signal_fn = make_exploration_signal()
        # Objective 100.001, very slow
        better = _make_result(objective=100.001,
                              history=[(100.001, 999.0)],
                              solve_time=1000000.0)
        # Objective 100.0, very fast
        worse = _make_result(objective=100.0,
                             history=[(100.0, 0.001)],
                             solve_time=1000000.0)
        assert signal_fn(better) > signal_fn(worse)


# ===================================================================
# Constrained Sampling
# ===================================================================


class TestConstrainedSatParams:
    """Tests for constrained_sat_params -- exploration-friendly bounds."""

    def test_constrained_sat_params_bias_in_range(self):
        """sat_branching_bias should be near n/4, within n/100 delta."""
        rng = np.random.default_rng(42)
        n_vars = 200
        for _ in range(50):
            params = constrained_sat_params(n_vars, rng)
            bias = params['sat_branching_bias']
            center = n_vars / 4.0
            delta_max = n_vars / 100.0
            assert center - delta_max <= bias <= center + delta_max

    def test_constrained_sat_params_weights_in_range(self):
        """sat_branching_weights should be in [-1, 1]."""
        rng = np.random.default_rng(123)
        n_vars = 50
        for _ in range(50):
            params = constrained_sat_params(n_vars, rng)
            weights = params['sat_branching_weights']
            assert len(weights) == n_vars
            for w in weights:
                assert -1.0 <= w <= 1.0

    def test_constrained_sat_params_branching_factor_in_range(self):
        """sat_branching_factor should be in [-1, 1]."""
        rng = np.random.default_rng(7)
        n_vars = 100
        for _ in range(50):
            params = constrained_sat_params(n_vars, rng)
            bf = params['sat_branching_factor']
            assert -1.0 <= bf <= 1.0

    def test_constrained_sat_params_bias_factor_fixed_one(self):
        """sat_bias_factor should always be exactly 1.0."""
        rng = np.random.default_rng(99)
        n_vars = 100
        for _ in range(50):
            params = constrained_sat_params(n_vars, rng)
            assert params['sat_bias_factor'] == 1.0


class TestConstrainedOptParams:
    """Tests for constrained_opt_sat_params and constrained_opt_only_params."""

    def test_constrained_opt_params_same_bounds(self):
        """opt_sat and opt params should respect the same bounds as sat."""
        rng = np.random.default_rng(55)
        n_vars = 200
        for _ in range(30):
            opt_sat = constrained_opt_sat_params(n_vars, rng)
            opt_only = constrained_opt_only_params(n_vars, rng)

            center = n_vars / 4.0
            delta_max = n_vars / 100.0

            # opt_sat bounds
            assert center - delta_max <= opt_sat['opt_sat_branching_bias'] <= center + delta_max
            assert opt_sat['opt_sat_bias_factor'] == 1.0
            assert -1.0 <= opt_sat['opt_sat_branching_factor'] <= 1.0
            for w in opt_sat['opt_sat_branching_weights']:
                assert -1.0 <= w <= 1.0

            # opt bounds
            assert center - delta_max <= opt_only['opt_branching_bias'] <= center + delta_max
            assert opt_only['opt_bias_factor'] == 1.0
            assert -1.0 <= opt_only['opt_branching_factor'] <= 1.0
            for w in opt_only['opt_branching_weights']:
                assert -1.0 <= w <= 1.0


class TestConstrainedParamsDiversity:
    """Test that constrained sampling produces diverse values."""

    def test_constrained_params_diverse_samples(self):
        """Multiple samples should produce different parameter values."""
        rng = np.random.default_rng(42)
        n_vars = 100
        biases = set()
        branching_factors = set()
        for _ in range(20):
            params = constrained_sat_params(n_vars, rng)
            biases.add(round(params['sat_branching_bias'], 6))
            branching_factors.add(round(params['sat_branching_factor'], 6))
        # With 20 samples, we should have multiple distinct values
        assert len(biases) > 5
        assert len(branching_factors) > 5
