"""Standalone Adam optimizer for ES training.

Minimal numpy-only implementation of the Adam optimizer (Kingma & Ba, 2015).
Used in the ES training loop to update the theta coefficient vector.

Provides:
- Adam: Optimizer with step(), state_dict(), and load_state_dict() methods.
"""

import copy

import numpy as np


class Adam:
    """Adam optimizer (numpy only, no PyTorch dependency).

    Implements the standard Adam algorithm with bias correction.
    The step() method is immutable: it returns a new theta array
    without modifying the input.

    Args:
        lr: Learning rate (default 0.001).
        beta1: Exponential decay rate for first moment (default 0.9).
        beta2: Exponential decay rate for second moment (default 0.999).
        eps: Small constant for numerical stability (default 1e-8).
    """

    def __init__(self, lr: float = 0.001, beta1: float = 0.9,
                 beta2: float = 0.999, eps: float = 1e-8):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps

        # Internal state (initialized lazily on first step)
        self._m = None  # First moment estimate
        self._v = None  # Second moment estimate
        self._t = 0     # Step count

    def step(self, theta: np.ndarray, gradient: np.ndarray) -> np.ndarray:
        """Perform one Adam update step.

        Args:
            theta: Current parameter vector (not modified).
            gradient: Gradient vector (same shape as theta).

        Returns:
            New parameter vector after the Adam update.
        """
        # Lazy initialization of moment estimates
        if self._m is None:
            self._m = np.zeros_like(theta, dtype=np.float64)
            self._v = np.zeros_like(theta, dtype=np.float64)

        self._t += 1
        g = np.asarray(gradient, dtype=np.float64)

        # Update biased first and second moment estimates
        self._m = self.beta1 * self._m + (1.0 - self.beta1) * g
        self._v = self.beta2 * self._v + (1.0 - self.beta2) * g * g

        # Bias-corrected moment estimates
        m_hat = self._m / (1.0 - self.beta1 ** self._t)
        v_hat = self._v / (1.0 - self.beta2 ** self._t)

        # Compute update and return new theta
        theta_new = np.array(theta, dtype=np.float64) - self.lr * m_hat / (np.sqrt(v_hat) + self.eps)
        return theta_new

    def state_dict(self) -> dict:
        """Return optimizer state for checkpointing.

        Returns:
            Dict with keys 'm' (first moment), 'v' (second moment),
            and 't' (step count). Moment arrays are copies.
        """
        return {
            'm': self._m.copy() if self._m is not None else None,
            'v': self._v.copy() if self._v is not None else None,
            't': self._t,
        }

    def load_state_dict(self, state: dict) -> None:
        """Restore optimizer state from a checkpoint.

        Args:
            state: Dict previously returned by state_dict().
        """
        self._m = state['m'].copy() if state['m'] is not None else None
        self._v = state['v'].copy() if state['v'] is not None else None
        self._t = state['t']
