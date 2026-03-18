"""Tests verifying sub-linear instance-level outputs remain O(1) at scale.

Verifies that the polynomial predictor's instance-level outputs (bias_delta,
branching_factor, bias_factor) remain bounded for large instances, and that
the C and Python prediction paths produce matching results.

The C path uses log(1+|x|) for unbounded instance features (n_variables,
n_constraints, coeff_mean, coeff_std, coeff_max) to ensure O(1) outputs.
"""
import random

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.polynomial import (
    PolynomialPredictor,
    linear_expand,
    poly_expand,
    pack_theta,
    unpack_theta,
    THETA_SIZE,
    N_VAR_TERMS,
    N_INST_TERMS,
    N_VAR_OUTPUTS,
    N_INST_OUTPUTS,
)
from cbqs.ml.features import FeatureExtractor


# Bitmask matching ML_INST_LOG_FEATURES in ml_features.h.
# Indices: 0=n_variables, 1=n_constraints, 6=coeff_mean, 7=coeff_std, 8=coeff_max
_INST_LOG_FEATURES = 0x1C3  # bits 0,1,6,7,8


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_knapsack(n_vars, seed=42):
    """Create a closed knapsack model with n_vars variables."""
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n_vars)
    weights = [rng.randint(1, 20) for _ in range(n_vars)]
    values = [rng.randint(1, 30) for _ in range(n_vars)]
    capacity = sum(weights) // 3
    m.add_constraint(sum(xs[i] * weights[i] for i in range(n_vars)) <= capacity)
    from cbqs.Constants import MAXIMIZE
    m.set_objective(sum(xs[i] * values[i] for i in range(n_vars)), MAXIMIZE)
    m.close()
    return m


def _log_linear_expand(x):
    """Python equivalent of C log_linear_dot's feature transform.

    Applies log(1+|x|) to unbounded features (matching ML_INST_LOG_FEATURES)
    and passes bounded features through unchanged. Returns [1, g(x1), ..., g(x11)].
    """
    n = len(x)
    result = np.empty(1 + n, dtype=np.float64)
    result[0] = 1.0
    for j in range(n):
        if _INST_LOG_FEATURES & (1 << j):
            result[1 + j] = np.log(1.0 + abs(x[j]))
        else:
            result[1 + j] = x[j]
    return result


def _python_predict_with_log(model, W_var, W_inst, delta_pct):
    """Python prediction matching the C log_linear_dot path."""
    fe = FeatureExtractor()
    var_features = fe.extract_variable_features(model)
    inst_features = fe.extract_instance_features(model)

    var_terms = poly_expand(var_features, degree=2)
    var_out = var_terms @ W_var.T
    weights = var_out[:, 0]
    priority_scores = var_out[:, 1]
    priorities = np.argsort(-priority_scores)

    inst_terms = _log_linear_expand(inst_features)
    inst_out = W_inst @ inst_terms

    n = len(model.variables)
    base_bias = n / 4.0
    bound = delta_pct * base_bias
    bias_delta = np.clip(inst_out[0], -bound, bound)
    bias = base_bias + bias_delta
    branching_factor = max(0.0, float(inst_out[1]))
    bias_factor = max(0.0, float(inst_out[2]))

    return {
        'branching_weights': np.maximum(0.0, weights),
        'variable_priorities': priorities,
        'branching_bias': float(bias),
        'branching_factor': branching_factor,
        'bias_factor': bias_factor,
    }


# ------------------------------------------------------------------
# Scaling: instance-level outputs remain O(1) for large n
# ------------------------------------------------------------------

class TestSublinearScaling:

    def test_n3000_factors_bounded(self):
        """On n=3000 knapsack, branching_factor and bias_factor stay O(1)."""
        rng = np.random.RandomState(12345)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        model = _make_knapsack(3000, seed=7)
        result = predictor.predict(model)

        assert abs(result['branching_factor']) < 10.0, (
            f"branching_factor={result['branching_factor']} is not O(1)"
        )
        assert abs(result['bias_factor']) < 10.0, (
            f"bias_factor={result['bias_factor']} is not O(1)"
        )

    def test_n3000_bias_near_n_over_4(self):
        """On n=3000, bias stays near n/4 regardless of theta."""
        rng = np.random.RandomState(99)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        model = _make_knapsack(3000, seed=11)
        result = predictor.predict(model)
        n = 3000
        base = n / 4.0
        bound = 0.03 * base
        assert base - bound - 1e-10 <= result['branching_bias'] <= base + bound + 1e-10

    def test_random_theta_outputs_bounded(self):
        """With random theta, no output should exceed ~10 in magnitude."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        for n in [100, 500, 1000, 3000]:
            model = _make_knapsack(n, seed=n)
            result = predictor.predict(model)

            assert abs(result['branching_factor']) < 10.0, (
                f"n={n}: branching_factor={result['branching_factor']}"
            )
            assert abs(result['bias_factor']) < 10.0, (
                f"n={n}: bias_factor={result['bias_factor']}"
            )

    def test_scaling_does_not_grow_with_n(self):
        """Instance-level outputs should not grow proportionally with n."""
        rng = np.random.RandomState(77)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        results = {}
        for n in [50, 500, 5000]:
            model = _make_knapsack(n, seed=n)
            result = predictor.predict(model)
            results[n] = result

        bf_50 = abs(results[50]['branching_factor']) + 1e-9
        bf_5000 = abs(results[5000]['branching_factor']) + 1e-9
        # If output were O(n), ratio would be ~100x; sub-linear should be much less
        ratio = bf_5000 / bf_50
        assert ratio < 50.0, (
            f"branching_factor ratio 5000/50 = {ratio}, suggests O(n) growth"
        )


# ------------------------------------------------------------------
# C vs Python comparison (using log_linear_expand reference)
# ------------------------------------------------------------------

class TestCVsPython:

    def test_c_and_python_match_small(self):
        """C and Python (with log transform) produce near-exact results."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        W_var, W_inst = unpack_theta(theta)
        delta_pct = 0.03

        model = _make_knapsack(20, seed=1)

        py_result = _python_predict_with_log(model, W_var, W_inst, delta_pct)

        try:
            from cbqs.SearchLib import c_predict_params
            c_result = c_predict_params(model, W_var, W_inst, delta_pct)
        except ImportError:
            pytest.skip("C extension not available")

        np.testing.assert_allclose(
            c_result['branching_weights'], py_result['branching_weights'],
            rtol=1e-10, atol=1e-12,
        )
        assert c_result['branching_bias'] == pytest.approx(
            py_result['branching_bias'], rel=1e-10
        )
        assert c_result['branching_factor'] == pytest.approx(
            py_result['branching_factor'], rel=1e-10
        )
        assert c_result['bias_factor'] == pytest.approx(
            py_result['bias_factor'], rel=1e-10
        )

    def test_c_and_python_match_large(self):
        """C and Python (with log transform) produce near-exact results on n=3000."""
        rng = np.random.RandomState(55)
        theta = rng.randn(THETA_SIZE) * 0.01
        W_var, W_inst = unpack_theta(theta)
        delta_pct = 0.03

        model = _make_knapsack(3000, seed=33)

        py_result = _python_predict_with_log(model, W_var, W_inst, delta_pct)

        try:
            from cbqs.SearchLib import c_predict_params
            c_result = c_predict_params(model, W_var, W_inst, delta_pct)
        except ImportError:
            pytest.skip("C extension not available")

        np.testing.assert_allclose(
            c_result['branching_weights'], py_result['branching_weights'],
            rtol=1e-6, atol=1e-10,
        )
        assert c_result['branching_bias'] == pytest.approx(
            py_result['branching_bias'], rel=1e-6
        )
        assert c_result['branching_factor'] == pytest.approx(
            py_result['branching_factor'], rel=1e-6
        )
        assert c_result['bias_factor'] == pytest.approx(
            py_result['bias_factor'], rel=1e-6
        )

    def test_c_outputs_bounded_at_scale(self):
        """C path produces bounded outputs on n=3000 with random theta."""
        try:
            from cbqs.SearchLib import c_predict_params
        except ImportError:
            pytest.skip("C extension not available")

        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        W_var, W_inst = unpack_theta(theta)

        model = _make_knapsack(3000, seed=77)
        result = c_predict_params(model, W_var, W_inst, 0.03)

        assert abs(result['branching_factor']) < 10.0
        assert abs(result['bias_factor']) < 10.0
        n = 3000
        base = n / 4.0
        bound = 0.03 * base
        assert base - bound - 1e-10 <= result['branching_bias'] <= base + bound + 1e-10


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------

class TestEdgeCases:

    def test_all_zero_features(self):
        """Prediction works on a trivial model (minimal features, many zeros)."""
        m = Model()
        xs = m.add_variables(3)
        m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
        m.set_objective(xs[0] + xs[1] + xs[2])
        m.close()

        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(m)

        assert result['branching_bias'] == pytest.approx(3 / 4.0)
        assert result['branching_factor'] == 0.0
        assert result['bias_factor'] == 0.0
        np.testing.assert_array_equal(result['branching_weights'], 0.0)

    def test_single_variable(self):
        """Prediction works with a single variable."""
        m = Model()
        xs = m.add_variables(1)
        m.add_constraint(xs[0] + 0 <= 1)
        m.set_objective(xs[0] + 0)
        m.close()

        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(m)

        assert result['branching_weights'].shape == (1,)
        assert result['variable_priorities'].shape == (1,)
        assert result['branching_bias'] == pytest.approx(
            1 / 4.0, abs=0.03 * 0.25 + 1e-10
        )
        assert result['branching_factor'] >= 0.0
        assert result['bias_factor'] >= 0.0

    def test_sparse_model_zero_features(self):
        """Features with value 0 (log(1+0)=0) do not cause issues.

        Instance features include counts that can be zero for sparse models.
        The sub-linear expansion should handle zeros gracefully.
        """
        m = Model()
        xs = m.add_variables(5)
        m.add_constraint(xs[0] + 0 <= 1)
        m.set_objective(xs[0] + 0)
        m.close()

        rng = np.random.RandomState(123)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(m)

        assert np.isfinite(result['branching_bias'])
        assert np.isfinite(result['branching_factor'])
        assert np.isfinite(result['bias_factor'])
        assert np.all(np.isfinite(result['branching_weights']))

    def test_zero_theta_all_sizes(self):
        """Zero theta gives bias=n/4 and zero factors for various sizes."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)

        for n in [1, 5, 50, 500, 3000]:
            model = _make_knapsack(n, seed=n)
            result = predictor.predict(model)
            assert result['branching_bias'] == pytest.approx(n / 4.0), (
                f"n={n}: expected bias={n / 4.0}, got {result['branching_bias']}"
            )
            assert result['branching_factor'] == 0.0
            assert result['bias_factor'] == 0.0

    def test_log_linear_expand_zeros(self):
        """log_linear_expand on all-zero features gives intercept=1 and zeros."""
        x = np.zeros(11)
        result = _log_linear_expand(x)
        assert result[0] == 1.0
        np.testing.assert_array_equal(result[1:], 0.0)

    def test_log_linear_expand_large_n(self):
        """log_linear_expand on feature[0]=3000 gives log(3001), not 3000."""
        x = np.zeros(11)
        x[0] = 3000.0  # n_variables
        result = _log_linear_expand(x)
        assert result[1] == pytest.approx(np.log(3001.0))
        assert result[1] < 9.0  # log(3001) ~ 8.006


# ------------------------------------------------------------------
# Non-degeneracy: weights and factor are not all zero
# ------------------------------------------------------------------

class TestNonDegeneracy:

    def test_nonzero_theta_produces_nonzero_weights(self):
        """Non-zero theta produces some non-zero branching weights."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.1
        predictor = PolynomialPredictor(theta)

        model = _make_knapsack(50, seed=1)
        result = predictor.predict(model)

        assert np.any(result['branching_weights'] > 0), (
            "branching_weights should not be all zero for non-zero theta"
        )

    def test_nonzero_theta_produces_nonzero_factor(self):
        """Non-zero theta can produce nonzero branching_factor."""
        theta = np.zeros(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        W_inst[1, 0] = 0.5  # positive intercept for branching_factor
        theta = pack_theta(W_var, W_inst)

        predictor = PolynomialPredictor(theta)
        model = _make_knapsack(50, seed=1)
        result = predictor.predict(model)

        assert result['branching_factor'] > 0, (
            "branching_factor should be positive with positive intercept"
        )

    def test_priorities_are_permutation(self):
        """variable_priorities is always a valid permutation."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        for n in [10, 100, 1000]:
            model = _make_knapsack(n, seed=n)
            result = predictor.predict(model)
            prio = result['variable_priorities']
            assert prio.shape == (n,)
            assert set(prio) == set(range(n))

    def test_weights_nonnegative(self):
        """branching_weights are always non-negative (clipped)."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.1
        predictor = PolynomialPredictor(theta)

        model = _make_knapsack(100, seed=1)
        result = predictor.predict(model)

        assert np.all(result['branching_weights'] >= 0.0)
