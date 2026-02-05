import random
import signal
import time
from copy import copy
from random import randint

import numpy as np
import os

from .branching import set_bias_wrapper, set_seed
from .Constants import *
from .Constraint cimport new_constraint
from .Model import Model

# Class containing all the states information and acts as wrapper for C functionality

cdef class incumbents:
	def __cinit__(self, n, st: state_py):
		self.incumbent = init_incumbents(n, st.state)
		self.ctx = NULL

	def __init__(self, n, st: state_py):
		pass

	def __dealloc__(self):
		free_incumbents(self.incumbent)
		# Note: ctx is NOT freed here - it's owned by the caller (run_sampling)

	def __str__(self):
		print_incumbents(self.incumbent)
		return ""

	cdef void _set_ctx(self, solver_ctx_t* ctx):
		"""Set the solver context for monte carlo sampler calls (C-level)"""
		self.ctx = ctx

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
		incumbents_list = []
		total_calls = 0

		cdef state_t *st
		cdef int init_samples = 0
		cdef solver_ctx_t *ctx = self.ctx
		t1 = time.time()

		# If no ctx was set, create one for this call
		cdef bint owns_ctx = False
		if ctx == NULL:
			ctx = solver_ctx_create()
			owns_ctx = True

		try:
			for i in range(self.incumbent[0].head):
				st = <state_t *> &self.incumbent[0].states[i]
				init_samples = self.incumbent[0].initial_samples[i]
				if solver == OPTIMIZE:
					if self.incumbent[0].search_stage[i] == 1:
						with nogil:
							ampl = CSearch_opt_sat_monte_carlo_sampler(
								ctx, st, &con.con, &obj.con, error, 1,
								init_samples
						)
					elif self.incumbent[0].search_stage[i] == 2:
						with nogil:
							ampl = CSearch_opt_sat_monte_carlo_sampler(ctx, st, &con.con, &obj.con, error, -1, init_samples
						)
					else:
						with nogil:
							ampl = CSearch_opt_monte_carlo_sampler(ctx, st, &con.con, &obj.con, error, init_samples)
				else:
					with nogil:
						ampl = CSearch_sat_monte_carlo_sampler(ctx, st, &con.con, error, init_samples)

				if ampl == 0.:
					ampl = StateProbability(ctx, &self.incumbent[0].states[i + 1], &self.incumbent[0].states[i])

				if ampl == 1.:
					m0 = 0.
					rounds = 1
				else:
					m0 = 1. / np.sin(2 * np.arcsin(np.sqrt(ampl)))
					rounds = int(np.ceil(np.log(m0) / np.log(6. / 5))) + 4 # estimate number of rounds

				# use tightest bound for quantum search
				total_calls += int(np.floor( 9 * m0 )) + rounds
				if -self.incumbent[0].states[i + 1].tot_profit >= 0:
					incumbents_list.append((-self.incumbent[0].states[i + 1].tot_profit, total_calls))
		finally:
			if owns_ctx:
				solver_ctx_free(ctx)

		return incumbents_list

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

# define callback functionality ===============================

# Python-compatible C wrapper
cdef void my_callback_c() with gil:
	if python_callback is not None:
		python_callback()

# python function to store the callback
cdef object python_callback = None

cpdef run_sampling(Model mod, object callback, not_stop: list[int]):
	t_start: float = time.time()
	t_total: float = 0
	set_seed(randint(0, 10000000))
	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c

	n = mod.mod[0].initial_state[0].vector.bits

	cur_sol: state_py = state_py(0, [0] * n)
	free_state(cur_sol.state, 1)
	cur_sol.state = copy_state(copy_state(mod.mod[0].initial_state))

	inc = incumbents(n, cur_sol)

	cdef state_t *stt = cur_sol.state
	cdef model_t *mod_ptr = <model_t *> mod.mod

	# Create solver context for this solve - manages per-solve state
	cdef solver_ctx_t *ctx = solver_ctx_create()
	# Share ctx with incumbents for monte carlo sampler calls
	inc._set_ctx(ctx)

	try:
		if mod.mod[0].solver == OPTIMIZE:
			# Run sampling for optimization based on user input
			with nogil:
				feasible = ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent)
		else:
			# Run satisfyability solver with increasing delta (only up to 7)
			# delta determines M and bias
			stpvl = -len(mod.mod[0].con[0].num_constraints)
			delta = 0
			mod.mod[0].stop_val = stpvl
			# for delta in range(1, max_delta):
			while delta < mod.mod[0].max_delta:
				delta += 1
				M_c = int((cur_sol.state[0].vector.bits / delta) ** (delta / 2) * np.exp(delta / 2))
				# Configure bias on the context for this delta iteration
				solver_ctx_set_bias(ctx, cur_sol.state[0].vector.bits / delta - 1)
				mod.mod[0].M = M_c

				with nogil:
					feasible = ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent)
				if stt.tot_profit == stpvl:
					not_stop[0] = 0
					t_total = time.time() - t_start
					signal.raise_signal(signal.SIGINT)
					break
				if not not_stop[0]:
					break

		cur_sol.get_x()
		arr = []
		for i in range(cur_sol.state[0].vector.bits):
			arr.append(sw_tstbit(cur_sol.state[0].vector, i))

		incumb = []
		# if mod.mod[0].monte_carlo_estimate:
		# 	if (mod.mod[0].solver == OPTIMIZE):
		# 		incumb = inc.estimate_grover_iterations(<new_constraints_t *> mod.mod[0].con, <new_constraints_t *> mod.mod[0].obj, 0.1, mod.mod[0].solver)

		del inc

		cur_sol.arr = np.array(arr, dtype = np.int32)
		return cur_sol, mod.mod[0].qtg_applications, feasible, arr, t_total, incumb
	finally:
		solver_ctx_free(ctx)


cpdef run_local_search(Model mod, object callback):
	cur_sol: state_py = state_py(0, [0] * mod.mod[0].initial_state[0].vector.bits)
	free_state(cur_sol.state, 1)
	cur_sol.state = copy_state(copy_state(mod.mod[0].initial_state))

	cdef state_t *st = cur_sol.state
	global python_callback
	python_callback = callback

	# python callback to c callback
	cdef callback_t cb_ptr = <callback_t> my_callback_c

	# Create solver context for this local search
	cdef solver_ctx_t *ctx = solver_ctx_create()
	try:
		with nogil:
			local_search(ctx, st, mod.mod, cb_ptr)
		return cur_sol
	finally:
		solver_ctx_free(ctx)

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

def reset_c_flags():
	"""Legacy function - no longer needed with ctx-based lifecycle.

	The solver context (ctx) manages stop flags per-solve, so there's no
	global state to reset. This function is kept for backward compatibility
	but does nothing.
	"""
	pass