from .Expression import Variable
from .Constants import INTEGER


cdef class CVariableVector:
	"""Compact vector of variables backed by a C array.

	Supports ``__getitem__``, ``__len__``, ``__iter__``, and ``__contains__``.
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

	def __getitem__(self, key):
		cdef int idx
		cdef int size = self._vec.n
		if isinstance(key, int):
			idx = <int>key
			if idx < 0:
				idx += size
			if idx < 0 or idx >= size:
				raise IndexError(f"index {key} out of range for CVariableVector of size {size}")
			return Variable(
				self._vec.indices[idx],
				f"{self._name_prefix}{self._vec.indices[idx]}",
				self._vec.lb[idx],
				self._vec.ub[idx],
				self._vec.vtype[idx],
			)
		raise TypeError(f"indices must be integers, not {type(key).__name__}")

	def __iter__(self):
		cdef int i
		for i in range(self._vec.n):
			yield Variable(
				self._vec.indices[i],
				f"{self._name_prefix}{self._vec.indices[i]}",
				self._vec.lb[i],
				self._vec.ub[i],
				self._vec.vtype[i],
			)

	def __contains__(self, item):
		if not isinstance(item, Variable):
			return False
		cdef int target = item.index
		cdef int i
		for i in range(self._vec.n):
			if self._vec.indices[i] == target:
				return True
		return False

	def __repr__(self):
		return f"CVariableVector(size={self._vec.n})"

	@property
	def model(self):
		return self._model


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
