"""Tests for polynomial expansion, pack/unpack theta, and PolynomialPredictor.

Covers ES-M1: poly_expand shape and value correctness, pack/unpack roundtrip,
zero-theta defaults, clipping behavior, save/load roundtrip, and predict output.
Uses real cbqs.Model.Model objects for predictor tests.
"""
import os
import tempfile

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.polynomial import (
    poly_expand,
    pack_theta,
    unpack_theta,
    PolynomialPredictor,
    N_VAR_FEATURES,
    N_INST_FEATURES,
    N_VAR_TERMS,
    N_INST_TERMS,
    N_VAR_OUTPUTS,
    N_INST_OUTPUTS,
    THETA_SIZE,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def small_model():
    """Closed model with 5 variables, 2 constraints, and an objective."""
    m = Model()
    xs = m.add_variables(5)
    m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
    m.add_constraint(xs[2] + xs[3] + xs[4] <= 2)
    m.set_objective(xs[0] + 2 * xs[1] + xs[2] + xs[3] + xs[4])
    m.close()
    return m


@pytest.fixture
def medium_model():
    """Closed model with 20 variables for bias scaling tests."""
    m = Model()
    xs = m.add_variables(20)
    m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
    m.add_constraint(xs[3] + xs[4] + xs[5] <= 2)
    m.add_constraint(xs[6] + xs[7] + xs[8] <= 2)
    m.set_objective(sum(xs[i] for i in range(20)))
    m.close()
    return m


@pytest.fixture
def large_model():
    """Closed model with 100 variables for clipping tests."""
    m = Model()
    xs = m.add_variables(100)
    m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
    m.add_constraint(xs[3] + xs[4] + xs[5] <= 2)
    m.set_objective(sum(xs[i] for i in range(100)))
    m.close()
    return m


def _make_model(n_vars):
    """Create a closed model with n_vars binary variables."""
    m = Model()
    xs = m.add_variables(n_vars)
    if n_vars >= 3:
        m.add_constraint(xs[0] + xs[1] + xs[2] <= 2)
    else:
        m.add_constraint(xs[0] + 0 <= 1)
    m.set_objective(sum(xs[i] for i in range(n_vars)))
    m.close()
    return m


# ------------------------------------------------------------------
# poly_expand
# ------------------------------------------------------------------

class TestPolyExpand:

    def test_shape_9_features(self):
        """9 per-variable features expand to 55 terms."""
        X = np.random.randn(10, 9)
        result = poly_expand(X, degree=2)
        assert result.shape == (10, 55)

    def test_shape_11_features(self):
        """11 instance features expand to 78 terms."""
        X = np.random.randn(1, 11)
        result = poly_expand(X, degree=2)
        assert result.shape == (1, 78)

    def test_shape_1d_input(self):
        """1D input (single sample) is handled correctly."""
        x = np.random.randn(11)
        result = poly_expand(x, degree=2)
        assert result.shape == (78,)

    def test_intercept_is_one(self):
        """First term is always 1 (intercept)."""
        X = np.random.randn(5, 9)
        result = poly_expand(X, degree=2)
        np.testing.assert_array_equal(result[:, 0], 1.0)

    def test_linear_terms(self):
        """Terms 1..n are the original features."""
        X = np.array([[2.0, 3.0, 5.0]])
        result = poly_expand(X, degree=2)
        # 1 + 3 + 3 + 3 = 10 terms for n=3
        assert result.shape == (1, 10)
        np.testing.assert_array_almost_equal(result[0, 1:4], [2.0, 3.0, 5.0])

    def test_cross_terms(self):
        """Cross-terms are correct for a known input."""
        X = np.array([[2.0, 3.0, 5.0]])
        result = poly_expand(X, degree=2)
        # Cross terms: x0*x1=6, x0*x2=10, x1*x2=15
        np.testing.assert_array_almost_equal(result[0, 4:7], [6.0, 10.0, 15.0])

    def test_squared_terms(self):
        """Squared terms are correct for a known input."""
        X = np.array([[2.0, 3.0, 5.0]])
        result = poly_expand(X, degree=2)
        # Squared: x0^2=4, x1^2=9, x2^2=25
        np.testing.assert_array_almost_equal(result[0, 7:10], [4.0, 9.0, 25.0])

    def test_term_count_formula(self):
        """Term count matches 1 + n + n*(n-1)/2 + n for various n."""
        for n in [1, 3, 5, 9, 11, 15]:
            X = np.random.randn(2, n)
            result = poly_expand(X, degree=2)
            expected_terms = 1 + n + n * (n - 1) // 2 + n
            assert result.shape[1] == expected_terms, f"Failed for n={n}"

    def test_zeros_input(self):
        """Zero input produces intercept=1 and all other terms=0."""
        X = np.zeros((1, 9))
        result = poly_expand(X, degree=2)
        assert result[0, 0] == 1.0
        np.testing.assert_array_equal(result[0, 1:], 0.0)

    def test_degree_not_2_raises(self):
        """Only degree=2 is supported; other values raise ValueError."""
        X = np.random.randn(3, 5)
        with pytest.raises(ValueError, match="Only degree=2"):
            poly_expand(X, degree=3)
        with pytest.raises(ValueError, match="Only degree=2"):
            poly_expand(X, degree=1)


# ------------------------------------------------------------------
# pack / unpack theta
# ------------------------------------------------------------------

class TestPackUnpack:

    def test_pack_shape(self):
        """pack_theta produces a flat vector of length THETA_SIZE."""
        W_var = np.random.randn(N_VAR_OUTPUTS, N_VAR_TERMS)
        W_inst = np.random.randn(N_INST_OUTPUTS, N_INST_TERMS)
        theta = pack_theta(W_var, W_inst)
        assert theta.shape == (THETA_SIZE,)

    def test_unpack_shapes(self):
        """unpack_theta produces correctly shaped matrices."""
        theta = np.random.randn(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        assert W_var.shape == (N_VAR_OUTPUTS, N_VAR_TERMS)
        assert W_inst.shape == (N_INST_OUTPUTS, N_INST_TERMS)

    def test_forward_roundtrip(self):
        """pack then unpack recovers the original matrices."""
        W_var = np.random.randn(N_VAR_OUTPUTS, N_VAR_TERMS)
        W_inst = np.random.randn(N_INST_OUTPUTS, N_INST_TERMS)
        theta = pack_theta(W_var, W_inst)
        W_var_rt, W_inst_rt = unpack_theta(theta)
        np.testing.assert_array_equal(W_var, W_var_rt)
        np.testing.assert_array_equal(W_inst, W_inst_rt)

    def test_reverse_roundtrip(self):
        """unpack then pack recovers the original theta."""
        theta = np.random.randn(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        theta_rt = pack_theta(W_var, W_inst)
        np.testing.assert_array_equal(theta, theta_rt)

    def test_wrong_theta_size_raises(self):
        """unpack_theta raises ValueError for wrong-sized input."""
        with pytest.raises(ValueError):
            unpack_theta(np.zeros(100))

    def test_wrong_theta_ndim_raises(self):
        """unpack_theta raises ValueError for 2D theta."""
        theta_2d = np.random.randn(2, THETA_SIZE // 2)
        with pytest.raises(ValueError):
            unpack_theta(theta_2d)

    def test_wrong_W_var_shape_raises(self):
        """pack_theta raises ValueError for wrong-shaped W_var."""
        W_var = np.zeros((3, N_VAR_TERMS))  # wrong: should be 2 rows
        W_inst = np.zeros((N_INST_OUTPUTS, N_INST_TERMS))
        with pytest.raises(ValueError, match="W_var shape"):
            pack_theta(W_var, W_inst)

    def test_wrong_W_inst_shape_raises(self):
        """pack_theta raises ValueError for wrong-shaped W_inst."""
        W_var = np.zeros((N_VAR_OUTPUTS, N_VAR_TERMS))
        W_inst = np.zeros((2, N_INST_TERMS))  # wrong: should be 3 rows
        with pytest.raises(ValueError, match="W_inst shape"):
            pack_theta(W_var, W_inst)


# ------------------------------------------------------------------
# PolynomialPredictor
# ------------------------------------------------------------------

class TestPolynomialPredictor:

    def test_zero_theta_bias_is_n_over_4(self, small_model):
        """Zero theta produces bias = n/4 exactly."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        n = len(small_model.variables)
        assert result['branching_bias'] == pytest.approx(n / 4.0)

    def test_zero_theta_weights_are_zero(self, small_model):
        """Zero theta produces all-zero branching weights."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        np.testing.assert_array_equal(result['branching_weights'], 0.0)

    def test_zero_theta_factors_are_zero(self, small_model):
        """Zero theta produces zero branching_factor and bias_factor."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        assert result['branching_factor'] == 0.0
        assert result['bias_factor'] == 0.0

    def test_predict_returns_all_keys(self, small_model):
        """predict() returns dict with all required keys."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        expected_keys = {
            'branching_weights',
            'variable_priorities',
            'branching_bias',
            'branching_factor',
            'bias_factor',
        }
        assert set(result.keys()) == expected_keys

    def test_predict_weights_shape(self, small_model):
        """branching_weights has shape (n_vars,)."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        n = len(small_model.variables)
        assert result['branching_weights'].shape == (n,)

    def test_predict_priorities_shape(self, small_model):
        """variable_priorities is a permutation of [0..n-1]."""
        rng = np.random.RandomState(42)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        n = len(small_model.variables)
        priorities = result['variable_priorities']
        assert priorities.shape == (n,)
        assert set(priorities) == set(range(n))

    def test_bias_clipping_positive(self, large_model):
        """Bias delta is clipped to +3% of n/4."""
        theta = np.zeros(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        W_inst[0, 0] = 1000.0  # large positive bias_delta intercept
        theta = pack_theta(W_var, W_inst)

        predictor = PolynomialPredictor(theta)
        result = predictor.predict(large_model)

        n = len(large_model.variables)
        base = n / 4.0
        max_bias = base + 0.03 * base
        assert result['branching_bias'] <= max_bias + 1e-10

    def test_bias_clipping_negative(self, large_model):
        """Bias delta is clipped to -3% of n/4."""
        theta = np.zeros(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        W_inst[0, 0] = -1000.0  # large negative bias_delta intercept
        theta = pack_theta(W_var, W_inst)

        predictor = PolynomialPredictor(theta)
        result = predictor.predict(large_model)

        n = len(large_model.variables)
        base = n / 4.0
        min_bias = base - 0.03 * base
        assert result['branching_bias'] >= min_bias - 1e-10

    def test_factors_clipped_nonnegative(self, small_model):
        """branching_factor and bias_factor are clipped >= 0."""
        theta = np.zeros(THETA_SIZE)
        W_var, W_inst = unpack_theta(theta)
        W_inst[1, 0] = -10.0  # negative branching_factor intercept
        W_inst[2, 0] = -10.0  # negative bias_factor intercept
        theta = pack_theta(W_var, W_inst)

        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        assert result['branching_factor'] == 0.0
        assert result['bias_factor'] == 0.0

    def test_bias_scales_with_n(self):
        """Zero-theta bias equals n/4 for various instance sizes."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)

        for n in [4, 10, 20, 50]:
            model = _make_model(n)
            result = predictor.predict(model)
            assert result['branching_bias'] == pytest.approx(n / 4.0)

    def test_nonzero_theta_changes_weights(self, small_model):
        """Non-zero theta produces non-zero branching weights."""
        rng = np.random.RandomState(99)
        theta = rng.randn(THETA_SIZE) * 0.1
        predictor = PolynomialPredictor(theta)
        result = predictor.predict(small_model)
        assert not np.allclose(result['branching_weights'], 0.0)


# ------------------------------------------------------------------
# Save / Load
# ------------------------------------------------------------------

class TestSaveLoad:

    def test_save_load_roundtrip(self, tmp_path):
        """save() then load() recovers the same predictor coefficients."""
        rng = np.random.RandomState(123)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        path = str(tmp_path / "model.npz")
        predictor.save(path)

        loaded = PolynomialPredictor.load(path)
        np.testing.assert_array_almost_equal(
            pack_theta(loaded.W_var, loaded.W_inst),
            pack_theta(predictor.W_var, predictor.W_inst),
        )

    def test_predictions_match_after_load(self, tmp_path, small_model):
        """Loaded predictor produces identical predictions."""
        rng = np.random.RandomState(456)
        theta = rng.randn(THETA_SIZE) * 0.01
        predictor = PolynomialPredictor(theta)

        result_before = predictor.predict(small_model)

        path = str(tmp_path / "model.npz")
        predictor.save(path)
        loaded = PolynomialPredictor.load(path)

        result_after = loaded.predict(small_model)

        np.testing.assert_array_almost_equal(
            result_before['branching_weights'],
            result_after['branching_weights'],
        )
        np.testing.assert_array_almost_equal(
            result_before['variable_priorities'],
            result_after['variable_priorities'],
        )
        assert result_before['branching_bias'] == pytest.approx(
            result_after['branching_bias']
        )
        assert result_before['branching_factor'] == pytest.approx(
            result_after['branching_factor']
        )
        assert result_before['bias_factor'] == pytest.approx(
            result_after['bias_factor']
        )

    def test_save_load_preserves_delta_pct(self, tmp_path):
        """Custom delta_pct is preserved through save/load."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta, delta_pct=0.10)

        path = str(tmp_path / "model.npz")
        predictor.save(path)
        loaded = PolynomialPredictor.load(path)

        assert loaded.delta_pct == pytest.approx(0.10)

    def test_load_nonexistent_raises(self):
        """Loading from nonexistent path raises an error."""
        with pytest.raises((FileNotFoundError, OSError)):
            PolynomialPredictor.load("/nonexistent/path/model.npz")


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

class TestConstants:

    def test_theta_size_is_344(self):
        """THETA_SIZE = 344."""
        assert THETA_SIZE == 344

    def test_theta_size_formula(self):
        """THETA_SIZE = N_VAR_OUTPUTS * N_VAR_TERMS + N_INST_OUTPUTS * N_INST_TERMS."""
        assert THETA_SIZE == N_VAR_OUTPUTS * N_VAR_TERMS + N_INST_OUTPUTS * N_INST_TERMS

    def test_var_terms_is_55(self):
        """N_VAR_TERMS = 1 + 9 + 36 + 9 = 55."""
        n = N_VAR_FEATURES
        expected = 1 + n + n * (n - 1) // 2 + n
        assert N_VAR_TERMS == expected == 55

    def test_inst_terms_is_78(self):
        """N_INST_TERMS = 1 + 11 + 55 + 11 = 78."""
        n = N_INST_FEATURES
        expected = 1 + n + n * (n - 1) // 2 + n
        assert N_INST_TERMS == expected == 78

    def test_var_features_count(self):
        """N_VAR_FEATURES = 9."""
        assert N_VAR_FEATURES == 9

    def test_inst_features_count(self):
        """N_INST_FEATURES = 11."""
        assert N_INST_FEATURES == 11

    def test_var_outputs_count(self):
        """N_VAR_OUTPUTS = 2 (weight, priority)."""
        assert N_VAR_OUTPUTS == 2

    def test_inst_outputs_count(self):
        """N_INST_OUTPUTS = 3 (bias_delta, branching_factor, bias_factor)."""
        assert N_INST_OUTPUTS == 3
