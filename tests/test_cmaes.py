"""
Unit tests for cbqs.ml.cmaes -- CMA-ES iterative parameter optimization.

Tests vector conversion helpers, CMA-ES search loop, warm-starting from
regressor predictions, per-generation logging, and convergence behavior.
"""

import pytest
import numpy as np

from cbqs.ml.cmaes import (
    CMAESOptimizer,
    params_to_vector,
    vector_to_params,
)
from cbqs.result import OptimizeResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_result(**overrides):
    """Create an OptimizeResult with sensible defaults."""
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
        num_threads=1,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


class FakeModel:
    """A fake model for testing CMA-ES without a real solver."""

    def __init__(self, n_vars=5, objective_fn=None):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._objective_fn = objective_fn

    def set_param(self, key, value):
        self._params[key] = value

    def solve(self):
        idx = self._solve_count
        self._solve_count += 1
        if self._objective_fn is not None:
            obj = self._objective_fn(idx, self._params)
        else:
            obj = 10.0 + idx
        return _make_result(
            objective=obj,
            feasible=True,
            history=[(obj, 0.01)],
            solve_time=50.0,
            num_threads=1,
        )


# ===================================================================
# params_to_vector / vector_to_params tests
# ===================================================================


class TestParamsToVector:
    """params_to_vector extracts scalar params into a flat numpy array."""

    def test_sat_params_round_trip(self):
        """SAT params convert to vector and back identically."""
        n_vars = 3
        params = {
            'sat_branching_weights': [1.0, 2.0, 3.0],
            'sat_variable_priorities': [0.5, -0.5, 0.0],
            'sat_branching_bias': 2.5,
            'sat_branching_factor': 1.2,
            'sat_bias_factor': 0.8,
        }
        vec = params_to_vector(params, 'sat', n_vars)
        restored = vector_to_params(vec, 'sat', n_vars)

        assert np.allclose(restored['sat_branching_weights'], params['sat_branching_weights'])
        assert np.allclose(restored['sat_variable_priorities'], params['sat_variable_priorities'])
        assert abs(restored['sat_branching_bias'] - 2.5) < 1e-9
        assert abs(restored['sat_branching_factor'] - 1.2) < 1e-9
        assert abs(restored['sat_bias_factor'] - 0.8) < 1e-9

    def test_opt_params_round_trip(self):
        """OPT params (opt_sat + opt) convert to vector and back."""
        n_vars = 2
        params = {
            'opt_sat_branching_weights': [1.0, 2.0],
            'opt_sat_variable_priorities': [0.1, 0.2],
            'opt_sat_branching_bias': 3.0,
            'opt_sat_branching_factor': 1.5,
            'opt_sat_bias_factor': 0.5,
            'opt_branching_weights': [3.0, 4.0],
            'opt_variable_priorities': [-0.1, -0.2],
            'opt_branching_bias': 4.0,
            'opt_branching_factor': 2.0,
            'opt_bias_factor': 1.0,
        }
        vec = params_to_vector(params, 'opt', n_vars)
        restored = vector_to_params(vec, 'opt', n_vars)

        for key in params:
            if isinstance(params[key], list):
                assert np.allclose(restored[key], params[key])
            else:
                assert abs(restored[key] - params[key]) < 1e-9

    def test_vector_length_sat(self):
        """SAT vector has length 2*n_vars + 3."""
        n_vars = 4
        params = {
            'sat_branching_weights': [1.0] * n_vars,
            'sat_variable_priorities': [0.0] * n_vars,
            'sat_branching_bias': 1.0,
            'sat_branching_factor': 1.0,
            'sat_bias_factor': 1.0,
        }
        vec = params_to_vector(params, 'sat', n_vars)
        assert len(vec) == 2 * n_vars + 3

    def test_vector_length_opt(self):
        """OPT vector has length 2*(2*n_vars + 3)."""
        n_vars = 4
        params = {
            'opt_sat_branching_weights': [1.0] * n_vars,
            'opt_sat_variable_priorities': [0.0] * n_vars,
            'opt_sat_branching_bias': 1.0,
            'opt_sat_branching_factor': 1.0,
            'opt_sat_bias_factor': 1.0,
            'opt_branching_weights': [1.0] * n_vars,
            'opt_variable_priorities': [0.0] * n_vars,
            'opt_branching_bias': 1.0,
            'opt_branching_factor': 1.0,
            'opt_bias_factor': 1.0,
        }
        vec = params_to_vector(params, 'opt', n_vars)
        assert len(vec) == 2 * (2 * n_vars + 3)


class TestVectorToParamsClipping:
    """vector_to_params clips values to valid ranges."""

    def test_bias_clipped_above_minus_one(self):
        """branching_bias is clipped to > -1."""
        n_vars = 2
        # Create a vector with bias = -5.0 (invalid)
        vec = np.array([1.0, 1.0, 0.0, 0.0, -5.0, 1.0, 1.0])
        restored = vector_to_params(vec, 'sat', n_vars)
        assert restored['sat_branching_bias'] > -1.0

    def test_weights_clipped_nonneg(self):
        """branching_weights are clipped to >= 0."""
        n_vars = 2
        vec = np.array([-1.0, -2.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        restored = vector_to_params(vec, 'sat', n_vars)
        for w in restored['sat_branching_weights']:
            assert w >= 0.0

    def test_factors_clipped_nonneg(self):
        """branching_factor and bias_factor are clipped to >= 0."""
        n_vars = 2
        vec = np.array([1.0, 1.0, 0.0, 0.0, 1.0, -3.0, -2.0])
        restored = vector_to_params(vec, 'sat', n_vars)
        assert restored['sat_branching_factor'] >= 0.0
        assert restored['sat_bias_factor'] >= 0.0


# ===================================================================
# CMAESOptimizer tests
# ===================================================================


class TestCMAESOptimizerBasic:
    """CMAESOptimizer runs the search loop and returns results."""

    def test_optimize_returns_best_params(self):
        """optimize() returns a dict with best_params, best_signal, log."""
        # Objective: closer to a known optimum in param space
        def obj_fn(idx, params):
            bias = params.get('sat_branching_bias', 5.0)
            return -abs(bias - 2.0)  # maximize = minimize distance

        model = FakeModel(n_vars=2, objective_fn=obj_fn)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=4,
            max_generations=3,
            sigma0=1.0,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)

        assert 'best_params' in result
        assert 'best_signal' in result
        assert 'log' in result
        assert isinstance(result['best_params'], dict)
        assert isinstance(result['best_signal'], float)

    def test_log_has_per_generation_entries(self):
        """Log contains one entry per generation with required fields."""
        model = FakeModel(n_vars=2)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=4,
            max_generations=5,
            sigma0=1.0,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)

        log = result['log']
        assert len(log) == 5
        for entry in log:
            assert 'generation' in entry
            assert 'best_signal' in entry
            assert 'mean_signal' in entry
            assert 'sigma' in entry


class TestCMAESWarmStart:
    """CMAESOptimizer uses initial_params for warm-starting."""

    def test_initial_params_sets_distribution_mean(self):
        """When initial_params provided, search starts from those values."""
        n_vars = 2
        initial = {
            'sat_branching_weights': [1.0, 1.0],
            'sat_variable_priorities': [0.0, 0.0],
            'sat_branching_bias': 3.0,
            'sat_branching_factor': 1.0,
            'sat_bias_factor': 1.0,
        }

        model = FakeModel(n_vars=n_vars)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=4,
            max_generations=2,
            sigma0=0.001,  # Very small sigma so candidates stay near mean
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn, initial_params=initial)

        assert 'best_params' in result
        best = result['best_params']
        # With tiny sigma, returned params must be very close to initial
        assert abs(best['sat_branching_bias'] - 3.0) < 0.1
        assert abs(best['sat_branching_factor'] - 1.0) < 0.1
        assert abs(best['sat_bias_factor'] - 1.0) < 0.1
        assert np.allclose(best['sat_branching_weights'], [1.0, 1.0], atol=0.1)
        assert np.allclose(best['sat_variable_priorities'], [0.0, 0.0], atol=0.1)

    def test_without_initial_params_uses_defaults(self):
        """Without initial_params, uses a default starting point."""
        model = FakeModel(n_vars=2)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=4,
            max_generations=2,
            sigma0=1.0,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)
        assert 'best_params' in result


class TestCMAESConvergence:
    """CMAESOptimizer stops early when sigma drops below threshold."""

    def test_early_stop_on_low_sigma(self):
        """Search stops early when sigma shrinks below threshold."""
        # Use a constant objective so all candidates score equally.
        # This causes the elite mean to converge rapidly, shrinking sigma
        # until it drops below sigma_threshold.
        def const_obj(idx, params):
            return 10.0

        model = FakeModel(n_vars=2, objective_fn=const_obj)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=4,
            max_generations=100,
            sigma0=1.0,  # Start above threshold
            sigma_threshold=0.01,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)

        # Must run at least 1 generation (sigma0 > threshold)
        assert len(result['log']) >= 1
        # Should stop well before 100 generations due to sigma collapse
        assert len(result['log']) < 100


class TestCMAESOptPhase:
    """CMAESOptimizer works for opt phase (opt_sat + opt params)."""

    def test_opt_phase_returns_combined_params(self):
        """Opt phase produces params with both opt_sat and opt prefixes."""
        model = FakeModel(n_vars=2)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='opt',
            pop_size=4,
            max_generations=2,
            sigma0=1.0,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)
        params = result['best_params']

        # Should have both opt_sat and opt keys
        assert 'opt_sat_branching_bias' in params
        assert 'opt_branching_bias' in params
        assert 'opt_sat_branching_weights' in params
        assert 'opt_branching_weights' in params


class TestCMAESUsesRepeatedEval:
    """CMAESOptimizer uses _evaluate_strategy_repeated for noise robustness."""

    def test_repeated_eval_called_with_min_repeats(self):
        """Each candidate is evaluated with repeated solves."""
        solve_count = [0]

        def obj_fn(idx, params):
            solve_count[0] += 1
            return 10.0

        model = FakeModel(n_vars=2, objective_fn=obj_fn)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=2,
            max_generations=1,
            sigma0=1.0,
            min_repeats=3,
            max_repeats=3,
            random_state=42,
        )
        optimizer.optimize(model, signal_fn)

        # pop_size=2, min_repeats=3 -> at least 6 solves
        assert solve_count[0] >= 6


class TestCMAESSignalImprovement:
    """CMA-ES improves signal over generations on a simple objective."""

    def test_signal_improves_or_stays(self):
        """Best signal across generations is non-decreasing."""
        # Objective: sum of weights closer to target
        target_bias = 3.0

        def obj_fn(idx, params):
            bias = params.get('sat_branching_bias', 5.0)
            return -abs(bias - target_bias)

        model = FakeModel(n_vars=2, objective_fn=obj_fn)
        signal_fn = lambda r: r.objective

        optimizer = CMAESOptimizer(
            phase='sat',
            pop_size=6,
            max_generations=10,
            sigma0=2.0,
            min_repeats=1,
            max_repeats=1,
            random_state=42,
        )
        result = optimizer.optimize(model, signal_fn)

        log = result['log']
        best_signals = [entry['best_signal'] for entry in log]
        # Global best should be non-decreasing
        running_best = best_signals[0]
        for s in best_signals[1:]:
            assert s >= running_best - 1e-9
            running_best = max(running_best, s)
