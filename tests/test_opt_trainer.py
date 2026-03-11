"""
Unit tests for cbqs.ml.opt_trainer -- OPTTrainer end-to-end OPT training
pipeline: Option C data collection, joint opt_sat/opt training, trivially-
feasible exclusion, screening budget, AUC/weighted signals, incremental
training, logging, and save/load.
"""

import os
import tempfile

import numpy as np
import pytest

from cbqs.ml.opt_trainer import OPTTrainer
from cbqs.ml.training_log import (
    TrainingLog, StrategyEvent, ModelEvent, RefitEvent, RetrainEvent,
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
    """Fake model for testing the OPT trainer without a real solver."""

    def __init__(self, n_vars=5, results=None, objective_range=(10, 50),
                 trivially_feasible=False):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_range = objective_range
        self._trivially_feasible = trivially_feasible
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
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            random_state=42,
        )
        trainer.fit([model])
        assert trainer.predictor._is_fitted

    def test_fit_multiple_models(self):
        """Trainer can fit on multiple models."""
        models = [FakeModel(n_vars=5) for _ in range(4)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
        assert len(trainer._collected) == 4

    def test_predict_returns_opt_sat_and_opt_params(self):
        """Prediction returns all 10 OPT parameter keys."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)

        new_model = FakeModel(n_vars=5)
        params = trainer.predict(new_model)
        expected_keys = {
            'opt_sat_branching_weights',
            'opt_sat_variable_priorities',
            'opt_sat_branching_bias',
            'opt_sat_branching_factor',
            'opt_sat_bias_factor',
            'opt_branching_weights',
            'opt_variable_priorities',
            'opt_branching_bias',
            'opt_branching_factor',
            'opt_bias_factor',
        }
        assert set(params.keys()) == expected_keys

    def test_predict_params_valid(self):
        """Predicted parameters satisfy validity constraints."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)

        params = trainer.predict(FakeModel(n_vars=5))
        # Weights non-negative
        assert all(w >= 0 for w in params['opt_sat_branching_weights'])
        assert all(w >= 0 for w in params['opt_branching_weights'])
        # Bias > -1
        assert params['opt_sat_branching_bias'] > -1
        assert params['opt_branching_bias'] > -1
        # Factors non-negative
        assert params['opt_sat_branching_factor'] >= 0
        assert params['opt_sat_bias_factor'] >= 0
        assert params['opt_branching_factor'] >= 0
        assert params['opt_bias_factor'] >= 0


# ------------------------------------------------------------------
# Option C data collection integration
# ------------------------------------------------------------------

class TestOptionC:

    def test_trivially_feasible_excluded_from_opt_sat(self):
        """Trivially feasible models have no opt_sat params in targets."""
        model = FakeModel(n_vars=5, trivially_feasible=True)
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=1, random_state=42,
        )
        trainer.fit([model])
        # Collected data should mark as trivially feasible
        assert trainer._collected[0][4] is True  # trivially_feasible flag

    def test_non_trivially_feasible_trains_both(self):
        """Non-trivially feasible models produce both opt_sat and opt targets."""
        model = FakeModel(n_vars=5, trivially_feasible=False)
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=1, random_state=42,
        )
        trainer.fit([model])
        assert trainer._collected[0][4] is False  # not trivially_feasible

    def test_screening_budget_respected(self):
        """Screening budget is passed to the collector."""
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            screening_budget=5.0, random_state=42,
        )
        assert trainer.collector.screening_budget == 5.0

    def test_full_budget_respected(self):
        """Full budget is passed to the collector."""
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            full_budget=30.0, random_state=42,
        )
        assert trainer.collector.full_budget == 30.0


# ------------------------------------------------------------------
# Joint training
# ------------------------------------------------------------------

class TestJointTraining:

    def test_opt_sat_and_opt_regressors_independent(self):
        """The predictor uses a single PhasePredictor in 'opt' mode with
        independent variable outputs for opt_sat and opt phases."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)
        assert trainer.predictor.mode == 'opt'
        # Variable regressor has 4 outputs (opt_sat_w, opt_sat_p, opt_w, opt_p)
        assert trainer.predictor.var_regressor.n_outputs == 4
        # Instance regressor has 6 outputs
        assert trainer.predictor.inst_regressor.n_outputs == 6

    def test_joint_prediction_coherent(self):
        """Joint prediction returns arrays of correct shape."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)

        params = trainer.predict(FakeModel(n_vars=5))
        assert len(params['opt_sat_branching_weights']) == 5
        assert len(params['opt_sat_variable_priorities']) == 5
        assert len(params['opt_branching_weights']) == 5
        assert len(params['opt_variable_priorities']) == 5


# ------------------------------------------------------------------
# Incremental training
# ------------------------------------------------------------------

class TestIncrementalTraining:

    def test_warm_start(self):
        """warm_start adds trees and keeps predictor functional."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42,
        )
        trainer.fit(models)
        trees_before = trainer.predictor.var_regressor.model.n_estimators

        new_models = [FakeModel(n_vars=5) for _ in range(2)]
        trainer.warm_start(new_models, n_new_trees=20)
        trees_after = trainer.predictor.var_regressor.model.n_estimators

        assert trees_after == trees_before + 20

        # Should still predict without error
        params = trainer.predict(FakeModel(n_vars=5))
        assert 'opt_branching_weights' in params

    def test_refit_frequency(self):
        """Refit happens at the configured frequency."""
        models = [FakeModel(n_vars=5) for _ in range(6)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=3, random_state=42,
        )
        trainer.fit(models)

        refits = [e for e in trainer.log._events
                  if isinstance(e, RefitEvent)]
        assert len(refits) == 2


# ------------------------------------------------------------------
# Signal options
# ------------------------------------------------------------------

class TestSignalOptions:

    def test_auc_signal(self):
        """AUC signal is the default and works."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            signal='auc', refit_every=2, random_state=42,
        )
        trainer.fit(models)
        assert trainer._signal_name == 'auc'
        assert trainer.predictor._is_fitted

    def test_weighted_signal(self):
        """Weighted signal can be used."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            signal='weighted', signal_kwargs={'lam': 0.5},
            refit_every=2, random_state=42,
        )
        trainer.fit(models)
        assert trainer._signal_name == 'weighted'
        assert trainer.predictor._is_fitted


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------

class TestLogging:

    def test_fit_logs_all_levels(self):
        """fit() produces strategy, model, and refit events."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=3, random_state=42,
        )
        trainer.fit(models)

        strat_events = [e for e in trainer.log._events
                        if isinstance(e, StrategyEvent)]
        model_events = [e for e in trainer.log._events
                        if isinstance(e, ModelEvent)]
        refit_events = [e for e in trainer.log._events
                        if isinstance(e, RefitEvent)]

        assert len(strat_events) > 0
        assert len(model_events) == 3
        assert len(refit_events) >= 1

    def test_log_includes_trivially_feasible_flag(self):
        """Model events record the trivially_feasible flag."""
        model_tf = FakeModel(n_vars=5, trivially_feasible=True)
        model_ntf = FakeModel(n_vars=5, trivially_feasible=False)
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            refit_every=5, random_state=42,
        )
        trainer.fit([model_tf, model_ntf])

        model_events = [e for e in trainer.log._events
                        if isinstance(e, ModelEvent)]
        assert model_events[0].trivially_feasible is True
        assert model_events[1].trivially_feasible is False

    def test_log_captures_screening_phase(self):
        """Strategy events include screening phase entries."""
        model = FakeModel(n_vars=5, trivially_feasible=False)
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=4,
            top_k=2, n_opt_per_candidate=2,
            refit_every=1, random_state=42,
        )
        trainer.fit([model])

        strat_events = [e for e in trainer.log._events
                        if isinstance(e, StrategyEvent)]
        phases = set(e.phase for e in strat_events)
        # Should have pair evaluation (opt_sat+opt) or opt-only phases
        assert 'opt_sat+opt' in phases or 'opt' in phases


# ------------------------------------------------------------------
# Save / load
# ------------------------------------------------------------------

class TestSaveLoad:

    def test_save_load_roundtrip(self):
        """Save/load preserves predictor and config."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3,
            top_k=2, n_opt_per_candidate=2,
            signal='auc', refit_every=2,
            screening_budget=5.0, full_budget=30.0,
            random_state=42,
        )
        trainer.fit(models)

        test_model = FakeModel(n_vars=5)
        original_params = trainer.predict(test_model)

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer.save(tmpdir)

            assert os.path.exists(os.path.join(tmpdir, 'predictor.joblib'))
            assert os.path.exists(os.path.join(tmpdir, 'training_log.json'))
            assert os.path.exists(os.path.join(tmpdir, 'config.json'))

            loaded = OPTTrainer.load(tmpdir)

        loaded_params = loaded.predict(test_model)

        np.testing.assert_array_almost_equal(
            original_params['opt_branching_weights'],
            loaded_params['opt_branching_weights'],
        )
        assert abs(original_params['opt_branching_bias']
                   - loaded_params['opt_branching_bias']) < 1e-10

        # Config values preserved
        assert loaded._signal_name == 'auc'
        assert loaded.refit_every == 2
        assert loaded._n_opt_sat_strategies == 3
        assert loaded._top_k == 2
        assert loaded._n_opt_per_candidate == 2
        assert loaded._screening_budget == 5.0
        assert loaded._full_budget == 30.0
        assert loaded._random_state == 42

        # Log preserved
        original_model_count = len([e for e in trainer.log._events
                                    if isinstance(e, ModelEvent)])
        loaded_model_count = len([e for e in loaded.log._events
                                  if isinstance(e, ModelEvent)])
        assert loaded_model_count == original_model_count
