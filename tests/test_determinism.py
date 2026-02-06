"""Tests for deterministic solve behavior (Phase 4: Thread Isolation)."""

import os
import pytest
import numpy as np

# Skip if cbqs not importable (e.g., CI without build)
pytest.importorskip("cbqs")

from cbqs.Model import Model
from cbqs.Constants import MINIMIZE
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
        m1.general_greedy()
        result1 = m1.solve(M=100, stopping_time=5, num_workers=1)

        m2 = self.create_simple_model()
        m2.seed = 12345
        m2.general_greedy()
        result2 = m2.solve(M=100, stopping_time=5, num_workers=1)

        # Compare objective values (both via Model property and OptimizeResult)
        assert m1.objective_value == m2.objective_value, \
            f"Same seed should give same objective: {m1.objective_value} vs {m2.objective_value}"
        assert result1.objective == result2.objective, \
            f"Same seed should give same result.objective: {result1.objective} vs {result2.objective}"

    def test_seed_used_populated(self):
        """seed_used should be populated after solve()."""
        m = self.create_simple_model()
        # Don't set seed - let it auto-generate
        m.general_greedy()
        m.solve(M=50, stopping_time=2, num_workers=1)

        assert m.seed_used is not None, "seed_used should be populated after solve()"
        assert isinstance(m.seed_used, int), "seed_used should be an integer"

    def test_seed_used_matches_set_seed(self):
        """When seed is set, seed_used should match."""
        m = self.create_simple_model()
        m.seed = 42
        m.general_greedy()
        m.solve(M=50, stopping_time=2, num_workers=1)

        assert m.seed_used == 42, f"seed_used ({m.seed_used}) should match set seed (42)"

    def test_seed_used_enables_reproduction(self):
        """Using seed_used from auto-generated run should reproduce results."""
        # First run without setting seed
        m1 = self.create_simple_model()
        m1.general_greedy()
        m1.solve(M=100, stopping_time=5, num_workers=1)
        captured_seed = m1.seed_used

        # Second run using captured seed
        m2 = self.create_simple_model()
        m2.seed = captured_seed
        m2.general_greedy()
        m2.solve(M=100, stopping_time=5, num_workers=1)

        assert m1.objective_value == m2.objective_value, \
            f"Replaying with seed_used should reproduce: {m1.objective_value} vs {m2.objective_value}"

    def test_different_seeds_can_differ(self):
        """Different seeds may produce different results (not guaranteed but likely)."""
        results = []
        for seed in [1, 2, 3, 4, 5]:
            m = self.create_simple_model()
            m.seed = seed
            m.general_greedy()
            m.solve(M=100, stopping_time=2, num_workers=1)
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
        m.general_greedy()

        # Should not raise and return OptimizeResult
        result = m.solve(M=50, stopping_time=2, num_workers=num_threads)
        assert isinstance(result, OptimizeResult)
        assert result.objective is not None

    def test_env_var_threads(self):
        """CBQS_THREADS environment variable should be respected."""
        # This test verifies the env var is read (actual effect is in C code)
        original = os.environ.get("CBQS_THREADS")
        try:
            os.environ["CBQS_THREADS"] = "2"
            m = self.create_simple_model()
            m.general_greedy()
            # Should not raise
            m.solve(M=50, stopping_time=2, num_workers=2)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
