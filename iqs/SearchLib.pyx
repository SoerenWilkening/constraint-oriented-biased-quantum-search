import random
import signal
import sys
import time
from copy import copy
from random import randint

import numpy as np

from .Constants import *

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

	def process(self, int n, enforce_density = False):
		tot = 0
		for i in range(self.con.num_constraints):
			tot += self.con.num_clauses[i]

		# print(tot, n * self.con.num_constraints)

		if 10 * tot > n * self.con.num_constraints or enforce_density:
			preprocessing(n, &self.con)
			return DENSE
		else:
			preprocessing_sparse(n, &self.con)
			return SPARSE

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

cdef class incumbents:
	def __cinit__(self, n, st: state_py):
		self.incumbent = init_incumbents(n, st.state)

	def __init__(self, n, st: state_py):
		pass

	def __dealloc__(self):
		free_incumbents(self.incumbent)

	def __str__(self):
		print_incumbents(self.incumbent)
		return ""

	def emulate_QSearch(self, ampl):
		if ampl == 0.: return 0
		calls = 0
		c = 6. / 5
		rounds = 0

		while True:
			rounds += 1
			m = np.ceil(c ** rounds)
			j = randint(0, m)
			calls += 2 * j + 1

			amplified = np.sin((2 * j + 1) * np.arcsin(np.sqrt(ampl))) ** 2
			# print(m, j, amplified, np.arcsin(np.sqrt(ampl)))
			if amplified >= random.random():
				return calls

	def estimate_grover_iterations(self, new_constraint con, new_constraint obj, double error, int solver):
		incumbents = []
		total_calls = 0

		# for i in range(self.incumbent[0].head):
		# print(self.incumbent[0].head)
		cdef state_t *st
		cdef int init_samples = 0
		t1 = time.time()
		for i in range(self.incumbent[0].head):
			st = <state_t *> &self.incumbent[0].states[i]
			init_samples = self.incumbent[0].initial_samples[i]
			if solver == OPTIMIZE:
				if self.incumbent[0].search_stage[i] == 1:
					with nogil:
						ampl = CSearch_opt_sat_monte_carlo_sampler(
							st, &con.con, &obj.con, error, 1,
							init_samples
					)
				elif self.incumbent[0].search_stage[i] == 2:
					with nogil:
						ampl = CSearch_opt_sat_monte_carlo_sampler(st, &con.con, &obj.con, error, -1, init_samples
					)
				else:
					with nogil:
						ampl = CSearch_opt_monte_carlo_sampler(st, &con.con, &obj.con, error, init_samples)
			else:
				with nogil:
					# if (con.num_constraints)
					ampl = CSearch_sat_monte_carlo_sampler(st, &con.con, error, init_samples)

			if ampl == 0.:
				ampl = StateProbability(&self.incumbent[0].states[i + 1], &self.incumbent[0].states[i])

			if ampl == 1.:
				m0 = 0.
				rounds = 1
			else:
				m0 = 1. / np.sin(2 * np.arcsin(np.sqrt(ampl)))
				rounds = int(np.ceil(np.log(m0) / np.log(6. / 5))) + 4 # estimate number of rounds

			# use tightest bound for quantum search
			total_calls += int(np.floor( 9 * m0 )) + rounds
			# total_calls += self.emulate_QSearch(ampl)
			if -self.incumbent[0].states[i + 1].tot_profit >= 0:
				incumbents.append((-self.incumbent[0].states[i + 1].tot_profit, total_calls))

		# print("done in ", time.time() - t1, "s")
		return incumbents

cdef class state_py:
	def __cinit__(self, int64_t ObjVal, array: list | np.ndarray) -> None:
		self.num_states = 1
		arr = np.array(array, dtype = np.int32)
		self.arr = arr  # easier handling when list it required

		cdef int * ptr = <int *> calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]): ptr[i] = <int> arr[i]
		self.state = init_state(ObjVal, ptr, arr.shape[0])
		free(<void *> ptr)

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
		# print_state(&self.state[])
		for i in range(self.num_states):
			print_state(&self.state[i])
			print()
		return ""

	def __dealloc__(self) -> None:
		if self.state is not NULL:
			free_state(self.state, self.num_states)

	# def __del__(self):
	# 	del self.arr

	@property
	def objective_value(self):
		return self.state[0].tot_profit

	def __iter__(self):
		return [sw_tstbit(self.state[0].vector, i) for i in range(self.state[0].vector.bits)].__iter__()
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

	def update(self, state_py threshold, int sense) -> state_py:
		up = state_py(0, [0])
		free_state(up.state, up.num_states)
		up.state = <state_t *> updated(self.state, self.num_states, &up.num_states, threshold.state, sense)

		return up

	def read(self, str name, int n) -> None:
		# print(name)
		directoy = os.path.dirname(name)
		# print(directoy)
		value = str(name).split("states_")[0].replace(directoy + "/", "")
		# print(value, directoy)
		files = [f"{directoy}/{i}".encode() for i in os.listdir(directoy) if
		         value in i and "test" not in i and "states" in i]
		# print(files)
		# sys.stdout.flush()

		num_files = len(files)
		# print(num_files)
		sys.stdout.flush()
		cdef char** f = <char **> calloc(num_files, sizeof(char *))
		for i in range(num_files):
			# print(i)
			sys.stdout.flush()
			file_bytes = files[i]
			f[i] = <char *> calloc(len(file_bytes) + 1, sizeof(char))
			for j in range(len(file_bytes)):
				f[i][j] = file_bytes[j]

		free_state(self.state, self.num_states)
		self.state = read_states(f, num_files, &self.num_states, n)

def QSearch_wrapper(bfs: state_py, int M) -> tuple[state_py | None, int, int]:
	cdef size_t iterations = 0
	cdef size_t rounds = 0
	res: state_py = state_py(11, [0, 0])
	free_state(res.state, 1)
	cdef size_t index = 0;
	res.state = QSearch(bfs.state, bfs.num_states, &iterations, &rounds, M, &index)
	if res.state == NULL:
		return None, iterations, rounds
	return res, iterations, rounds

import os

def store(states: list[float, tuple[list[int], list[int]]], where: bytes) -> int:
	if os.path.exists(where): return 1

	file = open(where, "a")
	for i in states:
		file.write(f'{int(i[0])} ')
		for j in range(len(i[1])):
			file.write(f'{i[1][j]} {i[2][j]} ')
		file.write("\n")

	file.close()
	return 0

def read_nodes_wrapper(str name, n: int) -> int | state_py:
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
	cur_sol: state_py = copy(initial)

	cdef size_t qtg_applications = 0;
	cdef int dpth = depth_look_ahead
	cdef int slvr = solver
	cdef int64_t stpvl = stop_val
	cdef int M_c = M
	cdef int stppngtm = stopping_time
	cdef new_constraints_t *cnstrs = &con.con
	cdef new_constraints_t *obctv = &obj.con
	cdef int feasible;
	cdef int n = cur_sol.state[0].vector.bits

	inc = incumbents(n, initial)

	# if solver == SATISFY:
	# 	random_array = [randint(0, 1) for _ in range(n)]
	# 	for i in range(n):
	# 		if random_array[i]:
	# 			sw_flpbit(cur_sol.state[0].vector, i)

	cdef state_t *stt = cur_sol.state

	if solver == OPTIMIZE:
		# Run sampling for optimization based on user input
		with nogil:
			feasible = ctg(stt, cnstrs, obctv, M_c, stppngtm, &qtg_applications, dpth, slvr,
			               stpvl, cb_ptr, global_opt.state, ignore_constraint_search,
			               inc.incumbent)
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
				feasible = ctg(stt, cnstrs, obctv, M_c, stppngtm, &qtg_applications, dpth, slvr, stpvl,
				               cb_ptr, global_opt.state, False,
				               inc.incumbent)
			# print(stt.tot_profit, qtg_applications)
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


	if (solver == OPTIMIZE):
		incumb = inc.estimate_grover_iterations(con, obj, 0.1, solver)
	else:
		incumb = [] # satisfy needs more adjustments
	del inc

	cur_sol.arr = np.array(arr, dtype = np.int32)
	return cur_sol, qtg_applications, feasible, arr, t_total, incumb

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
	cur_sol: state_py = copy(initial)

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
		local_search(st, &con.con, &obj.con, distance, stopping_time, solver, stop_val, cb_ptr, max_worse_acceptances,
		             stopping_condition)

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
