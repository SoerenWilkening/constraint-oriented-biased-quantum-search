"""Tests for C-level feature extraction via Cython bridge.

Verifies that c_extract_features() produces results matching the Python
FeatureExtractor reference implementation for various model configurations.
"""
import random

import numpy as np
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE, MINIMIZE, INTEGER
from cbqs.SearchLib import c_extract_features
from cbqs.ml.features import FeatureExtractor


def _make_simple_model():
    """3-variable model with one constraint and an objective."""
    m = Model()
    x = m.add_variables(3)
    m.set_objective(2 * x[0] + 3 * x[1] + x[2], sense=MAXIMIZE)
    m.add_constraint(x[0] + x[1] + x[2] <= 2)
    m.close()
    return m


def _make_knapsack_model(n=10):
    """n-variable knapsack with deterministic coefficients."""
    m = Model()
    x = m.add_variables(n)
    obj = sum((i % 7 + 1) * x[i] for i in range(n))
    m.set_objective(obj, sense=MAXIMIZE)
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n * 2)
    m.close()
    return m


def _make_sat_model(n, clause_ratio=4.27, seed=42):
    """n-variable random 3-SAT with deterministic clause generation."""
    rng = random.Random(seed)
    m = Model()
    x = m.add_variables(n)
    # Dummy objective (SAT instances still need one to close)
    m.set_objective(sum(1 * x[i] for i in range(n)), sense=MINIMIZE)
    n_clauses = int(clause_ratio * n)
    for _ in range(n_clauses):
        # Pick 3 distinct variables for each clause
        indices = rng.sample(range(n), min(3, n))
        # Each literal is x[i] or (1 - x[i]); model as sum >= 1
        expr = sum(1 * x[i] for i in indices)
        m.add_constraint(expr <= len(indices))
    m.close()
    return m


def _make_multi_constraint_model():
    """5-variable model with 3 constraints for richer co-occurrence."""
    m = Model()
    x = m.add_variables(5)
    m.set_objective(x[0] + 2 * x[1] + 3 * x[2] + x[3] + x[4], sense=MAXIMIZE)
    m.add_constraint(x[0] + x[1] <= 1)
    m.add_constraint(x[1] + x[2] + x[3] <= 2)
    m.add_constraint(x[3] + x[4] <= 1)
    m.close()
    return m


class TestCExtractFeaturesShape:
    """Verify output shapes from c_extract_features."""

    def test_var_features_shape(self):
        m = _make_simple_model()
        var_f, inst_f = c_extract_features(m)
        assert var_f.shape == (3, 9)

    def test_inst_features_shape(self):
        m = _make_simple_model()
        var_f, inst_f = c_extract_features(m)
        assert inst_f.shape == (11,)

    def test_dtype_float64(self):
        m = _make_simple_model()
        var_f, inst_f = c_extract_features(m)
        assert var_f.dtype == np.float64
        assert inst_f.dtype == np.float64

    def test_knapsack_shape(self):
        m = _make_knapsack_model(20)
        var_f, inst_f = c_extract_features(m)
        assert var_f.shape == (20, 9)
        assert inst_f.shape == (11,)


class TestCExtractFeaturesUnclosed:
    """Verify error on unclosed model."""

    def test_raises_on_unclosed_model(self):
        m = Model()
        x = m.add_variables(3)
        m.set_objective(x[0] + x[1], sense=MAXIMIZE)
        m.add_constraint(x[0] + x[1] <= 1)
        with pytest.raises(ValueError, match="closed"):
            c_extract_features(m)


class TestCExtractFeaturesMatchesPython:
    """Verify C implementation matches Python FeatureExtractor output."""

    def _compare(self, model, atol=1e-10):
        fe = FeatureExtractor()
        py_var = fe.extract_variable_features(model)
        py_inst = fe.extract_instance_features(model)
        c_var, c_inst = c_extract_features(model)
        np.testing.assert_allclose(c_var, py_var, atol=atol,
                                   err_msg="Variable features mismatch")
        np.testing.assert_allclose(c_inst, py_inst, atol=atol,
                                   err_msg="Instance features mismatch")

    def test_simple_model(self):
        self._compare(_make_simple_model())

    def test_knapsack_10(self):
        self._compare(_make_knapsack_model(10))

    def test_knapsack_20(self):
        self._compare(_make_knapsack_model(20))

    def test_multi_constraint(self):
        self._compare(_make_multi_constraint_model())

    def test_knapsack_100(self):
        self._compare(_make_knapsack_model(100))

    def test_knapsack_3000(self):
        self._compare(_make_knapsack_model(3000))

    def test_sat_20(self):
        self._compare(_make_sat_model(20))

    def test_sat_65(self):
        self._compare(_make_sat_model(65))

    def test_single_variable(self):
        m = Model()
        x = m.add_variables(2)
        m.set_objective(x[0] + x[1], sense=MAXIMIZE)
        m.add_constraint(x[0] + x[1] <= 1)
        m.close()
        self._compare(m)

    def test_single_variable_true(self):
        """Edge case: model with exactly one variable."""
        m = Model()
        x = m.add_variables(1)
        m.set_objective(1 * x[0], sense=MAXIMIZE)
        m.add_constraint(1 * x[0] <= 1)
        m.close()
        self._compare(m)

    def test_empty_model(self):
        """Edge case: minimal model with variables but no meaningful structure."""
        m = Model()
        x = m.add_variables(2)
        m.set_objective(x[0] + x[1], sense=MAXIMIZE)
        m.add_constraint(x[0] + x[1] <= 2)
        m.close()
        self._compare(m)


class TestCExtractFeaturesInstValues:
    """Spot-check specific instance feature values."""

    def test_n_variables(self):
        m = _make_simple_model()
        _, inst = c_extract_features(m)
        assert inst[0] == 3.0

    def test_n_constraints(self):
        m = _make_simple_model()
        _, inst = c_extract_features(m)
        assert inst[1] == 1.0

    def test_constraint_density(self):
        m = _make_simple_model()
        _, inst = c_extract_features(m)
        assert abs(inst[2] - 1.0 / 3.0) < 1e-10

    def test_multi_constraint_counts(self):
        m = _make_multi_constraint_model()
        _, inst = c_extract_features(m)
        assert inst[0] == 5.0
        assert inst[1] == 3.0


class TestCExtractFeaturesZScore:
    """Verify z-score normalization properties of variable features."""

    def test_zero_mean(self):
        m = _make_knapsack_model(20)
        var_f, _ = c_extract_features(m)
        for col in range(9):
            col_data = var_f[:, col]
            if np.std(col_data) > 0:
                assert abs(np.mean(col_data)) < 1e-10, \
                    f"Column {col} mean not zero"

    def test_unit_variance_or_zero(self):
        m = _make_knapsack_model(20)
        var_f, _ = c_extract_features(m)
        for col in range(9):
            col_data = var_f[:, col]
            std = np.std(col_data)
            if std > 0:
                assert abs(std - 1.0) < 1e-10, \
                    f"Column {col} std not 1.0"

    def test_constant_column_is_zero(self):
        """When all variables have same feature value, column should be all 0."""
        m = _make_simple_model()
        var_f, _ = c_extract_features(m)
        # is_integer column (6) should be constant (all 1.0 -> all 0 after z-score)
        assert np.all(var_f[:, 6] == 0.0)
