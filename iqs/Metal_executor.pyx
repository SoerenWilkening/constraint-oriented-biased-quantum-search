from .SearchLib cimport new_constraints_t, new_constraint

cdef extern from "objc/objc.h":
	ctypedef void * id

cdef extern from "src/metal_files/exec_metal.h":
	ctypedef void (*callback_t)(int, size_t, double)

	ctypedef struct gpu_info_t:
		id device;
		id queue;
		id library;
		id kernelFunction;
		id pipelineState;
		id pointer;

		id state;  #    stores state metadata
		id state_data;  # stores state data

		id move_length;
		id move_offset;
		id move_entries;

		id first_move;
		id last_move;

	int exec_gpu(int n, new_constraints_t *obj, new_constraints_t *con);

cdef class Executor:
	cdef gpu_info_t *info

	def __cinit__(self, ):
		pass

	def __init__(self):
		pass

	cdef exec(self, n, new_constraint obj, new_constraint con):
		exec_gpu(n, &obj.con, &con.con)

	def gpu_local_search(self, n,  obj: new_constraint,  con: new_constraint):
		self.exec(n, obj, con)
		return 0
