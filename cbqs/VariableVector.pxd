cdef extern from "src/variable_vector.h":
	ctypedef struct c_variable_vector_t:
		int *indices
		int *lb
		int *ub
		int *vtype
		int n

	c_variable_vector_t c_variable_vector_init(int n)
	void c_variable_vector_free(c_variable_vector_t *vv)


cdef class CVariableVector:
	cdef c_variable_vector_t _vec
	cdef bint _owns
	cdef object _model
	cdef object _name_prefix
