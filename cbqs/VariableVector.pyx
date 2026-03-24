from .Expression import Variable
from .Constants import INTEGER


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
