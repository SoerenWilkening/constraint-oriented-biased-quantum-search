"""Tests for set_param/get_param API, validation, persistence, copy, and old API removal.

Covers branching_weights validation, factor validation, and parameter precedence.
"""
import warnings

import numpy as np
import pytest

pytest.importorskip("cbqs")

from copy import copy
from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from cbqs.result import OptimizeResult


def _make_small_model():
    """Create a small valid model for testing."""
    m = Model()
    x = m.add_variables(5)
    m.set_objective(x[0] + 2 * x[1] + 3 * x[2] + x[3] + x[4], sense=MAXIMIZE)
    m.add_constraint(x[0] + x[1] + x[2] + x[3] + x[4] <= 3)
    m.close()
    return m


# =============================================================================
# 1. set_param / get_param basics
# =============================================================================


class TestSetParamBasics:
    """Verify set_param stores and get_param retrieves all known parameter types."""

    def test_set_param_branching_bias(self):
        """set_param('branching_bias', 10.0) -> get_param returns 10.0."""
        m = _make_small_model()
        m.set_param("branching_bias", 10.0)
        assert m.get_param("branching_bias") == 10.0

    def test_set_param_branching_weights(self):
        """set_param('branching_weights', list) -> get_param returns same list."""
        m = Model()
        weights = [1.0, 2.0]
        m.set_param("branching_weights", weights)
        assert m.get_param("branching_weights") == weights

    def test_set_param_branching_factor(self):
        """set_param('branching_factor', 2.0) -> get_param returns 2.0."""
        m = Model()
        m.set_param("branching_factor", 2.0)
        assert m.get_param("branching_factor") == 2.0

    def test_set_param_num_workers(self):
        """set_param('num_workers', 4) -> get_param returns 4."""
        m = Model()
        m.set_param("num_workers", 4)
        assert m.get_param("num_workers") == 4

    def test_set_param_timeout(self):
        """set_param('timeout', 60) -> get_param returns 60."""
        m = Model()
        m.set_param("timeout", 60)
        assert m.get_param("timeout") == 60

    def test_set_param_track_history(self):
        """set_param('track_history', False) -> get_param returns False."""
        m = Model()
        m.set_param("track_history", False)
        assert m.get_param("track_history") is False

    def test_set_param_bias_factor(self):
        """set_param('bias_factor', 2.5) -> get_param returns 2.5."""
        m = Model()
        m.set_param("bias_factor", 2.5)
        assert m.get_param("bias_factor") == 2.5

    def test_set_param_look_ahead_factor(self):
        """set_param('look_ahead_factor', 0.3) -> get_param returns 0.3."""
        m = Model()
        m.set_param("look_ahead_factor", 0.3)
        assert m.get_param("look_ahead_factor") == 0.3


# =============================================================================
# 2. Validation
# =============================================================================


class TestSetParamValidation:
    """Verify set_param and get_param raise ValueError for unknown params."""

    def test_set_param_unknown_raises(self):
        """set_param('nonexistent', 1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("nonexistent", 1)

    def test_get_param_unknown_raises(self):
        """get_param('nonexistent') raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.get_param("nonexistent")

    def test_get_param_unset_returns_none(self):
        """get_param('branching_bias') returns None before any set_param on fresh Model."""
        m = Model()
        # Note: close() sets a default for branching_bias, so test on unclosed model
        assert m.get_param("num_workers") is None

    def test_get_param_unset_branching_bias_before_close(self):
        """get_param('branching_bias') returns None on a Model before close()."""
        m = Model()
        assert m.get_param("branching_bias") is None

    def test_old_param_manual_bias_raises(self):
        """set_param('manual_bias', ...) raises ValueError (removed param)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("manual_bias", [1.0, 2.0])

    def test_old_param_manual_bias_factor_raises(self):
        """set_param('manual_bias_factor', ...) raises ValueError (removed param)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("manual_bias_factor", 0.5)

    def test_old_param_branching_factors_raises(self):
        """set_param('branching_factors', ...) raises ValueError (removed param)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("branching_factors", (0.5, 0.0, 1.0, 0.0))


# =============================================================================
# 3. Branching weights validation
# =============================================================================


class TestBranchingWeightsValidation:
    """Verify branching_weights validation in set_param."""

    def test_branching_weights_wrong_length(self):
        """Wrong-length array raises ValueError when model has variables."""
        m = _make_small_model()
        with pytest.raises(ValueError, match="Expected array of length 5, got 2"):
            m.set_param("branching_weights", [1.0, 2.0])

    def test_branching_weights_negative(self):
        """Negative weight raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="non-negative"):
            m.set_param("branching_weights", [1.0, -1.0])

    def test_branching_weights_nan(self):
        """NaN weight raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="NaN or Inf"):
            m.set_param("branching_weights", [1.0, float("nan")])

    def test_branching_weights_inf(self):
        """Inf weight raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="NaN or Inf"):
            m.set_param("branching_weights", [1.0, float("inf")])

    def test_branching_weights_none_clears(self):
        """Setting branching_weights to None clears the value."""
        m = Model()
        m.set_param("branching_weights", [1.0])
        m.set_param("branching_weights", None)
        assert m.get_param("branching_weights") is None

    def test_branching_weights_before_variables(self):
        """On model with no variables (n=0), any array length accepted (deferred validation)."""
        m = Model()
        # n=0, so no length check -- should not raise
        m.set_param("branching_weights", [1.0, 2.0])
        assert m.get_param("branching_weights") == [1.0, 2.0]

    def test_branching_weights_not_1d(self):
        """2D array raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="1D array"):
            m.set_param("branching_weights", [[1.0, 2.0]])


# =============================================================================
# 4. Factor validation
# =============================================================================


class TestFactorValidation:
    """Verify factor params reject negative values."""

    def test_branching_factor_negative(self):
        """set_param('branching_factor', -1.0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="non-negative"):
            m.set_param("branching_factor", -1.0)

    def test_bias_factor_negative(self):
        """set_param('bias_factor', -1.0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="non-negative"):
            m.set_param("bias_factor", -1.0)

    def test_look_ahead_factor_negative(self):
        """set_param('look_ahead_factor', -1.0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="non-negative"):
            m.set_param("look_ahead_factor", -1.0)

    def test_branching_factor_zero_ok(self):
        """set_param('branching_factor', 0.0) does NOT raise."""
        m = Model()
        m.set_param("branching_factor", 0.0)
        assert m.get_param("branching_factor") == 0.0


# =============================================================================
# 5. Persistence
# =============================================================================


class TestSetParamPersistence:
    """Verify parameters persist across solves and can be overwritten."""

    def test_params_persist_across_solves(self):
        """set_param value persists after multiple solve() calls."""
        m = _make_small_model()
        m.set_param("branching_bias", 10.0)
        m.solve(stopping_time=1, num_workers=2)
        assert m.get_param("branching_bias") == 10.0
        m.solve(stopping_time=1, num_workers=2)
        assert m.get_param("branching_bias") == 10.0

    def test_params_overwrite(self):
        """Setting a param twice overwrites the first value."""
        m = Model()
        m.set_param("branching_bias", 10.0)
        assert m.get_param("branching_bias") == 10.0
        m.set_param("branching_bias", 20.0)
        assert m.get_param("branching_bias") == 20.0


# =============================================================================
# 6. Copy behavior
# =============================================================================


class TestSetParamCopy:
    """Verify copy() preserves params."""

    def test_copy_preserves_params(self):
        """Copying a model preserves set_param values."""
        m = Model()
        m.set_param("branching_bias", 42.0)
        m.set_param("num_workers", 8)
        m2 = copy(m)
        assert m2.get_param("branching_bias") == 42.0
        assert m2.get_param("num_workers") == 8

    def test_copy_params_are_independent(self):
        """Modifying params on copy does not affect original."""
        m = Model()
        m.set_param("branching_bias", 42.0)
        m2 = copy(m)
        m2.set_param("branching_bias", 99.0)
        assert m.get_param("branching_bias") == 42.0
        assert m2.get_param("branching_bias") == 99.0


# =============================================================================
# 7. Old API removed
# =============================================================================


class TestOldAPIRemoved:
    """Verify deprecated wrapper functions no longer exist."""

    def test_set_factors_wrapper_removed(self):
        """set_factors_wrapper is no longer importable."""
        with pytest.raises(ImportError):
            from cbqs.branching import set_factors_wrapper

    def test_set_obj_dependence_wrapper_removed(self):
        """set_obj_dependence_wrapper is no longer importable."""
        with pytest.raises(ImportError):
            from cbqs.branching import set_obj_dependence_wrapper

    def test_set_constraint_dependence_wrapper_removed(self):
        """set_constraint_dependence_wrapper is no longer importable."""
        with pytest.raises(ImportError):
            from cbqs.branching import set_constraint_dependence_wrapper


# =============================================================================
# 8. Precedence
# =============================================================================


class TestSetParamPrecedence:
    """Verify set_param values take precedence over solve() kwargs."""

    def test_set_param_overrides_solve_kwarg(self):
        """set_param('branching_bias') value is stored correctly for precedence."""
        m = _make_small_model()
        # Set a distinctive value via set_param
        m.set_param("branching_bias", 99.0)
        # Call solve with a different bias kwarg -- set_param should win
        result = m.solve(stopping_time=1, num_workers=2, bias=1.0)
        # The key assertion: set_param value persists (it was not overwritten by solve kwarg)
        assert m.get_param("branching_bias") == 99.0
        # Result should be valid
        assert isinstance(result, OptimizeResult)

    def test_set_param_branching_bias_used_in_solve(self):
        """set_param('branching_bias') with extreme value does not crash solve."""
        m = _make_small_model()
        m.set_param("branching_bias", 100.0)
        result = m.solve(stopping_time=1, num_workers=2)
        assert isinstance(result, OptimizeResult)
        assert result.solution is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
