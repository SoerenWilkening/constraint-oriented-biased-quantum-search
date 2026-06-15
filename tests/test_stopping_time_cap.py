"""Wall-clock cap (``stopping_time``) for the ctg solve — a TRAINING lever, OFF by default.

Re-adds the NORTHSTAR-M0-removed wall-clock stop as an OPT-IN cap: ON when
``stopping_time > 0`` (seconds), OFF when ``stopping_time <= 0`` (the new default ``-1``).
OFF keeps the faithful oracle-budget-only termination — the frozen anchors and
single-worker determinism are unchanged. Faithfulness/reproducibility is explicitly
WAIVED when the cap is set (the truncated trajectory is machine-dependent); the cap is
checked BETWEEN Grover rounds, so it cannot interrupt a single in-progress large-j round.

Covers: SearchLib.c ctg while-condition, local_search.c:594 off-sentinel guard,
Model.pyx ``stopping_time`` param (default -1, validate -1-or->0).
"""
import os
import time

import numpy as np
import pytest

pytest.importorskip("cbqs")
from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from benchmarks.metric import oracle_budget


def _knapsack(n=40):
    """Self-contained deterministic knapsack (no benchmark clone needed)."""
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n * 2)
    m.close()
    return m


def _solve(n, stopping_time, seed=3, M=-1):
    m = _knapsack(n)
    m.seed = seed
    m.set_param("M", M)
    m.set_param("num_workers", 1)
    if stopping_time is not None:
        m.set_param("stopping_time", stopping_time)
    t0 = time.perf_counter()
    r = m.solve()
    return r, time.perf_counter() - t0


class TestStoppingTimeParamContract:
    def test_default_is_off_sentinel(self):
        assert _knapsack().get_param("stopping_time") == -1

    def test_off_and_positive_accepted(self):
        m = _knapsack()
        m.set_param("stopping_time", -1)
        assert m.get_param("stopping_time") == -1
        m.set_param("stopping_time", 2700)
        assert m.get_param("stopping_time") == 2700

    @pytest.mark.parametrize("bad", [0, -5, -0.5])
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError, match="stopping_time must be > 0"):
            _knapsack().set_param("stopping_time", bad)


class TestOffPreservesFaithfulPath:
    def test_off_runs_full_oracle_budget(self):
        n = 40
        r, _w = _solve(n, stopping_time=-1)
        assert r.oracle_calls == oracle_budget(n), "OFF must terminate on the oracle budget T(n)"

    def test_off_is_deterministic(self):
        r1, _ = _solve(40, stopping_time=-1, seed=7)
        r2, _ = _solve(40, stopping_time=-1, seed=7)
        assert r1.objective == r2.objective
        assert r1.oracle_calls == r2.oracle_calls
        assert np.array_equal(np.asarray(r1.solution), np.asarray(r2.solution))


class TestCapTruncates:
    @pytest.mark.skipif(not os.environ.get("CBQS_BENCHMARKS_DIR"),
                        reason="needs the Eq.29 instances (a solve slow enough to exercise the wall cap)")
    def test_cap_truncates_real_instance(self):
        try:
            from benchmarks.eq29_loader import load_eq29, build_model
        except ImportError:
            from eq29_loader import load_eq29, build_model
        n = 100
        c1, c2, c3 = load_eq29(n, 0)
        T = oracle_budget(n)

        def solve(st):
            m = build_model(c1, c2, c3, vectorized=True)
            m.seed = 3
            m.set_param("M", -1)
            m.set_param("num_workers", 1)
            m.set_param("stopping_time", st)
            t0 = time.perf_counter()
            r = m.solve()
            return r, time.perf_counter() - t0

        r_off, w_off = solve(-1)
        assert r_off.oracle_calls == T, "OFF baseline must run the full budget"
        # cap well under the off wall-time -> the between-rounds stop must fire early
        cap = max(0.004, w_off / 5.0)
        r_cap, _w = solve(cap)
        assert r_cap.oracle_calls < T, "wall cap must truncate below the full oracle budget"
        assert r_cap.oracle_calls > 0 and r_cap.feasible


class TestLocalSearchOffSentinelGuard:
    def test_local_search_off_matches_large_stopping_time(self):
        """local_search.c:594 guard: the -1 OFF default must behave like a huge cap.

        Without the `stopping_time > 0 &&` guard, `time > -1` is true at the first
        iteration's check, so local_search breaks immediately and under-optimizes.
        Comparing OFF (-1) against an effectively-unbounded cap (1e6 s) catches that:
        equal => guard works; OFF worse => regression.
        """
        m_big = _knapsack(40)
        m_big.seed = 3
        m_big.set_param("stopping_time", 1_000_000)
        r_big = m_big.local_search()

        m_off = _knapsack(40)
        m_off.seed = 3  # default stopping_time == -1 (OFF)
        r_off = m_off.local_search()

        assert r_off.feasible and r_big.feasible
        assert r_off.objective == r_big.objective, (
            "OFF (-1) must run the full local search, identical to an unbounded cap")
