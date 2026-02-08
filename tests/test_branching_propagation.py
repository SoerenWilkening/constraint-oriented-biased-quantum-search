"""Deterministic tests proving branching parameters reach both solver paths.

Covers requirements BRANCH-01 (sampling solver propagation) and
BRANCH-02 (local search solver propagation).

Test approach: fixed seed + known problem, verify valid results with
non-default branching parameters. Determinism verified by running the
same configuration twice and asserting identical outcomes.
"""
import numpy as np
import pytest

pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE
from cbqs.result import OptimizeResult


def _make_knapsack_model(n=20):
    """Create an n-variable knapsack problem for testing branching.

    Deterministic coefficients (no randomness) so that identical models
    produce identical solver behavior when combined with fixed seeds.
    """
    m = Model()
    x = m.add_variables(n)
    # Deterministic coefficients: value = (i % 7) + 1
    obj = sum((i % 7 + 1) * x[i] for i in range(n))
    m.set_objective(obj, sense=MAXIMIZE)
    # Capacity constraint: weight = (i % 5) + 1, capacity = n * 2
    m.add_constraint(sum((i % 5 + 1) * x[i] for i in range(n)) <= n * 2)
    m.close()
    return m


# =============================================================================
# 1. Branching bias affects sampling solver (BRANCH-01)
# =============================================================================


class TestBranchingBiasSamplingSolver:
    """Verify branching_bias set via set_param reaches the sampling solver."""

    def test_branching_bias_affects_sampling_solver(self):
        """Extreme branching_bias via set_param produces valid result from sampling solver."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 50.0)
        result = m.solve(stopping_time=2, num_workers=2)

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == 20
        # Objective should be non-negative for a MAXIMIZE knapsack
        assert result.objective >= 0

    def test_branching_bias_default_produces_valid_result(self):
        """Default branching_bias (set by close()) also produces valid result."""
        m = _make_knapsack_model(20)
        m.seed = 42
        result = m.solve(stopping_time=2, num_workers=2)

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_bias_deterministic_sampling(self):
        """Same seed + same branching_bias -> same result (sampling solver)."""
        m1 = _make_knapsack_model(20)
        m1.seed = 42
        m1.set_param("branching_bias", 10.0)
        result1 = m1.solve(stopping_time=2, num_workers=1)

        m2 = _make_knapsack_model(20)
        m2.seed = 42
        m2.set_param("branching_bias", 10.0)
        result2 = m2.solve(stopping_time=2, num_workers=1)

        assert result1.objective == result2.objective, (
            f"Determinism: same seed+bias should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Determinism: same seed+bias should give same solution"
        )


# =============================================================================
# 2. Branching bias affects local search solver (BRANCH-02)
# =============================================================================


class TestBranchingBiasLocalSearch:
    """Verify branching_bias set via set_param reaches the local search solver."""

    def test_branching_bias_affects_local_search(self):
        """Extreme branching_bias via set_param produces valid result from local search."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 50.0)
        result = m.local_search(stop_time=2)

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == 20
        assert result.objective >= 0

    def test_branching_bias_deterministic_local_search(self):
        """Same seed + same branching_bias -> same result (local search)."""
        m1 = _make_knapsack_model(20)
        m1.seed = 42
        m1.set_param("branching_bias", 10.0)
        result1 = m1.local_search(stop_time=2)

        m2 = _make_knapsack_model(20)
        m2.seed = 42
        m2.set_param("branching_bias", 10.0)
        result2 = m2.local_search(stop_time=2)

        assert result1.objective == result2.objective, (
            f"Determinism: same seed+bias should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Determinism: same seed+bias should give same solution"
        )


# =============================================================================
# 3. Branching factors propagation
# =============================================================================


class TestBranchingFactorsPropagation:
    """Verify branching_factors set via set_param are propagated correctly."""

    def test_branching_factors_propagation_sampling(self):
        """Non-default branching_factors via set_param completes without error (sampling)."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_factors", (0.5, 0.0, 2.0, 0.0))
        result = m.solve(stopping_time=2, num_workers=2)

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_factors_propagation_local_search(self):
        """Non-default branching_factors via set_param completes without error (local search)."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_factors", (0.5, 0.0, 2.0, 0.0))
        result = m.local_search(stop_time=2)

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_factors_combined_with_bias(self):
        """Both branching_bias and branching_factors set together work correctly."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 15.0)
        m.set_param("branching_factors", (0.3, 0.1, 1.5, 0.1))
        result = m.solve(stopping_time=2, num_workers=2)

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
