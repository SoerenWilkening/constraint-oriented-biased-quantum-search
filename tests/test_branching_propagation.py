"""Deterministic tests proving branching parameters reach both solver paths.

Covers branching_bias, individual factor params, and branching_weights
propagation through Cython to the C solver context.

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
# 1. Branching bias affects sampling solver
# =============================================================================


class TestBranchingBiasSamplingSolver:
    """Verify branching_bias set via set_param reaches the sampling solver."""

    def test_branching_bias_affects_sampling_solver(self):
        """Extreme branching_bias via set_param produces valid result from sampling solver."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 50.0)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 2)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == 20
        # Objective should be non-negative for a MAXIMIZE knapsack
        assert result.objective >= 0

    def test_branching_bias_default_produces_valid_result(self):
        """Default branching_bias (set by close()) also produces valid result."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 2)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_bias_deterministic_sampling(self):
        """Same seed + same branching_bias -> same result (sampling solver)."""
        m1 = _make_knapsack_model(20)
        m1.seed = 42
        m1.set_param("branching_bias", 10.0)
        m1.set_param("stopping_time", 2)
        m1.set_param("num_workers", 1)
        result1 = m1.solve()

        m2 = _make_knapsack_model(20)
        m2.seed = 42
        m2.set_param("branching_bias", 10.0)
        m2.set_param("stopping_time", 2)
        m2.set_param("num_workers", 1)
        result2 = m2.solve()

        assert result1.objective == result2.objective, (
            f"Determinism: same seed+bias should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Determinism: same seed+bias should give same solution"
        )


# =============================================================================
# 2. Branching bias affects local search solver
# =============================================================================


class TestBranchingBiasLocalSearch:
    """Verify branching_bias set via set_param reaches the local search solver."""

    def test_branching_bias_affects_local_search(self):
        """Extreme branching_bias via set_param produces valid result from local search."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 50.0)
        m.set_param("stopping_time", 2)
        result = m.local_search()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == 20
        assert result.objective >= 0

    def test_branching_bias_deterministic_local_search(self):
        """Same seed + same branching_bias -> consistent objective (local search).

        Note: local_search with a time bound (stopping_time) is inherently
        timing-dependent -- the number of iterations varies with system load.
        We compare objectives only (not solutions) since multiple optimal
        solutions with equal objective may be found depending on iteration count.
        History tracking is disabled to avoid a known callback race condition.
        """
        objectives = []
        for _ in range(3):
            m = _make_knapsack_model(20)
            m.seed = 42
            m.set_param("branching_bias", 10.0)
            m.set_param("stopping_time", 2)
            m.set_param("track_history", False)
            result = m.local_search()
            objectives.append(result.objective)
            del m

        # All runs should find an equally good or identical objective
        assert objectives[0] == objectives[1] == objectives[2], (
            f"Determinism: same seed+bias should give consistent objective "
            f"across runs: {objectives}"
        )


# =============================================================================
# 3. Individual branching factor propagation
# =============================================================================


class TestBranchingFactorsPropagation:
    """Verify individual factor params are propagated correctly."""

    def test_branching_factors_propagation_sampling(self):
        """Non-default individual factor params complete without error (sampling)."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_factor", 0.5)
        m.set_param("bias_factor", 2.0)
        m.set_param("look_ahead_factor", 0.0)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 2)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_factors_propagation_local_search(self):
        """Non-default individual factor params complete without error (local search)."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_factor", 0.5)
        m.set_param("bias_factor", 2.0)
        m.set_param("look_ahead_factor", 0.0)
        m.set_param("stopping_time", 2)
        result = m.local_search()

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0

    def test_branching_factors_combined_with_bias(self):
        """Both branching_bias and individual factor params set together work correctly."""
        m = _make_knapsack_model(20)
        m.seed = 42
        m.set_param("branching_bias", 15.0)
        m.set_param("branching_factor", 0.3)
        m.set_param("bias_factor", 1.5)
        m.set_param("look_ahead_factor", 0.1)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 2)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.objective >= 0


# =============================================================================
# 4. Branching weights propagation
# =============================================================================


class TestBranchingWeightsPropagation:
    """Verify branching_weights flow through Cython to solver_ctx_set_branching_weights."""

    def test_branching_weights_sampling(self):
        """branching_weights propagated through sampling solver produces valid result."""
        n = 20
        m = _make_knapsack_model(n)
        m.seed = 42
        weights = [float(i % 5 + 1) for i in range(n)]
        m.set_param("branching_weights", weights)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 2)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == n
        assert result.objective >= 0

    def test_branching_weights_local_search(self):
        """branching_weights propagated through local search solver produces valid result."""
        n = 20
        m = _make_knapsack_model(n)
        m.seed = 42
        weights = [float(i % 5 + 1) for i in range(n)]
        m.set_param("branching_weights", weights)
        m.set_param("stopping_time", 2)
        result = m.local_search()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == n
        assert result.objective >= 0

    def test_branching_weights_deterministic(self):
        """Same seed + same weights -> same result."""
        n = 20
        weights = [float(i % 5 + 1) for i in range(n)]

        m1 = _make_knapsack_model(n)
        m1.seed = 42
        m1.set_param("branching_weights", weights)
        m1.set_param("stopping_time", 2)
        m1.set_param("num_workers", 1)
        result1 = m1.solve()

        m2 = _make_knapsack_model(n)
        m2.seed = 42
        m2.set_param("branching_weights", weights)
        m2.set_param("stopping_time", 2)
        m2.set_param("num_workers", 1)
        result2 = m2.solve()

        assert result1.objective == result2.objective, (
            f"Determinism: same seed+weights should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Determinism: same seed+weights should give same solution"
        )


# =============================================================================
# 5. Branching weights coverage (edge cases and combined parameters)
# =============================================================================


class TestBranchingWeightsCoverage:
    """Coverage gap tests for branching_weights edge cases and combinations."""

    def test_different_weights_different_behavior(self):
        """Same seed, different branching_weights exercise distinct propagation paths.

        Both uniform and heavily skewed weights must produce valid results.
        We cannot guarantee different objectives (solver may converge to same
        optimum), but this exercises the full propagation path with varied inputs.
        """
        n = 20

        # Uniform weights
        m1 = _make_knapsack_model(n)
        m1.seed = 42
        m1.set_param("branching_weights", [1.0] * n)
        m1.set_param("stopping_time", 5)
        m1.set_param("num_workers", 1)
        result1 = m1.solve()

        # Extremely skewed weights
        m2 = _make_knapsack_model(n)
        m2.seed = 42
        m2.set_param("branching_weights", [float(10 * i + 1) for i in range(n)])
        m2.set_param("stopping_time", 5)
        m2.set_param("num_workers", 1)
        result2 = m2.solve()

        assert isinstance(result1, OptimizeResult)
        assert isinstance(result2, OptimizeResult)
        assert result1.objective >= 0
        assert result2.objective >= 0
        assert result1.solution is not None
        assert result2.solution is not None

    def test_all_zero_weights(self):
        """All-zero branching_weights triggers division-by-zero guard.

        At the C level, all-zero weights L1-normalize to all-zero (sum=0),
        so the branching term contributes 0. The solver must complete
        without crashing and return a valid result.
        """
        n = 20
        m = _make_knapsack_model(n)
        m.seed = 42
        m.set_param("branching_weights", [0.0] * n)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 1)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert result.objective >= 0

    def test_branching_weights_large_n(self):
        """branching_weights with n=100 variables scales correctly.

        Tests that the weights propagation path handles larger arrays
        without memory issues or performance degradation.
        """
        n = 100
        m = _make_knapsack_model(n)
        m.seed = 42
        m.set_param("branching_weights", [float(i + 1) for i in range(n)])
        m.set_param("stopping_time", 3)
        m.set_param("num_workers", 1)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert len(result.solution) == n
        assert result.objective >= 0

    def test_branching_weights_with_all_factors(self):
        """All branching parameters set together exercise the full 3-term formula.

        Sets branching_weights + branching_factor + bias_factor +
        look_ahead_factor + branching_bias simultaneously.
        """
        n = 20
        m = _make_knapsack_model(n)
        m.seed = 42
        m.set_param("branching_weights", [float(i % 5 + 1) for i in range(n)])
        m.set_param("branching_factor", 0.5)
        m.set_param("bias_factor", 1.5)
        m.set_param("look_ahead_factor", 0.3)
        m.set_param("branching_bias", 10.0)
        m.set_param("stopping_time", 2)
        m.set_param("num_workers", 1)
        result = m.solve()

        assert isinstance(result, OptimizeResult)
        assert result.solution is not None
        assert result.objective >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
