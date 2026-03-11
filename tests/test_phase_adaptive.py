"""Tests for phase-aware adaptive_solve() update (M14).

Covers:
- Accepting initial_phase_params from SATTrainer/OPTTrainer
- Per-phase EMA weight updates
- History recording active phase
- Backwards compatibility with unprefixed weights
"""

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.adaptation import adaptive_solve, AdaptiveResult


def _make_sat_model(n_vars):
    """Build a SATISFY-mode model (no objective set)."""
    m = Model()
    xs = m.add_variables(n_vars)
    if n_vars >= 2:
        m.add_constraint(xs[0] + xs[1] <= 1)
    else:
        m.add_constraint(xs[0] + 0 <= 1)
    m.close(validate=False)
    return m


def _make_opt_model(n_vars):
    """Build an OPTIMIZE-mode model with objective."""
    m = Model()
    xs = m.add_variables(n_vars)
    if n_vars >= 2:
        m.add_constraint(xs[0] + xs[1] <= 1)
    else:
        m.add_constraint(xs[0] + 0 <= 1)
    obj_expr = xs[0] + 0
    for i in range(1, n_vars):
        obj_expr = obj_expr + xs[i]
    m.set_objective(obj_expr)
    m.close(validate=False)
    return m


class TestAdaptiveWithSatParams:
    """Test adaptive_solve with SAT-phase initial params."""

    def test_adaptive_with_sat_params(self):
        """adaptive_solve accepts initial_phase_params with sat_ prefixed keys."""
        model = _make_sat_model(5)
        sat_weights = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        phase_params = {
            'sat_branching_weights': sat_weights.tolist(),
        }
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=phase_params, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        assert result.n_rounds_completed == 2
        # First round should use the provided sat weights
        first_entry = result.history[0]
        assert 'phase' in first_entry
        assert first_entry['phase'] == 'sat'
        np.testing.assert_array_equal(
            first_entry['phase_weights']['sat'],
            sat_weights,
        )


class TestAdaptiveWithOptParams:
    """Test adaptive_solve with OPT-phase initial params."""

    def test_adaptive_with_opt_params(self):
        """adaptive_solve accepts initial_phase_params with opt_ prefixed keys."""
        model = _make_opt_model(5)
        opt_sat_weights = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
        opt_weights = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
        phase_params = {
            'opt_sat_branching_weights': opt_sat_weights.tolist(),
            'opt_branching_weights': opt_weights.tolist(),
        }
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=phase_params, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        assert result.n_rounds_completed == 2
        first_entry = result.history[0]
        assert 'phase' in first_entry
        assert first_entry['phase'] == 'opt'


class TestEmaUpdatesPerPhase:
    """Test that EMA updates are applied to phase-specific weights."""

    def test_ema_updates_per_phase(self):
        """EMA updates modify only the weights for the active phase."""
        model = _make_sat_model(5)
        sat_weights = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        phase_params = {
            'sat_branching_weights': sat_weights.tolist(),
        }
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=phase_params, verbose=False
        )
        # Weights should change across rounds due to EMA
        first_w = result.history[0]['phase_weights']['sat']
        last_w = result.history[-1]['phase_weights']['sat']
        assert not np.array_equal(first_w, last_w)

    def test_ema_opt_updates_per_phase(self):
        """EMA updates modify opt-phase weights when in opt mode."""
        model = _make_opt_model(5)
        opt_weights = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        opt_sat_weights = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        phase_params = {
            'opt_branching_weights': opt_weights.tolist(),
            'opt_sat_branching_weights': opt_sat_weights.tolist(),
        }
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=phase_params, verbose=False
        )
        # opt weights should change
        first_opt = result.history[0]['phase_weights']['opt']
        last_opt = result.history[-1]['phase_weights']['opt']
        assert not np.array_equal(first_opt, last_opt)
        # opt_sat weights should also change (both phases updated in opt mode)
        first_opt_sat = result.history[0]['phase_weights']['opt_sat']
        last_opt_sat = result.history[-1]['phase_weights']['opt_sat']
        assert not np.array_equal(first_opt_sat, last_opt_sat)


class TestHistoryRecordsActivePhase:
    """Test that history entries include the active phase."""

    def test_history_records_active_phase(self):
        """Each history entry has a 'phase' key indicating which phase was used."""
        model = _make_sat_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        for entry in result.history:
            assert 'phase' in entry
            assert entry['phase'] in ('sat', 'opt')

    def test_sat_model_records_sat_phase(self):
        """SATISFY-mode model records phase='sat' in history."""
        model = _make_sat_model(5)
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        for entry in result.history:
            assert entry['phase'] == 'sat'

    def test_opt_model_records_opt_phase(self):
        """OPTIMIZE-mode model records phase='opt' in history."""
        model = _make_opt_model(5)
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, verbose=False
        )
        for entry in result.history:
            assert entry['phase'] == 'opt'


class TestBackwardsCompatUnprefixedWeights:
    """Test that existing unprefixed initial_weights still work."""

    def test_backwards_compat_unprefixed_weights(self):
        """initial_weights (unprefixed ndarray) still works as before."""
        model = _make_opt_model(5)
        init_w = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_weights=init_w, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        assert result.n_rounds_completed == 2
        # Should still have weights in history (backwards compat)
        np.testing.assert_array_equal(
            result.history[0]['weights'], init_w
        )

    def test_backwards_compat_none_weights(self):
        """initial_weights=None still defaults to uniform."""
        model = _make_opt_model(5)
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_weights=None, verbose=False
        )
        expected = np.ones(5)
        np.testing.assert_array_equal(
            result.history[0]['weights'], expected
        )


class TestPhasePredictorAsInitialWeights:
    """Test using trainer predictions as initial phase params."""

    def test_phase_predictor_as_initial_weights(self):
        """A dict of phase params from a trainer can initialize adaptive_solve."""
        model = _make_sat_model(5)
        # Simulate trainer output
        phase_params = {
            'sat_branching_weights': [2.0, 3.0, 4.0, 5.0, 6.0],
            'sat_branching_bias': 3.0,
            'sat_branching_factor': 1.5,
            'sat_bias_factor': 0.8,
        }
        result = adaptive_solve(
            model, n_rounds=2, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=phase_params, verbose=False
        )
        assert isinstance(result, AdaptiveResult)
        # The sat weights should be used in first round
        first_entry = result.history[0]
        np.testing.assert_array_almost_equal(
            first_entry['phase_weights']['sat'],
            [2.0, 3.0, 4.0, 5.0, 6.0],
        )
