"""Tests for adaptive_solve and online adaptation pipeline.

Covers ADAPT-01 (EMA multi-round solve), ADAPT-02 (combined reward signal),
ADAPT-03 (determinism), ADAPT-04 (thread safety).
"""
import threading

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.adaptation import adaptive_solve, AdaptiveResult


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


class TestAdaptiveSolveBasic:
    """Tests for adaptive_solve() core behavior (ADAPT-01)."""

    def test_adaptive_solve_returns_adaptive_result(self):
        """adaptive_solve returns an AdaptiveResult with expected attributes."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        assert hasattr(result, 'best_result')
        assert hasattr(result, 'best_weights')
        assert hasattr(result, 'history')
        assert hasattr(result, 'n_rounds_completed')

    def test_adaptive_result_best_weights_shape(self):
        """best_weights is a 1D float64 ndarray of length n_vars, non-negative."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert isinstance(result.best_weights, np.ndarray)
        assert result.best_weights.shape == (5,)
        assert result.best_weights.dtype == np.float64
        assert np.all(result.best_weights >= 0)

    def test_adaptive_result_history_structure(self):
        """history is a list of n_rounds dicts with required keys."""
        model = _make_test_model(5)
        n_rounds = 3
        result = adaptive_solve(
            model, n_rounds=n_rounds, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert isinstance(result.history, list)
        assert len(result.history) == n_rounds
        for i, entry in enumerate(result.history):
            assert isinstance(entry, dict)
            assert entry['round'] == i + 1
            assert 'objective' in entry
            assert 'feasible' in entry
            assert 'reward' in entry
            assert 'weights' in entry
            assert isinstance(entry['weights'], np.ndarray)

    def test_adaptive_result_n_rounds_completed(self):
        """n_rounds_completed equals the requested n_rounds."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=4, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert result.n_rounds_completed == 4


class TestRewardSignal:
    """Tests for combined reward signal (ADAPT-02)."""

    def test_reward_signal_combines_objective_and_feasibility(self):
        """Reward values are between 0.0 and 1.0 (normalized combined signal)."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        for entry in result.history:
            assert 0.0 <= entry['reward'] <= 1.0

    def test_weights_update_between_rounds(self):
        """EMA should change weights between rounds (not all identical)."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        first_weights = result.history[0]['weights']
        last_weights = result.history[-1]['weights']
        # Weights should differ after EMA updates (unless reward is exactly 1.0
        # which would preserve weights, but that's extremely unlikely)
        assert not np.array_equal(first_weights, last_weights)


class TestInitialWeights:
    """Tests for initial_weights parameter handling."""

    def test_initial_weights_none_defaults_uniform(self):
        """initial_weights=None uses np.ones(n_vars) as starting weights."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_weights=None, verbose=False
        )
        expected = np.ones(5)
        np.testing.assert_array_equal(result.history[0]['weights'], expected)

    def test_initial_weights_ndarray(self):
        """Provided ndarray is used as starting weights."""
        model = _make_test_model(5)
        init_w = np.full(5, 2.0)
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_weights=init_w, verbose=False
        )
        np.testing.assert_array_equal(result.history[0]['weights'], init_w)

    def test_initial_weights_mismatch_raises(self):
        """initial_weights with wrong length raises ValueError."""
        model = _make_test_model(5)
        wrong_weights = np.ones(10)
        with pytest.raises(ValueError, match="length"):
            adaptive_solve(
                model, n_rounds=2, stopping_time=2, num_workers=1,
                seed=42, initial_weights=wrong_weights, verbose=False
            )

    def test_initial_weights_not_mutated(self):
        """Input weight array is not modified by adaptive_solve."""
        model = _make_test_model(5)
        init_w = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        init_w_copy = init_w.copy()
        adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, initial_weights=init_w, verbose=False
        )
        np.testing.assert_array_equal(init_w, init_w_copy)

    def test_initial_weights_weight_predictor(self):
        """WeightPredictor can be passed as initial_weights."""
        from cbqs.ml.training import WeightPredictor

        model = _make_test_model(5)
        weights = np.ones(5, dtype=np.float64)
        predictor = WeightPredictor(random_state=42).fit([(model, weights)])

        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_weights=predictor, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        # First round weights should match predictor output
        expected = predictor.predict(model)
        np.testing.assert_array_equal(result.history[0]['weights'], expected)


class TestModelStateRestoration:
    """Tests for model state cleanup after adaptive_solve."""

    def test_model_restored_after_solve(self):
        """Model's branching_weights are restored after adaptive_solve."""
        model = _make_test_model(5)
        original = model.get_param('branching_weights')
        adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        restored = model.get_param('branching_weights')
        if original is None:
            assert restored is None
        else:
            np.testing.assert_array_equal(restored, original)

    def test_best_weights_from_best_round(self):
        """best_weights matches the weights from the best-performing round."""
        model = _make_test_model(5)
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        # Find the best round using the same ranking as the implementation
        best_entry = None
        for entry in result.history:
            if best_entry is None:
                best_entry = entry
            elif (entry['feasible'], entry['objective']) > (best_entry['feasible'], best_entry['objective']):
                best_entry = entry
        np.testing.assert_array_equal(result.best_weights, best_entry['weights'])


class TestVerboseOutput:
    """Tests for verbose print output."""

    def test_verbose_output(self, capsys):
        """Verbose mode prints per-round summaries."""
        model = _make_test_model(5)
        adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=True
        )
        captured = capsys.readouterr()
        assert 'Round 1/' in captured.out
        assert 'Round 2/' in captured.out

    def test_verbose_false_silent(self, capsys):
        """verbose=False produces no output."""
        model = _make_test_model(5)
        adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        captured = capsys.readouterr()
        assert captured.out == ''


# ---------------------------------------------------------------------------
# Determinism tests (ADAPT-03)
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Tests for deterministic behavior with same seed (ADAPT-03).

    Uses separate model instances for each run to avoid solver internal
    state carryover between runs. The model's C-level solver state may
    persist across solve() calls on the same object.
    """

    def test_determinism_same_seed_same_weights(self):
        """Same seed + num_workers=1 produces identical weights across runs."""
        model1 = _make_test_model(10)
        model2 = _make_test_model(10)
        r1 = adaptive_solve(
            model1, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        r2 = adaptive_solve(
            model2, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert len(r1.history) == len(r2.history)
        for h1, h2 in zip(r1.history, r2.history):
            np.testing.assert_array_equal(h1['weights'], h2['weights'])

    def test_determinism_same_seed_same_objectives(self):
        """Same seed produces identical objectives and feasibility."""
        model1 = _make_test_model(10)
        model2 = _make_test_model(10)
        r1 = adaptive_solve(
            model1, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        r2 = adaptive_solve(
            model2, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        for h1, h2 in zip(r1.history, r2.history):
            assert h1['objective'] == h2['objective']
            assert h1['feasible'] == h2['feasible']

    def test_determinism_same_seed_same_best_result(self):
        """Same seed produces identical best_result and best_weights."""
        model1 = _make_test_model(10)
        model2 = _make_test_model(10)
        r1 = adaptive_solve(
            model1, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        r2 = adaptive_solve(
            model2, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        assert r1.best_result.objective == r2.best_result.objective
        assert r1.best_result.feasible == r2.best_result.feasible
        np.testing.assert_array_equal(r1.best_weights, r2.best_weights)

    def test_determinism_different_seeds_differ(self):
        """Different seeds produce different results (determinism is not trivial)."""
        model1 = _make_test_model(10)
        model2 = _make_test_model(10)
        r1 = adaptive_solve(
            model1, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        r2 = adaptive_solve(
            model2, n_rounds=3, stopping_time=2, num_workers=1,
            seed=99, verbose=False
        )
        # At least one round's weights should differ between the two runs
        any_differ = False
        for h1, h2 in zip(r1.history, r2.history):
            if not np.array_equal(h1['weights'], h2['weights']):
                any_differ = True
                break
        assert any_differ, "Different seeds should produce different weights"


# ---------------------------------------------------------------------------
# Thread safety tests (ADAPT-04)
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Tests for concurrent adaptive_solve on different models (ADAPT-04)."""

    def test_concurrent_different_models_no_error(self):
        """Concurrent adaptive_solve on different models completes without errors."""
        model1 = _make_test_model(5)
        model2 = _make_test_model(8)
        results = [None, None]
        errors = [None, None]

        def run(idx, model):
            try:
                results[idx] = adaptive_solve(
                    model, n_rounds=3, stopping_time=2, num_workers=1,
                    seed=42, verbose=False
                )
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=run, args=(0, model1))
        t2 = threading.Thread(target=run, args=(1, model2))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"
        assert results[0] is not None
        assert results[1] is not None

    def test_concurrent_correct_shapes(self):
        """Concurrent results have correct best_weights shapes for their models."""
        model1 = _make_test_model(5)
        model2 = _make_test_model(8)
        results = [None, None]
        errors = [None, None]

        def run(idx, model):
            try:
                results[idx] = adaptive_solve(
                    model, n_rounds=3, stopping_time=2, num_workers=1,
                    seed=42, verbose=False
                )
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=run, args=(0, model1))
        t2 = threading.Thread(target=run, args=(1, model2))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"
        assert results[0].best_weights.shape == (5,)
        assert results[1].best_weights.shape == (8,)

    def test_concurrent_independent_histories(self):
        """Each concurrent result's history has correct sizes for its model."""
        model1 = _make_test_model(5)
        model2 = _make_test_model(8)
        n_rounds = 3
        results = [None, None]
        errors = [None, None]

        def run(idx, model):
            try:
                results[idx] = adaptive_solve(
                    model, n_rounds=n_rounds, stopping_time=2, num_workers=1,
                    seed=42, verbose=False
                )
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=run, args=(0, model1))
        t2 = threading.Thread(target=run, args=(1, model2))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"

        # Each history should have correct length and weight sizes
        assert len(results[0].history) == n_rounds
        assert len(results[1].history) == n_rounds
        for entry in results[0].history:
            assert entry['weights'].shape == (5,)
        for entry in results[1].history:
            assert entry['weights'].shape == (8,)
