"""Tests for Cython layer memory management.

These tests verify that Cython wrapper functions properly free
allocated memory. Run under Valgrind to confirm no leaks.

Usage:
    pytest tests/test_cython_memory.py -v

Under Valgrind:
    PYTHONMALLOC=malloc valgrind --leak-check=full \
        --suppressions=tests/valgrind-python.supp \
        python -m pytest tests/test_cython_memory.py -v
"""
import pytest
import gc


class TestBranchingMemory:
    """Test branching.pyx memory management."""

    def test_set_obj_dependence_no_leak(self):
        """set_obj_dependence_wrapper should not leak the internal array."""
        from cbqs.branching import set_obj_dependence_wrapper

        # Call multiple times to amplify any leak
        for _ in range(100):
            set_obj_dependence_wrapper([0.1, 0.2, 0.3, 0.4, 0.5])

        gc.collect()
        # If this leaks, Valgrind will report 100 * 5 * sizeof(double) lost

    def test_set_constraint_dependence_no_leak(self):
        """set_constraint_dependence_wrapper should not leak the internal array."""
        from cbqs.branching import set_constraint_dependence_wrapper

        for _ in range(100):
            set_constraint_dependence_wrapper([1.0, 2.0, 3.0])

        gc.collect()


class TestStateMemory:
    """Test state.pyx memory management."""

    def test_state_create_destroy_cycle(self):
        """state_py creation and destruction should not leak."""
        from cbqs.state import state_py

        for _ in range(50):
            st = state_py(0, [0, 1, 0, 1, 0])
            del st

        gc.collect()

    def test_state_copy_no_leak(self):
        """Copying state_py should not leak."""
        from cbqs.state import state_py
        from copy import copy

        original = state_py(100, [1, 0, 1, 0])
        for _ in range(50):
            copied = copy(original)
            del copied

        del original
        gc.collect()


class TestExpressionMemory:
    """Test Expression.pyx memory management."""

    def test_expression_create_destroy_cycle(self):
        """Expression creation and destruction should not leak."""
        from cbqs.Expression import Expression, Variable

        for _ in range(100):
            x = Variable(0)
            y = Variable(1)
            expr = x + y + 5
            expr2 = expr * 3
            del expr2
            del expr

        gc.collect()

    def test_expression_deep_copy_no_leak(self):
        """Deep copying Expression should not leak."""
        from cbqs.Expression import Expression, Variable
        from copy import deepcopy

        x = Variable(0)
        original = x + 5

        for _ in range(100):
            copied = deepcopy(original)
            del copied

        del original
        gc.collect()


class TestConstraintMemory:
    """Test Constraint.pyx memory management."""

    def test_constraint_create_destroy_cycle(self):
        """new_constraint creation and destruction should not leak."""
        from cbqs.Constraint import new_constraint
        from cbqs.Expression import Variable

        for _ in range(50):
            con = new_constraint()
            x = Variable(0)
            expr = x + 5 <= 10
            con.add_expression(expr)
            del con

        gc.collect()


class TestModelMemory:
    """Test Model.pyx memory management."""

    def test_model_create_destroy_cycle(self):
        """Model creation and destruction should not leak."""
        from cbqs.Model import Model

        for _ in range(20):
            m = Model()
            x = m.add_variables(5)
            m.add_constraint(x[0] + x[1] <= 1)
            m.close()
            del m

        gc.collect()
