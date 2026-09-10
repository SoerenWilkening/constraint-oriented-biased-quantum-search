"""opt_switch_oracles exploit->explore switch (bd 8an.1.6, M0f).

NORTHSTAR §4: the opt_sat->opt switch fires at a learned cumulative-oracle
threshold (per worker, ctx->oracle_count), replacing the hardcoded counter>10.
It is GATED ON FEASIBILITY -- CSearch_opt must never run on an infeasible point
(the implicit feasibility gate the old counter>10 had; see the core-change
review must-fix).
"""
import numpy as np
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE


def _covering_model(n):
    """All-zeros is INFEASIBLE: a covering (>=) constraint forces sum x >= 2, so
    the solver must reach feasibility in opt_sat before any opt switch."""
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n)  # capacity (<=)
    m.add_constraint(sum(x[i] for i in range(n)) >= 2)                # covering (>=)
    m.close()
    return m


class TestOptSwitchOracles:
    def test_param_settable(self):
        """opt_switch_oracles is a known param defaulting to the -1 auto sentinel."""
        m = _covering_model(10)
        assert m.get_param("opt_switch_oracles") == -1
        m.set_param("opt_switch_oracles", 5)
        assert m.get_param("opt_switch_oracles") == 5

    def test_feasibility_gate_zero_threshold(self):
        """opt_switch_oracles=0 (threshold met from the first round) must NOT
        optimize an infeasible point: the result stays feasible and genuinely
        satisfies the covering constraint. Under the pre-fix condition (missing
        `feasible &&`) the switch would fire round 1 while infeasible and
        CSearch_opt would ignore the covering constraint."""
        m = _covering_model(12)
        m.seed = 7
        m.set_param("num_workers", 1)
        m.set_param("opt_switch_oracles", 0)
        m.set_param("verify", True)  # crash if a reported-feasible solution is infeasible
        r = m.solve()
        assert r.feasible
        sol = np.asarray(r.solution)
        assert sol.sum() >= 2  # covering constraint genuinely satisfied

    def test_switch_deterministic(self):
        """Fixed seed + single worker => identical objective regardless of the
        switch threshold value (determinism baseline, §8)."""
        def run(sw):
            m = _covering_model(12)
            m.seed = 99
            m.set_param("num_workers", 1)
            m.set_param("opt_switch_oracles", sw)
            return m.solve()

        assert run(0).objective == run(0).objective
        assert run(50).objective == run(50).objective

    def test_default_auto_resolves(self):
        """The -1 default resolves and a default solve still produces a feasible
        result on a covering instance (the auto int(0.1*M) switch point works)."""
        m = _covering_model(10)
        m.seed = 3
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        r = m.solve()
        assert r.feasible


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
