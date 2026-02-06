"""
Pytest tests for post-solve solution verification.

Tests validate Model.verify_solution(), the verify=True parameter on
solve(), and the _verified attribute state transitions.
"""
import warnings

import pytest
from cbqs.Model import Model
from cbqs.Expression import Variable
from cbqs.Constants import MAXIMIZE, MINIMIZE


def _build_knapsack_model(n_vars=5, weights=None, capacity=6, sense=MAXIMIZE):
    """Helper: build and return a closed knapsack model.

    Default: 5 items, uniform weight 2, capacity 6, maximize count.
    """
    m = Model()
    xs = m.add_variables(n_vars)
    x = [xs[i] for i in range(n_vars)]

    if weights is None:
        weights = [2] * n_vars
    weight_expr = sum(weights[i] * x[i] for i in range(n_vars))
    m.add_constraint(weight_expr <= capacity)

    obj_expr = sum(x[i] for i in range(n_vars))
    m.set_objective(obj_expr, sense)
    m.close()
    return m


class TestVerifySolution:
    """Tests for verify_solution() method."""

    def test_valid_solution_verifies_true(self):
        """verify_solution() returns True for a valid solved model."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1)
        result = m.verify_solution()
        assert result is True

    def test_unsolved_model_returns_false(self):
        """verify_solution() returns False when solve() has not been called."""
        m = _build_knapsack_model()
        result = m.verify_solution()
        assert result is False

    def test_verified_flag_true_after_success(self):
        """_verified is True after successful verification."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1)
        m.verify_solution()
        assert m._verified is True

    def test_verified_flag_false_after_failure(self):
        """_verified is False after failed verification (unsolved)."""
        m = _build_knapsack_model()
        m.verify_solution()
        assert m._verified is False

    def test_verified_flag_none_initially(self):
        """_verified is None before any verification attempt."""
        m = Model()
        assert m._verified is None

    def test_verified_flag_state_transition(self):
        """_verified transitions: None -> False (unsolved) -> True (after solve)."""
        m = _build_knapsack_model()
        assert m._verified is None

        m.verify_solution()
        assert m._verified is False

        m.solve(stopping_time=5, num_workers=1)
        m.verify_solution()
        assert m._verified is True

    def test_verify_with_multiple_constraints(self):
        """verify_solution() works with multiple constraints."""
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]

        m.add_constraint((x[0] + x[1]) <= 1)
        m.add_constraint((x[2] + x[3]) <= 1)
        m.add_constraint((x[0] + x[2]) <= 1)

        m.set_objective(x[0] + x[1] + x[2] + x[3], MAXIMIZE)
        m.close()
        m.solve(stopping_time=5, num_workers=1)

        result = m.verify_solution()
        assert result is True
        assert m._verified is True

    def test_verify_minimize_sense(self):
        """verify_solution() works with MINIMIZE sense."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]

        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MINIMIZE)
        m.close()
        m.solve(stopping_time=5, num_workers=1)

        result = m.verify_solution()
        assert result is True

    def test_verify_weighted_objective(self):
        """verify_solution() works with weighted objective coefficients."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]

        m.add_constraint((2 * x[0] + 3 * x[1] + 4 * x[2]) <= 6)
        m.set_objective(5 * x[0] + 7 * x[1] + 8 * x[2], MAXIMIZE)
        m.close()
        m.solve(stopping_time=5, num_workers=1)

        result = m.verify_solution()
        assert result is True


class TestVerifyWarnings:
    """Tests for warning emission during verification."""

    def test_unsolved_emits_warning(self):
        """verify_solution() emits UserWarning when model is unsolved."""
        m = _build_knapsack_model()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.verify_solution()
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)
            assert "solve() has not been called" in str(w[0].message)

    def test_valid_solution_no_warnings(self):
        """verify_solution() emits no warnings on valid solution."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = m.verify_solution()
            assert result is True
            assert len(w) == 0


class TestVerifyOnSolve:
    """Tests for verify=True parameter on solve()."""

    def test_solve_verify_true_auto_verifies(self):
        """solve(verify=True) automatically calls verify_solution()."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1, verify=True)
        assert m._verified is True

    def test_solve_verify_false_no_verification(self):
        """solve(verify=False) does not call verify_solution()."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1, verify=False)
        assert m._verified is None

    def test_solve_default_no_verification(self):
        """solve() with default args does not call verify_solution()."""
        m = _build_knapsack_model()
        m.solve(stopping_time=5, num_workers=1)
        assert m._verified is None

    def test_solve_verify_true_returns_result(self):
        """solve(verify=True) still returns the incumbent list."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1, verify=True)
        assert isinstance(result, list)
        assert m._verified is True
