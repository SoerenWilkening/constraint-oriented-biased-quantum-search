"""
Unit tests for cbqs.ml.sat_trainer -- SATTrainer end-to-end SAT training
pipeline: data collection, feature extraction, regressor training,
prediction, incremental training, logging, and save/load.
"""

import os
import tempfile

import numpy as np
import pytest

from cbqs.ml.sat_trainer import SATTrainer
from cbqs.ml.training_log import TrainingLog
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
    """A fake model for testing the trainer without a real solver.

    Returns configurable results from solve() and supports set_param.
    Provides stub attributes needed by FeatureExtractor.
    """

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
            [[1, 0], [1, 1], 0, 1],   # x0 + x1 <= 1
            [[2, 1], [1, 2], 0, 3],   # 2*x1 + x2 <= 3
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
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, random_state=42,
        )
        trainer.fit([model])
        assert trainer.predictor._is_fitted

    def test_fit_multiple_models(self):
        """Trainer can fit on multiple models."""
        models = [FakeModel(n_vars=5) for _ in range(4)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
        assert len(trainer._collected) == 4

    def test_predict_returns_complete_params(self):
        """Prediction returns all 5 SAT parameter keys."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
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

    def test_predict_weights_nonneg(self):
        """Predicted weights are non-negative."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        params = trainer.predict(FakeModel(n_vars=5))
        weights = params['sat_branching_weights']
        assert all(w >= 0 for w in weights)

    def test_predict_bias_gt_minus_one(self):
        """Predicted bias is > -1."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        params = trainer.predict(FakeModel(n_vars=5))
        assert params['sat_branching_bias'] > -1


# ------------------------------------------------------------------
# Incremental training
# ------------------------------------------------------------------

class TestIncrementalTraining:

    def test_warm_start_increases_trees(self):
        """warm_start adds trees to the ensemble."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)
        trees_before = trainer.predictor.var_regressor.model.n_estimators

        new_models = [FakeModel(n_vars=5) for _ in range(2)]
        trainer.warm_start(new_models, n_new_trees=20)
        trees_after = trainer.predictor.var_regressor.model.n_estimators

        assert trees_after == trees_before + 20

    def test_warm_start_improves_or_maintains(self):
        """warm_start produces a predictor that still predicts."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        new_models = [FakeModel(n_vars=5) for _ in range(2)]
        trainer.warm_start(new_models, n_new_trees=20)

        # Should still predict without error
        params = trainer.predict(FakeModel(n_vars=5))
        assert 'sat_branching_weights' in params

    def test_refit_frequency_default_5(self):
        """Default refit_every is 5."""
        trainer = SATTrainer(n_estimators=10, n_strategies=3)
        assert trainer.refit_every == 5

    def test_refit_frequency_custom(self):
        """Custom refit_every is respected."""
        models = [FakeModel(n_vars=5) for _ in range(6)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=3,
            random_state=42,
        )
        trainer.fit(models)

        # With refit_every=3 and 6 models, there should be 2 refits
        refits = [e for e in trainer.log._events
                  if hasattr(e, 'n_training_models')]
        assert len(refits) == 2


# ------------------------------------------------------------------
# Logging integration
# ------------------------------------------------------------------

class TestLogging:

    def test_fit_logs_strategies(self):
        """fit() logs strategy events for each tried configuration."""
        models = [FakeModel(n_vars=5)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=4, refit_every=1,
            random_state=42,
        )
        trainer.fit(models)

        from cbqs.ml.training_log import StrategyEvent
        strategy_events = [e for e in trainer.log._events
                           if isinstance(e, StrategyEvent)]
        assert len(strategy_events) == 4

    def test_fit_logs_model_summaries(self):
        """fit() logs a model event for each model."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=5,
            random_state=42,
        )
        trainer.fit(models)

        from cbqs.ml.training_log import ModelEvent
        model_events = [e for e in trainer.log._events
                        if isinstance(e, ModelEvent)]
        assert len(model_events) == 3

    def test_fit_logs_refits(self):
        """fit() logs a refit event at refit boundaries."""
        models = [FakeModel(n_vars=5) for _ in range(5)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=5,
            random_state=42,
        )
        trainer.fit(models)

        from cbqs.ml.training_log import RefitEvent
        refit_events = [e for e in trainer.log._events
                        if isinstance(e, RefitEvent)]
        assert len(refit_events) == 1

    def test_warm_start_logs_retrain(self):
        """warm_start() logs a retrain event."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        new_models = [FakeModel(n_vars=5) for _ in range(2)]
        trainer.warm_start(new_models, n_new_trees=20)

        from cbqs.ml.training_log import RetrainEvent
        retrain_events = [e for e in trainer.log._events
                          if isinstance(e, RetrainEvent)]
        assert len(retrain_events) == 1
        evt = retrain_events[0]
        assert evt.trees_after == evt.trees_before + 20


# ------------------------------------------------------------------
# Save / load
# ------------------------------------------------------------------

class TestSaveLoad:

    def test_save_creates_joblib_and_json(self):
        """save() creates predictor.joblib, training_log.json, and config.json."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, 'predictor.joblib'))
            assert os.path.exists(os.path.join(tmpdir, 'training_log.json'))
            assert os.path.exists(os.path.join(tmpdir, 'config.json'))

    def test_load_restores_predictor(self):
        """load() restores a predictor that produces the same predictions."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        test_model = FakeModel(n_vars=5)
        original_params = trainer.predict(test_model)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            loaded = SATTrainer.load(tmpdir)
            loaded_params = loaded.predict(test_model)

        np.testing.assert_array_almost_equal(
            original_params['sat_branching_weights'],
            loaded_params['sat_branching_weights'],
        )
        assert abs(original_params['sat_branching_bias']
                    - loaded_params['sat_branching_bias']) < 1e-10

    def test_load_restores_log(self):
        """load() restores the training log."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        trainer.fit(models)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            loaded = SATTrainer.load(tmpdir)

        from cbqs.ml.training_log import ModelEvent
        original_count = len([e for e in trainer.log._events
                              if isinstance(e, ModelEvent)])
        loaded_count = len([e for e in loaded.log._events
                            if isinstance(e, ModelEvent)])
        assert loaded_count == original_count

    def test_load_restores_nondefault_config(self):
        """Non-default config values survive save/load round-trip."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=20, n_strategies=7, refit_every=3,
            signal='auc', time_budget=10.0, random_state=99,
        )
        trainer.fit(models)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)
            loaded = SATTrainer.load(tmpdir)

        assert loaded._signal_name == 'auc'
        assert loaded.refit_every == 3
        assert loaded._n_strategies == 7
        assert loaded._n_estimators == 20
        assert loaded._time_budget == 10.0
        assert loaded._random_state == 99


# ------------------------------------------------------------------
# Signal selection
# ------------------------------------------------------------------

class TestSignalSelection:

    def test_default_signal_constraint_count(self):
        """Default signal is 'constraint_count' (objective-based)."""
        trainer = SATTrainer(n_estimators=10, n_strategies=3)
        assert trainer._signal_name == 'constraint_count'

    def test_custom_signal_auc(self):
        """Custom AUC signal can be used."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            signal='auc', random_state=42,
        )
        trainer.fit(models)
        assert trainer._signal_name == 'auc'
        assert trainer.predictor._is_fitted
