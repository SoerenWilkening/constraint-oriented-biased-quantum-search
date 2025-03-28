from copy import copy
from time import time

import numpy as np

# def gpu_qmax_search(n: int, M: int, bias: float, gloabalSeed: int,
#                     constraint: list[int], c_terms: int,
#                     objective: list[int], o_terms: int,
#                     cur: int, arr: list[int]):
#
# 	cdef int * obj_c = <int *> calloc(len(objective), sizeof(int))
# 	for i in range(len(objective)):
# 		obj_c[i] = <int> objective[i]
#
# 	cdef int * con_c = <int *> calloc(len(constraint), sizeof(int))
# 	for i in range(len(constraint)):
# 		con_c[i] = <int> constraint[i]
#
# 	cdef uint32_t * arr_c = <uint32_t*> calloc(len(arr), sizeof(uint32_t))
# 	for i in range(len(arr)):
# 		arr_c[i] = <uint32_t> arr[i]
#
# 	gpu_qmax_search_c(n, M, bias, gloabalSeed,
# 	                  con_c, len(constraint),
# 	                  obj_c, len(objective),
# 	                  cur, arr_c)


def set_seed(seed):
	srand(seed)

cdef class constraints:
	cdef constraint_list_t con;
	cdef constraint_list_t *pointer;
	cdef int num_constraints;

	def __cinit__(self):
		self.con = init_con_list()
		self.pointer = &self.con
		self.num_constraints = 0

	def __iadd__(self, other):
		self.num_constraints += 1
		cdef constraint_t con = init_con()
		liste, sense, rhs = other[:-2], other[-2], other[-1]
		for i in liste:
			l_p = <int64_t *> calloc(len(i), sizeof(int64_t))
			for j in range(len(i)):
				l_p[j] = <int64_t> i[j]

			add_literal(&con, l_p, len(i))
		add_sense(&con, sense)
		add_rhs(&con, rhs)
		con.evaluated = -2
		add_constraint(&self.con, &con)
		return self

	def __str__(self):
		print_constraints(&self.con)
		return ""

	def __len__(self):
		return self.num_constraints

	def eval(self, state: state_py):
		return quantum_feasibility2(self.pointer, state.state, state.state[0].vector.bits, False)

	def obj(self, st: state_py):
		return ObjVal(st.state, self.pointer)

	def set_rhs(self, rhs):
		add_rhs(&self.con.constraints[0], rhs)

	def count(self, st: state_py, n: int):
		return count_satisfyed_constraints(&self.con, st.state, n + 1, False, n)

	def liste(self):
		return [[[self.con.constraints[i].literals[j].factor] +
		         [self.con.constraints[i].literals[j].variables[k] for k in range(1, self.con.constraints[i].literals[j].len_literal)]
			            for j in range(self.con.constraints[i].num_literals)] + [self.con.constraints[i].rhs]
		        for i in range(self.con.num_constraints)
		]


def set_factors_wrapper(double objective_factor, double constraint_factor, double bias_factor, double look_factor):
	set_factors(objective_factor, constraint_factor, bias_factor, look_factor)

def set_bias_wrapper(double bias):
	set_bias(bias)

def set_obj_dependence_wrapper(dependence: list[double]):
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_obj_dependence(ptr, len(dependence))

def set_constraint_dependence_wrapper(dependence: list[double]):
	arr = np.array(dependence, dtype = np.double)
	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
	for i in range(arr.shape[0]):
		ptr[i] = <double> arr[i]
	set_constraint_dependence(ptr, len(dependence))


# Class containing all the states information and acts as wrpper for C functionality

cdef class state_py:
	cdef state_t *state
	cdef size_t num_states
	cdef int[:] arr
	cdef int64_t objval

	def __cinit__(self, int64_t ObjVal, array: list | np.ndarray) -> None:
		self.num_states = 1
		arr = np.array(array, dtype = np.int32)
		self.arr = arr # easier handling when list it required

		cdef int* ptr = <int *>calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]): ptr[i] = <int>arr[i]
		self.state = init_state(ObjVal, ptr, arr.shape[0])
		free(<void *>ptr)

	def __init__(self, ObjVal, array):
		pass

	def load(self, file):
		f = open(file, "r").read().split()
		return state_py(float(f[0]), list(map(int, f[1:])))

	def get_x(self):
		if self.state is NULL: self.objval = 0
		else: self.objval = self.state[0].tot_profit

	def __copy__(self) -> state_py:
		return state_py(self.objval, self.arr)

	def __str__(self) -> str:
		if self.state is NULL: return "NULL state"
		print_state(self.state)
		return ""

	def __dealloc__(self) -> None:
		if self.state is not NULL:
			free_state(self.state, self.num_states)

	def objective_value(self):
		return self.objval

	def integer_liste(self):
		step = [[
			self.state[0].vector.part[i] & 0xFFFFFFFF,
			(self.state[0].vector.part[i] >> 32) & 0xFFFFFFFF
		] for i in range(self.state[0].vector.n)]
		return [j for i in step for j in i]

	def assignment(self):
		return list(self.arr)


def QSearch_wrapper(state_py bfs, int M) -> tuple[state_py, int, int]:
	cdef size_t iterations = 0
	cdef size_t rounds = 0
	res: state_py = state_py(0, [0])
	free_state(res.state, 1)

	res.state = QSearch(bfs.state, bfs.num_states, &iterations, &rounds, M)
	res.get_x()

	return res, iterations, rounds


# define callback functionality ===============================

# Python-compatible C wrapper
cdef void my_callback_c(int a, size_t b, double c):
	if python_callback is not None:
		python_callback(a, b, c)

# python function to store the callback
cdef object python_callback = None

def run_ctg(
		initial: state_py,
		con: constraints,
		obj: constraints,
		M: int,
		depth_look_ahead: int,
		solver: int,
		int64_t stop_val,
		object callback):

	cdef size_t qtg_applications = 0;
	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c

	# BranchingStats.bias = bias
	cur_sol : state_py = copy(initial)
	t1 = time()
	ctg(cur_sol.state, con.pointer, obj.pointer, M, &qtg_applications, depth_look_ahead, solver, stop_val, cb_ptr)
	t = time() - t1
	cur_sol.get_x()

	arr = []
	for i in range(cur_sol.state[0].vector.bits):
		arr.append(sw_tstbit(cur_sol.state[0].vector, i))

	cur_sol.arr = np.array(arr, dtype = np.int32)
	return qtg_applications, cur_sol, t
