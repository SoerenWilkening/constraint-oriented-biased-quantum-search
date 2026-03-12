"""
Unit tests for cbqs.ml.data_collection -- random parameter sampling,
SATDataCollector, and OPTDataCollector (Option C).
"""

import pytest
import numpy as np

from cbqs.ml.data_collection import (
    random_sat_params,
    random_opt_params,
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
        num_threads=4,
        seed=42,
    )
    defaults.update(overrides)
    return OptimizeResult(**defaults)


class FakeModel:
    """A fake model for testing data collection without a real solver.

    Accepts parameters via set_param and returns configurable results
    from solve(). Tracks the number of solve calls.
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
        self.mod = type('obj', (object,), {'solver': 1})()  # OPTIMIZE=1

    def set_param(self, key, value):
        self._params[key] = value

    def _get_effective(self, key):
        return self._params.get(key)

    def solve(self):
        idx = self._solve_count
        self._solve_count += 1
        if idx < len(self._results):
            return self._results[idx]
        # Return a default result with some variation
        obj = 10.0 + self._solve_count
        feasible = self._default_feasible
        return _make_result(
            objective=obj,
            feasible=feasible,
            history=[(obj, 0.01)],
            solve_time=50.0,
        )


# ===================================================================
# Random Parameter Generation
# ===================================================================


class TestRandomSATParams:
    """Tests for random_sat_params -- random SAT parameter sampling."""

    def test_random_sat_params_shape(self):
        """SAT params contain weights(n), priorities(n), bias, bf, bif."""
        rng = np.random.default_rng(42)
        params = random_sat_params(5, rng)
        assert 'sat_branching_weights' in params
        assert 'sat_variable_priorities' in params
        assert 'sat_branching_bias' in params
        assert 'sat_branching_factor' in params
        assert 'sat_bias_factor' in params
        assert len(params['sat_branching_weights']) == 5
        assert len(params['sat_variable_priorities']) == 5

    def test_random_weights_nonneg(self):
        """All sampled weights are non-negative."""
        rng = np.random.default_rng(123)
        for _ in range(20):
            params = random_sat_params(10, rng)
            assert np.all(np.array(params['sat_branching_weights']) >= 0)

    def test_random_bias_gt_minus_one(self):
        """All sampled biases are > -1."""
        rng = np.random.default_rng(456)
        for _ in range(50):
            params = random_sat_params(5, rng)
            assert params['sat_branching_bias'] > -1

    def test_random_params_diverse(self):
        """N samples are not identical."""
        rng = np.random.default_rng(789)
        samples = [random_sat_params(5, rng) for _ in range(10)]
        biases = [s['sat_branching_bias'] for s in samples]
        assert len(set(biases)) > 1


class TestRandomOPTParams:
    """Tests for random_opt_params -- random OPT parameter sampling."""

    def test_random_opt_params_shape(self):
        """OPT params contain opt_sat and opt parameter sets."""
        rng = np.random.default_rng(42)
        params = random_opt_params(5, rng)
        # opt_sat params
        assert 'opt_sat_branching_weights' in params
        assert 'opt_sat_variable_priorities' in params
        assert 'opt_sat_branching_bias' in params
        assert 'opt_sat_branching_factor' in params
        assert 'opt_sat_bias_factor' in params
        # opt params
        assert 'opt_branching_weights' in params
        assert 'opt_variable_priorities' in params
        assert 'opt_branching_bias' in params
        assert 'opt_branching_factor' in params
        assert 'opt_bias_factor' in params
        assert len(params['opt_sat_branching_weights']) == 5
        assert len(params['opt_branching_weights']) == 5

    def test_random_opt_weights_nonneg(self):
        """All sampled weights are non-negative."""
        rng = np.random.default_rng(42)
        params = random_opt_params(8, rng)
        assert np.all(np.array(params['opt_sat_branching_weights']) >= 0)
        assert np.all(np.array(params['opt_branching_weights']) >= 0)

    def test_random_opt_bias_gt_minus_one(self):
        """All sampled biases are > -1."""
        rng = np.random.default_rng(42)
        for _ in range(50):
            params = random_opt_params(5, rng)
            assert params['opt_sat_branching_bias'] > -1
            assert params['opt_branching_bias'] > -1


# ===================================================================
# SAT Data Collection
# ===================================================================


class TestSATDataCollector:
    """Tests for SATDataCollector -- SAT training data collection."""

    def test_collect_sat_data_returns_best(self):
        """collect() returns the best result by signal."""
        results = [
            _make_result(objective=5.0, feasible=True,
                         history=[(5.0, 0.01)], solve_time=100.0),
            _make_result(objective=10.0, feasible=True,
                         history=[(10.0, 0.01)], solve_time=100.0),
            _make_result(objective=8.0, feasible=True,
                         history=[(8.0, 0.01)], solve_time=100.0),
        ]
        model = FakeModel(n_vars=5, results=results)
        collector = SATDataCollector(n_strategies=3, signal_fn=lambda r: r.objective,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert data['best_signal'] == 10.0

    def test_collect_sat_data_tries_n_strategies(self):
        """collect() tries exactly n_strategies random configurations."""
        model = FakeModel(n_vars=5)
        collector = SATDataCollector(n_strategies=7, signal_fn=lambda r: r.objective,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert len(data['all_results']) == 7
        assert model._solve_count == 7

    def test_collect_sat_data_with_timeout(self):
        """collect() respects time_budget by passing through."""
        model = FakeModel(n_vars=5)
        collector = SATDataCollector(n_strategies=3, time_budget=10.0,
                                     signal_fn=lambda r: r.objective,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert 'best_params' in data
        assert 'best_signal' in data

    def test_collect_sat_single_strategy(self):
        """collect() works with a single strategy."""
        result = _make_result(objective=7.0, feasible=True,
                              history=[(7.0, 0.01)], solve_time=100.0)
        model = FakeModel(n_vars=5, results=[result])
        collector = SATDataCollector(n_strategies=1, signal_fn=lambda r: r.objective,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert data['best_signal'] == 7.0
        assert len(data['all_results']) == 1

    def test_collect_sat_all_results_recorded(self):
        """All strategy results are recorded in all_results."""
        model = FakeModel(n_vars=3)
        collector = SATDataCollector(n_strategies=5, signal_fn=lambda r: r.objective,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert len(data['all_results']) == 5
        for entry in data['all_results']:
            assert 'params' in entry
            assert 'result' in entry
            assert 'signal' in entry


# ===================================================================
# OPT Data Collection (Option C)
# ===================================================================


class TestOPTDataCollector:
    """Tests for OPTDataCollector -- Option C data collection."""

    def test_trivially_feasible_detection(self):
        """Trivially feasible models are detected."""
        model = FakeModel(n_vars=5, trivially_feasible=True)
        collector = OPTDataCollector(
            n_opt_sat=3, top_k=2, n_opt_per_candidate=2,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        assert collector._is_trivially_feasible(model) is True

    def test_feasibility_screening_selects_top_k(self):
        """Screening phase returns top_k candidates by screening signal."""
        # Create results with varying feasibility quality
        results = [
            _make_result(objective=3.0, feasible=True,
                         history=[(3.0, 0.01)], solve_time=100.0),
            _make_result(objective=10.0, feasible=True,
                         history=[(10.0, 0.01)], solve_time=100.0),
            _make_result(objective=7.0, feasible=True,
                         history=[(7.0, 0.01)], solve_time=100.0),
            _make_result(objective=1.0, feasible=True,
                         history=[(1.0, 0.01)], solve_time=100.0),
            _make_result(objective=5.0, feasible=True,
                         history=[(5.0, 0.01)], solve_time=100.0),
        ]
        model = FakeModel(n_vars=5, results=results)
        collector = OPTDataCollector(
            n_opt_sat=5, top_k=2, n_opt_per_candidate=1,
            signal_fn=lambda r: r.objective,
            screening_signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        candidates = collector._screen_opt_sat(model)
        assert len(candidates) == 2

    def test_full_solve_pairs_top_k_times_m(self):
        """Full solve evaluates top_k * n_opt_per_candidate pairs."""
        # 10 screening results + 2*3=6 full solve results = 16 total
        model = FakeModel(n_vars=5)
        collector = OPTDataCollector(
            n_opt_sat=10, top_k=2, n_opt_per_candidate=3,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        # Screening: 10 solves, full pairs: 2 * 3 = 6 solves
        assert model._solve_count == 10 + 6

    def test_option_c_returns_best_pair(self):
        """Option C returns the best (opt_sat, opt) pair."""
        model = FakeModel(n_vars=5)
        collector = OPTDataCollector(
            n_opt_sat=5, top_k=2, n_opt_per_candidate=3,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        assert 'best_opt_sat_params' in data
        assert 'best_opt_params' in data
        assert 'best_signal' in data

    def test_option_c_trivially_feasible_skips_opt_sat(self):
        """Trivially feasible models skip opt_sat screening."""
        model = FakeModel(n_vars=5, trivially_feasible=True)
        collector = OPTDataCollector(
            n_opt_sat=5, top_k=2, n_opt_per_candidate=3,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        assert data['trivially_feasible'] is True
        assert data['best_opt_sat_params'] is None

    def test_option_c_respects_time_budget(self):
        """OPTDataCollector accepts time budgets."""
        model = FakeModel(n_vars=5)
        collector = OPTDataCollector(
            n_opt_sat=3, top_k=2, n_opt_per_candidate=2,
            screening_budget=5.0, full_budget=10.0,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        assert 'best_signal' in data


# ===================================================================
# Signal Integration
# ===================================================================


class TestSignalIntegration:
    """Tests for data collection with different training signals."""

    def test_collect_with_auc_signal(self):
        """Data collection works with AUC signal function."""
        from cbqs.ml.signals import make_signal
        signal_fn = make_signal('auc')
        model = FakeModel(n_vars=5)
        collector = SATDataCollector(n_strategies=3, signal_fn=signal_fn,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert data['best_signal'] is not None

    def test_collect_with_weighted_signal(self):
        """Data collection works with weighted signal function."""
        from cbqs.ml.signals import make_signal
        signal_fn = make_signal('weighted', lam=1.0)
        model = FakeModel(n_vars=5)
        collector = SATDataCollector(n_strategies=3, signal_fn=signal_fn,
                                     random_state=42, single_thread=False)
        data = collector.collect(model)
        assert data['best_signal'] is not None


# ===================================================================
# Edge Cases
# ===================================================================


class TestEdgeCases:
    """Tests for edge cases in data collection."""

    def test_all_infeasible_strategies(self):
        """All infeasible strategies still return a best (least bad)."""
        results = [
            _make_result(objective=5.0, feasible=False,
                         history=[], solve_time=100.0),
            _make_result(objective=3.0, feasible=False,
                         history=[], solve_time=100.0),
        ]
        model = FakeModel(n_vars=5, results=results, feasible=False)
        collector = SATDataCollector(
            n_strategies=2,
            signal_fn=lambda r: r.objective if r.feasible else -1e6,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        assert data['best_signal'] is not None
        assert data['best_params'] is not None

    def test_single_strategy_opt(self):
        """OPT collector works with minimal configuration."""
        result = _make_result(objective=7.0, feasible=True,
                              history=[(7.0, 0.01)], solve_time=100.0)
        model = FakeModel(n_vars=3, results=[result] * 10)
        collector = OPTDataCollector(
            n_opt_sat=1, top_k=1, n_opt_per_candidate=1,
            signal_fn=lambda r: r.objective,
            random_state=42, single_thread=False,
        )
        data = collector.collect(model)
        assert data['best_signal'] is not None

    def test_random_sat_params_different_sizes(self):
        """random_sat_params works for different n_vars."""
        rng = np.random.default_rng(42)
        for n in [1, 5, 20, 100]:
            params = random_sat_params(n, rng)
            assert len(params['sat_branching_weights']) == n
            assert len(params['sat_variable_priorities']) == n

    def test_random_opt_params_different_sizes(self):
        """random_opt_params works for different n_vars."""
        rng = np.random.default_rng(42)
        for n in [1, 5, 20]:
            params = random_opt_params(n, rng)
            assert len(params['opt_sat_branching_weights']) == n
            assert len(params['opt_branching_weights']) == n
