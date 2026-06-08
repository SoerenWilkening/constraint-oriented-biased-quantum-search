"""opt_sample_cap: the classical Grover-round sample cap (bd 0o8).

A faithful CBQS solve simulates a Grover round of j iterations by drawing 4j^2+1
candidate states (CSearch_{sat,opt_sat,opt}); that O(n*j^2) classical cost makes
large-n (large-j) solves intractable and blocks the large-n baseline freeze.
`opt_sample_cap` bounds a round to `cap` candidates. It must NOT change the
oracle accounting -- the 2j+1 charge is applied in ctg BEFORE the sim
(CLAUDE.md sec 1.2) -- so the per-worker budget T(n) still binds and single-worker
runs stay deterministic. cap == 0 (default) is the exact unbounded sim, so every
existing baseline stays green.

These are the known-correct gates (not no-crash checks):
  * a cap larger than any round's realized sample count is BIT-IDENTICAL to cap=0
    (proves the cap path does not perturb the PRNG stream or the accounting);
  * a binding cap on a stalling instance still terminates at exactly T(n);
  * a capped run is deterministic and feasibility-correct (verify=True).
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
    """Covering (>=) knapsack that dwells in long non-improving stretches, so
    `rounds` grows and a stage-3 Grover round draws a large j -> the 4j^2+1 sim
    blows up. This is exactly the regime opt_sample_cap is meant to bound
    (mirrors test_oracle_budget._stalling)."""
    m = Model()
    x = m.add_variables(n)
    w = [i % 5 + 1 for i in range(n)]
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) >= sum(w) - 2)
    m.close()
    return m


def _T(n):
    """Default per-worker oracle budget T(n) = (n/4)^2 + 1200 (NORTHSTAR sec 3)."""
    return int((n / 4.0) ** 2 + 1200)


def _solve(mk, n, cap, *, seed=7, M=-1, workers=1, verify=False):
    m = mk(n)
    m.seed = seed
    m.set_param("M", M)
    m.set_param("num_workers", workers)
    m.set_param("opt_sample_cap", cap)
    if verify:
        m.set_param("verify", True)
    return m.solve()


class TestOptSampleCap:
    def test_default_is_zero_unbounded(self):
        """The default is 0 (exact unbounded sim) -- the cap is opt-in, so no
        committed baseline is affected unless a finite cap is set."""
        m = _knapsack(20)
        assert m._get_effective("opt_sample_cap") == 0

    def test_negative_cap_rejected(self):
        """The param guard rejects a negative cap (domain is >= 0)."""
        m = _knapsack(20)
        with pytest.raises((ValueError, Exception)):
            m.set_param("opt_sample_cap", -1)

    def test_large_cap_is_bit_identical_to_unbounded(self):
        """A cap larger than any round's realized sample count must reproduce the
        unbounded run BIT-FOR-BIT: identical oracle_calls, objective, AND solution
        array. This proves the cap code path -- when it does not bind -- neither
        perturbs the per-worker PRNG stream nor the oracle accounting (CLAUDE.md
        sec 1.2 / sec 8). n=40 keeps every round's 4j^2+1 well under 10**9."""
        r0 = _solve(_knapsack, 40, 0)
        rC = _solve(_knapsack, 40, 10**9)
        assert r0.oracle_calls == rC.oracle_calls
        assert r0.objective == rC.objective
        assert list(r0.solution) == list(rC.solution)

    def test_cap_preserves_oracle_budget_on_stalling(self):
        """REGRESSION: capping the classical sim must NOT change the oracle
        budget. A stalling instance (which forces large j) still terminates at
        exactly T(n) with a binding cap, just as the uncapped run does -- the
        2j+1 charge and the cumulative-budget gate in ctg are untouched."""
        n = 60
        T = _T(n)
        r_unc = _solve(_stalling, n, 0)
        r_cap = _solve(_stalling, n, 300)
        assert T - 2 <= r_unc.oracle_calls <= T
        assert T - 2 <= r_cap.oracle_calls <= T, (
            f"capped stalling oracle_calls={r_cap.oracle_calls} not in "
            f"[{T-2}, {T}] -- the cap must not alter the oracle budget"
        )

    def test_capped_run_is_deterministic(self):
        """Fixed seed + single worker + a binding cap => identical oracle_calls,
        objective, AND solution across runs (determinism survives the cap, sec 8)."""
        r1 = _solve(_stalling, 60, 300)
        r2 = _solve(_stalling, 60, 300)
        assert r1.oracle_calls == r2.oracle_calls
        assert r1.objective == r2.objective
        assert list(r1.solution) == list(r2.solution)

    def test_capped_run_is_feasible(self):
        """verify=True asserts every reported-feasible solution satisfies
        eval_constraints==0 (Model.pyx). A binding cap must not poison
        feasibility/sign accounting (CLAUDE.md sec 2.1 / sec 5)."""
        r = _solve(_stalling, 80, 500, verify=True)
        assert r.solution is not None

    def test_cap_preserves_multi_worker_budget(self):
        """With a cap and num_workers>1 the reported per-worker oracle_calls is
        still ~T(n) (best-of-portfolio), not corrupted by the cap."""
        n = 40
        T = _T(n)
        r = _solve(_knapsack, n, 200, workers=4)
        assert T <= r.oracle_calls < 2 * T, (
            f"multi-worker capped oracle_calls={r.oracle_calls} should be ~T(n)={T}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
