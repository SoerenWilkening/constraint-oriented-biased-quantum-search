"""
Stress tests for CBQS solver.

These tests run many iterations to surface memory issues that only
manifest after repeated operations. They are designed to catch:
- Memory leaks that accumulate over iterations
- Use-after-free that occasionally triggers
- Heap corruption that becomes visible after many allocations

Run with: pytest tests/test_stress.py -v --timeout=120
"""
import pytest

# Skip if cbqs not installed
cbqs = pytest.importorskip("cbqs")
from cbqs.Model import Model
from cbqs.Expression import Variable


class TestStressSolve:
    """Stress tests for solver memory stability."""

    @pytest.mark.timeout(60)
    def test_stress_solve_200_iterations(self):
        """Run 200 solve cycles to surface accumulated memory issues.

        This catches:
        - Leaks in preprocessing (tracked issue)
        - Use-after-free in accept_best_routine (fixed in Phase 2)
        - Expression memory corruption
        """
        for i in range(200):
            # Create fresh model each iteration
            m = Model()
            xs = m.add_variables(5)
            x = [xs[j] for j in range(5)]

            # Simple knapsack-like constraint
            m.add_constraint((x[0] + x[1] + x[2] + x[3] + x[4]) <= 3)

            # Objective: maximize weighted sum
            m.set_objective(x[0] + 2 * x[1] + 3 * x[2] + x[3] + x[4])

            # Close model before solving
            m.close()

            # Solve with short iteration limit
            try:
                m.solve(stopping_time=1, num_workers=1)
            except Exception as e:
                pytest.fail(f"Iteration {i} failed: {e}")

            # Clean up explicitly to help surface issues
            del m

            if (i + 1) % 50 == 0:
                print(f"  Completed {i + 1}/200 iterations")

    @pytest.mark.timeout(30)
    def test_stress_expression_creation(self):
        """Create many expressions to test Expression memory management."""
        for i in range(500):
            x = Variable(0)
            y = Variable(1)

            # Create expressions with various operations
            e1 = x + 3
            e2 = y + 5
            e3 = e1 + e2
            e4 = e3 * 2
            e5 = x + y + 10

            # Force evaluation
            list(e1)
            list(e2)
            list(e3)
            list(e4)
            list(e5)

            del e1, e2, e3, e4, e5

    @pytest.mark.timeout(30)
    def test_stress_expression_immutability(self):
        """Repeated immutable operations should not leak or corrupt."""
        x = Variable(0)
        base = x + 1

        for i in range(500):
            # Each iteration creates new expression, base unchanged
            result = base + i
            terms = list(result)
            assert [i] in terms or i == 0, f"Iteration {i}: constant {i} not found"

            # Verify base unchanged
            base_terms = list(base)
            assert base_terms == [[1], [1, 0]], f"Iteration {i}: base was mutated"

            del result

    @pytest.mark.timeout(60)
    def test_stress_model_creation_destruction(self):
        """Rapidly create and destroy models to test cleanup paths."""
        for i in range(300):
            m = Model()
            xs = m.add_variables(10)
            x = [xs[j] for j in range(10)]

            # Add several constraints
            m.add_constraint((x[0] + x[1]) <= 1)
            m.add_constraint((x[2] + x[3] + x[4]) <= 2)
            m.add_constraint((x[5] + x[6] + x[7] + x[8] + x[9]) <= 3)

            m.set_objective(x[0] + x[1] + x[2] + x[3] + x[4])

            # Close but don't solve - test compilation cleanup
            m.close()

            del m

            if (i + 1) % 100 == 0:
                print(f"  Completed {i + 1}/300 model creation cycles")
