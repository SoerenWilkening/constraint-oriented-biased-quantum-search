"""
Pytest tests for Expression and Variable Cython bindings.

Tests validate arithmetic operator overloading and expression building
through the cbqs.Expression Python API.
"""
import pytest
from copy import deepcopy
from cbqs.Expression import Variable, Expression
from cbqs.Constants import LOWER, EQUAL


class TestVariableCreation:
    """Tests for Variable instantiation."""

    def test_variable_creation(self):
        """Variable(0) creates a Variable with correct index."""
        x = Variable(0)
        assert x.index == 0
        assert x.name == "x0"

    def test_variable_creation_custom_name(self):
        """Variable with custom name preserves it."""
        x = Variable(3, name="y")
        assert x.index == 3
        assert x.name == "y"

    def test_variable_str(self):
        """Variable string representation is its name."""
        x = Variable(2)
        assert str(x) == "x2"


class TestExpressionArithmetic:
    """Tests for expression building via operator overloads."""

    def test_expression_add_constant(self):
        """Variable + int produces an Expression."""
        x = Variable(0)
        expr = x + 5
        assert isinstance(expr, Expression)
        terms = list(expr)
        # Should have a constant term [5] and a variable term [1, 0]
        assert [5] in terms
        assert [1, 0] in terms

    def test_expression_radd_constant(self):
        """int + Variable produces an Expression (reverse add)."""
        x = Variable(0)
        expr = 5 + x
        assert isinstance(expr, Expression)
        terms = list(expr)
        assert [5] in terms
        assert [1, 0] in terms

    def test_expression_add_variables(self):
        """Variable + Variable produces Expression with both variables."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        assert isinstance(expr, Expression)
        terms = list(expr)
        # Two variable terms: [1, 1] and [1, 0]
        assert [1, 1] in terms
        assert [1, 0] in terms

    def test_expression_multiply_constant(self):
        """int * Variable applies coefficient correctly."""
        x = Variable(0)
        expr = 3 * x
        assert isinstance(expr, Expression)
        terms = list(expr)
        # Single term with coefficient 3 and variable 0: [3, 0]
        assert [3, 0] in terms

    def test_expression_multiply_constant_rhs(self):
        """Variable * int applies coefficient correctly."""
        x = Variable(0)
        expr = x * 3
        assert isinstance(expr, Expression)
        terms = list(expr)
        assert [3, 0] in terms

    def test_expression_compound(self):
        """Compound expression 2*x0 + 3*x1 + 5 builds correctly."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = 2 * x0 + 3 * x1 + 5
        assert isinstance(expr, Expression)
        terms = list(expr)
        assert [2, 0] in terms
        assert [3, 1] in terms
        assert [5] in terms

    def test_expression_multiply_expressions(self):
        """Variable * Variable creates quadratic term."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 * x1
        assert isinstance(expr, Expression)
        terms = list(expr)
        # Quadratic term: [1, 1, 0]
        assert [1, 1, 0] in terms

    def test_float_raises_type_error(self):
        """Adding float to Variable raises TypeError."""
        x = Variable(0)
        with pytest.raises(TypeError):
            _ = x + 1.5

    def test_float_multiply_raises_type_error(self):
        """Multiplying Variable by float raises TypeError."""
        x = Variable(0)
        with pytest.raises(TypeError):
            _ = x * 2.5

    def test_expression_reuse_variable(self):
        """Creating a second expression from a Variable should not mutate the first.

        This test verifies that Expression operators return new objects instead of
        mutating self. Fixed in Phase 2 plan 02-03.
        """
        x = Variable(0)
        expr1 = x + 3
        terms_before = list(expr1)
        expr2 = expr1 + 5  # Should create new Expression, not mutate expr1
        terms_after = list(expr1)
        # expr1 should be unchanged after creating expr2
        assert terms_before == terms_after
        # expr1 and expr2 should be different objects
        assert expr1 is not expr2

    def test_expression_deepcopy_independence(self):
        """deepcopy() creates fully independent Expression.

        Verifies that modifying a deepcopy does not affect the original.
        """
        x = Variable(0)
        e1 = x + 3
        e2 = deepcopy(e1)
        e2 += 10
        terms_e1 = list(e1)
        terms_e2 = list(e2)
        # e1 should not contain the constant 10
        assert [10] not in terms_e1
        # e2 should contain the constant 10
        assert [10] in terms_e2
        # Original should be unchanged
        assert [3] in terms_e1
        assert [1, 0] in terms_e1

    def test_expression_inplace_add(self):
        """In-place += operator mutates self and returns self."""
        x = Variable(0)
        e1 = x + 3
        e1_id = id(e1)
        e1 += 5
        # Should be same object
        assert id(e1) == e1_id
        # Should have the added constant
        terms = list(e1)
        assert [5] in terms

    def test_expression_inplace_mul(self):
        """In-place *= operator mutates self and returns self."""
        x = Variable(0)
        e1 = x + 3
        e1_id = id(e1)
        e1 *= 2
        # Should be same object
        assert id(e1) == e1_id
        # Coefficients should be doubled
        terms = list(e1)
        assert [6] in terms  # 3 * 2
        assert [2, 0] in terms  # 1*x0 * 2

    def test_expression_mul_immutable(self):
        """Expression * int returns new object without modifying self."""
        x = Variable(0)
        e1 = x + 3
        terms_before = list(e1)
        e2 = e1 * 2
        terms_after = list(e1)
        # e1 should be unchanged
        assert terms_before == terms_after
        # e2 should have doubled coefficients
        terms_e2 = list(e2)
        assert [6] in terms_e2
        assert [2, 0] in terms_e2


class TestExpressionConstraintOperators:
    """Tests for comparison operators that create constraints."""

    def test_constraint_creation_leq(self):
        """Expression <= int creates constraint with LOWER sense."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr <= 5
        # The constraint is an Expression with sense and rhs appended to iteration
        terms = list(c)
        # Last two elements are sense and rhs
        assert LOWER in terms
        assert 5 in terms

    def test_constraint_creation_geq(self):
        """Expression >= int creates constraint (internally converted to LOWER)."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr >= 1
        # >= is converted internally by negating and using LOWER sense
        terms = list(c)
        assert LOWER in terms

    def test_constraint_creation_eq(self):
        """Expression == int creates constraint with EQUAL sense."""
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr == 2
        terms = list(c)
        assert EQUAL in terms
        assert 2 in terms
