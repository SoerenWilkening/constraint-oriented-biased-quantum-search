from .SearchLib cimport new_constraints_t, new_constraint
from libc.stdint cimport int32_t

cdef extern from "objc/objc.h":
	ctypedef void * id



cdef extern from "src/metal_files/exec_metal.h":
	ctypedef void (*callback_t)(int, size_t, double)

	ctypedef struct move_gpu_t:
		int32_t * length;
		int32_t *moves;
		int32_t *offset;

	ctypedef struct gpu_info_t:
		move_gpu_t move

		id device
		id queue
		id library
		id kernelFunction
		id pipelineState
		id pointer
		id state
		id state_data
		id num_integers
		id move_length
		id move_offset
		id move_entries
		id first_move
		id last_move
		id factors
		id num_clauses
		id clause_offset
		id clause_length
		id variable_offset
		id variables
		id obj_positive_indices
		id obj_negative_indices
		id obj_positive_offsets
		id obj_negative_offsets
		id obj_num_positive_indices
		id obj_num_negative_indices
		id con_factors
		id con_num_constraints
		id con_num_clauses
		id con_clause_offset
		id con_clause_length
		id con_variable_offset
		id con_variables
		id rhs
		id con_positive_indices
		id con_negative_indices
		id con_positive_offsets
		id con_negative_offsets
		id con_num_positive_indices
		id con_num_negative_indices
		id accepted_move

	int exec_gpu(int n, new_constraints_t *obj, new_constraints_t *con);

cdef class Executor:
	cdef gpu_info_t *info
	cdef new_constraints_t *obj
	cdef new_constraints_t *con
	cdef n

	def __cinit__(self, int n, obj: new_constraint, con: new_constraint):
		self.obj = <new_constraints_t *> &obj.con
		self.con = <new_constraints_t *> &con.con
		self.n = n

	def __init__(self, int n, obj: new_constraint, con: new_constraint):
		pass
	#
	# cdef exec(self):
	# 	exec_gpu(self.n, self.obj, self.con)
	#
	# def gpu_local_search(self):
	# 	self.exec()
	# 	return 0
