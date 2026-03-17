"""Tests verifying that PolynomialPredictor.predict() and evaluate() use the
C-level feature extraction and consolidated parameter setter, not Python
reimplementations.
"""
import inspect
import numpy as np
import pytest
from unittest.mock import patch

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from cbqs.SearchLib import c_extract_features, set_predicted_params
from cbqs.ml.polynomial import PolynomialPredictor, THETA_SIZE


def _make_model(n=5):
    """Create a simple closed model with n variables."""
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum((i + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum(x[i] for i in range(n)) <= n // 2 + 1)
    m.close()
    return m


class TestPredictUsesCExtraction:
    """Verify PolynomialPredictor.predict() calls c_extract_features."""

    def test_predict_calls_c_extract_features(self):
        """predict() must call c_extract_features for real Model objects."""
        model = _make_model(5)
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)

        # Patch at the source module; the lazy import resolves through it
        with patch('cbqs.SearchLib.c_extract_features',
                   wraps=c_extract_features) as mock_c:
            predictor.predict(model)
            mock_c.assert_called_once_with(model)

    def test_predict_no_python_extractor_attribute(self):
        """PolynomialPredictor should not store a FeatureExtractor instance."""
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)
        assert not hasattr(predictor, '_extractor')

    def test_predict_source_imports_c_extract_features(self):
        """predict() source code must import and call c_extract_features."""
        source = inspect.getsource(PolynomialPredictor.predict)
        assert 'c_extract_features' in source
        assert 'c_extract_features(model)' in source

    def test_predict_result_matches_c_features(self):
        """predict() output should be consistent with c_extract_features."""
        model = _make_model(8)
        theta = np.zeros(THETA_SIZE)
        predictor = PolynomialPredictor(theta)

        params = predictor.predict(model)
        assert params['branching_bias'] == pytest.approx(8 / 4.0)
        assert len(params['branching_weights']) == 8
        assert len(params['variable_priorities']) == 8

    def test_c_extract_features_returns_correct_shapes(self):
        """c_extract_features returns arrays matching expected feature dimensions."""
        model = _make_model(10)
        var_f, inst_f = c_extract_features(model)
        assert var_f.shape == (10, 9)
        assert inst_f.shape == (11,)


class TestEvaluateUsesConsolidatedSetter:
    """Verify evaluate() uses set_predicted_params, not multiple set_param()."""

    def test_evaluate_source_imports_set_predicted_params(self):
        """evaluate() source code must import set_predicted_params."""
        from cbqs.ml.es_evaluator import evaluate
        source = inspect.getsource(evaluate)
        assert 'set_predicted_params' in source

    def test_evaluate_source_does_not_use_individual_set_param(self):
        """evaluate() should not call set_param for predicted parameter keys."""
        from cbqs.ml.es_evaluator import evaluate
        source = inspect.getsource(evaluate)
        # Should not contain individual set_param calls for predicted keys
        for key in ('branching_weights', 'branching_bias',
                    'branching_factor', 'bias_factor'):
            assert f"set_param('{key}'" not in source, \
                f"evaluate() should not call set_param('{key}') directly"

    def test_set_predicted_params_sets_all_keys(self):
        """set_predicted_params must set all required param keys."""
        model = _make_model(5)
        weights = np.ones(5)
        priorities = np.arange(5)

        set_predicted_params(model, 1.25, 1.0, 1.0, weights, priorities, 5)

        assert model._params['branching_bias'] == 1.25
        assert model._params['branching_factor'] == 1.0
        assert model._params['bias_factor'] == 1.0
        np.testing.assert_array_equal(model._params['branching_weights'], weights)
        np.testing.assert_array_equal(model._params['variable_priorities'], priorities)

    def test_set_predicted_params_is_from_searchlib(self):
        """set_predicted_params must be the Cython function from SearchLib."""
        import cbqs.SearchLib as sl
        assert hasattr(sl, 'set_predicted_params')
        assert callable(sl.set_predicted_params)

    def test_evaluate_sets_params_via_consolidated_setter(self):
        """End-to-end: evaluate() with real Model sets all predicted params."""
        from cbqs.ml.es_evaluator import evaluate

        model = _make_model(5)
        theta = np.zeros(THETA_SIZE)

        # Use a short time budget and mock solve to avoid actual solving
        class FakeResult:
            objective = 0.0
            history = []

        original_solve = model.solve
        model_solved = [False]

        def fake_solve():
            model_solved[0] = True
            model.objective_value = 0.0
            model.runtime = 0.0
            return FakeResult()

        # Can't patch Cython methods, so monkey-patch through _params check
        # Just verify the params are set after evaluate returns
        # We need to prevent actual solve; use stopping_time=0
        try:
            model.solve = fake_solve
        except AttributeError:
            pytest.skip("Cannot override Cython Model.solve for testing")

        evaluate(theta, model, time_budget=1)

        expected_keys = {'branching_weights', 'branching_bias',
                         'branching_factor', 'bias_factor',
                         'variable_priorities'}
        for key in expected_keys:
            assert key in model._params, f"Missing key '{key}' in model._params"
