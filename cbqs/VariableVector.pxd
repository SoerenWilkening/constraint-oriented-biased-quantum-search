from libc.stdint cimport int64_t
from .Expression cimport expression_t

cdef extern from "src/variable_vector.h":
	ctypedef struct c_variable_vector_t:
		int *indices
		int *lb
		int *ub
		int *vtype
		int n

	c_variable_vector_t c_variable_vector_init(int n)
	void c_variable_vector_free(c_variable_vector_t *vv)

	expression_t *bilinear_reduce(const int *y_indices, int m,
	                              const int64_t *matrix,
	                              const int *x_indices, int n)
	expression_t *linear_reduce(const int64_t *coeffs,
	                            const int *x_indices, int n)


cdef class CVariableVector:
	cdef c_variable_vector_t _vec
	cdef bint _owns
	cdef object _model
	cdef object _name_prefix
	cdef inline object _variable_at(self, int pos)
	cdef inline int _pos_for_key(self, int key) except -1


cdef class ExpressionVector:
	cdef object _matrix     # numpy array reference (prevents GC)
	cdef int *_var_indices   # pointer into CVariableVector.indices
	cdef int _m              # rows
	cdef int _n              # cols
	cdef object _var_vec     # CVariableVector reference (prevents GC)
