from libc.stdint cimport int64_t
from .Expression import Variable
from .Expression cimport Expression, expression_t, free_expression
from .Constants import INTEGER
import numpy as np
cimport numpy as cnp


cdef class CVariableVector:
	"""Compact vector of variables backed by a C array.

	Dict-compatible interface: keys are variable indices, iteration yields
	integer keys, ``__getitem__`` accepts variable indices.
	Variable Python objects are created lazily on access.
	Holds a reference to the owning Model for lifetime safety.
	"""

	def __cinit__(self, int n=0):
		self._vec = c_variable_vector_init(n)
		self._owns = True
		self._model = None
		self._name_prefix = "x"

	def __dealloc__(self):
		if self._owns:
			c_variable_vector_free(&self._vec)

	def __len__(self):
		return self._vec.n

	cdef inline object _variable_at(self, int pos):
		"""Create a Variable for position *pos* (0-based)."""
		return Variable(
			self._vec.indices[pos],
			f"{self._name_prefix}{self._vec.indices[pos]}",
			self._vec.lb[pos],
			self._vec.ub[pos],
			self._vec.vtype[pos],
		)

	cdef inline int _pos_for_key(self, int key) except -1:
		"""Map a variable-index key to a 0-based position, or raise KeyError."""
		cdef int i
		for i in range(self._vec.n):
			if self._vec.indices[i] == key:
				return i
		raise KeyError(key)

	def __getitem__(self, key):
		if not isinstance(key, int):
			raise TypeError(f"indices must be integers, not {type(key).__name__}")
		cdef int pos = self._pos_for_key(<int>key)
		return self._variable_at(pos)

	def __iter__(self):
		"""Yield variable indices (dict-key compatible)."""
		cdef int i
		for i in range(self._vec.n):
			yield self._vec.indices[i]

	def __contains__(self, item):
		"""Check if an integer variable index is present."""
		if not isinstance(item, int):
			return False
		cdef int target = <int>item
		cdef int i
		for i in range(self._vec.n):
			if self._vec.indices[i] == target:
				return True
		return False

	def keys(self):
		"""Variable indices, like dict.keys()."""
		return list(self)

	def values(self):
		"""Variable objects, like dict.values()."""
		cdef int i
		return [self._variable_at(i) for i in range(self._vec.n)]

	def items(self):
		"""(index, Variable) pairs, like dict.items()."""
		cdef int i
		return [(self._vec.indices[i], self._variable_at(i))
		        for i in range(self._vec.n)]

	def __repr__(self):
		return f"CVariableVector(size={self._vec.n})"

	def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
		"""Handle numpy ufunc dispatch for matmul."""
		if ufunc is np.matmul and method == '__call__' and len(inputs) == 2:
			lhs, rhs = inputs
			if isinstance(rhs, CVariableVector):
				return rhs.__rmatmul__(lhs)
			if isinstance(lhs, CVariableVector):
				return lhs.__matmul__(rhs)
		return NotImplemented

	@property
	def model(self):
		return self._model

	def __matmul__(self, other):
		"""CVariableVector @ ExpressionVector → Expression (bilinear_reduce)."""
		cdef ExpressionVector ev
		cdef expression_t *result
		cdef Expression expr
		if not isinstance(other, ExpressionVector):
			return NotImplemented
		ev = <ExpressionVector>other
		if self._vec.n != ev._m:
			raise ValueError(
				f"vector size ({self._vec.n}) != matrix rows ({ev._m})")
		result = bilinear_reduce(
			self._vec.indices, self._vec.n,
			<const int64_t *>cnp.PyArray_DATA(ev._matrix),
			ev._var_indices, ev._n,
		)
		if result is NULL:
			raise MemoryError("bilinear_reduce failed")
		expr = Expression()
		free_expression(expr.expr)
		expr.expr = result
		return expr

	def __rmatmul__(self, other):
		"""numpy array @ CVariableVector → ExpressionVector or Expression."""
		cdef cnp.ndarray arr
		cdef expression_t *result
		cdef Expression expr
		if not isinstance(other, np.ndarray):
			return NotImplemented
		arr = np.ascontiguousarray(other, dtype=np.int64)
		if arr.ndim == 2:
			if arr.shape[1] != self._vec.n:
				raise ValueError(
					f"matrix columns ({arr.shape[1]}) != vector size ({self._vec.n})")
			return ExpressionVector._create(arr, self)
		elif arr.ndim == 1:
			if arr.shape[0] != self._vec.n:
				raise ValueError(
					f"vector length ({arr.shape[0]}) != variable count ({self._vec.n})")
			result = linear_reduce(
				<const int64_t *>cnp.PyArray_DATA(arr),
				self._vec.indices, self._vec.n,
			)
			if result is NULL:
				raise MemoryError("linear_reduce failed")
			expr = Expression()
			free_expression(expr.expr)
			expr.expr = result
			return expr
		else:
			raise ValueError(f"expected 1D or 2D array, got {arr.ndim}D")


cdef class ExpressionVector:
	"""Lazy representation of matrix @ variables (not yet reduced).

	Holds a reference to the numpy matrix and variable indices.
	Reduction happens when a CVariableVector is matmul'd with this.
	"""

	@staticmethod
	cdef ExpressionVector _create(object matrix, CVariableVector var_vec):
		cdef ExpressionVector ev = ExpressionVector.__new__(ExpressionVector)
		ev._matrix = matrix
		ev._var_vec = var_vec
		ev._var_indices = var_vec._vec.indices
		ev._m = matrix.shape[0]
		ev._n = matrix.shape[1]
		return ev

	def __repr__(self):
		return f"ExpressionVector(m={self._m}, n={self._n})"

	def __rmatmul__(self, other):
		"""CVariableVector @ ExpressionVector → Expression."""
		if isinstance(other, CVariableVector):
			return (<CVariableVector>other).__matmul__(self)
		return NotImplemented

	@property
	def shape(self):
		return (self._m, self._n)


def _make_variable_vector(model, int start, int count, str name_prefix="x",
                          int lb=0, int ub=1, int vtype=INTEGER):
	"""Build a CVariableVector for *count* contiguous variables.

	This is a module-level helper so that Model.add_variables() can construct
	the vector without exposing C internals.
	"""
	cdef CVariableVector vec = CVariableVector(count)
	vec._model = model
	vec._name_prefix = name_prefix
	cdef int i
	for i in range(count):
		vec._vec.indices[i] = start + i
		vec._vec.lb[i] = lb
		vec._vec.ub[i] = ub
		vec._vec.vtype[i] = vtype
	return vec
