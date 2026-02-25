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

    def test_get_param_unset_returns_default(self):
        """get_param returns documented default for unset params (never None for params with defaults)."""
        m = Model()
        # num_workers has default 12 in _PARAM_DEFS
        assert m.get_param("num_workers") == 12

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
        m.set_param("stopping_time", 1)
        m.set_param("num_workers", 2)
        m.solve()
        assert m.get_param("branching_bias") == 10.0
        m.solve()
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
    """Verify set_param values are read by solve()."""

    def test_set_param_values_used_by_solve(self):
        """set_param values are what solve() reads from _params."""
        m = _make_small_model()
        m.set_param("branching_bias", 99.0)
        m.set_param("stopping_time", 1)
        m.set_param("num_workers", 2)
        result = m.solve()
        # The key assertion: set_param value persists after solve
        assert m.get_param("branching_bias") == 99.0
        # Result should be valid
        assert isinstance(result, OptimizeResult)

    def test_set_param_branching_bias_used_in_solve(self):
        """set_param('branching_bias') with extreme value does not crash solve."""
        m = _make_small_model()
        m.set_param("branching_bias", 100.0)
        m.set_param("stopping_time", 1)
        m.set_param("num_workers", 2)
        result = m.solve()
        assert isinstance(result, OptimizeResult)
        assert result.solution is not None


# =============================================================================
# 9. Former solve() params basic set/get
# =============================================================================


class TestSetParamSolveParamsBasic:
    """Verify set_param/get_param works for all former solve() parameters."""

    @pytest.mark.parametrize("name,value", [
        ("M", 200),
        ("stopping_time", 60),
        ("stop_val", 10),
        ("max_delta", 3),
        ("reset_delta", False),
        ("depth_look_ahead", 2),
        ("num_workers", 4),
        ("ignore_constraint_search", True),
        ("monte_carlo_estimate", True),
        ("verify", True),
        ("track_history", False),
    ])
    def test_set_param_solve_params_basic(self, name, value):
        """set_param(name, value) -> get_param(name) returns value for all former solve() params."""
        m = Model()
        m.set_param(name, value)
        assert m.get_param(name) == value


# =============================================================================
# 10. Type coercion
# =============================================================================


class TestSetParamCoercion:
    """Verify type coercion works correctly in set_param."""

    def test_coerce_M_str_to_int(self):
        """set_param('M', '100') coerces string to int 100."""
        m = Model()
        m.set_param("M", "100")
        assert m.get_param("M") == 100
        assert isinstance(m.get_param("M"), int)

    def test_coerce_M_float_to_int(self):
        """set_param('M', 100.0) coerces float to int 100."""
        m = Model()
        m.set_param("M", 100.0)
        assert m.get_param("M") == 100
        assert isinstance(m.get_param("M"), int)

    def test_coerce_stopping_time_str_to_int(self):
        """set_param('stopping_time', '5') coerces to int 5."""
        m = Model()
        m.set_param("stopping_time", "5")
        assert m.get_param("stopping_time") == 5

    def test_coerce_num_workers_float_to_int(self):
        """set_param('num_workers', 2.0) coerces to int 2."""
        m = Model()
        m.set_param("num_workers", 2.0)
        assert m.get_param("num_workers") == 2


# =============================================================================
# 11. Set-time validation
# =============================================================================


class TestSetParamSetTimeValidation:
    """Verify validation is performed at set-time."""

    def test_stopping_time_zero_raises(self):
        """set_param('stopping_time', 0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="stopping_time must be positive"):
            m.set_param("stopping_time", 0)

    def test_stopping_time_negative_raises(self):
        """set_param('stopping_time', -1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="stopping_time must be positive"):
            m.set_param("stopping_time", -1)

    def test_num_workers_zero_raises(self):
        """set_param('num_workers', 0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="num_workers must be >= 1"):
            m.set_param("num_workers", 0)

    def test_max_delta_negative_raises(self):
        """set_param('max_delta', -1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="max_delta must be non-negative"):
            m.set_param("max_delta", -1)

    def test_depth_look_ahead_negative_raises(self):
        """set_param('depth_look_ahead', -1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="depth_look_ahead must be non-negative"):
            m.set_param("depth_look_ahead", -1)

    def test_results_removed_raises(self):
        """set_param('results', 'min') raises ValueError (removed orphaned param)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("results", "min")

    def test_bfs_removed_raises(self):
        """set_param('bfs', True) raises ValueError (removed orphaned param)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("bfs", True)

    def test_callback_not_callable_raises(self):
        """set_param('callback', 'not_a_function') raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="callback must be callable"):
            m.set_param("callback", "not_a_function")

    def test_M_non_numeric_raises(self):
        """set_param('M', 'abc') raises ValueError (coercion failure)."""
        m = Model()
        with pytest.raises(ValueError, match="Cannot coerce"):
            m.set_param("M", "abc")


# =============================================================================
# 12. Reset to default via None
# =============================================================================


class TestSetParamResetToDefault:
    """Verify set_param(name, None) resets param to its documented default."""

    @pytest.mark.parametrize("name,set_val,default_val", [
        ("M", 500, -1),
        ("stopping_time", 60, 300),
        ("num_workers", 4, 12),
        ("track_history", False, True),
        ("callback", lambda: None, None),
    ])
    def test_reset_to_default(self, name, set_val, default_val):
        """set_param(name, value) then set_param(name, None) returns documented default."""
        m = Model()
        m.set_param(name, set_val)
        m.set_param(name, None)
        assert m.get_param(name) == default_val


# =============================================================================
# 13. get_param defaults for all former solve() params
# =============================================================================


class TestGetParamDefaults:
    """Verify get_param returns correct defaults for all former solve() params without any set_param."""

    @pytest.mark.parametrize("name,expected", [
        ("M", -1),
        ("stopping_time", 300),
        ("stop_val", -1),
        ("callback", None),
        ("max_delta", 7),
        ("reset_delta", True),
        ("depth_look_ahead", 0),
        ("num_workers", 12),
        ("ignore_constraint_search", False),
        ("monte_carlo_estimate", False),
        ("verify", False),
        ("track_history", True),
    ])
    def test_get_param_default(self, name, expected):
        """get_param(name) returns documented default on a fresh Model."""
        m = Model()
        assert m.get_param(name) == expected


# =============================================================================
# 14. Unknown/removed params rejected
# =============================================================================


class TestUnknownParamRejected:
    """Verify dropped and misspelled params raise ValueError."""

    def test_bias_rejected(self):
        """set_param('bias', 1.0) raises ValueError (bias was dropped)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("bias", 1.0)

    def test_manual_bias_rejected(self):
        """set_param('manual_bias', 1.0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("manual_bias", 1.0)

    def test_monte_calor_estimate_typo_rejected(self):
        """set_param('monte_calor_estimate', True) raises ValueError (old typo name rejected)."""
        m = Model()
        with pytest.raises(ValueError, match="Unknown parameter"):
            m.set_param("monte_calor_estimate", True)

    def test_bias_factor_is_valid(self):
        """set_param('bias_factor', 1.0) does NOT raise -- Phase 14 branching bias_factor is valid."""
        m = Model()
        m.set_param("bias_factor", 1.0)
        assert m.get_param("bias_factor") == 1.0


# =============================================================================
# 15. Bool coercion strictness
# =============================================================================


class TestBoolCoercionStrict:
    """Verify bool coercion rejects strings, accepts bool and int."""

    def test_ignore_constraint_search_string_raises(self):
        """set_param('ignore_constraint_search', 'true') raises ValueError (string not accepted as bool)."""
        m = Model()
        with pytest.raises(ValueError, match="Cannot coerce"):
            m.set_param("ignore_constraint_search", "true")

    def test_ignore_constraint_search_int_coerced(self):
        """set_param('ignore_constraint_search', 1) coerces int to True."""
        m = Model()
        m.set_param("ignore_constraint_search", 1)
        assert m.get_param("ignore_constraint_search") is True

    def test_ignore_constraint_search_int_zero_coerced(self):
        """set_param('ignore_constraint_search', 0) coerces int 0 to False."""
        m = Model()
        m.set_param("ignore_constraint_search", 0)
        assert m.get_param("ignore_constraint_search") is False

    def test_ignore_constraint_search_bool_true_works(self):
        """set_param('ignore_constraint_search', True) works directly."""
        m = Model()
        m.set_param("ignore_constraint_search", True)
        assert m.get_param("ignore_constraint_search") is True

    def test_reset_delta_string_raises(self):
        """set_param('reset_delta', 'False') raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Cannot coerce"):
            m.set_param("reset_delta", "False")


# =============================================================================
# 16. Callback validation
# =============================================================================


class TestCallbackValidation:
    """Verify callback param accepts callable/None and rejects non-callable."""

    def test_callback_lambda_works(self):
        """set_param('callback', lambda: None) works."""
        m = Model()
        fn = lambda: None
        m.set_param("callback", fn)
        assert m.get_param("callback") is fn

    def test_callback_none_resets(self):
        """set_param('callback', None) resets to default (None)."""
        m = Model()
        m.set_param("callback", lambda: None)
        m.set_param("callback", None)
        assert m.get_param("callback") is None

    def test_callback_int_raises(self):
        """set_param('callback', 42) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="callback must be callable"):
            m.set_param("callback", 42)

    def test_callback_function_works(self):
        """set_param('callback', function) works for regular functions."""
        m = Model()

        def my_callback():
            pass

        m.set_param("callback", my_callback)
        assert m.get_param("callback") is my_callback


# =============================================================================
# 17. solve() rejects kwargs (Phase 15-02)
# =============================================================================


class TestSolveRejectsKwargs:
    """Verify solve() accepts zero arguments and rejects all kwargs."""

    def test_solve_rejects_M_kwarg(self):
        """solve(M=100) raises TypeError."""
        m = _make_small_model()
        with pytest.raises(TypeError):
            m.solve(M=100)

    def test_solve_rejects_stopping_time_kwarg(self):
        """solve(stopping_time=5) raises TypeError."""
        m = _make_small_model()
        with pytest.raises(TypeError):
            m.solve(stopping_time=5)

    def test_solve_rejects_num_workers_kwarg(self):
        """solve(num_workers=1) raises TypeError."""
        m = _make_small_model()
        with pytest.raises(TypeError):
            m.solve(num_workers=1)

    def test_solve_rejects_verify_kwarg(self):
        """solve(verify=True) raises TypeError."""
        m = _make_small_model()
        with pytest.raises(TypeError):
            m.solve(verify=True)

    def test_solve_rejects_positional_arg(self):
        """solve(100) raises TypeError."""
        m = _make_small_model()
        with pytest.raises(TypeError):
            m.solve(100)

    def test_solve_zero_args_works(self):
        """solve() with no arguments works when params configured via set_param."""
        m = _make_small_model()
        m.set_param("stopping_time", 1)
        m.set_param("num_workers", 1)
        result = m.solve()
        assert isinstance(result, OptimizeResult)

    def test_solve_reads_from_params(self):
        """solve() reads verify=True from _params and populates result.verified."""
        m = _make_small_model()
        m.set_param("stopping_time", 1)
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        result = m.solve()
        assert result.verified is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
