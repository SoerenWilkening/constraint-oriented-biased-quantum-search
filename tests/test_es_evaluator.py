"""Tests for the ES evaluator module (ES-M3).

Tests evaluate(), normalize_signals(), and helper functions.
Uses a FakeModel to avoid compiled Cython solver dependency.
"""
import numpy as np
import pytest

from cbqs.result import OptimizeResult
from cbqs.ml.polynomial import THETA_SIZE
from cbqs.ml.es_evaluator import evaluate, normalize_signals, extract_signal


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_result(**overrides):
    """Create an OptimizeResult with sensible defaults."""
    defaults = dict(
        solution=[1, 0, 1, 0, 1],
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


class _FakeVar:
    """Stub variable for FeatureExtractor."""
    lb = 0
    ub = 1
    vtype = 0  # BINARY


class FakeModel:
    """Fake model for testing evaluate() without a real solver."""

    def __init__(self, n_vars=5, results=None, objective_range=(10, 50)):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_range = objective_range
        self.constraints_compiled = True

        self.variables = {i: _FakeVar() for i in range(n_vars)}
        self.obj_expr = [[[1, i] for i in range(n_vars)]]
        self.con_expr = [
            [[1, 0], [1, 1], 0, 1],
            [[2, 1], [1, 2], 0, 3],
        ]

    def set_param(self, key, value):
        self._params[key] = value

    def solve(self):
        idx = self._solve_count
        self._solve_count += 1
        if idx < len(self._results):
            return self._results[idx]
        lo, hi = self._objective_range
        obj = lo + (idx % 10) * (hi - lo) / 10
        return _make_result(
            objective=obj,
            solution=[1] * self.n,
            history=[(obj * 0.8, 0.01), (obj, 0.05)],
        )


# ------------------------------------------------------------------
# extract_signal
# ------------------------------------------------------------------

class TestExtractSignal:

    def test_returns_tuple(self):
        """extract_signal returns a (best_objective, -time_to_best) tuple."""
        result = _make_result(objective=100.0, history=[(80.0, 0.1), (100.0, 0.5)])
        signal = extract_signal(result)
        assert isinstance(signal, tuple)
        assert len(signal) == 2

    def test_best_objective_is_first(self):
        """First element is the objective value."""
        result = _make_result(objective=77.0, history=[(77.0, 0.3)])
        signal = extract_signal(result)
        assert signal[0] == 77.0

    def test_negative_time_to_best(self):
        """Second element is negated time_to_best."""
        result = _make_result(history=[(10.0, 0.1), (20.0, 0.5)])
        signal = extract_signal(result)
        assert signal[1] == pytest.approx(-0.5)

    def test_empty_history(self):
        """Empty history yields time_to_best=0."""
        result = _make_result(history=[])
        signal = extract_signal(result)
        assert signal[1] == 0.0

    def test_lexicographic_comparison(self):
        """Higher objective wins regardless of time."""
        sig_a = (100.0, -1.0)  # high obj, slow
        sig_b = (50.0, -0.01)  # low obj, fast
        assert sig_a > sig_b


# ------------------------------------------------------------------
# normalize_signals
# ------------------------------------------------------------------

class TestNormalizeSignals:

    def test_zero_mean(self):
        """Normalized signals have zero mean."""
        diffs = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
        normed = normalize_signals(diffs)
        assert np.abs(np.mean(normed)) < 1e-10

    def test_unit_variance(self):
        """Normalized signals have unit variance."""
        diffs = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
        normed = normalize_signals(diffs)
        assert np.std(normed) == pytest.approx(1.0, abs=1e-6)

    def test_known_values(self):
        """Check normalization against hand-computed values."""
        diffs = np.array([2.0, 4.0, 6.0])
        # mean=4, std=sqrt(8/3) ~= 1.6330
        normed = normalize_signals(diffs)
        expected_mean = 4.0
        expected_std = np.std(diffs)
        expected = (diffs - expected_mean) / (expected_std + 1e-8)
        np.testing.assert_allclose(normed, expected, atol=1e-10)

    def test_constant_input(self):
        """Constant input (std=0) returns zeros, not NaN/Inf."""
        diffs = np.array([5.0, 5.0, 5.0, 5.0])
        normed = normalize_signals(diffs)
        assert np.all(np.isfinite(normed))
        np.testing.assert_allclose(normed, 0.0, atol=1e-6)

    def test_single_value(self):
        """Single value has std=0, should return zero."""
        diffs = np.array([3.0])
        normed = normalize_signals(diffs)
        assert np.all(np.isfinite(normed))
        assert normed[0] == pytest.approx(0.0, abs=1e-6)

    def test_preserves_length(self):
        """Output has same length as input."""
        diffs = np.array([1.0, 2.0, 3.0, 4.0])
        normed = normalize_signals(diffs)
        assert len(normed) == len(diffs)

    def test_list_input(self):
        """Accepts a plain Python list."""
        diffs = [1.0, 3.0, 5.0]
        normed = normalize_signals(diffs)
        assert isinstance(normed, np.ndarray)
        assert np.abs(np.mean(normed)) < 1e-10

    def test_negative_values(self):
        """Works correctly with negative signal differences."""
        diffs = np.array([-5.0, -1.0, 3.0, 7.0])
        normed = normalize_signals(diffs)
        assert np.abs(np.mean(normed)) < 1e-10
        assert np.std(normed) == pytest.approx(1.0, abs=1e-6)


# ------------------------------------------------------------------
# evaluate
# ------------------------------------------------------------------

class TestEvaluate:

    def test_returns_tuple(self):
        """evaluate returns a 2-tuple."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        signal = evaluate(theta, model, time_budget=10)
        assert isinstance(signal, tuple)
        assert len(signal) == 2

    def test_signal_values(self):
        """Signal matches the expected (objective, -time_to_best) from result."""
        result = _make_result(objective=99.0, history=[(80.0, 0.1), (99.0, 0.7)])
        model = FakeModel(n_vars=5, results=[result])
        theta = np.zeros(THETA_SIZE)
        signal = evaluate(theta, model, time_budget=10)
        assert signal[0] == 99.0
        assert signal[1] == pytest.approx(-0.7)

    def test_sets_stopping_time(self):
        """evaluate sets stopping_time on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=30)
        assert model._params['stopping_time'] == 30

    def test_sets_branching_weights(self):
        """evaluate sets branching_weights on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert 'branching_weights' in model._params

    def test_sets_variable_priorities(self):
        """evaluate sets variable_priorities on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert 'variable_priorities' in model._params

    def test_sets_branching_bias(self):
        """evaluate sets branching_bias on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert 'branching_bias' in model._params

    def test_sets_branching_factor(self):
        """evaluate sets branching_factor on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert 'branching_factor' in model._params

    def test_sets_bias_factor(self):
        """evaluate sets bias_factor on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert 'bias_factor' in model._params

    def test_all_param_keys_set(self):
        """All expected parameter keys are set on the model."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        expected_keys = {
            'stopping_time',
            'branching_weights',
            'variable_priorities',
            'branching_bias',
            'branching_factor',
            'bias_factor',
        }
        assert expected_keys.issubset(set(model._params.keys()))

    def test_zero_theta_bias_is_n_over_4(self):
        """Zero theta produces bias = n/4."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=20)
        evaluate(theta, model, time_budget=10)
        # n/4 = 5.0
        assert model._params['branching_bias'] == pytest.approx(5.0)

    def test_bias_in_valid_range(self):
        """Bias is always within [n/4 - 3%*n/4, n/4 + 3%*n/4]."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 10.0  # large random theta
        model = FakeModel(n_vars=100)
        evaluate(theta, model, time_budget=10)
        n = 100
        base = n / 4.0
        bound = 0.03 * base
        bias = model._params['branching_bias']
        assert base - bound <= bias <= base + bound

    def test_branching_factor_nonnegative(self):
        """branching_factor is always >= 0."""
        rng = np.random.RandomState(99)
        theta = rng.randn(THETA_SIZE) * 5.0
        model = FakeModel(n_vars=10)
        evaluate(theta, model, time_budget=10)
        assert model._params['branching_factor'] >= 0.0

    def test_bias_factor_nonnegative(self):
        """bias_factor is always >= 0."""
        rng = np.random.RandomState(99)
        theta = rng.randn(THETA_SIZE) * 5.0
        model = FakeModel(n_vars=10)
        evaluate(theta, model, time_budget=10)
        assert model._params['bias_factor'] >= 0.0

    def test_calls_solve_once(self):
        """evaluate calls model.solve() exactly once."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=5)
        evaluate(theta, model, time_budget=10)
        assert model._solve_count == 1

    def test_predictor_constructed_correctly(self):
        """PolynomialPredictor is constructed from theta and produces valid params."""
        theta = np.zeros(THETA_SIZE)
        model = FakeModel(n_vars=8)
        evaluate(theta, model, time_budget=10)
        weights = model._params['branching_weights']
        assert len(weights) == 8
        priorities = model._params['variable_priorities']
        assert len(priorities) == 8
