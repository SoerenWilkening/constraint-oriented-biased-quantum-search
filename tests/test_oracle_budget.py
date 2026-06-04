"""Oracle-budget accumulator + per-worker counter (bd 8an.1.4, M0d).

NORTHSTAR §11: mod->M is now a *cumulative* per-worker oracle budget enforced by
a never-reset accumulator in ctg (the old m_tot reset on every improvement, so it
only bounded work *between* improvements and could never cap cumulative oracles);
the wall-clock stop is disabled. The reported oracle count is per-worker and
race-free (ctx->oracle_count), scored best-of-portfolio (each worker capped at
T(n)), replacing the racy shared mod->qtg_applications.
"""

import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE


def _knapsack(n):
    """n-variable knapsack that improves several times before converging."""
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n * 2)
    m.close()
    return m


def _T(n):
    """Default per-worker oracle budget T(n) = (n/4)^2 + 1200 (float, NORTHSTAR §3)."""
    return int((n / 4.0) ** 2 + 1200)


class TestOracleBudget:
    def test_default_budget_reached(self):
        """Default M=-1 runs to ~T(n) oracles (within one Grover round)."""
        n = 40
        m = _knapsack(n)
        m.seed = 7
        m.set_param("M", -1)  # opt into the real T(n) default (conftest caps it otherwise)
        m.set_param("num_workers", 1)
        r = m.solve()
        T = _T(n)
        assert T <= r.oracle_calls < 2 * T, (
            f"oracle_calls={r.oracle_calls} not in [T, 2T)=[{T}, {2*T}) for n={n}"
        )

    def test_explicit_budget_caps_cumulative_oracles(self):
        """An explicit budget caps CUMULATIVE oracles regardless of improvement
        frequency -- the bug the reset-on-improvement m_tot could not catch."""
        n = 60  # many improvements before convergence
        budget = 800
        m = _knapsack(n)
        m.seed = 3
        m.set_param("num_workers", 1)
        m.set_param("M", budget)
        r = m.solve()
        assert budget <= r.oracle_calls < 2 * budget, (
            f"oracle_calls={r.oracle_calls} not in [{budget}, {2*budget})"
        )

    def test_oracle_calls_deterministic(self):
        """Fixed seed + single worker => identical oracle_calls (and objective)."""
        def run():
            m = _knapsack(40)
            m.seed = 12345
            m.set_param("num_workers", 1)
            return m.solve()

        r1, r2 = run(), run()
        assert r1.oracle_calls == r2.oracle_calls
        assert r1.objective == r2.objective

    def test_multi_worker_reports_per_worker_budget(self):
        """num_workers>1: reported oracle_calls is the per-worker budget (~T(n),
        best-of-P), NOT the old shared P*T(n) sum."""
        n = 40
        T = _T(n)
        m = _knapsack(n)
        m.seed = 7
        m.set_param("M", -1)  # opt into the real T(n) default (conftest caps it otherwise)
        m.set_param("num_workers", 4)
        r = m.solve()
        # best-of-P max over per-worker counts ~ T(n); definitely < 2*T, not ~4*T.
        assert T <= r.oracle_calls < 2 * T, (
            f"multi-worker oracle_calls={r.oracle_calls} should be ~T(n)={T}, "
            f"not the shared P*T sum"
        )

    def test_each_worker_capped_at_budget(self):
        """Every portfolio worker independently spends ~T(n) oracles, and
        worker_id=0 is reproducible (drives run_sampling directly)."""
        from cbqs.SearchLib import run_sampling

        n = 40
        T = _T(n)
        m = _knapsack(n)
        m.seed = 7
        m.set_param("M", -1)  # opt into the real T(n) default (conftest caps it otherwise)
        m.set_param("num_workers", 1)
        m.solve()  # populate the C model_t budget (mod.M = T(n))

        def worker_count(worker_id):
            m.reset()
            m.manual_initial(0, [0] * m.n)
            r = run_sampling(m, None, [1], True, 0.0, worker_id)
            return r[1]  # this worker's own oracle_count

        counts = [worker_count(w) for w in range(2)]
        for w, c in enumerate(counts):
            assert T <= c < 2 * T, f"worker {w} count={c} not in [T, 2T)=[{T}, {2*T})"
        # worker_id=0 reproducible (single-worker determinism, §8).
        assert worker_count(0) == counts[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
