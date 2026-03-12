"""
Unit tests for M18: composite signal + annealing.

Tests compute_normalized_auc(), compute_composite_signal(),
compute_annealing_a() in cbqs.ml.signals, and trainer integration.
"""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from cbqs.ml.signals import (
    compute_auc,
    compute_normalized_auc,
    compute_composite_signal,
    compute_annealing_a,
)
from cbqs.result import OptimizeResult


# ===================================================================
# compute_normalized_auc
# ===================================================================


class TestNormalizedAUC:
    """Tests for compute_normalized_auc -- AUC as fraction of ideal."""

    def test_normalized_auc_fraction_of_ideal(self):
        """Perfect run (find best at t=0) gives normalized AUC = 1.0."""
        # best=10, worst=0, history: (10, 0.0), total_time=5
        # Internally normalized history: (1.0, 0.0)
        # AUC on normalized = 1.0 * 5 = 5.0
        # Ideal = 1.0 * 5 = 5.0 -> normalized_auc = 5.0/5.0 = 1.0
        history = [(10.0, 0.0)]
        result = compute_normalized_auc(history, total_time=5.0,
                                        best=10.0, worst=0.0)
        assert result == pytest.approx(1.0)

    def test_normalized_auc_half_ideal(self):
        """Finding the best halfway through gives ~0.5 normalized AUC."""
        # worst=0, best=10, total_time=4
        # history: (0, 0.0), (10, 2.0)
        # normalized history: (0, 0.0), (1.0, 2.0)
        # AUC = 0 * (2-0) + 1.0 * (4-2) = 2.0
        # Ideal = 1.0 * 4 = 4.0 -> 2.0/4.0 = 0.5
        history = [(0.0, 0.0), (10.0, 2.0)]
        result = compute_normalized_auc(history, total_time=4.0,
                                        best=10.0, worst=0.0)
        assert result == pytest.approx(0.5)

    def test_normalized_auc_empty_history(self):
        """Empty history returns 0.0."""
        result = compute_normalized_auc([], total_time=5.0,
                                        best=10.0, worst=0.0)
        assert result == pytest.approx(0.0)

    def test_normalized_auc_best_equals_worst(self):
        """best == worst returns 0.0 (no discriminating range)."""
        history = [(5.0, 0.0)]
        result = compute_normalized_auc(history, total_time=5.0,
                                        best=5.0, worst=5.0)
        assert result == pytest.approx(0.0)

    def test_normalized_auc_partial_improvement(self):
        """Partial improvement scenario."""
        # worst=0, best=100, total_time=10
        # history: (20, 0.0), (60, 5.0)
        # normalized: (0.2, 0.0), (0.6, 5.0)
        # AUC = 0.2 * 5 + 0.6 * 5 = 1.0 + 3.0 = 4.0
        # Ideal = 1.0 * 10 = 10.0 -> 4.0/10.0 = 0.4
        history = [(20.0, 0.0), (60.0, 5.0)]
        result = compute_normalized_auc(history, total_time=10.0,
                                        best=100.0, worst=0.0)
        assert result == pytest.approx(0.4)


# ===================================================================
# compute_composite_signal
# ===================================================================


class TestCompositeSignal:
    """Tests for compute_composite_signal."""

    def test_composite_signal_basic(self):
        """score = normalized_AUC + a * best_normalized_objective."""
        score = compute_composite_signal(
            normalized_auc=0.5, best_normalized_obj=0.8, a=0.5)
        assert score == pytest.approx(0.5 + 0.5 * 0.8)

    def test_composite_signal_a_high_favors_objective(self):
        """With high a, objective quality dominates."""
        # Config A: low AUC but high obj
        score_a = compute_composite_signal(
            normalized_auc=0.2, best_normalized_obj=1.0, a=0.9)
        # Config B: high AUC but low obj
        score_b = compute_composite_signal(
            normalized_auc=0.8, best_normalized_obj=0.3, a=0.9)
        assert score_a > score_b

    def test_composite_signal_a_low_favors_auc(self):
        """With low a, AUC (speed) dominates."""
        # Config A: low AUC but high obj
        score_a = compute_composite_signal(
            normalized_auc=0.2, best_normalized_obj=1.0, a=0.1)
        # Config B: high AUC but low obj
        score_b = compute_composite_signal(
            normalized_auc=0.8, best_normalized_obj=0.3, a=0.1)
        assert score_b > score_a

    def test_composite_signal_a_zero(self):
        """a=0 gives pure AUC score."""
        score = compute_composite_signal(
            normalized_auc=0.7, best_normalized_obj=1.0, a=0.0)
        assert score == pytest.approx(0.7)

    def test_composite_signal_a_one(self):
        """a=1 gives AUC + full objective weight."""
        score = compute_composite_signal(
            normalized_auc=0.3, best_normalized_obj=0.6, a=1.0)
        assert score == pytest.approx(0.3 + 0.6)


# ===================================================================
# compute_annealing_a
# ===================================================================


class TestAnnealingA:
    """Tests for compute_annealing_a -- derive a from variance."""

    def test_annealing_high_variance_gives_high_a(self):
        """High within-instance variance of best_objective -> high a."""
        # All instances have high variance
        variances = [100.0, 200.0, 150.0]
        a = compute_annealing_a(variances, a_min=0.1, a_max=0.9)
        assert a > 0.5

    def test_annealing_low_variance_gives_low_a(self):
        """Low within-instance variance -> low a."""
        variances = [0.001, 0.002, 0.0005]
        a = compute_annealing_a(variances, a_min=0.1, a_max=0.9)
        assert a < 0.5

    def test_annealing_median_across_instances(self):
        """a is based on median variance, not mean."""
        # One very high outlier, but median is low
        variances = [0.001, 0.002, 1000.0]
        a = compute_annealing_a(variances, a_min=0.1, a_max=0.9)
        # Median variance is 0.002 -> should give low a
        assert a < 0.5

    def test_annealing_clamps_to_range(self):
        """Result always in [a_min, a_max]."""
        # Very high variances
        a_high = compute_annealing_a([1e10, 1e10], a_min=0.1, a_max=0.9)
        assert a_high <= 0.9
        assert a_high >= 0.1

        # Very low variances
        a_low = compute_annealing_a([0.0, 0.0], a_min=0.1, a_max=0.9)
        assert a_low <= 0.9
        assert a_low >= 0.1

    def test_annealing_empty_variances(self):
        """Empty list returns midpoint of range."""
        a = compute_annealing_a([], a_min=0.1, a_max=0.9)
        assert a == pytest.approx(0.5)

    def test_annealing_single_instance(self):
        """Single instance variance works."""
        a = compute_annealing_a([1.0], a_min=0.1, a_max=0.9)
        assert 0.1 <= a <= 0.9

    def test_annealing_monotone_in_variance(self):
        """Higher median variance -> higher a."""
        a_low = compute_annealing_a([0.01, 0.02, 0.015],
                                     a_min=0.1, a_max=0.9)
        a_high = compute_annealing_a([10.0, 20.0, 15.0],
                                      a_min=0.1, a_max=0.9)
        assert a_high > a_low


# ===================================================================
# Composite with renormalized values
# ===================================================================


class TestCompositeWithRenormalization:
    """Test composite signal works with values from InstanceNormalizer."""

    def test_composite_with_renormalized_values(self):
        """End-to-end: normalized AUC + a * normalized obj."""
        # Simulate: best=100, worst=0, history [(30, 0.0), (80, 2.0)],
        # total_time=4
        best, worst = 100.0, 0.0
        history = [(30.0, 0.0), (80.0, 2.0)]
        total_time = 4.0

        norm_auc = compute_normalized_auc(history, total_time, best, worst)
        # normalized history: (0.3, 0.0), (0.8, 2.0)
        # AUC = 0.3*2 + 0.8*2 = 0.6 + 1.6 = 2.2
        # ideal = 1.0 * 4 = 4.0 -> 2.2/4.0 = 0.55
        assert norm_auc == pytest.approx(0.55)

        best_norm_obj = (80.0 - worst) / (best - worst)  # 0.8
        a = 0.5
        score = compute_composite_signal(norm_auc, best_norm_obj, a)
        assert score == pytest.approx(0.55 + 0.5 * 0.8)


# ===================================================================
# Trainer integration tests
# ===================================================================


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


class _FakeVar:
    """Stub variable for FeatureExtractor."""
    lb = 0
    ub = 1
    vtype = 0


class _FakeModel:
    """Minimal model stub for trainer integration tests."""

    def __init__(self, n_vars=5, results=None):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
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
        lo, hi = 10, 50
        obj = lo + (idx % 10) * (hi - lo) / 10
        return _make_result(
            objective=obj,
            solution=[1] * self.n,
            history=[(obj * 0.8, 0.01), (obj, 0.05)],
        )


class TestTrainerUsesCompositeSignal:
    """Verify that trainers use compute_composite_signal for scoring."""

    def test_trainer_uses_composite_signal(self):
        """SATTrainer._select_best_composite calls compute_composite_signal."""
        from cbqs.ml.sat_trainer import SATTrainer

        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, random_state=42,
        )

        # Build fake all_results with known objective/history values
        results = []
        for obj in [10.0, 30.0, 50.0]:
            result = _make_result(
                objective=obj,
                history=[(obj * 0.5, 0.01), (obj, 0.05)],
                solve_time=100.0,
            )
            results.append({
                'params': {'sat_branching_bias': obj},
                'result': result,
                'signal': obj,
            })

        with patch('cbqs.ml.sat_trainer.compute_composite_signal',
                   wraps=compute_composite_signal) as mock_cs:
            best_params, best_score = trainer._select_best_composite(results)
            assert mock_cs.call_count == len(results)
            # Best should be obj=50 (highest composite score)
            assert best_params['sat_branching_bias'] == 50.0
            assert best_score > 0.0

    def test_opt_trainer_uses_composite_signal(self):
        """OPTTrainer._select_best_composite calls compute_composite_signal."""
        from cbqs.ml.opt_trainer import OPTTrainer

        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=3, random_state=42,
        )

        results = []
        for obj in [10.0, 30.0, 50.0]:
            result = _make_result(
                objective=obj,
                history=[(obj * 0.5, 0.01), (obj, 0.05)],
                solve_time=100.0,
            )
            results.append({
                'opt_sat_params': {'opt_sat_branching_bias': obj},
                'opt_params': {'opt_branching_bias': obj},
                'result': result,
                'signal': obj,
            })

        with patch('cbqs.ml.opt_trainer.compute_composite_signal',
                   wraps=compute_composite_signal) as mock_cs:
            opt_sat_p, opt_p, score = trainer._select_best_composite(results)
            assert mock_cs.call_count == len(results)
            assert opt_p['opt_branching_bias'] == 50.0
            assert score > 0.0


class TestTrainerAnnealsAOverTraining:
    """Verify that a changes over training as variance accumulates."""

    def test_trainer_anneals_a_over_training(self):
        """SATTrainer._current_a changes after refit as data accumulates."""
        from cbqs.ml.sat_trainer import SATTrainer

        trainer = SATTrainer(
            n_estimators=10, n_strategies=3, refit_every=2,
            random_state=42,
        )
        initial_a = trainer._current_a

        # Train on several models so refits happen
        models = [_FakeModel(n_vars=5) for _ in range(4)]
        trainer.fit(models)

        # After training, _current_a should have been updated by
        # compute_annealing_a (not still at the initial value)
        assert trainer._current_a != initial_a
        assert 0.1 <= trainer._current_a <= 0.9

    def test_opt_trainer_anneals_a_over_training(self):
        """OPTTrainer._current_a changes after refit as data accumulates."""
        from cbqs.ml.opt_trainer import OPTTrainer

        trainer = OPTTrainer(
            n_estimators=10, n_opt_sat_strategies=2, top_k=1,
            n_opt_per_candidate=2, refit_every=2, random_state=42,
        )
        initial_a = trainer._current_a

        models = [_FakeModel(n_vars=5) for _ in range(4)]
        trainer.fit(models)

        assert trainer._current_a != initial_a
        assert 0.1 <= trainer._current_a <= 0.9
