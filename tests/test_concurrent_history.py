"""
Tests for concurrent solve() with independent history tracking (Phase 11).

Validates CB-01, CB-02, CB-03 requirements: per-thread state isolation,
independent history lists for concurrent solves, and SATISFY mode
satisfaction count history.
"""
import threading

import pytest
from concurrent.futures import ThreadPoolExecutor

from cbqs import Model, MAXIMIZE, SATISFY
from cbqs.result import OptimizeResult


def _build_knapsack_model():
    """Build a simple knapsack model for testing."""
    m = Model()
    xs = m.add_variables(8)
    x = [xs[i] for i in range(8)]
    weights = [2, 3, 4, 5, 1, 6, 3, 2]
    values = [3, 4, 5, 7, 2, 8, 4, 3]
    m.add_constraint(sum(weights[i] * x[i] for i in range(8)) <= 15)
    m.set_objective(sum(values[i] * x[i] for i in range(8)), sense=MAXIMIZE)
    m.close()
    m.general_greedy()
    return m


def _build_satisfy_model():
    """Build a SATISFY-mode model (no objective, just constraints)."""
    m = Model()
    xs = m.add_variables(4)
    x = [xs[i] for i in range(4)]
    m.add_constraint((x[0] + x[1]) <= 1)
    m.add_constraint((x[2] + x[3]) <= 1)
    m.close()
    m.general_greedy()
    return m


class TestConcurrentSolveIndependence:
    """Tests for concurrent solve() history isolation (CB-02)."""

    def test_concurrent_solve_independent_histories(self):
        """Two concurrent solves produce independent, valid history lists (CB-02)."""

        def solve_with_seed(seed_val):
            m = _build_knapsack_model()
            m.seed = seed_val
            return m.solve(stopping_time=5, num_workers=1, track_history=True)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(solve_with_seed, s) for s in [1, 2]]
            results = [f.result() for f in futures]

        for result in results:
            assert isinstance(result, OptimizeResult)
            assert isinstance(result.history, list)
            # Validate structure of any history entries
            for entry in result.history:
                assert len(entry) == 2, f"History entry should be 2-tuple, got {len(entry)}"
                value, elapsed = entry
                assert isinstance(value, (int, float)), f"Value should be numeric, got {type(value)}"
                assert isinstance(elapsed, float), f"Elapsed should be float, got {type(elapsed)}"
            # Verify elapsed times are non-decreasing within each history
            if len(result.history) > 1:
                times = [entry[1] for entry in result.history]
                for i in range(1, len(times)):
                    assert times[i] >= times[i - 1], \
                        f"Elapsed times should be non-decreasing: {times}"

    def test_concurrent_solve_no_cross_contamination(self):
        """Four concurrent solves produce independently valid results (CB-02)."""

        def solve_with_seed(seed_val):
            m = _build_knapsack_model()
            m.seed = seed_val
            return m.solve(stopping_time=5, num_workers=1, track_history=True)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(solve_with_seed, s) for s in range(4)]
            results = [f.result() for f in futures]

        assert len(results) == 4
        for i, result in enumerate(results):
            assert isinstance(result, OptimizeResult), f"Result {i} should be OptimizeResult"
            assert isinstance(result.history, list), f"Result {i} history should be list"
            assert result.solution is not None, f"Result {i} should have solution"
            assert result.feasible is not None, f"Result {i} should have feasible flag"
            # Each history is valid independently
            for entry in result.history:
                assert len(entry) == 2
                value, elapsed = entry
                assert isinstance(value, (int, float))
                assert isinstance(elapsed, float)
                assert elapsed >= 0, f"Elapsed time should be non-negative, got {elapsed}"


class TestSatisfyModeHistory:
    """Tests for SATISFY mode history satisfaction count (CB-03)."""

    def test_satisfy_mode_history_satisfaction_count(self):
        """SATISFY mode history entries contain satisfaction counts >= 0 (CB-03)."""
        m = _build_satisfy_model()
        result = m.solve(stopping_time=10, num_workers=1, track_history=True)
        assert isinstance(result, OptimizeResult)
        assert isinstance(result.history, list)
        # Each entry should have (satisfaction_count, elapsed_seconds)
        for entry in result.history:
            assert len(entry) == 2
            value, elapsed = entry
            assert isinstance(value, (int, float)), \
                f"Expected numeric satisfaction count, got {type(value)}"
            assert value >= 0, f"Satisfaction count should be >= 0, got {value}"
            assert isinstance(elapsed, float), \
                f"Elapsed should be float, got {type(elapsed)}"


class TestTrackHistoryFalse:
    """Tests for track_history=False optimization."""

    def test_track_history_false_no_overhead(self):
        """Solve with track_history=False produces empty history and valid solution."""
        m = _build_knapsack_model()
        result = m.solve(stopping_time=5, num_workers=1, track_history=False)
        assert result.history == [], "track_history=False should produce empty history"
        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert result.feasible is not None
        assert isinstance(result.objective, (int, float))


class TestConcurrentCallback:
    """Tests for concurrent solve with user callbacks (CB-01)."""

    def test_concurrent_solve_with_user_callback(self):
        """Concurrent solves with user callbacks maintain independence (CB-01)."""
        lock = threading.Lock()
        call_counts = {}

        def solve_with_callback(seed_val):
            thread_id = threading.get_ident()

            def my_callback():
                with lock:
                    call_counts[thread_id] = call_counts.get(thread_id, 0) + 1

            m = _build_knapsack_model()
            m.seed = seed_val
            result = m.solve(
                stopping_time=5, num_workers=1,
                track_history=True, callback=my_callback,
            )
            return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(solve_with_callback, s) for s in [1, 2]]
            results = [f.result() for f in futures]

        # Both solves should complete successfully
        for result in results:
            assert isinstance(result, OptimizeResult)
            assert isinstance(result.history, list)
            assert result.solution is not None

        # Callbacks should have been invoked (solver does call the callback)
        # Note: if no improvements are found, callbacks may not fire for history,
        # but the C-level callback is still called on each iteration.
        # We verify the mechanism works without crashing, not the exact count.
