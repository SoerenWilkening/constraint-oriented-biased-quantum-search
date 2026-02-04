"""
Pytest tests for Constraint Cython bindings.

Tests validate constraint creation, expression addition, and
constraint evaluation through the cbqs.Constraint Python API.
"""
import pytest
from cbqs.Expression import Variable, Expression
from cbqs.Constraint import new_constraint
from cbqs.Constants import LOWER, EQUAL


class TestConstraintCreation:
    """Tests for new_constraint object creation and management."""

    def test_constraint_object_creation(self):
        """new_constraint() creates an empty constraint container."""
        con = new_constraint()
        assert len(con) == 0

    def test_add_leq_constraint(self):
        """Adding a <= constraint increments constraint count."""
        con = new_constraint()
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr <= 5
        con.add_expression(c)
        assert len(con) == 1

    def test_add_geq_constraint(self):
        """Adding a >= constraint increments constraint count."""
        con = new_constraint()
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr >= 1
        con.add_expression(c)
        assert len(con) == 1

    def test_add_eq_constraint(self):
        """Adding an == constraint increments constraint count."""
        con = new_constraint()
        x0 = Variable(0)
        x1 = Variable(1)
        expr = x0 + x1
        c = expr == 2
        con.add_expression(c)
        assert len(con) == 1

    def test_add_multiple_constraints(self):
        """Adding multiple constraints tracks count correctly."""
        con = new_constraint()

        x0 = Variable(0)
        x1 = Variable(1)
        x2 = Variable(2)

        c1 = (x0 + x1) <= 3
        con.add_expression(c1)

        c2 = (x1 + x2) <= 4
        con.add_expression(c2)

        c3 = (x0 + x2) == 1
        con.add_expression(c3)

        assert len(con) == 3

    def test_constraint_copy(self):
        """Copying a constraint container preserves count."""
        from copy import copy
        con = new_constraint()
        x0 = Variable(0)
        x1 = Variable(1)
        c = (x0 + x1) <= 5
        con.add_expression(c)
        con_copy = copy(con)
        assert len(con_copy) == 1
