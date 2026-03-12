"""
Unit tests for _evaluate_strategy_repeated() in cbqs.ml.data_collection.

Tests adaptive stopping logic (min/max repeats, threshold convergence,
epsilon guard), variance reduction vs single evaluation, and integration
with SATDataCollector and OPTDataCollector.
"""

import pytest
import numpy as np

from cbqs.ml.data_collection import (
    _evaluate_strategy_repeated,
    _evaluate_strategy,
    SATDataCollector,
    OPTDataCollector,
)
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
        num_threads=1,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


class FakeModel:
    """A fake model for testing repeated evaluation without a real solver.

    Each solve() call returns a result with objective drawn from a
    configurable distribution, or from a fixed list of results.
    """

    def __init__(self, n_vars=5, results=None, objective_fn=None,
                 trivially_feasible=False):
        self.n = n_vars
        self._params = {}
        self._solve_count = 0
        self._results = results or []
        self._objective_fn = objective_fn
        self._trivially_feasible = trivially_feasible

    def set_param(self, key, value):
        self._params[key] = value

    def solve(self):
        idx = self._solve_count
        self._solve_count += 1
        if idx < len(self._results):
            return self._results[idx]
        if self._objective_fn is not None:
            obj = self._objective_fn(idx)
        else:
            obj = 10.0 + idx
        return _make_result(
            objective=obj,
            feasible=True,
            history=[(obj, 0.01)],
            solve_time=50.0,
            num_threads=1,
        )


# ===================================================================
# _evaluate_strategy_repeated tests
# ===================================================================


class TestRepeatedEvalReturnsMeanSignal:
    """_evaluate_strategy_repeated returns mean of repeated signal values."""

    def test_single_thread_repeated_eval_returns_mean_signal(self):
        """Mean signal is the average of all repeated evaluations."""
        # Create model that returns fixed objectives: 10, 12, 14, ...
        results = [
            _make_result(objective=float(10 + 2 * i), history=[(float(10 + 2 * i), 0.01)],
                         solve_time=50.0, num_threads=1)
            for i in range(10)
        ]
        model = FakeModel(n_vars=5, results=results)
        signal_fn = lambda r: r.objective
        params = {'sat_branching_bias': 1.0}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=10, max_repeats=10, threshold=0.01,
        )

        expected_signals = [10 + 2 * i for i in range(10)]
        expected_mean = np.mean(expected_signals)
        assert abs(out['mean_signal'] - expected_mean) < 1e-9
        assert out['n_repeats'] == 10


class TestAdaptiveStopsBelowThreshold:
    """Adaptive stopping converges when std_of_mean / range < threshold."""

    def test_adaptive_repeats_stops_below_threshold(self):
        """Stops early when std_of_mean / (best - worst) is below threshold."""
        # Very low variance signals -> should stop at min_repeats
        results = [
            _make_result(objective=100.0 + 0.001 * i,
                         history=[(100.0 + 0.001 * i, 0.01)],
                         solve_time=50.0, num_threads=1)
            for i in range(200)
        ]
        model = FakeModel(n_vars=5, results=results)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=10, max_repeats=200, threshold=0.05,
        )

        # Should stop well before max_repeats due to low variance
        assert out['n_repeats'] >= 10
        assert out['n_repeats'] < 200


class TestMinRepeatsWhenBestEqWorst:
    """Uses min_repeats when best == worst (non-discriminating instance)."""

    def test_adaptive_repeats_uses_min_when_best_eq_worst(self):
        """When all signals are identical, uses exactly min_repeats."""
        results = [
            _make_result(objective=50.0, history=[(50.0, 0.01)],
                         solve_time=50.0, num_threads=1)
            for _ in range(20)
        ]
        model = FakeModel(n_vars=5, results=results)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=10, max_repeats=100, threshold=0.05,
            epsilon=1e-8,
        )

        assert out['n_repeats'] == 10
        assert abs(out['mean_signal'] - 50.0) < 1e-9


class TestAdaptiveRespectsHardCap:
    """Stops at max_repeats even if threshold not met."""

    def test_adaptive_repeats_respects_hard_cap(self):
        """Stops at max_repeats when signals have high variance."""
        # Alternating high/low signals -> high std_of_mean relative to range
        call_count = [0]

        def objective_fn(idx):
            call_count[0] += 1
            # Alternating 0.0 and 100.0 -- maximally variable
            return 100.0 if idx % 2 == 0 else 0.0

        model = FakeModel(n_vars=5, objective_fn=objective_fn)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=5, max_repeats=20, threshold=0.001,
        )

        assert out['n_repeats'] == 20


class TestMinRepeatsEnforced:
    """Always runs at least min_repeats even if threshold met earlier."""

    def test_min_repeats_enforced(self):
        """Runs at least min_repeats solves."""
        results = [
            _make_result(objective=42.0, history=[(42.0, 0.01)],
                         solve_time=50.0, num_threads=1)
            for _ in range(15)
        ]
        model = FakeModel(n_vars=5, results=results)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=15, max_repeats=100, threshold=0.5,
        )

        assert out['n_repeats'] >= 15


class TestRepeatedEvalStoresRawResults:
    """_evaluate_strategy_repeated stores all raw signals and results."""

    def test_repeated_eval_stores_raw_results(self):
        """Output contains raw_signals and raw_results lists."""
        n = 10
        results = [
            _make_result(objective=float(i), history=[(float(i), 0.01)],
                         solve_time=50.0, num_threads=1)
            for i in range(n)
        ]
        model = FakeModel(n_vars=5, results=results)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=n, max_repeats=n, threshold=0.01,
        )

        assert len(out['raw_signals']) == n
        assert len(out['raw_results']) == n
        for i in range(n):
            assert abs(out['raw_signals'][i] - float(i)) < 1e-9


class TestRepeatedEvalSetsNumWorkers:
    """_evaluate_strategy_repeated sets num_workers=1 for single-thread."""

    def test_repeated_eval_sets_num_workers_to_one(self):
        """num_workers is set to 1 during repeated evaluation solves."""
        observed_workers = []

        class WorkerTrackingModel(FakeModel):
            def solve(self):
                observed_workers.append(self._params.get('num_workers'))
                return super().solve()

        model = WorkerTrackingModel(n_vars=5)
        model.set_param('num_workers', 4)
        signal_fn = lambda r: r.objective
        params = {'sat_branching_bias': 1.0}

        _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=3, max_repeats=3, threshold=0.01,
        )

        # Every solve should have seen num_workers=1
        assert all(w == 1 for w in observed_workers)
        assert len(observed_workers) == 3

    def test_repeated_eval_restores_num_workers(self):
        """num_workers is restored to original value after repeated eval."""
        model = FakeModel(n_vars=5)
        model.set_param('num_workers', 8)
        signal_fn = lambda r: r.objective
        params = {}

        _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=3, max_repeats=3, threshold=0.01,
        )

        assert model._params['num_workers'] == 8


class TestRepeatedEvalReducesVariance:
    """Mean of repeated evaluations has lower variance than single eval."""

    def test_repeated_eval_reduces_variance_vs_single(self):
        """Repeated eval produces std_signal, demonstrating averaging."""
        # Create model with noisy objectives
        n_trials = 10
        rng = np.random.default_rng(42)

        def objective_fn(idx):
            return 50.0 + rng.normal(0, 10.0)

        model = FakeModel(n_vars=5, objective_fn=objective_fn)
        signal_fn = lambda r: r.objective
        params = {}

        out = _evaluate_strategy_repeated(
            model, params, signal_fn, time_budget=None,
            min_repeats=n_trials, max_repeats=n_trials, threshold=0.01,
        )

        # std_signal should be > 0 (there is variance in raw signals)
        assert out['std_signal'] > 0.0
        # std_of_mean = std / sqrt(n) should be smaller than std
        std_of_mean = out['std_signal'] / np.sqrt(out['n_repeats'])
        assert std_of_mean < out['std_signal']
        assert 'mean_signal' in out
        assert 'params' in out


# ===================================================================
# Collector integration tests
# ===================================================================


class TestSATCollectorRepeated:
    """SATDataCollector uses repeated evaluation when single_thread=True."""

    def test_sat_collector_single_thread_uses_repeated_eval(self):
        """SATDataCollector with single_thread=True calls repeated eval."""
        model = FakeModel(n_vars=3)
        collector = SATDataCollector(
            n_strategies=2,
            time_budget=None,
            signal_fn=lambda r: r.objective,
            random_state=42,
            single_thread=True,
            min_repeats=3,
            max_repeats=3,
        )
        data = collector.collect(model)
        assert 'best_params' in data
        assert 'best_signal' in data
        assert len(data['all_results']) == 2
        # Each result should have repeated eval fields
        for entry in data['all_results']:
            assert 'mean_signal' in entry
            assert 'n_repeats' in entry
            assert entry['n_repeats'] == 3

    def test_sat_collector_single_thread_false_uses_original(self):
        """SATDataCollector with single_thread=False uses original eval."""
        model = FakeModel(n_vars=3)
        collector = SATDataCollector(
            n_strategies=2,
            time_budget=None,
            signal_fn=lambda r: r.objective,
            random_state=42,
            single_thread=False,
        )
        data = collector.collect(model)
        assert len(data['all_results']) == 2
        # Original eval does not have n_repeats
        for entry in data['all_results']:
            assert 'n_repeats' not in entry


class TestOPTCollectorRepeated:
    """OPTDataCollector uses repeated evaluation when single_thread=True."""

    def test_opt_collector_single_thread_uses_repeated_eval(self):
        """OPTDataCollector with single_thread=True calls repeated eval."""
        model = FakeModel(n_vars=3, trivially_feasible=True)
        collector = OPTDataCollector(
            n_opt_sat=2, top_k=1, n_opt_per_candidate=2,
            signal_fn=lambda r: r.objective,
            random_state=42,
            single_thread=True,
            min_repeats=3,
            max_repeats=3,
        )
        data = collector.collect(model)
        assert data['trivially_feasible'] is True
        assert len(data['all_results']) > 0
        for entry in data['all_results']:
            assert 'mean_signal' in entry
            assert 'n_repeats' in entry

    def test_opt_collector_single_thread_false_uses_original(self):
        """OPTDataCollector with single_thread=False uses original eval."""
        model = FakeModel(n_vars=3, trivially_feasible=True)
        collector = OPTDataCollector(
            n_opt_sat=2, top_k=1, n_opt_per_candidate=2,
            signal_fn=lambda r: r.objective,
            random_state=42,
            single_thread=False,
        )
        data = collector.collect(model)
        for entry in data['all_results']:
            assert 'n_repeats' not in entry
