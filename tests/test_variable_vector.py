"""Tests for CVariableVector Cython wrapper with dict-compatible interface."""
import pytest
from cbqs.VariableVector import CVariableVector, _make_variable_vector
from cbqs.Expression import Variable, Expression
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
    """__getitem__ accepts variable indices (dict-key style)."""

    def test_basic_access(self):
        vec = _make_variable_vector(None, 10, 3)
        v = vec[10]
        assert isinstance(v, Variable)
        assert v.index == 10
        assert v.name == "x10"
        assert v.lb == 0
        assert v.ub == 1
        assert v.vtype == INTEGER

    def test_sequential_keys(self):
        vec = _make_variable_vector(None, 5, 4)
        assert vec[5].index == 5
        assert vec[6].index == 6
        assert vec[7].index == 7
        assert vec[8].index == 8

    def test_missing_key_raises(self):
        vec = _make_variable_vector(None, 10, 3)
        with pytest.raises(KeyError):
            vec[0]
        with pytest.raises(KeyError):
            vec[13]

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
    """__iter__ yields integer variable indices (dict-key compatible)."""

    def test_iter_count(self):
        vec = _make_variable_vector(None, 0, 5)
        keys = list(vec)
        assert len(keys) == 5

    def test_iter_yields_keys(self):
        vec = _make_variable_vector(None, 10, 3)
        keys = list(vec)
        assert keys == [10, 11, 12]

    def test_iter_empty(self):
        vec = CVariableVector()
        assert list(vec) == []

    def test_dict_pattern(self):
        """for i in x: x[i] works like a dict."""
        vec = _make_variable_vector(None, 5, 3)
        variables = [vec[i] for i in vec]
        assert len(variables) == 3
        assert variables[0].index == 5
        assert variables[2].index == 7


class TestCVariableVectorContains:
    """__contains__ checks integer variable indices."""

    def test_present(self):
        vec = _make_variable_vector(None, 0, 5)
        assert 3 in vec

    def test_absent(self):
        vec = _make_variable_vector(None, 0, 5)
        assert 10 not in vec

    def test_non_int(self):
        vec = _make_variable_vector(None, 0, 5)
        assert "x0" not in vec


class TestCVariableVectorDictCompat:
    """keys(), values(), items() for dict compatibility."""

    def test_keys(self):
        vec = _make_variable_vector(None, 10, 3)
        assert vec.keys() == [10, 11, 12]

    def test_values(self):
        vec = _make_variable_vector(None, 10, 3)
        vals = vec.values()
        assert len(vals) == 3
        assert all(isinstance(v, Variable) for v in vals)
        assert [v.index for v in vals] == [10, 11, 12]

    def test_items(self):
        vec = _make_variable_vector(None, 10, 2)
        items = vec.items()
        assert len(items) == 2
        assert items[0][0] == 10
        assert items[0][1].index == 10


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
        assert isinstance(expr, Expression)

    def test_multiply_variable(self):
        vec = _make_variable_vector(None, 0, 3)
        expr = 3 * vec[0]
        assert isinstance(expr, Expression)
