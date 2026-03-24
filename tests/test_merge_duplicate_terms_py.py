"""
Tests for C-level merge_duplicate_variable_terms called via Model API.

Verifies that duplicate variable terms are merged when adding objectives
and constraints with validate=True.
"""
import warnings
import pytest
from cbqs.Model import Model
from cbqs.Constants import MINIMIZE, MAXIMIZE


class TestMergeDuplicateTermsViaModel:
    """Integration tests: duplicate terms merged through set_objective/add_constraint."""

    def test_objective_duplicate_linear_terms_warns(self):
        """set_objective with duplicate terms emits a warning."""
        m = Model()
        x = m.add_variables(3)
        # Build expression with duplicate: x[0] appears twice
        expr = x[0] + x[1] + x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MINIMIZE)
            dup_warnings = [x for x in w if "Duplicate" in str(x.message)]
            assert len(dup_warnings) == 1

    def test_constraint_duplicate_linear_terms_warns(self):
        """add_constraint with duplicate terms emits a warning."""
        m = Model()
        x = m.add_variables(3)
        expr = x[0] + x[1] + x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.add_constraint(expr <= 5)
            dup_warnings = [x for x in w if "Duplicate" in str(x.message)]
            assert len(dup_warnings) == 1

    def test_no_warning_without_duplicates(self):
        """No warning when expression has no duplicate terms."""
        m = Model()
        x = m.add_variables(3)
        expr = x[0] + x[1] + x[2]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MINIMIZE)
            dup_warnings = [x for x in w if "Duplicate" in str(x.message)]
            assert len(dup_warnings) == 0

    def test_validate_false_skips_merge(self):
        """validate=False skips merge (no warning even with duplicates)."""
        m = Model()
        x = m.add_variables(3)
        expr = x[0] + x[1] + x[0]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MINIMIZE, validate=False)
            dup_warnings = [x for x in w if "Duplicate" in str(x.message)]
            assert len(dup_warnings) == 0

    def test_quadratic_duplicates_merged(self):
        """Quadratic duplicate terms (x0*x1 appearing twice) are merged."""
        m = Model()
        x = m.add_variables(3)
        # x[0]*x[1] + x[0]*x[1] should merge
        expr = x[0] * x[1] + x[0] * x[1]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.set_objective(expr, MINIMIZE)
            dup_warnings = [x for x in w if "Duplicate" in str(x.message)]
            assert len(dup_warnings) == 1
