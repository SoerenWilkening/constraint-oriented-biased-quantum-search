# from cpython cimport PyObject
# from objc cimport id
from libc.stdint cimport  uint32_t
from libc.stdlib cimport calloc
# cdef extern from "objc/objc.h":
#     ctypedef void* id  # 'id' in Objective-C is actually a pointer to an object
# print("Import")

cdef extern from "objc/objc.h":
	ctypedef void* id

cdef extern from "generators/main.h":
	ctypedef struct gpu_info_t:
		id device
		id commandQueue
		id pipelineState
		id cur_val_Buffer
		id cur_array_Buffer
		id new_val_Buffer
		id arrays_Buffer
		id reps_Buffer
		id bias_Buffer
		id objective_Buffer
		id constraint_Buffer
		id seed_Buffer

	gpu_info_t *init_buffers(int *constraint, int c_terms,
	                         int *objective, int o_terms,
	                         double bias, uint32_t globalSeed,
	                         int num_integers);

	int gpu_qmax_search_c(int n, int M,
	                      int *constraint, int c_terms,
	                      int *objective, int o_terms,
	                      int cur, uint32_t *arr,
	                      gpu_info_t *info
	                      );

cdef class Executor:
	cdef gpu_info_t *info
	cdef int * obj_c
	cdef int * con_c
	cdef int o_terms_c
	cdef int c_terms_c

	def __cinit__(self, n: int, bias: float, gloabalSeed: int,
	              constraint: list[int],
	              objective: list[int], ):

		self.obj_c = <int *> calloc(len(objective), sizeof(int))
		for i in range(len(objective)):
			self.obj_c[i] = <int> objective[i]

		self.o_terms_c = len(objective)
		self.c_terms_c = len(constraint)

		self.con_c = <int *> calloc(len(constraint), sizeof(int))
		for i in range(len(constraint)):
			self.con_c[i] = <int> constraint[i]

		self.info = init_buffers(self.con_c, len(constraint),
		                    self.obj_c, len(objective),
		                    bias, gloabalSeed, n // 32 + 1)

	def __init__(self, n: int, bias: float, gloabalSeed: int,
	              constraint: list[int],
	              objective: list[int]):
		pass

	def gpu_qmax_search(self, n: int, M: int,
	                    cur: int, arr: list[int]):

		cdef uint32_t * arr_c = <uint32_t *> calloc(len(arr), sizeof(uint32_t))
		for i in range(len(arr)):
			arr_c[i] = <uint32_t> arr[i]

		# print("Method included!")

		gpu_qmax_search_c(n, M,
		                  self.con_c, self.c_terms_c,
		                  self.obj_c, self.o_terms_c,
		                  cur, arr_c, self.info)

