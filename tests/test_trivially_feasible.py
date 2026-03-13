"""
Tests for trivially-feasible detection in OPTDataCollector.

Verifies that _is_trivially_feasible correctly identifies models where
the zero solution satisfies all constraints (e.g., knapsack instances).
"""

import pytest
import numpy as np

from cbqs.ml.data_collection import OPTDataCollector
from cbqs.result import OptimizeResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_result(**overrides):
    """Create an OptimizeResult with sensible defaults."""
    defaults = dict(
        solution=[1, 0, 1, 0],
        objective=42.0,
        feasible=True,
        solve_time=100.0,
        preprocessing_time=50.0,
        iterations=5000,
        oracle_calls=250,
        history=[(38.0, 0.005), (42.0, 0.020)],
        verified=True,
        violations=None,
        num_threads=4,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


class FakeModel:
    """Fake model without constraint evaluation (legacy behavior)."""

    def __init__(self, n_vars=5, trivially_feasible=False):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._trivially_feasible = trivially_feasible
        self.constraints_compiled = True
        self.mod = type('obj', (object,), {'solver': 1})()

    def set_param(self, key, value):
        self._params[key] = value

    def solve(self):
        self._solve_count += 1
        return _make_result(objective=10.0 + self._solve_count)


# ------------------------------------------------------------------
# Tests using real Model instances
# ------------------------------------------------------------------

from cbqs import Model, MAXIMIZE, MINIMIZE


def _make_knapsack_model(n=5, weights=None, capacity=10):
    """Create a knapsack model -- trivially feasible (zero solution works)."""
    m = Model()
    x = m.add_variables(n)
    if weights is None:
        weights = list(range(1, n + 1))
    values = list(range(1, n + 1))
    m.set_objective(sum(values[i] * x[i] for i in range(n)), MAXIMIZE)
    m.add_constraint(sum(weights[i] * x[i] for i in range(n)) <= capacity)
    m.close()
    return m


def _make_covering_model(n=5):
    """Create a set covering model -- NOT trivially feasible.

    Constraint: x0 + x1 + ... + x_{n-1} >= 1  (at least one selected).
    The zero solution violates this.
    """
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum(x[i] for i in range(n)), MINIMIZE)
    m.add_constraint(sum(x[i] for i in range(n)) >= 1)
    m.close()
    return m


def _make_equality_model(n=3):
    """Create a model with equality constraint -- NOT trivially feasible.

    Constraint: x0 + x1 + x2 == 1.
    The zero solution violates this.
    """
    m = Model()
    x = m.add_variables(n)
    m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
    m.add_constraint(x[0] + x[1] + x[2] == 1)
    m.close()
    return m


class TestTriviallyFeasibleDetection:
    """Tests for _is_trivially_feasible on real Model instances."""

    def test_knapsack_is_trivially_feasible(self):
        """Knapsack models are trivially feasible (zero solution works)."""
        model = _make_knapsack_model()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is True

    def test_covering_is_not_trivially_feasible(self):
        """Covering constraints (>= 1) make zero solution infeasible."""
        model = _make_covering_model()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is False

    def test_equality_is_not_trivially_feasible(self):
        """Equality constraints (== 1) make zero solution infeasible."""
        model = _make_equality_model()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is False

    def test_multiple_knapsack_constraints(self):
        """Multiple <= constraints are still trivially feasible."""
        m = Model()
        x = m.add_variables(5)
        m.set_objective(sum(x[i] for i in range(5)), MAXIMIZE)
        m.add_constraint(x[0] + x[1] + x[2] <= 5)
        m.add_constraint(x[2] + x[3] + x[4] <= 3)
        m.add_constraint(sum(x[i] for i in range(5)) <= 10)
        m.close()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(m) is True

    def test_mixed_constraints_not_trivially_feasible(self):
        """Mix of <= and >= constraints: zero solution may not work."""
        m = Model()
        x = m.add_variables(5)
        m.set_objective(sum(x[i] for i in range(5)), MAXIMIZE)
        m.add_constraint(x[0] + x[1] + x[2] <= 5)
        m.add_constraint(x[2] + x[3] + x[4] >= 1)  # zero violates this
        m.close()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(m) is False


class TestTriviallyFeasibleFallback:
    """Tests for fallback behavior when model has no constraint attribute."""

    def test_fake_model_with_attribute_true(self):
        """FakeModel with _trivially_feasible=True is detected."""
        model = FakeModel(n_vars=5, trivially_feasible=True)
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is True

    def test_fake_model_with_attribute_false(self):
        """FakeModel with _trivially_feasible=False is not detected."""
        model = FakeModel(n_vars=5, trivially_feasible=False)
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is False

    def test_no_attribute_defaults_false(self):
        """Object without _trivially_feasible or constraint defaults to False."""
        class BareModel:
            n = 5
        model = BareModel()
        collector = OPTDataCollector(random_state=42)
        assert collector._is_trivially_feasible(model) is False
