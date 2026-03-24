"""
Tests for matrix-variable operations producing correct expressions.

Compares fast matmul path (c @ x, x @ M @ x, y @ M @ x) against
the slow Python loop path to verify correctness.
"""
import pytest
import numpy as np
from cbqs.Expression import Variable, Expression
from cbqs.VariableVector import (
    CVariableVector, ExpressionVector, _make_variable_vector,
)


def _expr_terms(expr):
    """Extract terms from an Expression as a list of lists."""
    return list(expr)


def _slow_linear(c, variables):
    """Slow Python path: sum(c[i] * x[i]) for non-zero c[i]."""
    result = None
    for i in range(len(variables)):
        if c[i] == 0:
            continue
        term = int(c[i]) * variables[i]
        result = term if result is None else result + term
    return result


def _slow_bilinear(M, y_vars, x_vars):
    """Slow Python path: sum(M[i,j] * y[i] * x[j]) for non-zero M[i,j]."""
    result = None
    m, n = M.shape
    for i in range(m):
        for j in range(n):
            if M[i, j] == 0:
                continue
            term = int(M[i, j]) * y_vars[i] * x_vars[j]
            result = term if result is None else result + term
    return result


class TestLinearDotProduct:
    """(1) c @ x produces same expression as sum(c[i]*x[i])."""

    def test_c_dot_x_basic(self):
        vec = _make_variable_vector(None, 0, 4)
        c = np.array([3, -2, 5, 1], dtype=np.int64)
        fast = c @ vec
        variables = vec.values()
        slow = _slow_linear(c, variables)
        assert isinstance(fast, Expression)
        assert set(map(tuple, _expr_terms(fast))) == set(map(tuple, _expr_terms(slow)))

    def test_c_dot_x_single(self):
        vec = _make_variable_vector(None, 0, 1)
        c = np.array([7], dtype=np.int64)
        fast = c @ vec
        assert isinstance(fast, Expression)
        assert [7, 0] in _expr_terms(fast)

    def test_c_dot_x_large_coefficients(self):
        vec = _make_variable_vector(None, 0, 2)
        c = np.array([10**15, -10**15], dtype=np.int64)
        fast = c @ vec
        terms = _expr_terms(fast)
        assert [10**15, 0] in terms
        assert [-10**15, 1] in terms


class TestQuadraticFormSameVector:
    """(2) x @ M @ x produces same expression as sum(M[i,j]*x[i]*x[j])."""

    def test_xtMx_diagonal(self):
        vec = _make_variable_vector(None, 0, 3)
        M = np.array([[2, 0, 0], [0, 3, 0], [0, 0, 5]], dtype=np.int64)
        ev = M @ vec
        fast = vec @ ev
        variables = vec.values()
        slow = _slow_bilinear(M, variables, variables)
        assert isinstance(fast, Expression)
        assert set(map(tuple, _expr_terms(fast))) == set(map(tuple, _expr_terms(slow)))

    def test_xtMx_full_3x3(self):
        vec = _make_variable_vector(None, 0, 3)
        M = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.int64)
        ev = M @ vec
        fast = vec @ ev
        variables = vec.values()
        slow = _slow_bilinear(M, variables, variables)
        assert isinstance(fast, Expression)
        fast_terms = set(map(tuple, _expr_terms(fast)))
        slow_terms = set(map(tuple, _expr_terms(slow)))
        assert fast_terms == slow_terms


class TestQuadraticFormDifferentVectors:
    """(3) y @ M @ x works with different variable vectors."""

    def test_ytMx_2x2(self):
        x = _make_variable_vector(None, 0, 2)
        y = _make_variable_vector(None, 10, 2)
        M = np.array([[3, 1], [2, 4]], dtype=np.int64)
        ev = M @ x
        fast = y @ ev
        x_vars = x.values()
        y_vars = y.values()
        slow = _slow_bilinear(M, y_vars, x_vars)
        assert isinstance(fast, Expression)
        assert set(map(tuple, _expr_terms(fast))) == set(map(tuple, _expr_terms(slow)))

    def test_ytMx_non_square(self):
        x = _make_variable_vector(None, 0, 3)
        y = _make_variable_vector(None, 10, 2)
        M = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int64)
        ev = M @ x
        fast = y @ ev
        x_vars = x.values()
        y_vars = y.values()
        slow = _slow_bilinear(M, y_vars, x_vars)
        assert isinstance(fast, Expression)
        assert set(map(tuple, _expr_terms(fast))) == set(map(tuple, _expr_terms(slow)))


class TestDiagonalTerms:
    """(4) Diagonal terms x[i]*x[i] evaluate correctly via matmul."""

    def test_diagonal_only(self):
        vec = _make_variable_vector(None, 0, 3)
        M = np.diag(np.array([2, 3, 7], dtype=np.int64))
        ev = M @ vec
        fast = vec @ ev
        terms = _expr_terms(fast)
        assert [2, 0, 0] in terms
        assert [3, 1, 1] in terms
        assert [7, 2, 2] in terms
        assert len(terms) == 3


class TestZeroCoefficientsSkipped:
    """(5) Zero coefficients are skipped."""

    def test_sparse_linear(self):
        vec = _make_variable_vector(None, 0, 4)
        c = np.array([3, 0, 0, 2], dtype=np.int64)
        fast = c @ vec
        terms = _expr_terms(fast)
        assert len(terms) == 2
        for t in terms:
            assert t[0] != 0

    def test_sparse_quadratic(self):
        vec = _make_variable_vector(None, 0, 3)
        M = np.array([[1, 0, 0], [0, 0, 2], [0, 0, 3]], dtype=np.int64)
        ev = M @ vec
        fast = vec @ ev
        terms = _expr_terms(fast)
        assert len(terms) == 3

    def test_all_zero_linear(self):
        vec = _make_variable_vector(None, 0, 3)
        c = np.array([0, 0, 0], dtype=np.int64)
        fast = c @ vec
        terms = _expr_terms(fast)
        assert len(terms) == 0

    def test_all_zero_quadratic(self):
        vec = _make_variable_vector(None, 0, 2)
        M = np.zeros((2, 2), dtype=np.int64)
        ev = M @ vec
        fast = vec @ ev
        terms = _expr_terms(fast)
        assert len(terms) == 0


class TestDtypeAndContiguityErrors:
    """(6) dtype/contiguity errors are raised."""

    def test_dimension_mismatch_1d(self):
        vec = _make_variable_vector(None, 0, 3)
        c = np.array([1, 2], dtype=np.int64)
        with pytest.raises(ValueError, match="length"):
            c @ vec

    def test_dimension_mismatch_2d(self):
        vec = _make_variable_vector(None, 0, 3)
        M = np.array([[1, 2]], dtype=np.int64)
        with pytest.raises(ValueError, match="columns"):
            M @ vec

    def test_bilinear_dimension_mismatch(self):
        x = _make_variable_vector(None, 0, 3)
        y = _make_variable_vector(None, 10, 5)
        M = np.array([[1, 0, 2], [0, 3, 0]], dtype=np.int64)
        ev = M @ x
        with pytest.raises(ValueError, match="rows"):
            y @ ev

    def test_3d_array_raises(self):
        vec = _make_variable_vector(None, 0, 2)
        arr = np.ones((2, 2, 2), dtype=np.int64)
        with pytest.raises(ValueError, match="1D or 2D"):
            arr @ vec

    def test_float_dtype_coerced(self):
        """Float arrays are coerced to int64 (no error), values preserved."""
        vec = _make_variable_vector(None, 0, 2)
        c = np.array([3.0, 5.0], dtype=np.float64)
        result = c @ vec
        assert isinstance(result, Expression)
        terms = _expr_terms(result)
        assert [3, 0] in terms
        assert [5, 1] in terms

    def test_non_contiguous_array_handled(self):
        """Non-contiguous arrays are coerced to contiguous."""
        vec = _make_variable_vector(None, 0, 2)
        arr = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.int64)
        # Slicing creates non-contiguous view
        c = arr[0, ::2]  # [1, 3], non-contiguous
        result = c @ vec
        assert isinstance(result, Expression)
        terms = _expr_terms(result)
        assert [1, 0] in terms
        assert [3, 1] in terms

    def test_expression_vector_type(self):
        """2D matmul returns ExpressionVector."""
        vec = _make_variable_vector(None, 0, 3)
        M = np.eye(3, dtype=np.int64)
        result = M @ vec
        assert isinstance(result, ExpressionVector)
        assert result.shape == (3, 3)
