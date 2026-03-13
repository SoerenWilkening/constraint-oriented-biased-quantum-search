"""
Unit tests for checkpoint callback support in SATTrainer, OPTTrainer,
and ExplorationTrainer.

Validates that each trainer accepts checkpoint_callback and
checkpoint_interval parameters, calls the callback approximately every
checkpoint_interval seconds with (trainer, elapsed_seconds), and works
correctly when no callback is provided.
"""

import tempfile

import numpy as np
import pytest

from cbqs.ml.sat_trainer import SATTrainer
from cbqs.ml.opt_trainer import OPTTrainer
from cbqs.ml.exploration_trainer import ExplorationTrainer
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
    """Fake model for testing trainers without a real solver."""

    def __init__(self, n_vars=5, results=None, objective_range=(10, 50)):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_range = objective_range
        self.constraints_compiled = True

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
# Tests
# ------------------------------------------------------------------

class TestCheckpointCallback:

    def test_sat_trainer_checkpoint_callback(self):
        """SATTrainer calls checkpoint callback during fit."""
        calls = []

        def on_checkpoint(trainer, elapsed):
            calls.append((trainer, elapsed))

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(calls) >= 1
        assert calls[0][0] is trainer

    def test_opt_trainer_checkpoint_callback(self):
        """OPTTrainer calls checkpoint callback during fit."""
        calls = []

        def on_checkpoint(trainer, elapsed):
            calls.append((trainer, elapsed))

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=2, top_k=1,
            n_opt_per_candidate=2, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(calls) >= 1
        assert calls[0][0] is trainer

    def test_exploration_trainer_checkpoint_callback(self):
        """ExplorationTrainer calls checkpoint callback during fit."""
        calls = []

        def on_checkpoint(trainer, elapsed):
            calls.append((trainer, elapsed))

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(calls) >= 1
        assert calls[0][0] is trainer

    def test_checkpoint_interval_respected(self):
        """With a large interval, no checkpoint is called for fast fits."""
        calls = []

        def on_checkpoint(trainer, elapsed):
            calls.append(elapsed)

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=9999.0,
        )
        trainer.fit(models)
        # With a 9999s interval, callback should not be called
        assert len(calls) == 0

    def test_checkpoint_receives_elapsed_time(self):
        """Checkpoint callback receives positive elapsed time."""
        elapsed_times = []

        def on_checkpoint(trainer, elapsed):
            elapsed_times.append(elapsed)

        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
            checkpoint_callback=on_checkpoint,
            checkpoint_interval=0.0,
        )
        trainer.fit(models)
        assert len(elapsed_times) >= 1
        for t in elapsed_times:
            assert isinstance(t, float)
            assert t > 0.0

    def test_no_callback_no_error(self):
        """Trainers work without checkpoint callback (default None)."""
        models = [FakeModel(n_vars=5) for _ in range(3)]

        sat = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        sat.fit(models)
        assert sat.predictor._is_fitted

        opt_models = [FakeModel(n_vars=5) for _ in range(3)]
        opt = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=2, top_k=1,
            n_opt_per_candidate=2, refit_every=2,
            random_state=42,
        )
        opt.fit(opt_models)
        assert opt.predictor._is_fitted

        exp_models = [FakeModel(n_vars=5) for _ in range(3)]
        exp = ExplorationTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        exp.fit(exp_models)
        assert exp.predictor._is_fitted
