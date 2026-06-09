import logging
import random
import signal
import threading
import time
import time as time_mod
from copy import copy
from random import randint

import numpy as np
import os

from libc.stdlib cimport srand, calloc, free
from .Constants import *
from .Constraint cimport new_constraint
from .Model import Model
from .phase_params import PhaseParamResolver, DEFAULTS as _PHASE_DEFAULTS, radius_to_bias

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

# Python-compatible C wrapper. Matches the M0e callback_t ABI void(void* ctx):
# `ctx_ptr` is a solver_ctx_t* (or NULL from quantum_local_search). We read the
# per-worker, never-reset ctx->oracle_count (M0d) and hand it to the Python
# callback so history is oracle-indexed, not wall-clock-indexed (NORTHSTAR §11).
cdef void my_callback_c(void* ctx_ptr) with gil:
	cdef unsigned long long oracle = 0
	if ctx_ptr is not NULL:
		oracle = <unsigned long long> (<solver_ctx_t*> ctx_ptr).oracle_count
	if python_callback is not None:
		python_callback(oracle)

# python function to store the callback
cdef object python_callback = None


# Per-thread/per-solve callback state for thread-safe history tracking.
# Replaces the old module-level cdef globals that caused cross-contamination
# when multiple solve() calls ran concurrently.

class _SolveState:
	"""Per-thread/per-solve callback state."""
	__slots__ = ('history', 'prev_best', 'mod', 'original_callback',
	             'start_time', 'mode')
	def __init__(self, mod, original_callback, start_time, mode):
		self.history = []
		self.prev_best = None
		self.mod = mod
		self.original_callback = original_callback
		self.start_time = start_time
		self.mode = mode

_solve_states = {}  # dict[int, _SolveState] keyed by threading.get_ident()


def _history_callback_fn(oracle):
	"""Thread-safe callback that accumulates oracle-indexed improvement history.

	`oracle` is this worker's cumulative oracle count (ctx->oracle_count) at the
	moment of a global_opt improvement, supplied by my_callback_c. History entries
	are (value, oracle:int) (NORTHSTAR §11 M0e) -- the running global-best value
	stamped with the per-worker oracle count, replacing the old wall-clock stamp.

	Looks up per-thread state via threading.get_ident() to support
	concurrent solve() calls without cross-contamination.
	"""
	tid = threading.get_ident()
	state = _solve_states.get(tid)
	if state is None:
		return
	try:
		mod = state.mod
		value = mod._callback_value()
		if state.prev_best is None or value != state.prev_best:
			state.history.append((value, int(oracle)))
			state.prev_best = value
	except Exception:
		logging.warning("History callback: error computing entry, skipping", exc_info=True)
	# Call original user callback if provided
	if state.original_callback is not None:
		try:
			state.original_callback()
		except Exception:
			logging.warning("History callback: error in user callback", exc_info=True)


def _drop_oracle_arg(cb):
	"""Adapt a user zero-arg callback to the M0e (oracle:int)->None callback ABI.

	my_callback_c now calls python_callback(oracle); user callbacks remain
	zero-arg, so the direct-assignment paths wrap them to drop the oracle stamp.
	"""
	def _wrapped(oracle):
		cb()
	return _wrapped

cdef _set_phase_bias(solver_ctx_t *ctx, str phase, double bias):
	"""Set bias for a specific phase on the solver context."""
	if phase == 'sat':
		solver_ctx_set_sat_bias(ctx, bias)
	elif phase == 'opt_sat':
		solver_ctx_set_opt_sat_bias(ctx, bias)
	else:
		solver_ctx_set_opt_bias(ctx, bias)

cdef _set_phase_branching_factor(solver_ctx_t *ctx, str phase, double factor):
	"""Set branching_factor for a specific phase on the solver context."""
	if phase == 'sat':
		solver_ctx_set_sat_branching_factor(ctx, factor)
	elif phase == 'opt_sat':
		solver_ctx_set_opt_sat_branching_factor(ctx, factor)
	else:
		solver_ctx_set_opt_branching_factor(ctx, factor)

cdef _set_phase_bias_factor(solver_ctx_t *ctx, str phase, double factor):
	"""Set bias_factor for a specific phase on the solver context."""
	if phase == 'sat':
		solver_ctx_set_sat_bias_factor(ctx, factor)
	elif phase == 'opt_sat':
		solver_ctx_set_opt_sat_bias_factor(ctx, factor)
	else:
		solver_ctx_set_opt_bias_factor(ctx, factor)

cdef _set_phase_weights(solver_ctx_t *ctx, str phase, weights, int n):
	"""Set branching_weights for a specific phase on the solver context."""
	cdef double *bw_ptr = NULL
	arr_bw = np.array(weights, dtype=np.double)
	bw_ptr = <double *> calloc(n, sizeof(double))
	for i in range(n):
		bw_ptr[i] = <double> arr_bw[i]
	if phase == 'sat':
		solver_ctx_set_sat_branching_weights(ctx, bw_ptr, n)
	elif phase == 'opt_sat':
		solver_ctx_set_opt_sat_branching_weights(ctx, bw_ptr, n)
	else:
		solver_ctx_set_opt_branching_weights(ctx, bw_ptr, n)
	free(bw_ptr)

cdef _propagate_phase_params(solver_ctx_t *ctx, Model mod, int n):
	"""Resolve and propagate phase-specific parameters to the solver context.

	Uses PhaseParamResolver to resolve all 18 phase-specific parameters
	with fallback: phase-specific > unprefixed > built-in default.
	Sets per-phase bias, weights, and factors via phase-specific C setters.
	A per-phase branching_radius (if set) takes precedence over branching_bias
	via bias = n/r - 2 (scale-invariant radius, NORTHSTAR §4/§1.5).
	Variable ordering is set once for all phases via solver_ctx_set_variable_order.
	"""
	cdef double *prio_ptr = NULL

	params = mod._params if hasattr(mod, '_params') else {}
	# Use n/4 as default bias if not set (matches close() default)
	defaults = dict(_PHASE_DEFAULTS)
	if 'branching_bias' not in params:
		defaults['branching_bias'] = n / 4.0

	resolver = PhaseParamResolver(params, defaults)
	resolved = resolver.resolve_all()

	for phase in ('sat', 'opt_sat', 'opt'):
		p = resolved[phase]

		# Bias: a target radius (branching_radius) takes precedence over
		# branching_bias -- bias = n/r - 2 makes the realized Hamming radius r
		# at every n (scale-invariant lever, NORTHSTAR §4/§1.5).
		radius = p['branching_radius']
		if radius is not None:
			bias = radius_to_bias(n, radius)
		else:
			bias = p['branching_bias']
		if bias is not None:
			_set_phase_bias(ctx, phase, bias)

		# Branching factor
		bf = p['branching_factor']
		if bf is not None:
			_set_phase_branching_factor(ctx, phase, bf)

		# Bias factor
		bif = p['bias_factor']
		if bif is not None:
			_set_phase_bias_factor(ctx, phase, bif)

		# Weights
		weights = p['branching_weights']
		if weights is not None:
			_set_phase_weights(ctx, phase, weights, n)

	# look_ahead_factor is not phase-specific; propagate from unprefixed param
	param_look_factor = params.get('look_ahead_factor')
	if param_look_factor is not None:
		solver_ctx_set_look_ahead_factor(ctx, param_look_factor)

	# Variable ordering: set from priorities if available, else default.
	# solver_ctx_set_variable_order sets all three phases at once.
	# Use the first non-None priorities found (phase-specific or unprefixed).
	priorities = None
	for phase in ('sat', 'opt_sat', 'opt'):
		p_prio = resolved[phase]['variable_priorities']
		if p_prio is not None:
			priorities = p_prio
			break

	if priorities is not None:
		arr_prio = np.array(priorities, dtype=np.double)
		prio_ptr = <double *> calloc(n, sizeof(double))
		for i in range(n):
			prio_ptr[i] = <double> arr_prio[i]
		solver_ctx_set_variable_order(ctx, prio_ptr, n)
		free(prio_ptr)
	else:
		solver_ctx_set_default_order(ctx, n)


cpdef run_sampling(Model mod, object callback, not_stop: list[int], bint track_history=True,
                   double solve_start_time=0.0, int worker_id=0):
	preprocess_start = time_mod.monotonic()
	t_start: float = time.time()
	t_total: float = 0
	srand(randint(0, 10000000))
	global python_callback

	# Determine callback pointer based on track_history and user callback
	cdef callback_t cb_ptr
	if track_history or callback is not None:
		cb_ptr = <callback_t> my_callback_c
	else:
		cb_ptr = NULL

	cdef unsigned long long seed_used_val = 0

	n = mod.mod[0].initial_state[0].vector.bits

	cur_sol: state_py = state_py(0, [0] * n)
	free_state(cur_sol.state, 1)
	cur_sol.state = copy_state(copy_state(mod.mod[0].initial_state))

	inc = incumbents(n, cur_sol)

	cdef state_t *stt = cur_sol.state
	cdef model_t *mod_ptr = <model_t *> mod.mod

	# Create solver context for this solve - manages per-solve state
	cdef solver_ctx_t *ctx = solver_ctx_create()

	# Configure seed from model (if exposed)
	if hasattr(mod, '_seed') and mod._seed is not None:
		ctx.seed = mod._seed

	# Configure num_threads from model (if exposed)
	if hasattr(mod, '_num_threads') and mod._num_threads is not None:
		ctx.num_threads = mod._num_threads

	# Decorrelate this portfolio worker's PRNG stream. Each worker jumps the
	# shared master stream worker_id times so fixed-seed workers explore
	# independently instead of collapsing onto one trajectory; worker_id == 0
	# reproduces the legacy stream, preserving single-worker determinism.
	solver_ctx_set_worker_id(ctx, worker_id)

	# Initialize PRNG with configured seed/threads/worker_id
	solver_ctx_init_prng(ctx)

	# Propagate phase-specific branching parameters to solver context
	_propagate_phase_params(ctx, mod, n)

	# Share ctx with incumbents for monte carlo sampler calls
	inc._set_ctx(ctx)

	# Set up per-thread callback state for history tracking
	if track_history:
		tid = threading.get_ident()
		mode = mod.mod[0].solver
		_solve_states[tid] = _SolveState(mod, callback, solve_start_time, mode)
		python_callback = _history_callback_fn
	elif callback is not None:
		# Direct user callback without history wrapping; wrap to drop the M0e oracle arg.
		python_callback = _drop_oracle_arg(callback)

	# End preprocessing, start solve timing
	preprocess_end = time_mod.monotonic()
	preprocessing_time_ms = (preprocess_end - preprocess_start) * 1000.0

	try:
		if mod.mod[0].solver == OPTIMIZE:
			# Run sampling for optimization based on user input
			with nogil:
				feasible = ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent)
		else:
			# Run satisfyability solver with increasing delta (only up to 7)
			# delta determines M and bias
			stpvl = -mod.mod[0].con[0].num_constraints
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
					solver_ctx_request_stop(ctx)
					break
				if not not_stop[0]:
					break

		# Capture history from per-thread state
		if track_history:
			history = list(_solve_states[threading.get_ident()].history)
		else:
			history = []

		cur_sol.get_x()
		arr = []
		for i in range(cur_sol.state[0].vector.bits):
			arr.append(sw_tstbit(cur_sol.state[0].vector, i))

		# Per-worker FINAL incumbent (value, feasible) for §8.3 median-of-P (M0e).
		# CSearch_opt accepts only strictly-improving moves (solver.c:396), so the
		# final cur_sol is this worker's best -> max over workers == global_opt,
		# keeping best-of-P consistent with median-of-P. Value uses the same
		# sign/sat convention as Model._callback_value.
		if mod.mod[0].solver == SATISFY:
			final_value = mod.mod[0].con[0].num_constraints + cur_sol.state[0].tot_profit
		else:
			final_value = cur_sol.state[0].tot_profit * mod.sense
		incumb = (final_value, bool(cur_sol.state[0].feasible))

		del inc

		cur_sol.arr = np.array(arr, dtype = np.int32)
		# Store actual seed used back to model for reproducibility tracking
		seed_used_val = ctx.seed_used
		try:
			mod._seed_used = seed_used_val
		except AttributeError:
			pass  # Model doesn't have _seed_used attribute (old code path)

		# Index 1 is this worker's own cumulative oracle count (race-free,
		# never-reset); read here while ctx is still alive (the finally below
		# frees it). Replaces the racy shared mod.qtg_applications.
		#
		# Index 8 is this worker's opt-phase branching diagnostics (M0g / bd
		# 8an.1.7): raw per-worker counters over every candidate CSearch_opt
		# generated. Pooled across workers in Model.solve() into the realized
		# Hamming-radius mean+var and free-decision fraction f(n) that the §9
		# scale-invariance test checks. Read here while ctx is still alive.
		branch_diag = {
			"opt_candidates": <unsigned long long> ctx.opt_candidates,
			"opt_flip_sum":   <unsigned long long> ctx.opt_flip_sum,
			"opt_flip_sumsq": <unsigned long long> ctx.opt_flip_sumsq,
			"opt_free_sum":   <unsigned long long> ctx.opt_free_sum,
		}
		# Index 9 is this worker's own wall-clock telemetry (ctx.runtime, seconds;
		# bd lif). Read here while ctx is still alive (the finally below frees it).
		# solve() reduces it max-over-workers into mod->runtime, replacing the racy
		# unlocked shared mod->runtime write ctg used to do every iteration.
		return cur_sol, <unsigned long long> ctx.oracle_count, feasible, arr, t_total, incumb, history, preprocessing_time_ms, branch_diag, <double> ctx.runtime
	finally:
		# Clean up per-thread state
		if track_history:
			_solve_states.pop(threading.get_ident(), None)
		solver_ctx_free(ctx)


cpdef run_local_search(Model mod, object callback, bint track_history=True, double solve_start_time=0.0):
	preprocess_start = time_mod.monotonic()
	cur_sol: state_py = state_py(0, [0] * mod.mod[0].initial_state[0].vector.bits)
	free_state(cur_sol.state, 1)
	cur_sol.state = copy_state(copy_state(mod.mod[0].initial_state))

	cdef state_t *st = cur_sol.state
	cdef unsigned long long seed_used_local = 0
	cdef double *bw_ptr_ls = NULL
	global python_callback

	# Determine callback pointer based on track_history and user callback
	cdef callback_t cb_ptr
	if track_history or callback is not None:
		cb_ptr = <callback_t> my_callback_c
	else:
		cb_ptr = NULL

	# Create solver context for this local search
	cdef solver_ctx_t *ctx = solver_ctx_create()

	# Configure seed from model (if exposed)
	if hasattr(mod, '_seed') and mod._seed is not None:
		ctx.seed = mod._seed

	# Configure num_threads from model (if exposed)
	if hasattr(mod, '_num_threads') and mod._num_threads is not None:
		ctx.num_threads = mod._num_threads

	# Initialize PRNG with configured seed/threads
	solver_ctx_init_prng(ctx)

	# Propagate branching parameters to solver context
	n_ls = mod.mod[0].initial_state[0].vector.bits

	# Branching bias (from _params, default n/4)
	param_bias_ls = mod._params.get('branching_bias') if hasattr(mod, '_params') else None
	if param_bias_ls is not None:
		solver_ctx_set_bias(ctx, param_bias_ls)
	else:
		solver_ctx_set_bias(ctx, n_ls / 4)

	# Individual branching factors
	param_branching_factor_ls = mod._params.get('branching_factor') if hasattr(mod, '_params') else None
	if param_branching_factor_ls is not None:
		solver_ctx_set_branching_factor(ctx, param_branching_factor_ls)

	param_bias_factor_ls = mod._params.get('bias_factor') if hasattr(mod, '_params') else None
	if param_bias_factor_ls is not None:
		solver_ctx_set_bias_factor(ctx, param_bias_factor_ls)

	param_look_factor_ls = mod._params.get('look_ahead_factor') if hasattr(mod, '_params') else None
	if param_look_factor_ls is not None:
		solver_ctx_set_look_ahead_factor(ctx, param_look_factor_ls)

	# Branching weights (new unified array)
	param_weights_ls = mod._params.get('branching_weights') if hasattr(mod, '_params') else None
	if param_weights_ls is not None:
		arr_bw_ls = np.array(param_weights_ls, dtype=np.double)
		bw_ptr_ls = <double *> calloc(arr_bw_ls.shape[0], sizeof(double))
		for i in range(arr_bw_ls.shape[0]):
			bw_ptr_ls[i] = <double> arr_bw_ls[i]
		solver_ctx_set_branching_weights(ctx, bw_ptr_ls, len(param_weights_ls))
		free(bw_ptr_ls)
		bw_ptr_ls = NULL

	# Set up per-thread callback state for history tracking
	if track_history:
		tid = threading.get_ident()
		mode = mod.mod[0].solver
		_solve_states[tid] = _SolveState(mod, callback, solve_start_time, mode)
		python_callback = _history_callback_fn
	elif callback is not None:
		# Direct user callback without history wrapping; wrap to drop the M0e oracle arg.
		python_callback = _drop_oracle_arg(callback)

	# End preprocessing, start solve timing
	preprocess_end = time_mod.monotonic()
	preprocessing_time_ms = (preprocess_end - preprocess_start) * 1000.0

	try:
		with nogil:
			local_search(ctx, st, mod.mod, cb_ptr)

		# Capture history from per-thread state
		if track_history:
			history = list(_solve_states[threading.get_ident()].history)
		else:
			history = []

		# Store actual seed used back to model for reproducibility tracking
		seed_used_local = ctx.seed_used
		try:
			mod._seed_used = seed_used_local
		except AttributeError:
			pass  # Model doesn't have _seed_used attribute (old code path)

		solve_time_ms = mod.mod[0].runtime * 1000.0
		return cur_sol, history, preprocessing_time_ms, solve_time_ms
	finally:
		# Clean up per-thread state
		if track_history:
			_solve_states.pop(threading.get_ident(), None)
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
	# Wrap the zero-arg user callback to the M0e (oracle:int)->None ABI (ctx is NULL here).
	python_callback = _drop_oracle_arg(callback) if callback is not None else None
	cdef callback_t cb_ptr = <callback_t> my_callback_c

	with nogil:
		quantum_local_search(&obj.con, &con.con, st, distance, &oracle_applications, cb_ptr)

def set_predicted_params(mod, double bias, double branching_factor,
                         double bias_factor, weights, variable_priorities, int n):
	"""Set all predicted parameters on the model in one call.

	Stores parameters in the model's _params dict, bypassing per-parameter
	validation for performance in the ES prediction hot path.

	Parameters
	----------
	mod : Model
		A Model instance (or any object with a _params dict).
	bias : float
		Branching bias value.
	branching_factor : float
		Branching factor value.
	bias_factor : float
		Bias factor value.
	weights : numpy.ndarray
		Per-variable branching weights, shape (n,).
	variable_priorities : numpy.ndarray
		Per-variable priority ordering, shape (n,).
	n : int
		Number of variables.
	"""
	mod._params['branching_bias'] = bias
	mod._params['branching_factor'] = branching_factor
	mod._params['bias_factor'] = bias_factor
	mod._params['branching_weights'] = weights
	mod._params['variable_priorities'] = variable_priorities


def reset_c_flags():
	"""Legacy function - no longer needed with ctx-based lifecycle.

	The solver context (ctx) manages stop flags per-solve, so there's no
	global state to reset. This function is kept for backward compatibility
	but does nothing.
	"""
	pass