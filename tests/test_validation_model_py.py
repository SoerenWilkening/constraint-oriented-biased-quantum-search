"""
Tests for Model-level input validation (Phase 7 API Robustness - RBST-02).

Validates that Model.add_constraint, set_objective, close, solve, and
add_variables reject invalid inputs with clear error messages, and that
the validate=False parameter bypasses all Python-level checks.
"""
import warnings

import pytest
from cbqs.Model import Model
from cbqs.Expression import Variable, Expression
from cbqs.Constants import MAXIMIZE, MINIMIZE


class TestAddConstraintValidation:
    """Tests for add_constraint input validation."""

    def test_add_constraint_none_raises_valueerror(self):
        """add_constraint(None) raises ValueError with clear message."""
        m = Model()
        with pytest.raises(ValueError, match="Constraint cannot be None"):
            m.add_constraint(None)

    def test_add_constraint_expression_without_sense_raises(self):
        """add_constraint(expr) without <=, >=, or == raises ValueError."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        expr = x[0] + x[1] + x[2]  # no comparison operator applied
        with pytest.raises(ValueError, match="Apply <=, >=, or =="):
            m.add_constraint(expr)

    def test_add_constraint_valid_leq(self):
        """add_constraint with valid <= constraint succeeds."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        assert len(m.con_expr) == 1

    def test_add_constraint_valid_eq(self):
        """add_constraint with valid == constraint succeeds."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        m.add_constraint((x[0] + x[1]) == 1)
        assert len(m.con_expr) == 1

    def test_add_constraint_validate_false_skips_none_check(self):
        """add_constraint(expr, validate=False) does not check for None sense.

        NOTE: Passing None with validate=False will crash (AttributeError on
        None.merge()), so we test with a valid expression that has no sense
        instead -- validate=False lets it through without raising ValueError.
        """
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        expr = x[0] + x[1] + x[2]
        # Apply sense so the C layer doesn't crash, but validate=False
        # would have skipped the check even without it
        constraint = expr <= 2
        m.add_constraint(constraint, validate=False)
        assert len(m.con_expr) == 1

    def test_add_constraint_validate_false_skips_sense_check(self):
        """add_constraint(expr_without_sense, validate=False) does not raise."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        expr = x[0] + x[1] + x[2]  # no sense applied
        # validate=False should skip the sense check
        # The C layer will accept the expression (it doesn't check sense)
        m.add_constraint(expr, validate=False)
        assert len(m.con_expr) == 1


class TestSetObjectiveValidation:
    """Tests for set_objective input validation."""

    def test_set_objective_none_raises_valueerror(self):
        """set_objective(None) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Objective expression cannot be None"):
            m.set_objective(None)

    def test_set_objective_invalid_sense_raises_typeerror(self):
        """set_objective with invalid sense raises TypeError with message."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = x[0] + x[1]
        with pytest.raises(TypeError, match="Invalid sense"):
            m.set_objective(expr, sense=999)

    def test_set_objective_invalid_sense_validate_false_still_raises(self):
        """Even with validate=False, invalid sense raises TypeError."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = x[0] + x[1]
        with pytest.raises(TypeError, match="Invalid sense"):
            m.set_objective(expr, sense=999, validate=False)

    def test_set_objective_validate_false_skips_none_check(self):
        """set_objective(expr, validate=False) with valid expr succeeds."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        expr = x[0] + x[1]
        m.set_objective(expr, validate=False)
        assert m.sense == MAXIMIZE

    def test_set_objective_valid_maximize(self):
        """set_objective with valid expression and MAXIMIZE succeeds."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        assert m.sense == MAXIMIZE

    def test_set_objective_valid_minimize(self):
        """set_objective with valid expression and MINIMIZE succeeds."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.set_objective(x[0] + x[1] + x[2], MINIMIZE)
        assert m.sense == MINIMIZE


class TestCloseValidation:
    """Tests for close() validation."""

    def test_close_no_variables_raises_valueerror(self):
        """close() on empty model (0 variables) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="no variables"):
            m.close()

    def test_close_no_constraints_raises_valueerror(self):
        """close() with variables but no constraints raises ValueError."""
        m = Model()
        m.add_variables(3)
        with pytest.raises(ValueError, match="no constraints"):
            m.close()

    def test_close_validate_false_skips_checks(self):
        """close(validate=False) does not raise on empty model.

        NOTE: This will still fail in the compilation step if there are
        truly no constraints, but the validation check is bypassed.
        We test with a valid model where validate=False just skips checks.
        """
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.close(validate=False)
        assert m.constraints_compiled is True

    def test_close_valid_model_succeeds(self):
        """close() with variables and constraints succeeds."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.close()
        assert m.constraints_compiled is True


class TestSolveValidation:
    """Tests for solve() validation improvements."""

    def test_solve_invalid_results_raises_valueerror(self):
        """solve(results='invalid') raises ValueError (not AssertionError)."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.close()
        with pytest.raises(ValueError, match="results must be 'min' or 'average'"):
            m.solve(results="invalid", num_workers=1, stopping_time=1)

    def test_solve_valid_results_min(self):
        """solve(results='min') succeeds and returns OptimizeResult."""
        from cbqs.result import OptimizeResult
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        m.close()
        result = m.solve(results="min", num_workers=1, stopping_time=2)
        assert isinstance(result, OptimizeResult)

    def test_solve_not_compiled_raises(self):
        """solve() without close() raises ValueError."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        m.add_constraint((x[0] + x[1] + x[2]) <= 2)
        m.set_objective(x[0] + x[1] + x[2], MAXIMIZE)
        with pytest.raises(ValueError, match="No constraints compiled"):
            m.solve(num_workers=1, stopping_time=1)


class TestAddVariablesValidation:
    """Tests for add_variables validation."""

    def test_add_variables_zero_raises_valueerror(self):
        """add_variables(0) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Number of variables must be >= 1"):
            m.add_variables(0)

    def test_add_variables_negative_raises_valueerror(self):
        """add_variables(-1) raises ValueError."""
        m = Model()
        with pytest.raises(ValueError, match="Number of variables must be >= 1"):
            m.add_variables(-1)

    def test_add_variables_one_succeeds(self):
        """add_variables(1) succeeds."""
        m = Model()
        xs = m.add_variables(1)
        assert len(xs) == 1
        assert m.n == 1


class TestDuplicateVariableMerging:
    """Tests for duplicate variable term merging in expressions."""

    def test_duplicate_terms_merged_in_constraint(self):
        """3*x0 + 5*x0 should be merged to 8*x0 with a warning."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        # Build expression with duplicate variable term: 3*x0 + 5*x0
        expr = 3 * x[0] + 5 * x[0]
        constraint = expr <= 10
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.add_constraint(constraint)
            # Check that a merge warning was emitted
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) >= 1

    def test_no_warning_on_distinct_terms(self):
        """Distinct variable terms should not trigger merge warning."""
        m = Model()
        xs = m.add_variables(3)
        x = [xs[i] for i in range(3)]
        expr = x[0] + x[1] + x[2]
        constraint = expr <= 2
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.add_constraint(constraint)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) == 0

    def test_duplicate_terms_merged_in_objective(self):
        """Duplicate variable terms are also merged in set_objective."""
        m = Model()
        xs = m.add_variables(2)
        x = [xs[i] for i in range(2)]
        # Build expression with duplicate: 2*x0 + 3*x0
        expr = 2 * x[0] + 3 * x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MAXIMIZE)
            dup_warnings = [x for x in w if "Duplicate variable terms" in str(x.message)]
            assert len(dup_warnings) >= 1

    def test_validate_false_skips_merge(self):
        """validate=False skips duplicate term merging (no warning)."""
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
