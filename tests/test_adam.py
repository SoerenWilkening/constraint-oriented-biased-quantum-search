"""Tests for the standalone Adam optimizer."""

import numpy as np
import pytest

from cbqs.ml.adam import Adam


class TestAdamDefaults:
    """Test default hyperparameter values."""

    def test_default_lr(self):
        opt = Adam()
        assert opt.lr == 0.001

    def test_default_beta1(self):
        opt = Adam()
        assert opt.beta1 == 0.9

    def test_default_beta2(self):
        opt = Adam()
        assert opt.beta2 == 0.999

    def test_default_eps(self):
        opt = Adam()
        assert opt.eps == 1e-8


class TestAdamCustomHyperparams:
    """Test that custom hyperparameters are accepted."""

    def test_custom_lr(self):
        opt = Adam(lr=0.01)
        assert opt.lr == 0.01

    def test_custom_beta1(self):
        opt = Adam(beta1=0.8)
        assert opt.beta1 == 0.8

    def test_custom_beta2(self):
        opt = Adam(beta2=0.99)
        assert opt.beta2 == 0.99

    def test_custom_eps(self):
        opt = Adam(eps=1e-6)
        assert opt.eps == 1e-6

    def test_all_custom(self):
        opt = Adam(lr=0.1, beta1=0.5, beta2=0.9, eps=1e-4)
        assert opt.lr == 0.1
        assert opt.beta1 == 0.5
        assert opt.beta2 == 0.9
        assert opt.eps == 1e-4


class TestAdamStep:
    """Test the step() method."""

    def test_step_returns_new_array(self):
        """step() should return a NEW theta, not modify in place."""
        opt = Adam()
        theta = np.array([1.0, 2.0, 3.0])
        gradient = np.array([0.1, 0.2, 0.3])
        theta_original = theta.copy()
        theta_new = opt.step(theta, gradient)
        # Original must be unchanged
        np.testing.assert_array_equal(theta, theta_original)
        # New must be different
        assert not np.array_equal(theta_new, theta)

    def test_step_returns_correct_shape(self):
        opt = Adam()
        theta = np.zeros(344)
        gradient = np.ones(344)
        theta_new = opt.step(theta, gradient)
        assert theta_new.shape == (344,)

    def test_step_moves_in_negative_gradient_direction(self):
        """With positive gradient, theta should decrease."""
        opt = Adam(lr=0.1)
        theta = np.array([5.0, 5.0, 5.0])
        gradient = np.array([1.0, 1.0, 1.0])
        theta_new = opt.step(theta, gradient)
        assert np.all(theta_new < theta)

    def test_step_moves_up_with_negative_gradient(self):
        """With negative gradient, theta should increase."""
        opt = Adam(lr=0.1)
        theta = np.array([5.0, 5.0, 5.0])
        gradient = np.array([-1.0, -1.0, -1.0])
        theta_new = opt.step(theta, gradient)
        assert np.all(theta_new > theta)

    def test_zero_gradient_no_change(self):
        """With zero gradient, theta should not change."""
        opt = Adam()
        theta = np.array([1.0, 2.0, 3.0])
        gradient = np.zeros(3)
        theta_new = opt.step(theta, gradient)
        np.testing.assert_array_equal(theta_new, theta)


class TestAdamConvergence:
    """Test that Adam converges on simple objectives."""

    def test_quadratic_convergence(self):
        """Multiple steps should converge toward the minimum of f(x) = x^2."""
        opt = Adam(lr=0.1)
        theta = np.array([10.0])
        for _ in range(300):
            gradient = 2.0 * theta  # gradient of x^2
            theta = opt.step(theta, gradient)
        assert abs(theta[0]) < 0.5

    def test_multidim_quadratic_convergence(self):
        """Converge on f(x) = sum(x_i^2) with multiple dimensions."""
        opt = Adam(lr=0.05)
        theta = np.array([5.0, -3.0, 7.0, -1.0])
        for _ in range(300):
            gradient = 2.0 * theta
            theta = opt.step(theta, gradient)
        assert np.all(np.abs(theta) < 0.5)

    def test_step_count_increments(self):
        """Internal step counter should increment each call."""
        opt = Adam()
        theta = np.array([1.0])
        gradient = np.array([0.1])
        for i in range(5):
            theta = opt.step(theta, gradient)
        state = opt.state_dict()
        assert state['t'] == 5


class TestAdamStateDict:
    """Test state_dict / load_state_dict for checkpoint support."""

    def test_state_dict_keys(self):
        opt = Adam()
        theta = np.array([1.0, 2.0])
        opt.step(theta, np.array([0.1, 0.2]))
        state = opt.state_dict()
        assert 'm' in state
        assert 'v' in state
        assert 't' in state

    def test_state_dict_shapes(self):
        opt = Adam()
        theta = np.array([1.0, 2.0, 3.0])
        opt.step(theta, np.array([0.1, 0.2, 0.3]))
        state = opt.state_dict()
        assert state['m'].shape == (3,)
        assert state['v'].shape == (3,)

    def test_state_dict_roundtrip(self):
        """Save and restore state, verify exact match."""
        opt = Adam()
        theta = np.array([1.0, 2.0, 3.0])
        for _ in range(5):
            theta = opt.step(theta, np.random.randn(3))
        state = opt.state_dict()

        opt2 = Adam()
        opt2.load_state_dict(state)
        state2 = opt2.state_dict()

        np.testing.assert_array_equal(state['m'], state2['m'])
        np.testing.assert_array_equal(state['v'], state2['v'])
        assert state['t'] == state2['t']

    def test_restored_optimizer_same_results(self):
        """A restored optimizer must produce identical results to a continuous run."""
        rng = np.random.default_rng(42)

        # Run optimizer for 10 steps
        opt_a = Adam(lr=0.01)
        theta_a = np.array([5.0, -3.0, 7.0])
        gradients = [rng.standard_normal(3) for _ in range(10)]

        for g in gradients[:5]:
            theta_a = opt_a.step(theta_a, g)

        # Save state after 5 steps
        state = opt_a.state_dict()
        theta_checkpoint = theta_a.copy()

        # Continue original for 5 more steps
        for g in gradients[5:]:
            theta_a = opt_a.step(theta_a, g)

        # Restore from checkpoint and run same 5 steps
        opt_b = Adam(lr=0.01)
        opt_b.load_state_dict(state)
        theta_b = theta_checkpoint.copy()
        for g in gradients[5:]:
            theta_b = opt_b.step(theta_b, g)

        np.testing.assert_array_almost_equal(theta_a, theta_b)

    def test_fresh_optimizer_state_dict(self):
        """state_dict on a fresh optimizer should return empty/zero state."""
        opt = Adam()
        state = opt.state_dict()
        assert state['t'] == 0
        assert state['m'] is None or (isinstance(state['m'], np.ndarray) and np.all(state['m'] == 0))
        assert state['v'] is None or (isinstance(state['v'], np.ndarray) and np.all(state['v'] == 0))
