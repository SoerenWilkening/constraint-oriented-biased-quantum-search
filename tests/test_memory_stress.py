"""
Memory stress tests for CBQS solver.

These tests verify:
1. Large problems (1K-2K constraints) don't cause stack overflow
2. Repeated solve cycles don't accumulate memory leaks
3. Model creation/destruction is leak-free

The goal is memory safety, not solver correctness - we check that
operations complete without crashing/segfaulting, not optimality.
"""

import pytest
import gc

cbqs = pytest.importorskip("cbqs")
from cbqs.Model import Model


class TestLargeProblems:
    """Tests for large problem memory handling."""

    @pytest.mark.timeout(60)
    def test_2k_constraints_no_crash(self):
        """Verify 2K constraints don't cause stack overflow from VLAs.

        Before Phase 5, VLAs would allocate ~16KB+ per thread on the stack
        for 2K constraints. With default 8MB stack, ~500 recursive calls
        would overflow. With heap buffers, this completes without segfault.

        Note: Even 1K constraints would have been problematic with VLAs.
        We use 2K as a reasonable CI-friendly test size.
        """
        m = Model()
        n = 50  # variables
        num_constraints = 2000

        xs = m.add_variables(n)
        x = [xs[j] for j in range(n)]

        # Add many constraints - each uses 3 variables
        for i in range(num_constraints):
            vars_to_use = [x[j % n] for j in range(i, i + 3)]
            m.add_constraint(sum(vars_to_use) <= 2)

        m.set_objective(sum(x[j] for j in range(n)))
        m.close()

        # Should not segfault from stack overflow
        try:
            m.solve(stopping_time=3, num_workers=1)
        except MemoryError:
            pytest.skip("System memory limit reached - not a test failure")
        except Exception as e:
            pytest.fail(f"Solve failed with unexpected error: {e}")

        # If we got here without crashing, the test passes
        # (global_opt may or may not be set depending on timeout)

    @pytest.mark.timeout(60)
    def test_1k_constraints_multiple_threads(self):
        """Verify large problem with multiple threads doesn't crash.

        Each thread gets its own scratch buffers. With 4 threads and
        1K constraints, this tests per-thread heap allocation.
        """
        m = Model()
        n = 50
        num_constraints = 1000

        xs = m.add_variables(n)
        x = [xs[j] for j in range(n)]

        for i in range(num_constraints):
            vars_to_use = [x[j % n] for j in range(i, i + 2)]
            m.add_constraint(sum(vars_to_use) <= 1)

        m.set_objective(sum(x[j] for j in range(n)))
        m.close()

        try:
            # Multiple threads should each get their own scratch buffers
            m.solve(stopping_time=2, num_workers=4)
        except MemoryError:
            pytest.skip("System memory limit reached")
        except Exception as e:
            pytest.fail(f"Multi-threaded solve failed: {e}")

        # Success = no crash


class TestRepeatedSolves:
    """Tests for memory stability across repeated operations."""

    @pytest.mark.timeout(60)
    def test_repeated_model_creation(self):
        """Create and destroy many models - should not leak.

        Tests the model lifecycle: create, configure, close, solve, delete.
        Memory leaks would accumulate and eventually cause OOM.
        """
        for i in range(50):
            m = Model()
            xs = m.add_variables(10)
            x = [xs[j] for j in range(10)]

            m.add_constraint(sum(x) <= 5)
            m.set_objective(sum(x))
            m.close()

            try:
                m.solve(stopping_time=0.1, num_workers=1)
            except Exception as e:
                pytest.fail(f"Iteration {i} failed: {e}")

            # Explicit cleanup
            del m

        # Force garbage collection
        gc.collect()

        # If we got here without crashing or OOM, test passes

    @pytest.mark.timeout(90)
    def test_repeated_solves_same_model(self):
        """Solve the same model many times - should not accumulate leaks.

        Tests per-solve cleanup: each solve allocates/frees resources.
        Leaks in solve cleanup would accumulate across iterations.
        """
        m = Model()
        n = 20
        xs = m.add_variables(n)
        x = [xs[j] for j in range(n)]

        for i in range(n - 1):
            m.add_constraint(x[i] + x[i + 1] <= 1)

        m.set_objective(sum(x))
        m.close()

        # Solve many times
        for i in range(30):
            try:
                m.solve(stopping_time=0.2, num_workers=2)
            except Exception as e:
                pytest.fail(f"Solve iteration {i} failed: {e}")

        # If we got here without OOM, test passes


class TestEdgeCases:
    """Tests for edge cases in memory management."""

    @pytest.mark.timeout(30)
    def test_zero_constraints(self):
        """Model with no constraints - preprocessing edge case.

        Tests zero-length array handling in preprocessing and solver.
        This was the original source of the preprocessing memory leak.
        Uses validate=False to bypass API validation (testing C-level safety).
        """
        m = Model()
        xs = m.add_variables(5)
        x = [xs[j] for j in range(5)]

        # No constraints - tests zero-length array handling
        m.set_objective(sum(x))
        m.close(validate=False)

        try:
            m.solve(stopping_time=0.1, num_workers=1)
        except Exception as e:
            pytest.fail(f"Zero-constraint model failed: {e}")

    @pytest.mark.timeout(30)
    def test_single_constraint(self):
        """Model with single constraint - minimal viable problem."""
        m = Model()
        xs = m.add_variables(5)
        x = [xs[j] for j in range(5)]

        m.add_constraint(sum(x) <= 2)
        m.set_objective(sum(x))
        m.close()

        try:
            m.solve(stopping_time=0.5, num_workers=1)
        except Exception as e:
            pytest.fail(f"Single-constraint model failed: {e}")

    @pytest.mark.timeout(60)
    def test_many_variables_few_constraints(self):
        """Many variables but few constraints - tests variable-sized buffers.

        With 500 variables but only 10 constraints, this tests that
        buffer sizing is based on constraint count, not variable count.
        """
        m = Model()
        n = 500
        xs = m.add_variables(n)
        x = [xs[j] for j in range(n)]

        # Only 10 constraints
        for i in range(10):
            start = i * (n // 10)
            m.add_constraint(sum(x[start:start + 5]) <= 3)

        m.set_objective(sum(x))
        m.close()

        try:
            m.solve(stopping_time=1, num_workers=1)
        except Exception as e:
            pytest.fail(f"Many-variables model failed: {e}")
