"""
Tests for validate=False fast path that skips merge() and
_merge_duplicate_variable_terms() in set_objective and add_constraint.

Verifies that matmul-produced (clean) expressions work correctly without
the merge overhead, and that validate=True still merges as before.
"""
import warnings

import numpy as np
import pytest
from cbqs.Model import Model
from cbqs.Expression import Expression
from cbqs.Constants import MAXIMIZE, MINIMIZE


class TestSetObjectiveValidateFalseSkipsMerge:
    """set_objective(validate=False) skips merge() and dedup."""

    def test_validate_false_no_duplicate_warning(self):
        """validate=False skips dedup so no warning for duplicate terms."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = 3 * x[0] + 5 * x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MAXIMIZE, validate=False)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) == 0

    def test_validate_true_emits_duplicate_warning(self):
        """validate=True emits warning for duplicate terms (merge runs)."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = 3 * x[0] + 5 * x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MAXIMIZE, validate=True)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) >= 1

    def test_validate_false_clean_expr_produces_correct_model(self):
        """A clean expression with validate=False produces a solvable model."""
        m = Model()
        xs = m.add_variables(4)
        x = [xs[i] for i in range(4)]
        m.set_objective(x[0] + x[1] + x[2] + x[3], MAXIMIZE, validate=False)
        m.add_constraint((x[0] + x[1] + x[2] + x[3]) <= 2, validate=False)
        m.close()
        m.set_param('num_workers', 1)
        m.set_param('stopping_time', 1)
        m.solve()
        assert m.objective_value >= 0

    def test_validate_false_still_checks_sense(self):
        """validate=False still rejects invalid sense values."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = x[0] + x[1]
        with pytest.raises(TypeError, match="Invalid sense"):
            m.set_objective(expr, sense=999, validate=False)


class TestAddConstraintValidateFalseSkipsMerge:
    """add_constraint(validate=False) skips merge() and dedup."""

    def test_validate_false_no_duplicate_warning(self):
        """validate=False skips dedup so no warning for duplicate terms."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = 3 * x[0] + 5 * x[0]
        constraint = expr <= 10
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.add_constraint(constraint, validate=False)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) == 0

    def test_validate_true_emits_duplicate_warning(self):
        """validate=True emits warning for duplicate terms (merge runs)."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = 3 * x[0] + 5 * x[0]
        constraint = expr <= 10
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.add_constraint(constraint, validate=True)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) >= 1

    def test_validate_false_constraint_added(self):
        """validate=False still adds the constraint to the model."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        constraint = (x[0] + x[1] + x[2]) <= 2
        m.add_constraint(constraint, validate=False)
        assert len(m.con_expr) == 1


class TestMatmulExpressionClean:
    """Matmul-produced expressions work correctly with validate=False."""

    def test_matmul_objective_validate_false(self):
        """Matrix-variable matmul objective works with validate=False."""
        m = Model()
        x = m.add_variables(3)
        A = np.array([[1, 0, 0], [2, 3, 0], [4, 5, 6]], dtype=np.int64)
        m.set_objective(x @ (A @ x), sense=MAXIMIZE, validate=False)
        m.add_constraint(x @ (np.eye(3, dtype=np.int64) @ x) <= 2)
        m.close()
        m.set_param('num_workers', 1)
        m.set_param('stopping_time', 1)
        m.solve()
        assert m.objective_value >= 0

    def test_matmul_constraint_validate_false(self):
        """Matrix-variable matmul constraint works with validate=False."""
        m = Model()
        x = m.add_variables(3)
        v = [x[i] for i in range(3)]
        A = np.array([[1, 0, 0], [2, 3, 0], [4, 5, 6]], dtype=np.int64)
        m.set_objective(v[0] + v[1] + v[2], MAXIMIZE)
        m.add_constraint(x @ (A @ x) <= 10, validate=False)
        m.close()
        m.set_param('num_workers', 1)
        m.set_param('stopping_time', 1)
        m.solve()
        assert m.objective_value >= 0

    def test_full_model_all_validate_false(self):
        """Complete model with all validate=False calls solves correctly."""
        n = 5
        m = Model()
        x = m.add_variables(n)

        A = np.tril(np.ones((n, n), dtype=np.int64))
        m.set_objective(x @ (A @ x), sense=MAXIMIZE, validate=False)
        m.add_constraint(x @ (A @ x) <= n, validate=False)
        m.close()
        m.set_param('num_workers', 1)
        m.set_param('stopping_time', 1)
        m.solve()
        assert m.objective_value >= 0
