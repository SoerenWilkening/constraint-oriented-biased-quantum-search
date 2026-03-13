"""Tests for phase-switch logic in adaptive_solve() (M24).

Covers:
- Phase switch triggers on stall (relative improvement < epsilon)
- Set B params used after switch
- No oscillation back to Set A
- Configurable epsilon
- Switch round recorded in history
- No switch when continuously improving
- Switch on first stall round
- Backwards compatibility when no Set B params given
"""

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.ml.adaptation import adaptive_solve, AdaptiveResult


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


class TestPhaseSwitch:
    """Tests for phase-switch (greedy -> exploration) in adaptive_solve."""

    def test_phase_switch_triggers_on_stall(self):
        """Phase switch activates when objective improvement stalls.

        We use switch_epsilon=1e10 to force a deterministic switch on
        round 2, then verify that 'exploration' appears in the history.
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
            'sat_branching_bias': 3.0,
        }
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e10, verbose=False,
        )
        assert isinstance(result, AdaptiveResult)
        # Every history entry should have 'adaptive_phase'
        phases_seen = set()
        for entry in result.history:
            assert 'adaptive_phase' in entry
            phases_seen.add(entry['adaptive_phase'])
        # First round is greedy, switch must occur
        assert result.history[0]['adaptive_phase'] == 'greedy'
        assert 'exploration' in phases_seen

    def test_phase_switch_uses_set_b_params_after_switch(self):
        """After phase switch, the solver uses Set B exploration params.

        We use switch_epsilon=1e10 to force a deterministic switch, then
        verify that the phase_weights in the history entry after the switch
        reflect the Set B values.
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b_weights = [5.0, 5.0, 5.0, 5.0, 5.0]
        set_b = {
            'sat_branching_weights': set_b_weights,
        }
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e10, verbose=False,
        )
        # Find the first exploration round (must exist with epsilon=1e10)
        switch_idx = None
        for i, entry in enumerate(result.history):
            if entry['adaptive_phase'] == 'exploration':
                switch_idx = i
                break
        assert switch_idx is not None, "Switch must occur with switch_epsilon=1e10"
        # The switch round's phase_weights should reflect Set B values
        # Set B only provided 'sat_branching_weights', so check that key
        sat_w = result.history[switch_idx]['phase_weights']['sat']
        np.testing.assert_array_almost_equal(sat_w, set_b_weights)

    def test_phase_switch_no_oscillation(self):
        """Once switched to exploration, never go back to greedy.

        Uses switch_epsilon=1e10 to force a deterministic switch, then
        verifies no oscillation back to greedy.
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
        }
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e10, verbose=False,
        )
        found_exploration = False
        for entry in result.history:
            if entry['adaptive_phase'] == 'exploration':
                found_exploration = True
            elif found_exploration:
                # After exploration, must never return to greedy
                assert entry['adaptive_phase'] == 'exploration', (
                    "Oscillation detected: returned to greedy after exploration"
                )
        assert found_exploration, "Switch must occur with switch_epsilon=1e10"

    def test_phase_switch_epsilon_configurable(self):
        """A very large epsilon triggers immediate switch (round 2).

        With epsilon=1e10, any relative improvement will be below epsilon,
        so the switch should happen at the first opportunity (round 2).
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
        }
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e10, verbose=False,
        )
        # Round 1 is always greedy (no prev_best to compare)
        assert result.history[0]['adaptive_phase'] == 'greedy'
        # Round 2 should be exploration because epsilon is huge
        assert result.history[1]['adaptive_phase'] == 'exploration'
        # All subsequent rounds should be exploration
        for entry in result.history[2:]:
            assert entry['adaptive_phase'] == 'exploration'

    def test_phase_switch_records_switch_round_in_history(self):
        """History contains 'switch_round' indicating when the switch happened.

        Before the switch, entries have switch_round=None.
        After the switch, entries have the 1-indexed switch round number.
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
        }
        result = adaptive_solve(
            model, n_rounds=10, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e-6, verbose=False,
        )
        # Every history entry should have 'switch_round' key
        for entry in result.history:
            assert 'switch_round' in entry
        # Find the switch round from exploration entries
        exploration_entries = [
            e for e in result.history if e['adaptive_phase'] == 'exploration'
        ]
        if exploration_entries:
            # All exploration entries should agree on the switch round
            sr = exploration_entries[0]['switch_round']
            assert sr is not None
            assert isinstance(sr, int)
            for e in exploration_entries:
                assert e['switch_round'] == sr
            # Greedy entries before switch should have switch_round=None
            for e in result.history:
                if e['adaptive_phase'] == 'greedy':
                    assert e['switch_round'] is None

    def test_no_switch_when_improving(self):
        """When epsilon is 0.0 (impossible to stall), no switch occurs.

        With epsilon=0.0, the relative improvement must be strictly < 0
        (i.e., worsening) to trigger a switch. If the solver never worsens,
        we stay greedy. We use epsilon=-1 to ensure no switch.
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
        }
        # epsilon=-1 means relative improvement must be < -1 which is
        # impossible for non-negative objectives, so no switch ever
        result = adaptive_solve(
            model, n_rounds=5, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=-1.0, verbose=False,
        )
        for entry in result.history:
            assert entry['adaptive_phase'] == 'greedy'
        assert result.history[0]['switch_round'] is None

    def test_switch_on_first_stall_round(self):
        """Phase switch happens on the first round that detects a stall.

        With a huge epsilon (1e10), the switch should occur at round 2
        (the first round where we can compare to prev_best).
        """
        model = _make_opt_model(5)
        set_a = {
            'opt_sat_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
            'opt_branching_weights': [1.0, 1.0, 1.0, 1.0, 1.0],
        }
        set_b = {
            'sat_branching_weights': [2.0, 2.0, 2.0, 2.0, 2.0],
        }
        result = adaptive_solve(
            model, n_rounds=4, stopping_time=2, num_workers=1,
            seed=42, initial_phase_params=set_a,
            exploration_phase_params=set_b,
            switch_epsilon=1e10, verbose=False,
        )
        # First round is always greedy
        assert result.history[0]['adaptive_phase'] == 'greedy'
        # Round 2 should be exploration (switch happens there)
        assert result.history[1]['adaptive_phase'] == 'exploration'
        assert result.history[1]['switch_round'] == 2

    def test_backwards_compat_no_set_b_params(self):
        """Without exploration_phase_params, adaptive_solve works as before.

        No 'adaptive_phase' or 'switch_round' disruption; they should
        default to 'greedy' and None respectively.
        """
        model = _make_opt_model(5)
        result = adaptive_solve(
            model, n_rounds=3, stopping_time=2, num_workers=1,
            seed=42, verbose=False,
        )
        assert isinstance(result, AdaptiveResult)
        assert result.n_rounds_completed == 3
        for entry in result.history:
            assert entry['adaptive_phase'] == 'greedy'
            assert entry['switch_round'] is None
