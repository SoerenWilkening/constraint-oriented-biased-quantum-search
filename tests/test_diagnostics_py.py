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


def _configure_solve(m, stopping_time=5, num_workers=1, **extra):
    """Set common solve params on model."""
    m.set_param('stopping_time', stopping_time)
    m.set_param('num_workers', num_workers)
    for k, v in extra.items():
        m.set_param(k, v)


class TestSolveDiagnostics:
    """Tests for OptimizeResult returned by solve()."""

    def test_solve_returns_optimize_result(self):
        """solve() returns an OptimizeResult instance."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result, OptimizeResult)

    def test_result_has_solution_array(self):
        """result.solution is a numpy array with correct length."""
        m = _build_knapsack_model(n_vars=5)
        _configure_solve(m)
        result = m.solve()
        assert result.solution is not None
        assert isinstance(result.solution, np.ndarray)
        assert len(result.solution) == 5

    def test_result_has_objective(self):
        """result.objective is a number."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.objective, (int, float))
        assert result.objective == m.objective_value

    def test_result_has_feasible(self):
        """result.feasible is a bool."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.feasible, bool)

    def test_result_has_timing(self):
        """result.solve_time > 0, result.preprocessing_time >= 0, result.time > 0."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert result.solve_time >= 0
        assert result.preprocessing_time >= 0
        assert result.time > 0

    def test_result_has_oracle_calls(self):
        """result.oracle_calls >= 0."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.oracle_calls, int)
        assert result.oracle_calls >= 0

    def test_result_has_iterations(self):
        """result.iterations >= 0."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.iterations, int)
        assert result.iterations >= 0

    def test_result_has_history(self):
        """result.history is a list."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.history, list)

    def test_result_has_reproducibility(self):
        """result.num_threads is int, result.seed is int."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        assert isinstance(result.num_threads, int)
        assert isinstance(result.seed, int)

    def test_result_repr(self):
        """repr(result) contains 'OptimizeResult'."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        r = repr(result)
        assert "OptimizeResult" in r

    def test_result_to_dict(self):
        """result.to_dict() returns dict, json.dumps works."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        d = result.to_dict()
        assert isinstance(d, dict)
        # Must be JSON-serializable
        s = json.dumps(d)
        assert isinstance(s, str)

    def test_result_summary(self):
        """result.summary() returns non-empty string."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        s = result.summary()
        assert isinstance(s, str)
        assert len(s) > 0


class TestLocalSearchDiagnostics:
    """Tests for OptimizeResult returned by local_search()."""

    def test_local_search_returns_optimize_result(self):
        """local_search() returns an OptimizeResult instance."""
        m = _build_knapsack_model()
        m.set_param("stopping_time", 3)
        result = m.local_search()
        assert isinstance(result, OptimizeResult)

    def test_local_search_result_has_timing(self):
        """Timing fields populated in local_search result."""
        m = _build_knapsack_model()
        m.set_param("stopping_time", 3)
        result = m.local_search()
        assert result.solve_time >= 0
        assert result.preprocessing_time >= 0
        assert result.time > 0

    def test_local_search_result_has_solution(self):
        """Solution array present in local_search result."""
        m = _build_knapsack_model(n_vars=5)
        m.set_param("stopping_time", 3)
        result = m.local_search()
        assert result.solution is not None
        assert isinstance(result.solution, np.ndarray)
        assert len(result.solution) == 5
        assert isinstance(result.objective, (int, float))

    def test_local_search_history_oracle_stamp_is_zero(self):
        """The classical k-flip local_search() path issues no oracle queries, so its
        oracle-indexed history entries are stamped oracle == 0 (M0e). Pins the
        deliberate intent so the local_search history meaning cannot silently drift
        (ctx->oracle_count is incremented only on the quantum solve()/ctg path)."""
        m = _build_knapsack_model(n_vars=8, capacity=6)
        m.manual_initial(0, [0] * 8)  # start away from optimum so the search improves
        m.set_param("stopping_time", 3)
        m.set_param("track_history", True)
        m.set_param("distance", 2)
        result = m.local_search()
        for value, oracle in result.history:
            assert isinstance(value, (int, float))
            assert isinstance(oracle, int) and not isinstance(oracle, bool)
            assert oracle == 0, \
                f"local_search makes no oracle queries; stamp must be 0, got {oracle}"


class TestVerifyIntegration:
    """Tests for verify parameter integration with OptimizeResult."""

    def test_solve_verify_true_populates_result(self):
        """result.verified is True and result.violations is list when verify=True."""
        m = _build_knapsack_model()
        _configure_solve(m, verify=True)
        result = m.solve()
        assert result.verified is True
        assert isinstance(result.violations, list)

    def test_solve_verify_false_result(self):
        """result.verified is None when verify=False."""
        m = _build_knapsack_model()
        _configure_solve(m, verify=False)
        result = m.solve()
        assert result.verified is None
        assert result.violations is None

    def test_local_search_verify_true(self):
        """local_search with verify=True populates verified and violations."""
        m = _build_knapsack_model()
        m.set_param("stopping_time", 3)
        m.set_param("verify", True)
        result = m.local_search()
        assert result.verified is True
        assert isinstance(result.violations, list)

    def test_local_search_verify_false(self):
        """local_search with verify=False leaves verified as None."""
        m = _build_knapsack_model()
        m.set_param("stopping_time", 3)
        m.set_param("verify", False)
        result = m.local_search()
        assert result.verified is None
        assert result.violations is None


class TestHistoryAccumulation:
    """Tests for improvement history in OptimizeResult."""

    def test_history_entries_are_tuples(self):
        """Each entry in result.history has 2 elements (value, oracle:int) (M0e)."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        for entry in result.history:
            assert len(entry) == 2, f"History entry should have 2 elements, got {len(entry)}"

    def test_history_objectives_monotonic(self):
        """For maximization, values in history should be non-decreasing (if any entries exist)."""
        m = _build_knapsack_model(sense=MAXIMIZE)
        _configure_solve(m)
        result = m.solve()
        if len(result.history) > 1:
            objectives = [entry[0] for entry in result.history]
            for i in range(1, len(objectives)):
                assert objectives[i] >= objectives[i - 1], \
                    f"History should be non-decreasing for MAXIMIZE: {objectives}"

    def test_history_entries_have_correct_types(self):
        """History entries contain (value, oracle:int) -- oracle-indexed, not seconds (M0e)."""
        m = _build_knapsack_model()
        _configure_solve(m)
        result = m.solve()
        for entry in result.history:
            value, oracle = entry
            assert isinstance(value, (int, float))
            # Oracle stamp is an integer oracle count (NORTHSTAR §11), not a float time.
            assert isinstance(oracle, int) and not isinstance(oracle, bool), \
                f"Oracle stamp should be int, got {type(oracle)}"
            assert oracle >= 0

    def test_multi_worker_history_merged_running_max(self):
        """Multi-worker history is a flat best-of-portfolio curve: sorted by oracle,
        running-max value (NORTHSTAR §11/§1.3 M0e)."""
        m = _build_knapsack_model()
        _configure_solve(m, num_workers=2)
        result = m.solve()
        assert isinstance(result.history, list)
        # The history axis IS the §1.2 per-worker oracle metric (ctx->oracle_count):
        # every stamp is a non-bool int in [0, result.oracle_calls] (the per-worker
        # T(n) budget == max-over-workers oracle_count). A wall-clock float, or a
        # stamp exceeding the budget, would fail here.
        for value, oracle in result.history:
            assert isinstance(oracle, int) and not isinstance(oracle, bool)
            assert 0 <= oracle <= result.oracle_calls, \
                f"oracle stamp {oracle} outside [0, oracle_calls={result.oracle_calls}]"
        if len(result.history) > 1:
            oracles = [entry[1] for entry in result.history]
            values = [entry[0] for entry in result.history]
            for i in range(1, len(oracles)):
                assert oracles[i] >= oracles[i - 1], \
                    f"Merged history should be sorted by oracle: {oracles}"
                # Running-max best-of-portfolio: value strictly improves at each kept point.
                assert values[i] > values[i - 1], \
                    f"Best-of-portfolio value should be monotone-increasing: {values}"

    def test_final_incumbents_best_of_portfolio(self):
        """result.final_incumbents holds one (value, feasible) per worker, and the best
        feasible per-worker value equals the reported best-of-portfolio objective (M0e §8.3).

        Pins the faithfulness identity max-over-workers == global_opt (the worker's final
        cur_sol is its best because CSearch_opt only accepts strictly-improving moves)."""
        m = _build_knapsack_model(sense=MAXIMIZE)
        _configure_solve(m, num_workers=3)
        result = m.solve()
        assert isinstance(result.final_incumbents, list)
        assert len(result.final_incumbents) == 3
        for entry in result.final_incumbents:
            assert len(entry) == 2
            value, feasible = entry
            assert isinstance(value, (int, float))
            assert isinstance(feasible, bool)
        feas_vals = [v for (v, f) in result.final_incumbents if f]
        if result.feasible and feas_vals:
            assert max(feas_vals) == result.objective, \
                f"best-of-P {max(feas_vals)} must equal global_opt objective {result.objective}"

    def test_track_history_false_returns_empty(self):
        """track_history=False produces empty history."""
        m = _build_knapsack_model()
        _configure_solve(m, track_history=False)
        result = m.solve()
        assert result.history == []
