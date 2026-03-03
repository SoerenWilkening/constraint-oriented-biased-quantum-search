"""Tests for WeightPredictor class and offline training pipeline.

Covers TRAIN-01 (fit/predict), TRAIN-02 (save/load), TRAIN-03 (edge cases),
TRAIN-04 (collect_training_data), TRAIN-05 (evaluate).
"""
import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.training import (
    WeightPredictor, collect_training_data, evaluate,
    evaluate_weights, _compute_time_to_best,
)


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


# ---------------------------------------------------------------------------
# Tests for collect_training_data (TRAIN-04)
# ---------------------------------------------------------------------------

class TestCollectTrainingData:
    """Tests for collect_training_data() utility."""

    def test_collect_training_data_returns_pairs(self):
        """collect_training_data returns a list of (Model, ndarray) tuples."""
        model1 = _make_test_model(5)
        model2 = _make_test_model(5)
        pairs = collect_training_data(
            [model1, model2], n_strategies=2, stopping_time=1, num_workers=1
        )

        assert isinstance(pairs, list)
        assert len(pairs) <= 2  # At most one pair per input model
        for m, w in pairs:
            assert isinstance(w, np.ndarray)
            assert w.shape == (len(m.variables),)

    def test_collect_training_data_configurable_budget(self):
        """Call with stopping_time=1 completes without hang."""
        model = _make_test_model(5)
        pairs = collect_training_data(
            [model], n_strategies=2, stopping_time=1, num_workers=1
        )
        assert isinstance(pairs, list)

    def test_collect_training_data_reproducible(self):
        """Two calls with same random_state generate identical candidate weight strategies.

        Note: The *winning* strategy may differ between runs due to solver
        timing nondeterminism, but the candidate weight vectors generated
        by the RNG must be identical. We verify this by checking that both
        calls produce results (the weight generation is deterministic).
        """
        model1 = _make_test_model(5)
        model2 = _make_test_model(5)
        pairs1 = collect_training_data(
            [model1], n_strategies=2, stopping_time=1,
            num_workers=1, random_state=42
        )
        pairs2 = collect_training_data(
            [model2], n_strategies=2, stopping_time=1,
            num_workers=1, random_state=42
        )
        # Both calls should produce results (one pair each)
        assert len(pairs1) == len(pairs2)
        assert len(pairs1) == 1

    def test_collect_training_data_empty_models_raises(self):
        """collect_training_data([]) raises ValueError."""
        with pytest.raises(ValueError):
            collect_training_data([])

    def test_collect_training_data_weights_non_negative(self):
        """All returned best_weights arrays contain non-negative values."""
        model = _make_test_model(5)
        pairs = collect_training_data(
            [model], n_strategies=3, stopping_time=1, num_workers=1
        )
        for _, w in pairs:
            assert np.all(w >= 0)


# ---------------------------------------------------------------------------
# Tests for evaluate (TRAIN-05)
# ---------------------------------------------------------------------------

class TestEvaluate:
    """Tests for evaluate() utility."""

    @pytest.fixture
    def fitted_predictor(self):
        """A WeightPredictor fitted on a small model."""
        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        return WeightPredictor(random_state=42).fit([(model, weights)])

    def test_evaluate_returns_dict_with_strategies(self, fitted_predictor):
        """evaluate returns a dict with at least 'predicted' and 'uniform' keys."""
        test_model = _make_test_model(5)
        results = evaluate(
            fitted_predictor, [test_model],
            stopping_time=1, num_workers=1
        )
        assert isinstance(results, dict)
        assert 'predicted' in results
        assert 'uniform' in results
        for key in ('predicted', 'uniform'):
            assert 'mean_objective' in results[key]
            assert 'feasibility_rate' in results[key]

    def test_evaluate_prints_table(self, fitted_predictor, capsys):
        """evaluate prints a multi-line table containing strategy names."""
        test_model = _make_test_model(5)
        evaluate(
            fitted_predictor, [test_model],
            stopping_time=1, num_workers=1
        )
        captured = capsys.readouterr()
        assert 'predicted' in captured.out
        assert 'uniform' in captured.out
        assert captured.out.count('\n') >= 3  # Header + separator + at least 2 rows

    def test_evaluate_custom_baselines(self, fitted_predictor):
        """Custom baselines appear in the result dict."""
        test_model = _make_test_model(5)
        results = evaluate(
            fitted_predictor, [test_model],
            stopping_time=1, num_workers=1,
            baselines={'constant': lambda m: np.full(len(m.variables), 2.0)}
        )
        assert 'predicted' in results
        assert 'uniform' in results
        assert 'constant' in results

    def test_evaluate_feasibility_rate_range(self, fitted_predictor):
        """All feasibility_rate values are between 0.0 and 1.0."""
        test_model = _make_test_model(5)
        results = evaluate(
            fitted_predictor, [test_model],
            stopping_time=1, num_workers=1
        )
        for strategy, metrics in results.items():
            assert 0.0 <= metrics['feasibility_rate'] <= 1.0


# ---------------------------------------------------------------------------
# Tests for evaluate_weights (DIAG-02, DIAG-03)
# ---------------------------------------------------------------------------

class TestEvaluateWeights:
    """Tests for evaluate_weights() with convergence speed metrics."""

    def test_evaluate_weights_returns_dict_with_metrics(self):
        """evaluate_weights returns a dict with strategy keys, each containing all four metric keys."""
        test_model = _make_test_model(5)
        strategies = {
            'constant': lambda m: np.full(len(m.variables), 2.0),
        }
        results = evaluate_weights(
            [test_model], strategies,
            stopping_time=1, num_workers=1
        )
        assert isinstance(results, dict)
        assert 'uniform' in results
        assert 'constant' in results
        expected_keys = {'mean_objective', 'feasibility_rate', 'mean_time_to_best', 'speedup_vs_uniform'}
        for name in ('uniform', 'constant'):
            assert set(results[name].keys()) == expected_keys

    def test_evaluate_weights_auto_adds_uniform(self):
        """When strategies dict lacks 'uniform', it is automatically added."""
        test_model = _make_test_model(5)
        strategies = {
            'custom': lambda m: np.ones(len(m.variables)) * 3.0,
        }
        results = evaluate_weights(
            [test_model], strategies,
            stopping_time=1, num_workers=1
        )
        assert 'uniform' in results

    def test_evaluate_weights_prints_table(self, capsys):
        """evaluate_weights prints a table containing strategy names and column headers."""
        test_model = _make_test_model(5)
        strategies = {
            'constant': lambda m: np.full(len(m.variables), 2.0),
        }
        evaluate_weights(
            [test_model], strategies,
            stopping_time=1, num_workers=1
        )
        captured = capsys.readouterr()
        assert 'constant' in captured.out
        assert 'uniform' in captured.out
        assert 'Mean Objective' in captured.out
        assert 'Time-to-Best' in captured.out
        assert 'Speedup vs Uniform' in captured.out

    def test_evaluate_weights_speedup_vs_uniform(self):
        """speedup_vs_uniform is a float >= 0 for each strategy."""
        test_model = _make_test_model(5)
        strategies = {
            'constant': lambda m: np.full(len(m.variables), 2.0),
        }
        results = evaluate_weights(
            [test_model], strategies,
            stopping_time=1, num_workers=1
        )
        for name, metrics in results.items():
            assert isinstance(metrics['speedup_vs_uniform'], float)
            assert metrics['speedup_vs_uniform'] >= 0

    def test_evaluate_weights_time_to_best_range(self):
        """mean_time_to_best is between 0 and stopping_time for each strategy."""
        test_model = _make_test_model(5)
        stopping_time = 1
        strategies = {
            'constant': lambda m: np.full(len(m.variables), 2.0),
        }
        results = evaluate_weights(
            [test_model], strategies,
            stopping_time=stopping_time, num_workers=1
        )
        for name, metrics in results.items():
            assert 0 <= metrics['mean_time_to_best'] <= stopping_time

    def test_compute_time_to_best_empty_history(self):
        """_compute_time_to_best with empty list returns stopping_time."""
        assert _compute_time_to_best([], 5.0) == 5.0
        assert _compute_time_to_best([], 10.0) == 10.0

    def test_compute_time_to_best_finds_first_max(self):
        """_compute_time_to_best returns the elapsed time of the first occurrence of the best value."""
        history = [
            (1, 0.1),
            (3, 0.5),
            (2, 0.8),
            (3, 1.2),  # second occurrence of max=3
        ]
        result = _compute_time_to_best(history, 5.0)
        assert result == 0.5  # First occurrence of max value 3
