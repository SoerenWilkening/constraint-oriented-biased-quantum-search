"""Tests for RBST-01: Input validation at Expression/Variable level.

Validates that Variable construction rejects invalid inputs (negative index,
non-int types, inconsistent bounds) and that operator overloads reject NaN,
Inf, and int64 overflow with clear error messages.
"""
import math
import pytest
from cbqs.Expression import Variable, Expression, _validate_numeric


class TestVariableValidation:
    """Tests for Variable construction validation."""

    def test_valid_variable(self):
        """Valid Variable creation works as before."""
        v = Variable(0, "x0", 0, 1)
        assert v.index == 0

    def test_valid_variable_defaults(self):
        """Variable with default parameters creates successfully."""
        v = Variable(5)
        assert v.index == 5
        assert v.name == "x5"
        assert v.lb == 0
        assert v.ub == 1

    def test_negative_index_raises(self):
        with pytest.raises(ValueError, match="must be non-negative"):
            Variable(index=-1)

    def test_large_negative_index(self):
        with pytest.raises(ValueError, match="must be non-negative"):
            Variable(index=-999)

    def test_string_index_raises(self):
        with pytest.raises(TypeError, match="must be int"):
            Variable(index="abc")

    def test_float_index_raises(self):
        with pytest.raises(TypeError, match="must be int"):
            Variable(index=1.5)

    def test_bool_index_raises(self):
        with pytest.raises(TypeError, match="must be int"):
            Variable(index=True)

    def test_none_index_raises(self):
        with pytest.raises(TypeError, match="must be int"):
            Variable(index=None)

    def test_inconsistent_bounds_raises(self):
        with pytest.raises(ValueError, match="inconsistent"):
            Variable(index=0, lb=5, ub=0)

    def test_equal_bounds_allowed(self):
        """lb == ub is valid (fixed variable)."""
        v = Variable(index=0, lb=3, ub=3)
        assert v.lb == 3 and v.ub == 3

    def test_float_lower_bound_raises(self):
        with pytest.raises(TypeError, match="lower bound must be int"):
            Variable(index=0, lb=0.5)

    def test_float_upper_bound_raises(self):
        with pytest.raises(TypeError, match="upper bound must be int"):
            Variable(index=0, ub=1.5)

    def test_bool_lower_bound_raises(self):
        with pytest.raises(TypeError, match="lower bound must be int"):
            Variable(index=0, lb=True)

    def test_bool_upper_bound_raises(self):
        with pytest.raises(TypeError, match="upper bound must be int"):
            Variable(index=0, ub=False)

    def test_zero_index_allowed(self):
        """Index 0 is valid."""
        v = Variable(index=0)
        assert v.index == 0

    def test_large_index_allowed(self):
        """Large positive index is valid."""
        v = Variable(index=99999)
        assert v.index == 99999


class TestValidateNumericHelper:
    """Tests for the _validate_numeric helper function directly."""

    def test_nan_raises_value_error(self):
        with pytest.raises(ValueError, match="NaN"):
            _validate_numeric(float('nan'))

    def test_inf_raises_value_error(self):
        with pytest.raises(ValueError, match="Inf"):
            _validate_numeric(float('inf'))

    def test_neg_inf_raises_value_error(self):
        with pytest.raises(ValueError, match="Inf"):
            _validate_numeric(float('-inf'))

    def test_float_raises_type_error(self):
        with pytest.raises(TypeError, match="Float"):
            _validate_numeric(1.5)

    def test_int64_overflow_raises(self):
        with pytest.raises(OverflowError, match="int64"):
            _validate_numeric(2**63)

    def test_int64_underflow_raises(self):
        with pytest.raises(OverflowError, match="int64"):
            _validate_numeric(-(2**63) - 1)

    def test_int64_max_allowed(self):
        """Value exactly at int64 max boundary should be allowed."""
        _validate_numeric(2**63 - 1)  # Should not raise

    def test_int64_min_allowed(self):
        """Value exactly at int64 min boundary should be allowed."""
        _validate_numeric(-(2**63))  # Should not raise

    def test_normal_int_allowed(self):
        """Normal integers pass validation."""
        _validate_numeric(42)

    def test_zero_allowed(self):
        """Zero passes validation."""
        _validate_numeric(0)

    def test_negative_int_allowed(self):
        """Negative integers pass validation."""
        _validate_numeric(-100)

    def test_context_in_nan_message(self):
        """Context string is included in NaN error message."""
        with pytest.raises(ValueError, match="in __add__"):
            _validate_numeric(float('nan'), context="__add__")

    def test_context_in_inf_message(self):
        """Context string is included in Inf error message."""
        with pytest.raises(ValueError, match="in __mul__"):
            _validate_numeric(float('inf'), context="__mul__")

    def test_variable_passes(self):
        """Variable objects pass through (not numeric type)."""
        v = Variable(0)
        _validate_numeric(v)  # Should not raise

    def test_expression_passes(self):
        """Expression objects pass through (not numeric type)."""
        v = Variable(0)
        expr = v + 1
        _validate_numeric(expr)  # Should not raise

    def test_bool_passes(self):
        """Bool is excluded from int overflow check."""
        _validate_numeric(True)  # Should not raise
        _validate_numeric(False)  # Should not raise


class TestVariableOperatorValidation:
    """Tests for coefficient validation in Variable operator overloads."""

    def test_var_add_nan_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="NaN"):
            v + float('nan')

    def test_var_add_inf_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="Inf"):
            v + float('inf')

    def test_var_add_neg_inf_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="Inf"):
            v + float('-inf')

    def test_var_radd_nan_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="NaN"):
            float('nan') + v

    def test_var_mul_nan_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="NaN"):
            v * float('nan')

    def test_var_rmul_nan_raises(self):
        v = Variable(0)
        with pytest.raises(ValueError, match="NaN"):
            float('nan') * v

    def test_var_add_float_raises_type_error(self):
        v = Variable(0)
        with pytest.raises(TypeError, match="Float"):
            v + 1.5

    def test_var_mul_float_raises_type_error(self):
        v = Variable(0)
        with pytest.raises(TypeError, match="Float"):
            v * 2.5

    def test_var_add_int_works(self):
        """Normal integer addition still works."""
        v = Variable(0)
        expr = v + 3
        assert isinstance(expr, Expression)

    def test_var_mul_int_works(self):
        """Normal integer multiplication still works."""
        v = Variable(0)
        expr = v * 3
        assert isinstance(expr, Expression)


class TestExpressionOperatorValidation:
    """Tests for coefficient validation in Expression operator overloads."""

    def test_expr_add_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr + float('nan')

    def test_expr_radd_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            float('nan') + expr

    def test_expr_mul_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr * float('nan')

    def test_expr_rmul_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            float('nan') * expr

    def test_expr_iadd_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr += float('nan')

    def test_expr_isub_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr -= float('nan')

    def test_expr_imul_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr *= float('nan')

    def test_expr_add_inf_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="Inf"):
            expr + float('inf')

    def test_expr_mul_inf_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="Inf"):
            expr * float('inf')

    def test_expr_add_float_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(TypeError, match="Float"):
            expr + 1.5

    def test_int64_overflow_add_raises(self):
        v = Variable(0)
        expr = v + 0
        with pytest.raises(OverflowError, match="int64"):
            expr + (2**63)

    def test_int64_underflow_add_raises(self):
        v = Variable(0)
        expr = v + 0
        with pytest.raises(OverflowError, match="int64"):
            expr + (-(2**63) - 1)

    def test_int64_overflow_mul_raises(self):
        v = Variable(0)
        expr = v + 0
        with pytest.raises(OverflowError, match="int64"):
            expr * (2**63)

    def test_int64_max_allowed(self):
        """Value exactly at int64 max boundary should be allowed."""
        v = Variable(0)
        expr = v + (2**63 - 1)
        assert expr is not None

    def test_int64_min_allowed(self):
        """Value exactly at int64 min boundary should be allowed."""
        v = Variable(0)
        expr = v + (-(2**63))
        assert expr is not None

    def test_valid_int_operations_unchanged(self):
        """Normal integer operations still work correctly."""
        v = Variable(0)
        expr = v + 3
        expr2 = expr * 2
        assert expr2 is not None
        terms = list(expr2)
        assert [6] in terms
        assert [2, 0] in terms


class TestComparisonOperatorValidation:
    """Tests for validation in comparison operators (__le__, __ge__, __eq__)."""

    def test_le_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr <= float('nan')

    def test_ge_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr >= float('nan')

    def test_eq_nan_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="NaN"):
            expr == float('nan')

    def test_le_inf_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(ValueError, match="Inf"):
            expr <= float('inf')

    def test_ge_float_raises(self):
        v = Variable(0)
        expr = v + 1
        with pytest.raises(TypeError, match="Float"):
            expr >= 1.5

    def test_le_valid_int_works(self):
        """Normal comparison operations still work."""
        v = Variable(0)
        expr = v + 1
        c = expr <= 5
        assert c is not None

    def test_ge_valid_int_works(self):
        """Normal >= comparison works."""
        v = Variable(0)
        expr = v + 1
        c = expr >= 1
        assert c is not None

    def test_eq_valid_int_works(self):
        """Normal == comparison works."""
        v = Variable(0)
        expr = v + 1
        c = expr == 2
        assert c is not None
