"""
Unit tests for soft top-k target selection (M19).

Tests the soft_topk_target() helper and its integration into SATTrainer
and OPTTrainer pipelines.
"""

import numpy as np
import pytest

from cbqs.ml.sat_trainer import soft_topk_target, SATTrainer
from cbqs.ml.opt_trainer import OPTTrainer
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

    def __init__(self, n_vars=5, results=None, objective_range=(10, 50),
                 trivially_feasible=False):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_range = objective_range
        self._trivially_feasible = trivially_feasible
        self.constraints_compiled = True

        self.variables = {i: _FakeVar() for i in range(n_vars)}
        self.obj_expr = [[[1, i] for i in range(n_vars)]]
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
    lb = 0
    ub = 1
    vtype = 0


# ------------------------------------------------------------------
# soft_topk_target unit tests
# ------------------------------------------------------------------

class TestSoftTopkTarget:

    def test_topk_selects_k_best(self):
        """Top-k selection picks the k configs with highest scores."""
        configs = [
            {'a': 1.0, 'b': 10.0},
            {'a': 2.0, 'b': 20.0},
            {'a': 3.0, 'b': 30.0},
            {'a': 4.0, 'b': 40.0},
        ]
        scores = [0.1, 0.4, 0.2, 0.3]
        # Top-2 by score: indices 1 (0.4) and 3 (0.3)
        result = soft_topk_target(configs, scores, k=2)
        # Result should be weighted avg of configs[1] and configs[3]
        # weights: 0.4, 0.3 => normalized: 0.4/0.7, 0.3/0.7
        w1 = 0.4 / 0.7
        w3 = 0.3 / 0.7
        expected_a = w1 * 2.0 + w3 * 4.0
        expected_b = w1 * 20.0 + w3 * 40.0
        assert abs(result['a'] - expected_a) < 1e-10
        assert abs(result['b'] - expected_b) < 1e-10

    def test_topk_weights_proportional_to_score(self):
        """Weights are proportional to scores, not uniform."""
        configs = [
            {'x': 0.0},
            {'x': 10.0},
        ]
        # Score ratio 3:1 => weighted avg should be closer to config[0]
        scores = [3.0, 1.0]
        result = soft_topk_target(configs, scores, k=2)
        expected_x = (3.0 * 0.0 + 1.0 * 10.0) / (3.0 + 1.0)
        assert abs(result['x'] - expected_x) < 1e-10

    def test_weighted_avg_params_scalar(self):
        """Scalar parameters are correctly weighted-averaged."""
        configs = [
            {'bias': 5.0, 'factor': 1.0},
            {'bias': 10.0, 'factor': 2.0},
            {'bias': 15.0, 'factor': 3.0},
        ]
        scores = [0.5, 0.3, 0.2]
        result = soft_topk_target(configs, scores, k=3)
        total = 0.5 + 0.3 + 0.2
        expected_bias = (0.5 * 5.0 + 0.3 * 10.0 + 0.2 * 15.0) / total
        expected_factor = (0.5 * 1.0 + 0.3 * 2.0 + 0.2 * 3.0) / total
        assert abs(result['bias'] - expected_bias) < 1e-10
        assert abs(result['factor'] - expected_factor) < 1e-10

    def test_weighted_avg_params_per_variable(self):
        """Per-variable (list) parameters are correctly weighted-averaged."""
        configs = [
            {'weights': [1.0, 2.0, 3.0]},
            {'weights': [4.0, 5.0, 6.0]},
        ]
        scores = [0.6, 0.4]
        result = soft_topk_target(configs, scores, k=2)
        total = 0.6 + 0.4
        w0 = 0.6 / total
        w1 = 0.4 / total
        expected = [w0 * 1.0 + w1 * 4.0,
                    w0 * 2.0 + w1 * 5.0,
                    w0 * 3.0 + w1 * 6.0]
        np.testing.assert_allclose(result['weights'], expected, atol=1e-10)

    def test_weighted_avg_priorities_preserves_ordering(self):
        """Weighted avg of priority values preserves a meaningful ordering.

        If both configs agree on variable ordering (just different magnitudes),
        the weighted average should preserve that ordering.
        """
        # Both configs rank variables as 2 > 1 > 0
        configs = [
            {'priorities': [1.0, 2.0, 3.0]},
            {'priorities': [10.0, 20.0, 30.0]},
        ]
        scores = [0.5, 0.5]
        result = soft_topk_target(configs, scores, k=2)
        prios = result['priorities']
        # Ordering should be preserved: prios[0] < prios[1] < prios[2]
        assert prios[0] < prios[1] < prios[2]

    def test_topk_k_larger_than_n_uses_all(self):
        """When k > number of configs, all configs are used."""
        configs = [
            {'x': 1.0},
            {'x': 3.0},
        ]
        scores = [0.6, 0.4]
        result = soft_topk_target(configs, scores, k=10)
        total = 0.6 + 0.4
        expected = (0.6 * 1.0 + 0.4 * 3.0) / total
        assert abs(result['x'] - expected) < 1e-10

    def test_topk_single_config_returns_itself(self):
        """A single config is returned as-is regardless of k."""
        configs = [{'a': 7.0, 'b': [1.0, 2.0]}]
        scores = [1.0]
        result = soft_topk_target(configs, scores, k=3)
        assert abs(result['a'] - 7.0) < 1e-10
        np.testing.assert_allclose(result['b'], [1.0, 2.0], atol=1e-10)


# ------------------------------------------------------------------
# Trainer integration tests
# ------------------------------------------------------------------

class TestTrainerIntegration:

    def test_sat_trainer_uses_soft_targets(self):
        """SATTrainer uses soft top-k target selection in fit()."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = SATTrainer(
            n_estimators=10, n_strategies=5, refit_every=2,
            random_state=42, target_k=3,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
        # Verify the trainer has the target_k parameter
        assert trainer._target_k == 3

    def test_opt_trainer_uses_soft_targets(self):
        """OPTTrainer uses soft top-k target selection in fit()."""
        models = [FakeModel(n_vars=5) for _ in range(3)]
        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=5,
            top_k=2, n_opt_per_candidate=2,
            refit_every=2, random_state=42, target_k=3,
        )
        trainer.fit(models)
        assert trainer.predictor._is_fitted
        assert trainer._target_k == 3
