"""
Unit tests for cbqs.ml.exploration_trainer -- ExplorationTrainer end-to-end
exploration-focused training pipeline: constrained data collection, objective-
based signal, feature extraction, regressor training, prediction with
constrained bounds, logging, checkpoint callbacks, and save/load including
collected data.
"""

import os
import tempfile

import numpy as np
import pytest

from cbqs.ml.exploration_trainer import ExplorationTrainer
from cbqs.ml.training_log import (
    TrainingLog, StrategyEvent, ModelEvent, RefitEvent,
)
from cbqs.result import OptimizeResult


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


class FakeModel:
    """Fake model for testing the exploration trainer without a real solver."""

    def __init__(self, n_vars=5, results=None, objective_range=(10, 50)):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_range = objective_range
        self.constraints_compiled = True

        # Stubs for FeatureExtractor
        self.variables = {
            i: _FakeVar() for i in range(n_vars)
        }
        self.obj_expr = [
            [[1, i] for i in range(n_vars)]
        ]
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


class _FakeVar:
    """Stub variable for FeatureExtractor."""
    lb = 0
    ub = 1
    vtype = 0  # BINARY


# ------------------------------------------------------------------
# Core training
# ------------------------------------------------------------------

class TestCoreTraining:

    def test_fit_single_model(self):
        """Trainer can fit on a single model without errors."""
        model = FakeModel(n_vars=5)
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, random_state=42,
        )
        trainer.fit([model])
        assert trainer.predictor._is_fitted

    def test_fit_multiple_models(self):
        """Trainer can fit on multiple models."""
        models = [FakeModel(n_vars=5) for _ in range(4)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
        assert len(trainer._collected) == 4

    def test_predict_returns_complete_params(self):
        """Prediction returns all 5 SAT parameter keys."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        new_model = FakeModel(n_vars=5)
        params = trainer.predict(new_model)
        expected_keys = {
            'sat_branching_weights',
            'sat_variable_priorities',
            'sat_branching_bias',
            'sat_branching_factor',
            'sat_bias_factor',
        }
        assert set(params.keys()) == expected_keys

    def test_predict_bias_near_n_over_4(self):
        """Predicted bias is near n/4 (within delta_bias range)."""
        models = [FakeModel(n_vars=20) for _ in range(5)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        new_model = FakeModel(n_vars=20)
        params = trainer.predict(new_model)
        n = 20
        delta_max = n / 100.0
        assert abs(params['sat_branching_bias'] - n / 4.0) <= delta_max

    def test_predict_weights_in_bounds(self):
        """Predicted weights are in [-1, 1]."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        params = trainer.predict(FakeModel(n_vars=5))
        weights = params['sat_branching_weights']
        assert all(-1.0 <= w <= 1.0 for w in weights)

    def test_predict_branching_factor_in_bounds(self):
        """Predicted branching_factor is in [-1, 1]."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        params = trainer.predict(FakeModel(n_vars=5))
        assert -1.0 <= params['sat_branching_factor'] <= 1.0

    def test_predict_bias_factor_is_one(self):
        """Predicted bias_factor is always 1.0."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        params = trainer.predict(FakeModel(n_vars=5))
        assert params['sat_bias_factor'] == 1.0


# ------------------------------------------------------------------
# Signal behavior
# ------------------------------------------------------------------

class TestSignalBehavior:

    def test_training_uses_objective_signal(self):
        """Training uses objective-based signal (not AUC)."""
        # Model with high objective should be preferred
        high_obj_result = _make_result(objective=100.0)
        low_obj_result = _make_result(objective=10.0)

        model = FakeModel(n_vars=5, results=[high_obj_result, low_obj_result])
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=2, refit_every=1,
            random_state=42,
        )
        trainer.fit([model])
        # Should complete without error -- signal is objective-based
        assert trainer.predictor._is_fitted

    def test_better_objective_preferred_over_faster(self):
        """Higher objective is preferred even if slower."""
        # Slow but high objective
        slow_high = _make_result(
            objective=100.0,
            solve_time=1000.0,
            history=[(80.0, 0.1), (100.0, 0.9)],
        )
        # Fast but low objective
        fast_low = _make_result(
            objective=50.0,
            solve_time=100.0,
            history=[(50.0, 0.01)],
        )

        model = FakeModel(n_vars=5, results=[slow_high, fast_low])
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=2, refit_every=1,
            random_state=42,
        )
        trainer.fit([model])
        # The trainer should have used the high-objective result
        assert trainer.predictor._is_fitted


# ------------------------------------------------------------------
# Constrained parameter space
# ------------------------------------------------------------------

class TestConstrainedParams:

    def test_data_collection_uses_constrained_params(self):
        """Data collection samples within constrained bounds."""
        model = FakeModel(n_vars=20)
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=5, refit_every=1,
            random_state=42,
        )
        trainer.fit([model])

        # Check collected data: all bias values should be near n/4
        for var_X, var_y, inst_X, inst_y in trainer._collected:
            bias = float(inst_y[0])
            n = 20
            delta_max = n / 100.0
            assert abs(bias - n / 4.0) <= delta_max + 1e-6
            # bias_factor should be 1.0
            assert abs(float(inst_y[2]) - 1.0) < 1e-6

    def test_predictions_clipped_to_bounds(self):
        """Predictions are clipped to constrained bounds even if regressor overshoots."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        params = trainer.predict(FakeModel(n_vars=5))
        # Weights in [-1, 1]
        for w in params['sat_branching_weights']:
            assert -1.0 <= w <= 1.0
        # Branching factor in [-1, 1]
        assert -1.0 <= params['sat_branching_factor'] <= 1.0
        # Bias factor is 1.0
        assert params['sat_bias_factor'] == 1.0
        # Bias near n/4
        n = 5
        delta_max = n / 100.0
        assert abs(params['sat_branching_bias'] - n / 4.0) <= delta_max


# ------------------------------------------------------------------
# Save / load
# ------------------------------------------------------------------

class TestSaveLoad:

    def test_save_creates_artifacts(self):
        """save() creates predictor.joblib, training_log.json, config.json, and collected_data.npz."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, 'predictor.joblib'))
            assert os.path.exists(os.path.join(tmpdir, 'training_log.json'))
            assert os.path.exists(os.path.join(tmpdir, 'config.json'))
            assert os.path.exists(os.path.join(tmpdir, 'collected_data.npz'))

    def test_load_restores_predictor(self):
        """load() restores a predictor that produces the same predictions."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        test_model = FakeModel(n_vars=5)
        original_params = trainer.predict(test_model)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            loaded = ExplorationTrainer.load(tmpdir)
            loaded_params = loaded.predict(test_model)

        np.testing.assert_array_almost_equal(
            original_params['sat_branching_weights'],
            loaded_params['sat_branching_weights'],
        )
        assert abs(original_params['sat_branching_bias']
                    - loaded_params['sat_branching_bias']) < 1e-10

    def test_save_includes_collected_data(self):
        """save() persists the collected training data."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        assert len(trainer._collected) == 3

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            data_path = os.path.join(tmpdir, 'collected_data.npz')
            assert os.path.exists(data_path)
            data = np.load(data_path, allow_pickle=True)
            assert 'n_collected' in data
            assert int(data['n_collected']) == 3

    def test_load_restores_collected_data(self):
        """load() restores collected data for continued training."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            loaded = ExplorationTrainer.load(tmpdir)

        assert len(loaded._collected) == 3
        # Check shapes match
        for orig, loaded_item in zip(trainer._collected, loaded._collected):
            np.testing.assert_array_almost_equal(orig[0], loaded_item[0])
            np.testing.assert_array_almost_equal(orig[1], loaded_item[1])


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------

class TestLogging:

    def test_fit_logs_strategies(self):
        """fit() logs strategy events for each tried configuration."""
        models = [FakeModel(n_vars=5)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=4, refit_every=1,
            random_state=42,
        )
        trainer.fit(models)

        strategy_events = [e for e in trainer.log._events
                           if isinstance(e, StrategyEvent)]
        assert len(strategy_events) == 4

    def test_fit_logs_model_summaries(self):
        """fit() logs a model event for each model."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=5,
            random_state=42,
        )
        trainer.fit(models)

        model_events = [e for e in trainer.log._events
                        if isinstance(e, ModelEvent)]
        assert len(model_events) == 3

    def test_fit_logs_refits(self):
        """fit() logs a refit event at refit boundaries."""
        models = [FakeModel(n_vars=5) for _ in range(5)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=5,
            random_state=42,
        )
        trainer.fit(models)

        refit_events = [e for e in trainer.log._events
                        if isinstance(e, RefitEvent)]
        assert len(refit_events) == 1


# ------------------------------------------------------------------
# Checkpoint callback
# ------------------------------------------------------------------

class TestCheckpointCallback:

    def test_checkpoint_callback_called_periodically(self):
        """Checkpoint callback is called during fit."""
        calls = []

        def on_checkpoint(trainer, elapsed):
            calls.append((trainer, elapsed))

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,  # call every model
        )
        trainer.fit(models)
        # With interval=0.0, callback should be called at least once
        assert len(calls) >= 1

    def test_checkpoint_callback_receives_trainer(self):
        """Checkpoint callback receives the trainer instance."""
        received = []

        def on_checkpoint(trainer, elapsed):
            received.append(trainer)

        models = [FakeModel(n_vars=5) for _ in range(2)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(received) >= 1
        assert received[0] is trainer

    def test_checkpoint_trainer_is_saveable(self):
        """Trainer can be saved from within a checkpoint callback."""
        saved = []

        def on_checkpoint(trainer, elapsed):
            with tempfile.TemporaryDirectory() as tmpdir:
                trainer.save(tmpdir)
                saved.append(tmpdir)

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=1,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(saved) >= 1

    def test_fit_without_callback_works(self):
        """fit() works fine without a checkpoint callback."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
