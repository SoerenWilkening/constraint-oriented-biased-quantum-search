import os
from copy import copy
from time import time

import numpy as np

def set_seed(seed):
	srand(seed)

# cdef class constraints:
# 	cdef constraint_list_t con;
# 	cdef constraint_list_t *pointer;
# 	cdef int num_constraints;
#
# 	def __cinit__(self):
# 		self.con = init_con_list()
# 		self.pointer = &self.con
# 		self.num_constraints = 0
#
# 	def __iadd__(self, other):
# 		self.num_constraints += 1
# 		cdef constraint_t con = init_con()
# 		liste, sense, rhs, digits = other[:-3], other[-3], other[-2], other[-1]
# 		for i in liste:
# 			l_p = <long double *> calloc(len(i), sizeof(long double))
# 			for j in range(len(i)):
# 				l_p[j] = <long double> i[j]
#
# 			add_literal(&con, l_p, len(i))
# 		if sense == "<": add_sense(&con, -1)
# 		elif sense == "=": add_sense(&con, 0)
# 		else: add_sense(&con, 1)
# 		add_rhs(&con, rhs)
# 		add_digits(&con, digits)
# 		con.evaluated = undetermined
# 		add_constraint(&self.con, &con)
# 		return self
#
# 	def __str__(self):
# 		print_constraints(&self.con)
# 		return ""
#
# 	def __len__(self):
# 		return self.num_constraints
#
# 	def eval(self, assignment):
# 		l = np.array(assignment, dtype = np.int32)
# 		l_p = <int *> calloc(len(assignment), sizeof(int))
# 		for i in range(len(assignment)):
# 			l_p[i] = <int> l[i]
#
# 		return quantum_feasibility(self.pointer, l_p, len(assignment))
#
# 	def obj(self, st: state_py):
# 		return ObjVal(st.state, self.pointer)
#
# 	def set_rhs(self, rhs):
# 		add_rhs(&self.con.constraints[0], rhs)
#
# 	def count(self, st: state_py, n: int):
# 		return count_satisfyed_constraints(&self.con, st.state, n + 1, False, n)
#
# 	def liste(self):
# 		return [[[self.con.constraints[i].literals[j].literal[k] for k in range(self.con.constraints[i].literals[j].len_literal)]
# 			            for j in range(self.con.constraints[i].num_literals)] + [self.con.constraints[i].rhs]
# 		        for i in range(self.con.num_constraints)
# 		]
#
#
# def set_factors_wrapper(double objective_factor, double constraint_factor, double bias_factor, double look_factor):
# 	set_factors(objective_factor, constraint_factor, bias_factor, look_factor)
#
# def set_bias_wrapper(double bias):
# 	set_bias(bias)
#
# def set_obj_dependence_wrapper(dependence: list[double]):
# 	arr = np.array(dependence, dtype = np.double)
# 	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
# 	for i in range(arr.shape[0]):
# 		ptr[i] = <double> arr[i]
# 	set_obj_dependence(ptr, len(dependence))
#
# def set_constraint_dependence_wrapper(dependence: list[double]):
# 	arr = np.array(dependence, dtype = np.double)
# 	cdef double * ptr = <double *> calloc(arr.shape[0], sizeof(double))
# 	for i in range(arr.shape[0]):
# 		ptr[i] = <double> arr[i]
# 	set_constraint_dependence(ptr, len(dependence))
#

# Class containing all the states information and acts as wrpper for C functionality
#
cdef class state_py:
	cdef state_t *state
	cdef size_t num_states
	cdef int[:] arr
	cdef long double objval

	def __cinit__(self, int64_t ObjVal, array: list | np.ndarray) -> None:
		self.num_states = 1
		self.arr = array # easier handling when list it required
		arr = np.array(array, dtype = np.int32)

		cdef int* ptr = <int *>calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]):
			ptr[i] = <int>arr[i]
		self.state = init_state(ObjVal, ptr, arr.shape[0])
		free(<void *>ptr)

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

	def assignment(self):
		return list(self.arr)


# # def QSearch_wrapper(state_py bfs, int M) -> tuple[state_py, int, int]:
# # 	cdef size_t iterations = 0
# # 	cdef size_t rounds = 0
# # 	res: state_py = state_py(0, [0])
# # 	free_state(res.state, 1)
# #
# # 	res.state = QSearch(bfs.state, bfs.num_states, &iterations, &rounds, M)
# # 	res.get_x()
# #
# # 	return res, iterations, rounds
#
# def run_ctg(initial: state_py, con: constraints, obj: constraints, M: int, depth_look_ahead: int, solver: int, store: str, long double stop_val):
# 	cdef int qtg_applications = 0;
# 	# BranchingStats.bias = bias
# 	cur_sol : state_py = copy(initial)
# 	t1 = time()
# 	ctg(cur_sol.state, con.pointer, obj.pointer, M, &qtg_applications, depth_look_ahead, solver, store.encode('utf-8'), stop_val)
# 	t = time() - t1
# 	cur_sol.get_x()
#
# 	arr = []
# 	for i in range(cur_sol.state[0].vector.bits):
# 		arr.append(sw_tstbit(cur_sol.state[0].vector, i))
#
# 	cur_sol.arr = np.array(arr, dtype = np.int32)
# 	return qtg_applications, cur_sol, t