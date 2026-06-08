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


def _stalling(n):
    """Covering (>=) knapsack whose warm-start is infeasible (bd 8an.1.17).

    Maximize sum (i%7+1) x_i subject to a near-total covering constraint
    sum (i%5+1) x_i >= sum(weights) - 2. The greedy warm-start is infeasible, so
    the worker dwells in the opt_sat (constraint-tightening) phase -- where the
    Grover count is a fixed j=1 (cost 3) -- without a tightness improvement, so
    `rounds` grows unbounded. The opt_sat->opt switch then draws from a huge
    m=ceil((6/5)**rounds), so a SINGLE stage-3 Grover round overshoots T(n) by
    >2x on the pre-fix code (the real Eq.29 c2 covering-constraint blow-up:
    measured 44x at n=100, 26000x at n=500). With the cap-j clamp the per-round
    charge 2j+1 is capped to the remaining budget, so cumulative oracles land at
    exactly T(n) (within one bounded final round)."""
    m = Model()
    x = m.add_variables(n)
    w = [i % 5 + 1 for i in range(n)]
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) >= sum(w) - 2)
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

    def test_stalling_instance_budget_binds(self):
        """REGRESSION (bd 8an.1.17): a STALLING instance must terminate AT the
        budget T(n), not overshoot by an unbounded Grover round.

        Pre-fix the per-round charge 2j+1 is added AFTER the `total_oracles < M`
        gate, and m=ceil((6/5)**rounds) grows unbounded between improvements, so
        a single stuck round overshoots T(n) by orders of magnitude (here ~2.6x
        at n=60; 44x at the real n=100). The cap-j clamp caps 2j+1 to the
        remaining budget, so a stage-3 terminal round lands at exactly T(n) (a
        stage-2 break at most 2 oracles short). KNOWN-CORRECT value, not a
        no-crash check: cumulative oracle charges == T(n)."""
        n = 60
        m = _stalling(n)
        m.seed = 7
        m.set_param("M", -1)  # opt into real T(n); conftest caps the default to 200
        m.set_param("num_workers", 1)
        r = m.solve()
        T = _T(n)
        assert T - 2 <= r.oracle_calls <= T, (
            f"stalling oracle_calls={r.oracle_calls} not in [{T-2}, {T}] for n={n} "
            f"(pre-fix bd 8an.1.17 overshoot is ~3683 = 2.6x)"
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
