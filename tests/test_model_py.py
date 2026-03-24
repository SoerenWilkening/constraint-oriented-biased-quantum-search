"""
Pytest tests for the Model API including solve integration.

Tests validate the full user-facing Model API: variable creation,
constraint addition, objective setting, and solve execution through
the Cython bindings.
"""
import pytest
from cbqs.Model import Model
from cbqs.Expression import Variable, Expression
from cbqs.Constants import MAXIMIZE, MINIMIZE, OPTIMIZE, SATISFY
from cbqs.result import OptimizeResult


class TestModelCreation:
    """Tests for Model instantiation and initial state."""

    def test_model_creation(self):
        """Model() creates an instance with expected initial state."""
        m = Model()
        assert m.n == 0
        assert m.sense == MAXIMIZE
        assert m.variables == {}
        # constraints_compiled is a Python-level attribute
        assert m.constraints_compiled is False

    def test_model_initial_variable_count(self):
        """New model has zero variables."""
        m = Model()
        assert m.n == 0
        assert len(m.variables) == 0


class TestModelVariables:
    """Tests for variable creation through Model API."""

    def test_add_single_variable(self):
        """add_variable() returns a Variable and increments n."""
        m = Model()
        x = m.add_variable()
        assert isinstance(x, Variable)
        assert m.n == 1

    def test_add_multiple_variables_individually(self):
        """Adding variables one by one gives distinct indices."""
        m = Model()
        x0 = m.add_variable()
        x1 = m.add_variable()
        assert x0.index != x1.index
        assert m.n == 2

    def test_add_variables_batch(self):
        """add_variables(n) returns CVariableVector with n variables."""
        m = Model()
        xs = m.add_variables(5)
        assert not isinstance(xs, dict)  # now CVariableVector
        assert len(xs) == 5
        assert m.n == 5
        # All indices should be unique
        indices = [xs[k].index for k in xs]
        assert len(set(indices)) == 5

    def test_add_variables_sequential_indices(self):
        """Variables added in batch have sequential indices."""
        m = Model()
        xs = m.add_variables(3)
        indices = sorted(xs[k].index for k in xs)
        assert indices == [0, 1, 2]


class TestModelObjectiveAndConstraints:
    """Tests for setting objectives and adding constraints."""

    def test_set_objective_maximize(self):
        """Setting objective with MAXIMIZE does not crash."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        obj_expr = x[0] + x[1] + x[2]
        m.set_objective(obj_expr, MAXIMIZE)
        assert m.sense == MAXIMIZE

    def test_set_objective_minimize(self):
        """Setting objective with MINIMIZE does not crash."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        obj_expr = x[0] + x[1] + x[2]
        m.set_objective(obj_expr, MINIMIZE)
        assert m.sense == MINIMIZE

    def test_set_objective_invalid_sense(self):
        """Setting objective with invalid sense raises TypeError."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        obj_expr = x[0] + x[1]
        with pytest.raises(TypeError):
            m.set_objective(obj_expr, 999)

    def test_add_constraint_leq(self):
        """Adding a <= constraint does not crash."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        c = (x[0] + x[1] + x[2]) <= 2
        m.add_constraint(c)
        # Verify constraint was stored
        assert len(m.con_expr) == 1

    def test_add_multiple_constraints(self):
        """Adding multiple constraints tracks them correctly."""
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]

        m.add_constraint((x[0] + x[1]) <= 1)
        m.add_constraint((x[2] + x[3]) <= 1)
        m.add_constraint((x[0] + x[2]) <= 1)

        assert len(m.con_expr) == 3


class TestModelSolve:
    """Integration tests for the solve pipeline."""

    def test_solve_requires_close(self):
        """Calling solve before close raises ValueError."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_param('stopping_time', 1)
        m.set_param('num_workers', 1)
        with pytest.raises(ValueError, match="No constraints compiled"):
            m.solve()

    def test_close_compiles_constraints(self):
        """close() sets constraints_compiled flag."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.close()
        assert m.constraints_compiled is True

    def test_solve_small_knapsack(self):
        """Solve a 5-variable knapsack and verify feasibility.

        Problem: 5 binary variables, each weight 2, capacity 6.
        Maximize: x0 + x1 + x2 + x3 + x4
        Constraint: 2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4 <= 6
        Optimal: select 3 of 5 variables (obj = 3).
        """
        m = Model()
        xs = m.add_variables(5)
        x = [xs[i] for i in range(5)]

        # Constraint: total weight <= 6
        weight_expr = 2 * x[0] + 2 * x[1] + 2 * x[2] + 2 * x[3] + 2 * x[4]
        m.add_constraint(weight_expr <= 6)

        # Objective: maximize number of items
        obj_expr = x[0] + x[1] + x[2] + x[3] + x[4]
        m.set_objective(obj_expr, MAXIMIZE)

        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        m.solve()

        # Verify feasibility: objective value should be <= 3
        # (at most 3 items fit with weight 2 each, capacity 6)
        obj_val = m.objective_value
        assert obj_val >= 0, "Objective should be non-negative"
        assert obj_val <= 5, "Cannot exceed total number of variables"
        # The constraint allows at most 3 items
        assert obj_val <= 3, "Feasibility: at most 3 items fit (weight 2 each, cap 6)"

    def test_solve_tight_knapsack(self):
        """Solve a knapsack with varying weights and verify feasibility.

        Items with weights [3, 4, 5, 2], capacity 8.
        Maximize: x0 + x1 + x2 + x3
        Constraint: 3*x0 + 4*x1 + 5*x2 + 2*x3 <= 8
        """
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]

        # Constraint: 3*x0 + 4*x1 + 5*x2 + 2*x3 <= 8
        weight_expr = 3 * x[0] + 4 * x[1] + 5 * x[2] + 2 * x[3]
        m.add_constraint(weight_expr <= 8)

        # Objective: maximize number of items selected
        obj_expr = x[0] + x[1] + x[2] + x[3]
        m.set_objective(obj_expr, MAXIMIZE)

        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        m.solve()

        # Feasibility check: objective value should be reasonable
        obj_val = m.objective_value
        assert obj_val >= 0, "Objective should be non-negative"
        assert obj_val <= 4, "Cannot exceed total number of variables"

    def test_solve_weighted_objective_knapsack(self):
        """Solve a knapsack with weighted objective.

        3 items: weights [2, 3, 4], values [5, 7, 8], capacity 6.
        Maximize: 5*x0 + 7*x1 + 8*x2
        Constraint: 2*x0 + 3*x1 + 4*x2 <= 6
        """
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]

        m.add_constraint((2 * x[0] + 3 * x[1] + 4 * x[2]) <= 6)
        m.set_objective(5 * x[0] + 7 * x[1] + 8 * x[2], MAXIMIZE)

        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        m.solve()

        obj_val = m.objective_value
        assert obj_val >= 0, "Objective should be non-negative"

    def test_solve_completes_without_crash(self):
        """Solve with multiple workers completes without crashing."""
        m = Model()
        xs = m.add_variables(5)
        x = [xs[i] for i in range(5)]

        m.add_constraint((x[0] + x[1] + x[2] + x[3] + x[4]) <= 3)
        m.set_objective(x[0] + x[1] + x[2] + x[3] + x[4], MAXIMIZE)

        m.close()
        m.set_param('stopping_time', 3)
        m.set_param('num_workers', 2)
        result = m.solve()

        # Should complete without exception and return OptimizeResult
        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert result.objective == m.objective_value

    def test_model_copy(self):
        """Copying a model preserves sense."""
        from copy import copy
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)

        m2 = copy(m)
        assert m2.sense == m.sense


class TestSatisfyMode:
    """Integration tests for SATISFY mode (no objective).

    These tests validate the fixes from Plan 09-01 (CRASH-01 through CRASH-04).
    SATISFY mode is active when no objective is set on the Model.
    """

    def test_satisfy_mode_completes(self):
        """SATISFY-mode solve completes without TypeError crash (CRASH-01)."""
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]
        m.add_constraint((x[0] + x[1]) <= 1)
        m.add_constraint((x[2] + x[3]) <= 1)
        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        result = m.solve()
        assert isinstance(result, OptimizeResult)

    def test_satisfy_objective_value_is_none(self):
        """objective_value property returns None in SATISFY mode (CRASH-03)."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        result = m.solve()
        assert m.objective_value is None
        assert result.objective is None

    def test_satisfy_result_feasible(self):
        """SATISFY solve on a satisfiable problem reports feasible=True (CRASH-01/03/04).

        Uses a trivially satisfiable problem (all-zeros satisfies the single
        constraint) with enough stopping time for the solver to find it.
        """
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]
        m.add_constraint((x[0] + x[1]) <= 1)
        m.add_constraint((x[2] + x[3]) <= 1)
        m.close()
        m.set_param('stopping_time', 30)
        m.set_param('num_workers', 1)
        result = m.solve()
        # For a trivially satisfiable problem the solver should find a feasible solution
        assert result.feasible is True

    def test_satisfy_history_has_satisfaction_count(self):
        """History entries in SATISFY mode have satisfaction count >= 0 (CB-03)."""
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]
        m.add_constraint((x[0] + x[1]) <= 1)
        m.add_constraint((x[2] + x[3]) <= 1)
        m.close()
        m.set_param('stopping_time', 10)
        m.set_param('num_workers', 1)
        result = m.solve()
        # SATISFY history entries are (satisfaction_count, elapsed_seconds)
        for entry in result.history:
            value, elapsed = entry
            assert isinstance(value, (int, float)), f"Expected numeric satisfaction count, got {value}"
            assert value >= 0, f"Satisfaction count should be >= 0, got {value}"

    def test_satisfy_verify_does_not_crash(self):
        """verify=True on a SATISFY solve does not raise TypeError (CRASH-04)."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.close()
        m.set_param('stopping_time', 5)
        m.set_param('num_workers', 1)
        m.set_param('verify', True)
        result = m.solve()
        assert isinstance(result, OptimizeResult)
        # verified should be True or False, not None (since verify=True was passed)
        assert result.verified is not None
