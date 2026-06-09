"""Tests for deterministic solve behavior (Phase 4: Thread Isolation)."""

import os
import pytest
import numpy as np

# Skip if cbqs not importable (e.g., CI without build)
pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MINIMIZE, MAXIMIZE
from cbqs.result import OptimizeResult


class TestDeterminism:
    """Verify that same seed + same conditions = same result."""

    def create_simple_model(self):
        """Create a small reproducible optimization problem."""
        m = Model()
        x = m.add_variables(10)  # 10 binary variables

        # Simple objective: minimize sum
        obj = sum(x[i] for i in range(10))
        m.set_objective(obj, MINIMIZE)

        # Simple constraint: at most 5 variables can be 1
        m.add_constraint(sum(x[i] for i in range(10)) <= 5)

        m.close()
        return m

    def test_same_seed_same_result(self):
        """Same seed should produce identical results."""
        m1 = self.create_simple_model()
        m1.seed = 12345
        m1.set_param('M', 100)
        m1.set_param('stopping_time', 5)
        m1.set_param('num_workers', 1)
        m1.general_greedy()
        result1 = m1.solve()

        m2 = self.create_simple_model()
        m2.seed = 12345
        m2.set_param('M', 100)
        m2.set_param('stopping_time', 5)
        m2.set_param('num_workers', 1)
        m2.general_greedy()
        result2 = m2.solve()

        # Compare objective values (both via Model property and OptimizeResult)
        assert m1.objective_value == m2.objective_value, \
            f"Same seed should give same objective: {m1.objective_value} vs {m2.objective_value}"
        assert result1.objective == result2.objective, \
            f"Same seed should give same result.objective: {result1.objective} vs {result2.objective}"

    def test_seed_used_populated(self):
        """seed_used should be populated after solve()."""
        m = self.create_simple_model()
        # Don't set seed - let it auto-generate
        m.set_param('M', 50)
        m.set_param('stopping_time', 2)
        m.set_param('num_workers', 1)
        m.general_greedy()
        m.solve()

        assert m.seed_used is not None, "seed_used should be populated after solve()"
        assert isinstance(m.seed_used, int), "seed_used should be an integer"

    def test_seed_used_matches_set_seed(self):
        """When seed is set, seed_used should match."""
        m = self.create_simple_model()
        m.seed = 42
        m.set_param('M', 50)
        m.set_param('stopping_time', 2)
        m.set_param('num_workers', 1)
        m.general_greedy()
        m.solve()

        assert m.seed_used == 42, f"seed_used ({m.seed_used}) should match set seed (42)"

    def test_seed_used_enables_reproduction(self):
        """Using seed_used from auto-generated run should reproduce results."""
        # First run without setting seed
        m1 = self.create_simple_model()
        m1.set_param('M', 100)
        m1.set_param('stopping_time', 5)
        m1.set_param('num_workers', 1)
        m1.general_greedy()
        m1.solve()
        captured_seed = m1.seed_used

        # Second run using captured seed
        m2 = self.create_simple_model()
        m2.seed = captured_seed
        m2.set_param('M', 100)
        m2.set_param('stopping_time', 5)
        m2.set_param('num_workers', 1)
        m2.general_greedy()
        m2.solve()

        assert m1.objective_value == m2.objective_value, \
            f"Replaying with seed_used should reproduce: {m1.objective_value} vs {m2.objective_value}"

    def test_different_seeds_can_differ(self):
        """Different seeds may produce different results (not guaranteed but likely)."""
        results = []
        for seed in [1, 2, 3, 4, 5]:
            m = self.create_simple_model()
            m.seed = seed
            m.set_param('M', 100)
            m.set_param('stopping_time', 2)
            m.set_param('num_workers', 1)
            m.general_greedy()
            m.solve()
            results.append(m.objective_value)

        # At least some variation expected (not a hard requirement)
        # This test documents behavior rather than enforcing it
        unique_results = len(set(results))
        print(f"Unique results from 5 seeds: {unique_results}")

    @pytest.mark.parametrize("num_threads", [1, 2, 4])
    def test_num_threads_property(self, num_threads):
        """num_threads property can be set and affects solve."""
        m = self.create_simple_model()
        m.num_threads = num_threads
        m.seed = 42  # Fixed seed for reproducibility
        m.set_param('M', 50)
        m.set_param('stopping_time', 2)
        m.set_param('num_workers', num_threads)
        m.general_greedy()

        # Should not raise and return OptimizeResult
        result = m.solve()
        assert isinstance(result, OptimizeResult)
        assert result.objective is not None

    def test_env_var_threads(self):
        """CBQS_THREADS environment variable should be respected."""
        # This test verifies the env var is read (actual effect is in C code)
        original = os.environ.get("CBQS_THREADS")
        try:
            os.environ["CBQS_THREADS"] = "2"
            m = self.create_simple_model()
            m.set_param('M', 50)
            m.set_param('stopping_time', 2)
            m.set_param('num_workers', 2)
            m.general_greedy()
            # Should not raise
            m.solve()
        finally:
            if original is None:
                os.environ.pop("CBQS_THREADS", None)
            else:
                os.environ["CBQS_THREADS"] = original


class TestSeedValidation:
    """Tests for seed and num_threads property validation."""

    def test_seed_accepts_int(self):
        """seed property should accept integers."""
        m = Model()
        m.seed = 12345
        assert m.seed == 12345

    def test_seed_accepts_none(self):
        """seed property should accept None (default)."""
        m = Model()
        m.seed = None
        assert m.seed is None

    def test_seed_rejects_float(self):
        """seed property should reject float values."""
        m = Model()
        with pytest.raises(TypeError, match="seed must be an integer"):
            m.seed = 3.14

    def test_seed_rejects_string(self):
        """seed property should reject string values."""
        m = Model()
        with pytest.raises(TypeError, match="seed must be an integer"):
            m.seed = "12345"

    def test_num_threads_accepts_positive_int(self):
        """num_threads property should accept positive integers."""
        m = Model()
        m.num_threads = 4
        assert m.num_threads == 4

    def test_num_threads_accepts_none(self):
        """num_threads property should accept None (default)."""
        m = Model()
        m.num_threads = None
        assert m.num_threads is None

    def test_num_threads_rejects_zero(self):
        """num_threads property should reject zero."""
        m = Model()
        with pytest.raises(ValueError, match="num_threads must be a positive integer"):
            m.num_threads = 0

    def test_num_threads_rejects_negative(self):
        """num_threads property should reject negative values."""
        m = Model()
        with pytest.raises(ValueError, match="num_threads must be a positive integer"):
            m.num_threads = -1

    def test_num_threads_rejects_float(self):
        """num_threads property should reject float values."""
        m = Model()
        with pytest.raises(ValueError, match="num_threads must be a positive integer"):
            m.num_threads = 2.5


def _make_knapsack_model(n=20):
    """Create an n-variable knapsack problem for determinism testing.

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


class TestBranchingWeightsDeterminism:
    """Verify deterministic behavior survives across separate model lifecycles.

    These tests create two completely independent model instances with
    identical configuration and verify they produce identical results.
    """

    def test_cross_lifecycle_determinism_with_weights(self):
        """Two independent models with same seed + branching_weights produce identical results."""
        n = 20
        weights = [float(i % 5 + 1) for i in range(n)]

        # First lifecycle
        m1 = _make_knapsack_model(n)
        m1.seed = 42
        m1.set_param("branching_weights", weights)
        m1.set_param("stopping_time", 3)
        m1.set_param("num_workers", 1)
        result1 = m1.solve()

        # Second lifecycle -- completely new model
        m2 = _make_knapsack_model(n)
        m2.seed = 42
        m2.set_param("branching_weights", weights)
        m2.set_param("stopping_time", 3)
        m2.set_param("num_workers", 1)
        result2 = m2.solve()

        assert isinstance(result1, OptimizeResult)
        assert isinstance(result2, OptimizeResult)
        assert result1.objective == result2.objective, (
            f"Cross-lifecycle determinism: same seed+weights should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Cross-lifecycle determinism: same seed+weights should give same solution"
        )

    def test_cross_lifecycle_determinism_with_factors(self):
        """Two independent models with same seed + factor params produce identical results."""
        n = 20

        # First lifecycle
        m1 = _make_knapsack_model(n)
        m1.seed = 42
        m1.set_param("branching_factor", 0.5)
        m1.set_param("bias_factor", 2.0)
        m1.set_param("look_ahead_factor", 0.1)
        m1.set_param("branching_bias", 8.0)
        m1.set_param("stopping_time", 3)
        m1.set_param("num_workers", 1)
        result1 = m1.solve()

        # Second lifecycle -- completely new model
        m2 = _make_knapsack_model(n)
        m2.seed = 42
        m2.set_param("branching_factor", 0.5)
        m2.set_param("bias_factor", 2.0)
        m2.set_param("look_ahead_factor", 0.1)
        m2.set_param("branching_bias", 8.0)
        m2.set_param("stopping_time", 3)
        m2.set_param("num_workers", 1)
        result2 = m2.solve()

        assert isinstance(result1, OptimizeResult)
        assert isinstance(result2, OptimizeResult)
        assert result1.objective == result2.objective, (
            f"Cross-lifecycle determinism: same seed+factors should give same objective: "
            f"{result1.objective} vs {result2.objective}"
        )
        np.testing.assert_array_equal(
            result1.solution, result2.solution,
            err_msg="Cross-lifecycle determinism: same seed+factors should give same solution"
        )


class TestPerWorkerPRNGDecorrelation:
    """M0c (bd 8an.1.3): per-worker PRNG stream decorrelation.

    Before the fix, every worker seeded prng_seed_thread(master, 0), so under a
    fixed seed all workers ran the identical trajectory -- portfolio collapse
    (CLAUDE.md §5). Each worker now jumps the xoshiro stream by its worker_id,
    so distinct workers diverge while worker_id=0 reproduces the legacy stream
    (single-worker determinism, §8, is preserved).

    These tests drive run_sampling directly with explicit worker_id values. The
    incumbent-history callback only fires when a worker improves the *shared*
    model global_opt (SearchLib.c:193-197), so each trajectory is measured after
    reset() + manual_initial(), which rebuilds global_opt at the worst value
    while keeping the C-level budget (mod.M, set by the prior solve()) intact.
    Thus the only thing that varies between measurements is worker_id.
    """

    def _prepared_model(self, n=50, seed=12345, M=200, stopping_time=5):
        m = _make_knapsack_model(n)
        m.seed = seed
        m.set_param("M", M)
        m.set_param("stopping_time", stopping_time)
        m.set_param("num_workers", 1)
        # solve() once to populate the C model_t budget/phase fields
        # (mod.M, max_delta, stopping_time, ...) that run_sampling reads.
        m.solve()
        return m

    def _trajectory(self, m, worker_id):
        from cbqs.SearchLib import run_sampling
        # Fresh, un-shadowed global_opt for this measurement; mod.M is preserved.
        m.reset()
        m.manual_initial(0, [0] * m.n)
        r = run_sampling(m, None, [1], True, 0.0, worker_id)
        # r = (cur_sol, qtg, feasible, arr, t_total, incumb, history, prep, branch_diag, worker_runtime_s)
        history = r[6]
        return tuple(value for (value, _elapsed) in history)

    def test_worker0_trajectory_is_reproducible(self):
        """worker_id=0 reproduces an identical trajectory (legacy stream stable)."""
        m = self._prepared_model()
        h0a = self._trajectory(m, 0)
        h0b = self._trajectory(m, 0)
        assert len(h0a) > 1, "expected a non-trivial multi-step trajectory to compare"
        assert h0a == h0b, (
            "worker_id=0 must reproduce the same trajectory across runs "
            "(single-worker determinism preserved)"
        )

    def test_two_workers_have_distinct_trajectories(self):
        """Fixed seed, workers 0 and 1 explore divergent trajectories."""
        m = self._prepared_model()
        h0 = self._trajectory(m, 0)
        h1 = self._trajectory(m, 1)
        assert len(h0) > 1, "expected a non-trivial trajectory"
        assert h0 != h1, (
            "worker_id=0 and worker_id=1 must diverge under a fixed seed "
            "(was: every worker seeded prng_seed_thread(master, 0))"
        )

    def test_fixed_seed_workers_not_collapsed(self):
        """A fixed-seed portfolio must not collapse onto one trajectory."""
        m = self._prepared_model()
        trajectories = {self._trajectory(m, w) for w in range(4)}
        assert len(trajectories) > 1, (
            "fixed-seed workers all share one trajectory -- portfolio collapse"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
