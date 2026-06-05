"""branching_radius scale-invariant bias lever (bd 8an.1.6, M0f).

NORTHSTAR §4/§1.5: a target radius r sets bias = n/r - 2 so the realized Hamming
neighborhood is r at every n. branching_radius is a per-phase param that takes
precedence over branching_bias. (The full statistical scale-invariance
end-to-end test across n is M0g / 8an.1.7.)
"""
import numpy as np
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from cbqs.phase_params import radius_to_bias


def _model(n):
    m = Model()
    x = m.add_variables(n)
    m.set_objective(sum((i % 7 + 1) * x[i] for i in range(n)), sense=MAXIMIZE)
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n * 2)
    m.close()
    return m


class TestBranchingRadius:
    def test_param_settable_and_validated(self):
        m = _model(10)
        m.set_param("branching_radius", 4.0)
        assert m.get_param("branching_radius") == 4.0
        # per-phase variant
        m.set_param("opt_branching_radius", 2.0)
        assert m.get_param("opt_branching_radius") == 2.0
        # must be > 0
        with pytest.raises(ValueError, match="branching_radius must be > 0"):
            m.set_param("branching_radius", 0.0)

    def test_resolves_per_phase(self):
        """branching_radius appears in the per-phase resolved params with
        phase > unprefixed > default fallback."""
        m = _model(10)
        m.set_param("branching_radius", 5.0)
        m.set_param("opt_branching_radius", 2.0)
        resolved = m._resolve_phase_params()
        assert resolved["sat"]["branching_radius"] == 5.0       # unprefixed fallback
        assert resolved["opt_sat"]["branching_radius"] == 5.0   # unprefixed fallback
        assert resolved["opt"]["branching_radius"] == 2.0       # phase-specific override

    def test_radius_overrides_bias_in_solve(self):
        """Setting both branching_bias and branching_radius runs without error
        (radius takes precedence in propagation); the solve stays feasible."""
        m = _model(10)
        m.seed = 7
        m.set_param("num_workers", 1)
        m.set_param("branching_bias", 5.0)
        m.set_param("branching_radius", 3.0)  # -> bias = 10/3 - 2, overrides 5.0
        m.set_param("verify", True)
        r = m.solve()
        assert r.feasible

    def test_radius_bias_equivalence(self):
        """A model with branching_radius=r is equivalent to one with the
        explicit bias = n/r - 2 (fixed seed, single worker => identical objective).
        Pins that the harness applies exactly bias = radius_to_bias(n, r)."""
        n = 12
        r = 4.0

        def run_radius():
            m = _model(n)
            m.seed = 123
            m.set_param("num_workers", 1)
            m.set_param("branching_radius", r)
            return m.solve()

        def run_bias():
            m = _model(n)
            m.seed = 123
            m.set_param("num_workers", 1)
            m.set_param("branching_bias", radius_to_bias(n, r))
            return m.solve()

        assert run_radius().objective == run_bias().objective


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
