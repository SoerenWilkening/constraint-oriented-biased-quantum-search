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
    """Test branching weights memory management via solver context."""

    def test_branching_weights_no_leak(self):
        """branching_weights propagation through solve should not leak."""
        from cbqs.Model import Model
        from cbqs.Constants import MAXIMIZE

        # Create and solve multiple times to amplify any leak
        for _ in range(20):
            m = Model()
            x = m.add_variables(5)
            m.set_objective(x[0] + x[1] + x[2] + x[3] + x[4], sense=MAXIMIZE)
            m.add_constraint(x[0] + x[1] + x[2] + x[3] + x[4] <= 3)
            m.close()
            m.set_param("branching_weights", [0.1, 0.2, 0.3, 0.2, 0.2])
            m.set_param("stopping_time", 1)
            m.set_param("num_workers", 1)
            m.solve()
            del m

        gc.collect()
        # If this leaks, Valgrind will report leaked branching_weights arrays

    def test_branching_weights_realloc_no_leak(self):
        """Repeated set_param with different-sized weights across solves should not leak."""
        from cbqs.Model import Model
        from cbqs.Constants import MAXIMIZE

        for size in [5, 10, 20, 10, 5, 15, 3]:
            m = Model()
            x = m.add_variables(size)
            m.set_objective(sum(x[i] for i in range(size)), sense=MAXIMIZE)
            m.add_constraint(sum(x[i] for i in range(size)) <= size // 2)
            m.close()
            m.set_param("branching_weights", [float(i + 1) for i in range(size)])
            m.set_param("stopping_time", 1)
            m.set_param("num_workers", 1)
            m.solve()
            del m

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
