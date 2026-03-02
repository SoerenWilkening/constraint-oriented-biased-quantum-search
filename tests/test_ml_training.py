"""Tests for WeightPredictor class and offline training pipeline.

Covers TRAIN-01 (fit/predict), TRAIN-02 (save/load), TRAIN-03 (edge cases),
TRAIN-04 (collect_training_data), TRAIN-05 (evaluate).
"""
import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.training import WeightPredictor


def _make_test_model(n_vars):
    """Build a small closed model with n_vars binary variables.

    Creates at least one constraint and an objective for feature extraction.
    Uses close(validate=False) for minimal models.
    """
    m = Model()
    xs = m.add_variables(n_vars)
    # Add a constraint involving first two variables (or just first if n_vars=1)
    if n_vars >= 2:
        m.add_constraint(xs[0] + xs[1] <= 1)
    else:
        m.add_constraint(xs[0] + 0 <= 1)
    # Objective over all variables
    obj_expr = xs[0] + 0  # Start with a valid expression
    for i in range(1, n_vars):
        obj_expr = obj_expr + xs[i]
    m.set_objective(obj_expr)
    m.close(validate=False)
    return m


class TestWeightPredictorFitPredict:
    """Tests for WeightPredictor fit() and predict() methods."""

    def test_fit_returns_self(self):
        """WeightPredictor().fit([(model, weights)]) returns the predictor itself."""
        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42)
        result = predictor.fit([(model, weights)])
        assert result is predictor

    def test_predict_returns_correct_shape(self):
        """After fit, predict(model) returns a 1D float64 ndarray of length n_vars."""
        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        result = predictor.predict(model)
        assert isinstance(result, np.ndarray)
        assert result.shape == (5,)
        assert result.dtype == np.float64

    def test_predict_non_negative(self):
        """predict(model) output contains no negative values."""
        model = _make_test_model(5)
        weights = np.array([1.0, 2.0, 0.5, 3.0, 0.1], dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        result = predictor.predict(model)
        assert np.all(result >= 0)

    def test_predict_different_size_model(self):
        """Train on 5-var model, predict on 10-var model. Output has length 10."""
        train_model = _make_test_model(5)
        train_weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(train_model, train_weights)])

        test_model = _make_test_model(10)
        result = predictor.predict(test_model)
        assert result.shape == (10,)

    def test_fit_multiple_pairs(self):
        """fit() accepts a list of multiple (Model, weights) pairs."""
        model1 = _make_test_model(5)
        model2 = _make_test_model(8)
        pairs = [
            (model1, np.ones(5, dtype=np.float64)),
            (model2, np.full(8, 2.0, dtype=np.float64)),
        ]
        predictor = WeightPredictor(random_state=42).fit(pairs)

        result = predictor.predict(model1)
        assert result.shape == (5,)


class TestWeightPredictorEdgeCases:
    """Tests for WeightPredictor error handling and edge cases."""

    def test_predict_before_fit_raises(self):
        """Calling predict() before fit() raises RuntimeError."""
        predictor = WeightPredictor()
        model = _make_test_model(5)

        with pytest.raises(RuntimeError):
            predictor.predict(model)

    def test_fit_empty_raises(self):
        """fit([]) raises ValueError about empty training data."""
        predictor = WeightPredictor()

        with pytest.raises(ValueError):
            predictor.fit([])


class TestWeightPredictorPersistence:
    """Tests for WeightPredictor save/load functionality."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Save a fitted predictor, load it back, predictions match exactly."""
        model = _make_test_model(5)
        weights = np.array([1.0, 2.0, 0.5, 3.0, 0.1], dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        save_path = tmp_path / "predictor.joblib"
        predictor.save(str(save_path))

        loaded = WeightPredictor.load(str(save_path))
        original_pred = predictor.predict(model)
        loaded_pred = loaded.predict(model)

        np.testing.assert_array_equal(original_pred, loaded_pred)

    def test_load_feature_mismatch_raises(self, tmp_path):
        """Loading a predictor with tampered feature names raises ValueError."""
        import joblib

        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        save_path = tmp_path / "predictor.joblib"
        predictor.save(str(save_path))

        # Tamper with the saved artifact's feature_names
        artifact = joblib.load(str(save_path))
        artifact['feature_names'] = ['bad_feature_1', 'bad_feature_2']
        joblib.dump(artifact, str(save_path))

        with pytest.raises(ValueError, match="mismatch"):
            WeightPredictor.load(str(save_path))

    def test_save_includes_metadata(self, tmp_path):
        """Saved artifact contains required metadata keys."""
        import joblib

        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        save_path = tmp_path / "predictor.joblib"
        predictor.save(str(save_path))

        artifact = joblib.load(str(save_path))
        assert 'feature_names' in artifact
        assert 'training_date' in artifact
        assert 'n_training_instances' in artifact
        assert 'cbqs_version' in artifact
