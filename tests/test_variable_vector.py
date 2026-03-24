"""Tests for CVariableVector Cython wrapper."""
import pytest
from cbqs.VariableVector import CVariableVector, _make_variable_vector
from cbqs.Expression import Variable
from cbqs.Constants import INTEGER


class TestCVariableVectorLen:
    """__len__ returns the number of stored variables."""

    def test_empty_vector(self):
        vec = CVariableVector()
        assert len(vec) == 0

    def test_after_make(self):
        vec = _make_variable_vector(None, 0, 5)
        assert len(vec) == 5


class TestCVariableVectorGetitem:
    """__getitem__ returns a Variable with correct metadata."""

    def test_basic_access(self):
        vec = _make_variable_vector(None, 10, 3)
        v = vec[0]
        assert isinstance(v, Variable)
        assert v.index == 10
        assert v.name == "x10"
        assert v.lb == 0
        assert v.ub == 1
        assert v.vtype == INTEGER

    def test_sequential_indices(self):
        vec = _make_variable_vector(None, 5, 4)
        assert vec[0].index == 5
        assert vec[1].index == 6
        assert vec[2].index == 7
        assert vec[3].index == 8

    def test_negative_index(self):
        vec = _make_variable_vector(None, 0, 3)
        assert vec[-1].index == 2
        assert vec[-3].index == 0

    def test_out_of_range_raises(self):
        vec = _make_variable_vector(None, 0, 3)
        with pytest.raises(IndexError):
            vec[3]
        with pytest.raises(IndexError):
            vec[-4]

    def test_non_int_key_raises(self):
        vec = _make_variable_vector(None, 0, 3)
        with pytest.raises(TypeError):
            vec["a"]

    def test_lazy_creation(self):
        """Each access creates a new Variable object (lazy, not cached)."""
        vec = _make_variable_vector(None, 0, 3)
        v1 = vec[0]
        v2 = vec[0]
        assert v1.index == v2.index
        assert v1 is not v2

    def test_custom_name_prefix(self):
        vec = _make_variable_vector(None, 0, 2, name_prefix="y")
        assert vec[0].name == "y0"
        assert vec[1].name == "y1"


class TestCVariableVectorIter:
    """__iter__ yields Variable objects in order."""

    def test_iter_count(self):
        vec = _make_variable_vector(None, 0, 5)
        items = list(vec)
        assert len(items) == 5

    def test_iter_order(self):
        vec = _make_variable_vector(None, 10, 3)
        indices = [v.index for v in vec]
        assert indices == [10, 11, 12]

    def test_iter_empty(self):
        vec = CVariableVector()
        assert list(vec) == []


class TestCVariableVectorContains:
    """__contains__ checks by Variable.index."""

    def test_present(self):
        vec = _make_variable_vector(None, 0, 5)
        v = Variable(3)
        assert v in vec

    def test_absent(self):
        vec = _make_variable_vector(None, 0, 5)
        v = Variable(10)
        assert v not in vec

    def test_non_variable(self):
        vec = _make_variable_vector(None, 0, 5)
        assert 3 not in vec
        assert "x0" not in vec


class TestCVariableVectorModel:
    """CVariableVector holds a reference to the Model for lifetime safety."""

    def test_model_ref_none(self):
        vec = _make_variable_vector(None, 0, 3)
        assert vec.model is None

    def test_model_ref_kept(self):
        sentinel = object()
        vec = _make_variable_vector(sentinel, 0, 3)
        assert vec.model is sentinel


class TestCVariableVectorRepr:
    def test_repr(self):
        vec = _make_variable_vector(None, 0, 7)
        assert "7" in repr(vec)


class TestCVariableVectorArithmetic:
    """Variables from CVariableVector can be used in expressions."""

    def test_add_variables(self):
        vec = _make_variable_vector(None, 0, 3)
        expr = vec[0] + vec[1]
        # Should create an Expression without error
        from cbqs.Expression import Expression
        assert isinstance(expr, Expression)

    def test_multiply_variable(self):
        vec = _make_variable_vector(None, 0, 3)
        expr = 3 * vec[0]
        from cbqs.Expression import Expression
        assert isinstance(expr, Expression)
