"""Tests for branching_bias > -1 validation in Model.pyx _PARAM_DEFS.

M3: Ensures branching_bias rejects values <= -1 at set_param time.
"""
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE


def _make_small_model():
    """Create a small valid model for testing."""
    m = Model()
    x = m.add_variables(5)
    m.set_objective(x[0] + 2 * x[1] + 3 * x[2] + x[3] + x[4], sense=MAXIMIZE)
    m.add_constraint(x[0] + x[1] + x[2] + x[3] + x[4] <= 3)
    m.close()
    return m


class TestBiasValidation:
    """Validate branching_bias rejects values <= -1."""

    def test_bias_minus_one_rejected(self):
        """set_param('branching_bias', -1) raises ValueError."""
        m = _make_small_model()
        with pytest.raises(ValueError, match="greater than -1"):
            m.set_param("branching_bias", -1)

    def test_bias_below_minus_one_rejected(self):
        """set_param('branching_bias', -5) raises ValueError."""
        m = _make_small_model()
        with pytest.raises(ValueError, match="greater than -1"):
            m.set_param("branching_bias", -5)

    def test_bias_just_above_minus_one_ok(self):
        """set_param('branching_bias', -0.99) works."""
        m = _make_small_model()
        m.set_param("branching_bias", -0.99)
        assert m.get_param("branching_bias") == pytest.approx(-0.99)

    def test_bias_positive_ok(self):
        """set_param('branching_bias', 5.0) works."""
        m = _make_small_model()
        m.set_param("branching_bias", 5.0)
        assert m.get_param("branching_bias") == 5.0

    def test_bias_zero_ok(self):
        """set_param('branching_bias', 0) works."""
        m = _make_small_model()
        m.set_param("branching_bias", 0)
        assert m.get_param("branching_bias") == 0.0

    def test_bias_none_resets_to_default(self):
        """set_param('branching_bias', None) resets to default."""
        m = _make_small_model()
        m.set_param("branching_bias", 5.0)
        m.set_param("branching_bias", None)
        # Default is None (auto-set to n/4 at close), but close() already set it
        # After reset, get_param should return the _PARAM_DEFS default (None)
        # However close() wrote n/4 into _params. Resetting removes the stored value.
        assert m.get_param("branching_bias") is None
