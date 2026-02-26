"""Tests for feature extraction from CBQS Model objects.

Covers FEAT-01 (per-variable features), FEAT-02 (instance-level features),
and FEAT-03 (size-invariant feature extraction).
"""
import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.features import (
    FeatureExtractor,
    VARIABLE_FEATURE_NAMES,
    INSTANCE_FEATURE_NAMES,
)


@pytest.fixture
def closed_model_with_constraints():
    """Model with 3 binary variables, 2 constraints, and an objective."""
    m = Model()
    xs = m.add_variables(3)
    m.add_constraint(xs[0] + xs[1] <= 1)
    m.add_constraint(xs[1] + xs[2] <= 1)
    m.set_objective(xs[0] + 2 * xs[1] + xs[2])
    m.close()
    return m, xs


@pytest.fixture
def closed_model_no_constraints():
    """Model with 3 binary variables, objective only, no meaningful constraints.

    Uses close(validate=False) since Model.close() requires constraints.
    """
    m = Model()
    xs = m.add_variables(3)
    m.set_objective(xs[0] + xs[1] + xs[2])
    m.close(validate=False)
    return m, xs


@pytest.fixture
def single_var_model():
    """Model with 1 variable and a trivial constraint."""
    m = Model()
    xs = m.add_variables(1)
    # Variable <= int requires an Expression, so use xs[0] + 0 to create one
    m.add_constraint(xs[0] + 0 <= 1)
    m.set_objective(xs[0] + 0)
    m.close()
    return m


def test_variable_features_shape(closed_model_with_constraints):
    """FEAT-01: Variable features have shape (n_vars, 9)."""
    model, _ = closed_model_with_constraints
    fe = FeatureExtractor()
    result = fe.extract_variable_features(model)

    assert isinstance(result, np.ndarray)
    assert result.shape == (3, 9)
    assert result.dtype == np.float64


def test_instance_features_shape(closed_model_with_constraints):
    """FEAT-02: Instance features have shape (11,)."""
    model, _ = closed_model_with_constraints
    fe = FeatureExtractor()
    result = fe.extract_instance_features(model)

    assert isinstance(result, np.ndarray)
    assert result.shape == (11,)
    assert result.dtype == np.float64


def test_unclosed_model_raises():
    """ValueError raised when extracting features from unclosed model."""
    m = Model()
    xs = m.add_variables(3)

    fe = FeatureExtractor()

    with pytest.raises(ValueError, match="Model must be closed"):
        fe.extract_variable_features(m)

    with pytest.raises(ValueError, match="Model must be closed"):
        fe.extract_instance_features(m)


def test_no_constraints_returns_zeros_for_constraint_features(closed_model_no_constraints):
    """Constraint-related features are zero when model has no constraints."""
    model, _ = closed_model_no_constraints
    fe = FeatureExtractor()

    vf = fe.extract_variable_features(model)
    assert vf.shape == (3, 9)

    # Degree column (0) should be all zeros (no constraints)
    assert np.all(vf[:, 0] == 0.0)
    # Coefficient stats (1-3) should be all zeros
    assert np.all(vf[:, 1] == 0.0)
    assert np.all(vf[:, 2] == 0.0)
    assert np.all(vf[:, 3] == 0.0)

    # Instance features: constraint count and coefficient stats
    inst = fe.extract_instance_features(model)
    assert inst[1] == 0.0   # n_constraints
    assert inst[6] == 0.0   # coeff_mean
    assert inst[7] == 0.0   # coeff_std
    assert inst[8] == 0.0   # coeff_max


def test_variable_feature_names():
    """Feature name lists have correct length and content."""
    fe = FeatureExtractor()
    names = fe.feature_names

    assert isinstance(names, list)
    assert len(names) == 9
    assert len(VARIABLE_FEATURE_NAMES) == 9
    assert names[0] == "degree"
    assert names[-1] == "num_co_occurring_vars"


def test_instance_feature_names():
    """Instance feature name list has correct length and content."""
    fe = FeatureExtractor()
    names = fe.instance_feature_names

    assert isinstance(names, list)
    assert len(names) == 11
    assert len(INSTANCE_FEATURE_NAMES) == 11
    assert names[0] == "n_variables"
    assert names[-1] == "bounds_tightness_std"


def test_instance_features_values(closed_model_with_constraints):
    """FEAT-02: Instance feature values are correct for a known model."""
    model, _ = closed_model_with_constraints
    fe = FeatureExtractor()
    inst = fe.extract_instance_features(model)

    # n_variables
    assert inst[0] == 3.0
    # n_constraints (2 constraints added)
    assert inst[1] == 2.0
    # constraint_density = 2/3
    assert abs(inst[2] - 2.0 / 3.0) < 1e-10
    # integer_variable_fraction = 1.0 (all binary = integer)
    assert inst[5] == 1.0


def test_single_variable_model(single_var_model):
    """Feature extraction works on a model with only 1 variable."""
    fe = FeatureExtractor()

    vf = fe.extract_variable_features(single_var_model)
    assert vf.shape == (1, 9)

    inst = fe.extract_instance_features(single_var_model)
    assert inst.shape == (11,)
    assert inst[0] == 1.0  # n_variables


def test_feature_extraction_size_invariant():
    """FEAT-03: Feature count is fixed regardless of model size."""
    fe = FeatureExtractor()

    # 5-variable model
    m5 = Model()
    xs5 = m5.add_variables(5)
    m5.add_constraint(xs5[0] + xs5[1] <= 1)
    m5.set_objective(xs5[0] + xs5[1])
    m5.close()

    vf5 = fe.extract_variable_features(m5)
    assert vf5.shape == (5, 9)

    # 10-variable model
    m10 = Model()
    xs10 = m10.add_variables(10)
    m10.add_constraint(xs10[0] + xs10[1] + xs10[2] <= 2)
    m10.set_objective(xs10[0] + xs10[1])
    m10.close()

    vf10 = fe.extract_variable_features(m10)
    assert vf10.shape == (10, 9)

    # Same number of feature columns regardless of variable count
    assert vf5.shape[1] == vf10.shape[1] == 9


def test_normalization_no_nan(closed_model_with_constraints):
    """Z-score normalization produces no NaN values."""
    model, _ = closed_model_with_constraints
    fe = FeatureExtractor()

    result = fe.extract_variable_features(model)
    assert not np.any(np.isnan(result))


def test_co_occurring_vars(closed_model_with_constraints):
    """Co-occurrence features reflect constraint structure."""
    model, _ = closed_model_with_constraints
    fe = FeatureExtractor()

    # Before normalization we can't test exact values, but we can verify
    # the feature matrix has the right shape and no NaN
    vf = fe.extract_variable_features(model)
    assert vf.shape == (3, 9)
    assert not np.any(np.isnan(vf))

    # The co-occurring vars column (8) should not be all zeros since
    # variables share constraints
    # After normalization, at least one value should be non-zero
    # (unless all variables have the same co-occurrence count, which
    # would normalize to zero -- in our model, x1 appears in 2
    # constraints while x0 and x2 appear in 1 each, so co-occurrence
    # counts differ)
    assert not np.all(vf[:, 8] == 0.0)
