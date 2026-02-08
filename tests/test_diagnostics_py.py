"""Integration tests for solve diagnostics (Phase 8).

Tests verify that solve() and local_search() return OptimizeResult objects
with all fields correctly populated from actual solver execution.
"""
import json

import numpy as np
import pytest

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE, MINIMIZE
from cbqs.result import OptimizeResult


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


class TestSolveDiagnostics:
    """Tests for OptimizeResult returned by solve()."""

    def test_solve_returns_optimize_result(self):
        """solve() returns an OptimizeResult instance."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result, OptimizeResult)

    def test_result_has_solution_array(self):
        """result.solution is a numpy array with correct length."""
        m = _build_knapsack_model(n_vars=5)
        result = m.solve(stopping_time=5, num_workers=1)
        assert result.solution is not None
        assert isinstance(result.solution, np.ndarray)
        assert len(result.solution) == 5

    def test_result_has_objective(self):
        """result.objective is a number."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.objective, (int, float))
        assert result.objective == m.objective_value

    def test_result_has_feasible(self):
        """result.feasible is a bool."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.feasible, bool)

    def test_result_has_timing(self):
        """result.solve_time > 0, result.preprocessing_time >= 0, result.time > 0."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert result.solve_time >= 0
        assert result.preprocessing_time >= 0
        assert result.time > 0

    def test_result_has_oracle_calls(self):
        """result.oracle_calls >= 0."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.oracle_calls, int)
        assert result.oracle_calls >= 0

    def test_result_has_iterations(self):
        """result.iterations >= 0."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.iterations, int)
        assert result.iterations >= 0

    def test_result_has_history(self):
        """result.history is a list."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.history, list)

    def test_result_has_reproducibility(self):
        """result.num_threads is int, result.seed is int."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        assert isinstance(result.num_threads, int)
        assert isinstance(result.seed, int)

    def test_result_repr(self):
        """repr(result) contains 'OptimizeResult'."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        r = repr(result)
        assert "OptimizeResult" in r

    def test_result_to_dict(self):
        """result.to_dict() returns dict, json.dumps works."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        d = result.to_dict()
        assert isinstance(d, dict)
        # Must be JSON-serializable
        s = json.dumps(d)
        assert isinstance(s, str)

    def test_result_summary(self):
        """result.summary() returns non-empty string."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        s = result.summary()
        assert isinstance(s, str)
        assert len(s) > 0


class TestLocalSearchDiagnostics:
    """Tests for OptimizeResult returned by local_search()."""

    def test_local_search_returns_optimize_result(self):
        """local_search() returns an OptimizeResult instance."""
        m = _build_knapsack_model()
        result = m.local_search(stop_time=3)
        assert isinstance(result, OptimizeResult)

    def test_local_search_result_has_timing(self):
        """Timing fields populated in local_search result."""
        m = _build_knapsack_model()
        result = m.local_search(stop_time=3)
        assert result.solve_time >= 0
        assert result.preprocessing_time >= 0
        assert result.time > 0

    def test_local_search_result_has_solution(self):
        """Solution array present in local_search result."""
        m = _build_knapsack_model(n_vars=5)
        result = m.local_search(stop_time=3)
        assert result.solution is not None
        assert isinstance(result.solution, np.ndarray)
        assert len(result.solution) == 5
        assert isinstance(result.objective, (int, float))


class TestVerifyIntegration:
    """Tests for verify parameter integration with OptimizeResult."""

    def test_solve_verify_true_populates_result(self):
        """result.verified is True and result.violations is list when verify=True."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1, verify=True)
        assert result.verified is True
        assert isinstance(result.violations, list)

    def test_solve_verify_false_result(self):
        """result.verified is None when verify=False."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1, verify=False)
        assert result.verified is None
        assert result.violations is None

    def test_local_search_verify_true(self):
        """local_search(verify=True) populates verified and violations."""
        m = _build_knapsack_model()
        result = m.local_search(stop_time=3, verify=True)
        assert result.verified is True
        assert isinstance(result.violations, list)

    def test_local_search_verify_false(self):
        """local_search(verify=False) leaves verified as None."""
        m = _build_knapsack_model()
        result = m.local_search(stop_time=3, verify=False)
        assert result.verified is None
        assert result.violations is None


class TestHistoryAccumulation:
    """Tests for improvement history in OptimizeResult."""

    def test_history_entries_are_tuples(self):
        """Each entry in result.history has 2 elements (value, elapsed_seconds)."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        for entry in result.history:
            assert len(entry) == 2, f"History entry should have 2 elements, got {len(entry)}"

    def test_history_objectives_monotonic(self):
        """For maximization, values in history should be non-decreasing (if any entries exist)."""
        m = _build_knapsack_model(sense=MAXIMIZE)
        result = m.solve(stopping_time=5, num_workers=1)
        if len(result.history) > 1:
            objectives = [entry[0] for entry in result.history]
            for i in range(1, len(objectives)):
                assert objectives[i] >= objectives[i - 1], \
                    f"History should be non-decreasing for MAXIMIZE: {objectives}"

    def test_history_entries_have_correct_types(self):
        """History entries contain (value, elapsed_seconds)."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1)
        for entry in result.history:
            value, elapsed_seconds = entry
            assert isinstance(value, (int, float))
            assert isinstance(elapsed_seconds, float)

    def test_multi_worker_history_merged(self):
        """History from multiple workers is merged into single list."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=2)
        # History should be a flat list (not nested), sorted by elapsed_seconds
        assert isinstance(result.history, list)
        if len(result.history) > 1:
            times = [entry[1] for entry in result.history]
            for i in range(1, len(times)):
                assert times[i] >= times[i - 1], \
                    f"Merged history should be sorted by elapsed_seconds: {times}"

    def test_track_history_false_returns_empty(self):
        """track_history=False produces empty history."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1, track_history=False)
        assert result.history == []
