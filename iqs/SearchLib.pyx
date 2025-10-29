import sys
from copy import copy
import time
import numpy as np
import signal
from .Constants import *
from random import randint

def set_seed(unsigned int seed):
	srand(seed)

cdef class new_constraint:
	def __cinit__(self):
		self.con = init_new_constraint()
		self.num_constraints = 0

	def __str__(self):
		print_new_constraint(&self.con)
		return ""

	def __dealloc__(self):
		free_constraints(&self.con)

	def __copy__(self):
		new_con = new_constraint()
		new_con.con = copy_new_constraint(&self.con)
		new_con.num_constraints = self.num_constraints
		return new_con

	def __len__(self):
		return self.num_constraints

	cdef void add(self, Expression expr):
		self.num_constraints += 1
		add_expression_to_constraints(&self.con, <expression_t *> expr.expr)

	def process(self, int n):
		preprocessing(n, &self.con)

	def add_expression(self, expr: Expression):
		self.add(expr)

	def eval_con(self, state: state_py):
		return eval_constraints(&self.con, state.state, state.state[0].vector.bits)

	def eval_con_from_array(self, array: list):
		st = state_py(0, array)
		res = self.eval_con(st)
		del st
		return res

	def eval_obj(self, state: state_py):
		return objective_value(&self.con, state.state)


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

	def __len__(self):
		return self.num_states

	def load(self, file):
		f = open(file, "r").read().split()
		return state_py(float(f[0]), list(map(int, f[1:])))

	def get_x(self):
		if self.state is NULL: self.objval = 0
		else: self.objval = self.state[0].tot_profit

	def __copy__(self) -> state_py:
		cop_st = state_py(0, [0])
		free_state(cop_st.state, 1)
		cop_st.state = copy_state(self.state)
		cop_st.get_x()
		return cop_st

	def __str__(self) -> str:
		if self.state is NULL: return "NULL state"
		for i in range(self.num_states):
			print_state(&self.state[i])
			print()
		return ""

	def __dealloc__(self) -> None:
		if self.state is not NULL:
			free_state(self.state, self.num_states)

	@property
	def objective_value(self):
		return self.state[0].tot_profit

	def __iter__(self):
		return [sw_tstbit(self.state[0].vector, i)  for i in range(self.state[0].vector.bits)].__iter__()
		# return [self.state[0].vector.part[i] for i in range(self.state[0].vector.n)].__iter__()

	def integer_liste(self):
		step = [[
			self.state[0].vector.part[i] & 0xFFFFFFFF,
			(self.state[0].vector.part[i] >> 32) & 0xFFFFFFFF
		] for i in range(self.state[0].vector.n)]
		return [j for i in step for j in i]

	def assignment(self):
		return list(self.arr)

	def store(self, file):
		f = open(file, "w")
		f.write(f"{self.objval} ")
		for i in self.arr:
			f.write(f"{i} ")
		f.close()

	def read(self, str name, int n) -> None:
		# print(name)
		directoy = os.path.dirname(name)
		value = str(name).split("states_")[0].replace(directoy + "/", "")
		# print(value, directoy)
		files = [f"{directoy}/{i}".encode() for i in os.listdir(directoy) if value in i]
		# print(files)

		num_files = len(files)
		cdef char** f = <char **> calloc(num_files, sizeof(char *))
		for i in range(num_files):
			file_bytes = files[i]
			f[i] = <char *> calloc(len(file_bytes) + 1, sizeof(char))
			for j in range(len(file_bytes)):
				f[i][j] = file_bytes[j]

		free_state(self.state, self.num_states)
		self.state = read_states(f, num_files, &self.num_states, n)


def QSearch_wrapper(bfs: state_py, int M) -> tuple[state_py, int, int]:
	cdef size_t iterations = 0
	cdef size_t rounds = 0
	print(bfs)
	print("done")
	sys.stdout.flush()
	res: state_py = state_py(11, [0, 0])
	print("freed")
	sys.stdout.flush()
	print(res)
	cdef size_t index = 0;
	res.state = QSearch(bfs.state, bfs.num_states, &iterations, &rounds, M, &index)

	return res, iterations, rounds

import os

def store(states: list[float, tuple[list[int], list[int]]] , where: bytes) -> int:
	if os.path.exists(where): return 1

	file = open(where, "a")
	for i in states:
		file.write(f'{int(i[0])} ')
		for j in range(len(i[1])):
			file.write(f'{i[1][j]} {i[2][j]} ')
		file.write("\n")

	file.close()
	return 0

def read_nodes_wrapper(str name ,n: int) -> int | state_py:
	if not os.path.exists(name):
		return 1

	res = state_py(0, [0])
	res.read(name, n)
	return res


# define callback functionality ===============================

# Python-compatible C wrapper
cdef void my_callback_c(int64_t a, size_t b, double c, double d) with gil:
	if python_callback is not None:
		python_callback(a, b, c, d)

# python function to store the callback
cdef object python_callback = None

cpdef run_sampling(
		initial: state_py,
		con: new_constraint,
		obj: new_constraint,
		M: int,
		stopping_time: int,
		depth_look_ahead: int,
		solver: int,
		int64_t stop_val,
		object callback,
		int max_delta,
		int reset_delta,
		global_opt: state_py,
		not_stop: list[int],
		int ignore_constraint_search
):

	t_start: float = time.time()
	t_total: float = 0
	set_seed(randint(0, 10000000))
	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c
	cur_sol : state_py = copy(initial)

	cdef size_t qtg_applications = 0;
	cdef int dpth = depth_look_ahead
	cdef int slvr = solver
	cdef int64_t stpvl = stop_val
	cdef int M_c = M
	cdef int stppngtm = stopping_time
	cdef new_constraints_t *cnstrs = &con.con
	cdef new_constraints_t *obctv = &obj.con
	cdef int feasible;
	cdef int brk_tm = 0;
	cdef int n = cur_sol.state[0].vector.bits

	# if solver == SATISFY:
	# 	random_array = [randint(0, 1) for _ in range(n)]
	# 	for i in range(n):
	# 		if random_array[i]:
	# 			sw_flpbit(cur_sol.state[0].vector, i)

	cdef state_t *stt = cur_sol.state

	if solver == OPTIMIZE:
		# Run sampling for optimization based on user input
		with nogil:
			feasible = ctg(stt, cnstrs, obctv, M_c, stppngtm, &qtg_applications, dpth, slvr, stpvl, cb_ptr, &brk_tm, global_opt.state, ignore_constraint_search)
	else:
		# Run satisfyability solver with increasing delta (only up to 7)
		# delta determines M and bias
		stpvl = -len(con)
		delta = 0
		# for delta in range(1, max_delta):
		while delta < max_delta:
			delta += 1
			# print(delta)
			M_c = int((cur_sol.state[0].vector.bits / delta) ** (delta / 2) * np.exp(delta / 2))
			# M_c = (cur_sol.state[0].vector.bits / delta) ** (delta / 2)
			# print(cur_sol.state[0].vector.bits / delta - 1)
			set_bias_wrapper(cur_sol.state[0].vector.bits / delta - 1)

			with nogil:
				feasible = ctg(stt, cnstrs, obctv, M_c, stppngtm, &qtg_applications, dpth, slvr, stpvl, cb_ptr, &brk_tm, global_opt.state, False)

			if stt.tot_profit == stpvl:
				not_stop[0] = 0
				t_total: float = time.time() - t_start
				# print(qtg_applications)
				signal.raise_signal(signal.SIGINT)
				break
			if not not_stop[0]:
				break

	cur_sol.get_x()
	arr = []
	for i in range(cur_sol.state[0].vector.bits):
		arr.append(sw_tstbit(cur_sol.state[0].vector, i))

	cur_sol.arr = np.array(arr, dtype = np.int32)
	return cur_sol, qtg_applications, feasible, arr, brk_tm, t_total

cpdef run_bfs(
		initial: state_py,
		con: new_constraint,
		obj: new_constraint,
		M: int,
		depth_look_ahead: int,
		solver: int,
		int64_t stop_val,
		object callback,
		int max_delta,
		int reset_delta):

	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c
	cur_sol : state_py = copy(initial)

	cdef size_t qtg_applications = 0;
	cdef int dpth = depth_look_ahead
	cdef int slvr = solver
	cdef int64_t stpvl = stop_val
	cdef int M_c = M
	cdef state_t *stt = cur_sol.state
	cdef new_constraints_t *cnstrs = &con.con
	cdef new_constraints_t *obctv = &obj.con
	cdef int found_new;

	bfs(stt, cnstrs, obctv, M_c, &qtg_applications, dpth, slvr, stpvl, cb_ptr)

	cur_sol.get_x()
	arr = []
	for i in range(cur_sol.state[0].vector.bits):
		arr.append(sw_tstbit(cur_sol.state[0].vector, i))

	cur_sol.arr = np.array(arr, dtype = np.int32)
	return cur_sol, qtg_applications
	# return qtg_applications

cpdef run_local_search(initial: state_py,
		con: new_constraint,
		obj: new_constraint,
        int distance,
		int stopping_time,
        int solver,
        int64_t stop_val,
        object callback,
        int max_worse_acceptances,
        int stopping_condition):

	new_state: state_py = copy(initial)
	cdef state_t *st = new_state.state
	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c
	with nogil:
		local_search(st, &con.con, &obj.con, distance, stopping_time, solver, stop_val, cb_ptr, max_worse_acceptances, stopping_condition)

	new_state.get_x()
	return new_state


cpdef run_quantum_local_search(initial: state_py,
		con: new_constraint,
		obj: new_constraint,
        int distance,
        callback):

	srand(100 * os.getpid() + int(time.time()))
	cdef state_t *st = initial.state
	cdef size_t oracle_applications = 0
	global python_callback
	python_callback = callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c

	with nogil:
		quantum_local_search(&obj.con, &con.con, st, distance, &oracle_applications, cb_ptr)

cpdef run_general_greedy(initial: state_py, con: new_constraint, obj: new_constraint):
	cdef int break_item = 0;
	initial_state_preparation(initial.state, NULL, &con.con, &obj.con, 3, &break_item)
	return break_item


def reset_c_flags():
	reset_flag()

cdef class model:

	def __cinit__(self):
		self.c_model.runtime = 0
		self.c_model.value = 0

	@property
	def objective_value(self):
		return self.c_model.value

	@property
	def runtime(self):
		return self.c_model.value
