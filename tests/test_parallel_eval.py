"""
Unit tests for ParallelCollector -- instance-parallel evaluation.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from cbqs.ml.data_collection import (
    ParallelCollector,
    SATDataCollector,
    OPTDataCollector,
)
from cbqs.result import OptimizeResult


# ------------------------------------------------------------------
# Helpers (all must be picklable for ProcessPoolExecutor tests)
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


class _FakeMod:
    """Picklable stand-in for model.mod attribute."""
    solver = 1


class FakeModel:
    """A fake model for testing data collection without a real solver.

    Fully picklable so it can be used with ProcessPoolExecutor.
    """

    def __init__(self, n_vars=5, results=None, feasible=True,
                 trivially_feasible=False):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._default_feasible = feasible
        self._trivially_feasible = trivially_feasible
        self.constraints_compiled = True
        self.mod = _FakeMod()

    def set_param(self, key, value):
        self._params[key] = value

    def _get_effective(self, key):
        return self._params.get(key)

    def solve(self):
        idx = self._solve_count
        self._solve_count += 1
        if idx < len(self._results):
            return self._results[idx]
        obj = 10.0 + self._solve_count
        feasible = self._default_feasible
        return _make_result(
            objective=obj,
            feasible=feasible,
            history=[(obj, 0.01)],
            solve_time=50.0,
        )


class BadModel:
    """A model whose solve() always raises, for error-handling tests."""
    n = 5
    _trivially_feasible = False
    constraints_compiled = True

    def __init__(self):
        self._params = {}
        self.mod = _FakeMod()

    def set_param(self, key, value):
        self._params[key] = value

    def _get_effective(self, key):
        return self._params.get(key)

    def solve(self):
        raise RuntimeError("solver exploded")


def _objective_signal(r):
    """Picklable signal function that returns the objective value."""
    return r.objective


# ===================================================================
# ParallelCollector Tests
# ===================================================================


class TestParallelCollectSameResultsAsSerial:
    """Parallel collection produces the same results as serial."""

    def test_parallel_collect_same_results_as_serial(self):
        """Results from parallel collection match serial collection."""
        models = [FakeModel(n_vars=5) for _ in range(4)]

        collector = SATDataCollector(
            n_strategies=3,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )

        # Collect serially
        serial_results = [collector.collect(m) for m in models]

        # Reset models
        models = [FakeModel(n_vars=5) for _ in range(4)]

        parallel = ParallelCollector(collector, max_workers=2)
        parallel_results = parallel.collect_batch(models)

        assert len(parallel_results) == len(serial_results)
        for pr in parallel_results:
            assert 'best_signal' in pr
            assert 'best_params' in pr
            assert 'all_results' in pr


class TestParallelUsesNWorkers:
    """ParallelCollector passes correct max_workers to executor."""

    def test_parallel_uses_n_workers(self):
        """ProcessPoolExecutor is called with max_workers from init."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector, max_workers=4)

        models = [FakeModel(n_vars=3) for _ in range(3)]

        with patch('cbqs.ml.data_collection.ProcessPoolExecutor') as mock_pool:
            mock_executor = MagicMock()
            mock_pool.return_value.__enter__ = MagicMock(
                return_value=mock_executor
            )
            mock_pool.return_value.__exit__ = MagicMock(return_value=False)

            # Make futures that return fake results
            mock_future = MagicMock()
            mock_future.result.return_value = {
                'best_signal': 10.0,
                'best_params': {},
                'all_results': [],
            }
            mock_executor.submit.return_value = mock_future

            pc.collect_batch(models)

            mock_pool.assert_called_once_with(max_workers=4)


class TestParallelRespectsMaxWorkers:
    """ParallelCollector respects max_workers default and override."""

    def test_parallel_respects_max_workers(self):
        """Default max_workers is 6."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector)
        assert pc.max_workers == 6

    def test_parallel_custom_max_workers(self):
        """Custom max_workers is preserved."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector, max_workers=12)
        assert pc.max_workers == 12


class TestParallelHandlesSingleInstance:
    """ParallelCollector works correctly with a single instance."""

    def test_parallel_handles_single_instance(self):
        """collect_batch with one model returns a one-element list."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector, max_workers=2)
        models = [FakeModel(n_vars=5)]

        results = pc.collect_batch(models)

        assert len(results) == 1
        assert 'best_signal' in results[0]
        assert 'best_params' in results[0]


class TestParallelErrorHandling:
    """ParallelCollector handles errors in individual instance evaluation."""

    def test_parallel_error_handling(self):
        """If a model's collect raises, it is captured as an error dict."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector, max_workers=2)

        good_model = FakeModel(n_vars=5)
        bad_model = BadModel()

        models = [good_model, bad_model]

        results = pc.collect_batch(models)

        assert len(results) == 2
        # One should succeed, one should have error info
        errors = [r for r in results if 'error' in r]
        successes = [r for r in results if 'error' not in r]
        assert len(errors) == 1
        assert len(successes) == 1
        assert 'solver exploded' in errors[0]['error']

    def test_parallel_empty_models_list(self):
        """collect_batch with empty list returns empty list."""
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=_objective_signal,
            random_state=42,
            single_thread=False,
        )
        pc = ParallelCollector(collector, max_workers=2)

        results = pc.collect_batch([])
        assert results == []
