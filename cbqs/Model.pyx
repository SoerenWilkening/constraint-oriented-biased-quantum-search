from copy import copy
from time import time
import warnings
from warnings import warn

import numpy as np
from joblib import Parallel, delayed
# CircuitBackendBinder is optional - requires circuit_backend directory
try:
	from .CircuitBackendBinder import circuit
except ImportError:
	circuit = None
from .Constants import *
from .Expression import Variable
from .Expression cimport Expression
from .state import state_py
from .state cimport init_state
from .Constraint import new_constraint
from .Constraint cimport add_expression_to_constraints, process_constraints
from .Expression cimport expression_t
from .branching import set_seed, set_bias_wrapper, set_factors_wrapper, set_obj_dependence_wrapper
from .SearchLib import (run_local_search, run_quantum_local_search, reset_c_flags)
from .SearchLib import run_sampling
from .StateGenerator import exact_simulator
from .state_sampler import approximate_state
from .SearchLib cimport initial_state_preparation
from .state cimport print_state
from .state cimport sw_tstbit


def _merge_duplicate_variable_terms(Expression expr):
	"""Merge duplicate variable terms in an expression.

	Scans all terms and if two terms have the same set of variable indices,
	adds the coefficient of the later term to the earlier one and zeroes
	the later term. For example, 3*x1 + 5*x1 becomes 8*x1.

	This operates directly on the C expression_t structure for efficiency.
	"""
	cdef int i, j, k
	cdef int expr_size = expr.expr[0].expr_size
	cdef int found_dup = 0

	# Build a dict mapping variable-index tuples to term index
	# Only consider terms with len_literal >= 2 (variable terms, not constants)
	term_map = {}  # frozenset of variable indices -> first term index
	for i in range(expr_size):
		ll = expr.expr[0].len_literal[i]
		if ll < 2:
			continue  # skip constants and zeroed terms
		# Extract variable indices (everything after the coefficient at position 0)
		var_indices = tuple(sorted(
			expr.expr[0].literals[MAXCLAUSESIZE * i + k] for k in range(1, ll)
		))
		if var_indices in term_map:
			# Duplicate found -- merge coefficient into the earlier term
			first_idx = term_map[var_indices]
			expr.expr[0].literals[MAXCLAUSESIZE * first_idx] += expr.expr[0].literals[MAXCLAUSESIZE * i]
			# Zero out this duplicate term
			expr.expr[0].literals[MAXCLAUSESIZE * i] = 0
			expr.expr[0].len_literal[i] = 0
			found_dup = 1
		else:
			term_map[var_indices] = i

	if found_dup:
		warnings.warn(
			"Duplicate variable terms detected and merged in expression",
			UserWarning,
			stacklevel=3
		)

cdef class Model:
	def __cinit__(self):
		self.mod = init_model()
		self.gpu_imported = False

	def __init__(self):
		self.initialized = False
		self.sparsity = None
		self.stgen = None
		self.global_opt = None
		self.gpu_imported: bool = False

		# self.gpu_executor: Executor | None = None

		self.calls = 0
		self.met = None
		self.objective: new_constraint = new_constraint()
		self.constraint: new_constraint = new_constraint()

		self.obj_expr = []
		self.con_expr = []

		self.sense = MAXIMIZE

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.mod.solver = SATISFY

		# self.runtime: float = 0
		self.feasible = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		# self.objective_value: list[int] | int = 0
		self.final_state: list[state_py] | state_py | list | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False

		self.constraints_compiled: bool = False

		self.circuit: circuit | None = None

		# Post-solve verification (Phase 7)
		self._verified = None  # None = not verified, True = passed, False = failed

		# Thread isolation (Phase 4): seed and thread configuration
		self._seed = None  # None = auto-generate
		self._num_threads = None  # None = auto-detect
		self._seed_used = None  # Populated after solve() by SearchLib

	def __copy__(self):
		new_m = Model()
		new_m.objective = copy(self.objective)
		new_m.constraint = copy(self.constraint)
		new_m.initial_state = copy(self.initial_state)
		new_m.mod.solver = self.mod.solver
		new_m.sense = self.sense
		return new_m

	def __str__(self):
		if not self.improved:
			return "No better solution found"
		return f"""
Found solution with Objective = {self.objective_value}
using either {self.grover_iterations} grover iterations 
or {self.runtime}s sampling
		"""

	def reset(self):
		# self.runtime: float = 0
		self.quantum_cycles: int = 0
		# self.objective_value: int = 0
		self.final_state: state_py | None = None
		self.improved: bool = False
		self.global_opt = None

	def add_variable(self, index: int = 0, name: str = "x", bound: int = 1) -> int | Variable | Expression:
		if bound > 1:
			number = int(np.floor(np.log2(bound))) + 1
			x = self.add_variables(number, name = name)
			expr = sum(2 ** i * x[list(x.keys())[i]] for i in range(number))
			# print(expr <= bound)
			self.add_constraint(expr <= bound)
			# print(expr)
			return expr

		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x", bound = 1) -> dict:
		if n < 1:
			raise ValueError(f"Number of variables must be >= 1, got {n}")
		x = {}
		if bound > 1:
			for i in range(n):
				# print(i)
				x[i] = self.add_variable(self.n, name = name, bound = bound)
			return x
		for i in range(n):
			x[self.n + i] = Variable(self.n + i, f"{name}{self.n + i}")
			self.variables[self.n + i] = x[self.n + i]
		self.n += n

		return x

	def set_objective(self, Expression objective = None, sense: int = MAXIMIZE, validate = True) -> None:
		if validate:
			if objective is None:
				raise ValueError("Objective expression cannot be None")
			if sense not in [MINIMIZE, MAXIMIZE]:
				raise TypeError(
					f"Invalid sense {sense}. Use MAXIMIZE ({MAXIMIZE}) or MINIMIZE ({MINIMIZE})"
				)
		else:
			# Even without validation, sense check is critical for correctness
			if sense not in [MINIMIZE, MAXIMIZE]:
				raise TypeError(
					f"Invalid sense {sense}. Use MAXIMIZE ({MAXIMIZE}) or MINIMIZE ({MINIMIZE})"
				)

		self.sense = sense
		self.mod.solver = OPTIMIZE
		expr = objective
		expr.merge()
		if validate:
			_merge_duplicate_variable_terms(expr)
		if sense == MINIMIZE:
			expr = expr <= 0
		else:
			expr = expr >= 0

		self.obj_expr.append(expr)
		add_expression_to_constraints(self.mod.obj, <expression_t *> objective.expr)
		self.objective.add_expression(expr)

	def add_constraint(self, Expression constraint = None, validate = True) -> None:
		if validate:
			if constraint is None:
				raise ValueError("Constraint cannot be None")
			if constraint.sense == -2:
				raise ValueError(
					"Expression is not a constraint. Apply <=, >=, or == first "
					"(e.g., expr <= 5)"
				)
		expr = constraint
		expr.merge()
		if validate:
			_merge_duplicate_variable_terms(expr)
		add_expression_to_constraints(self.mod.con, <expression_t *> constraint.expr)
		self.constraint.add_expression(expr)
		self.con_expr.append(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initialized = True

		arr = np.array(assignment, dtype = np.int32)
		cdef int * ptr = <int *> calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]): ptr[i] = <int> arr[i]
		self.mod.initial_state = init_state(P, ptr, arr.shape[0])
		self.mod.global_opt = init_state(P, ptr, arr.shape[0])
		free(<void *> ptr)
	# self.initial_state = state_py(P, assignment)

	def compile(self):
		self.gpu_compiled = True

	# self.gpu_executor = Executor(self.n, self.n / 4, int(time()), self.linear_con_form, self.linear_obj_form,
	#                              len(self.constraint.liste()), self.constraint.liste(), self.objective.liste(),
	#                              self.solver)

	def __del__(self):
		free_model(self.mod)
		if self.final_state is not None: self.final_state = None
		if self.initial_state is not None: self.initial_state = None
		self.objective = None
		self.constraint = None
		self.circuit = None

	def close(self, enforce_density = False, validate = True):
		if validate:
			if self.n == 0:
				raise ValueError("Model has no variables; add variables before closing")
			if len(self.con_expr) == 0:
				raise ValueError("Model has no constraints; add constraints before closing")
		if not self.constraints_compiled:
			self.objective.process(self.n)
			process_constraints(self.mod.obj, self.n, enforce_density)
			process_constraints(self.mod.con, self.n, enforce_density)
			# self.sparsity = self.constraint.process(self.n, enforce_density)
			# print_model(self.mod)
			set_bias_wrapper(self.n / 4)
			self.constraints_compiled = True

	def general_greedy(self):
		if not self.initialized:
			self.manual_initial(0, [0] * self.n)
		initial_state_preparation(self.mod)

	def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1, stop_val: int = -1, callback = None,
	          max_delta = 7, reset_delta = True, depth_look_ahead = 0, num_workers: int = 12,
	          results = "min", bfs = False,
	          ignore_constraint_search = False,
	          manual_bias: list[float] | None = None,
	          bias_factor = 1.,
	          manual_bias_factor = 0.,
	          look_ahead_factor = 0.,
	          monte_calor_estimate = False,
	          verify = False
	          ) -> list | None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		if not self.constraints_compiled:
			raise ValueError("No constraints compiled")

		if results not in ["min", "average"]:
			raise ValueError(f"results must be 'min' or 'average', got '{results}'")

		self.calls += 1

		if self.mod.solver == SATISFY:
			if M != -1: warn("Defined M will be ignored when solving SAT")
			if bias != -1: warn("Defined bias will be ignored when solving SAT")
			if stop_val != -1: warn("Defined stop_val will be ignored when solving SAT")

		if not self.initialized: self.manual_initial(0, [0] * self.n)
		if M == -1: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4
		set_bias_wrapper(bias)
		set_factors_wrapper(manual_bias_factor, 0, bias_factor, look_ahead_factor)
		if manual_bias is not None: set_obj_dependence_wrapper(manual_bias)

		not_stop = [1]

		self.mod.M = M
		self.mod.depth_look_ahead = depth_look_ahead
		self.mod.stop_val = stop_val
		self.mod.stopping_time = stopping_time
		self.mod.ignore_constraint_search = ignore_constraint_search
		self.mod.monte_carlo_estimate = monte_calor_estimate
		self.mod.max_delta = max_delta
		self.mod.reset_delta = reset_delta

		res = Parallel(n_jobs = num_workers, backend = "threading")(
			delayed(run_sampling)(self, callback, not_stop) for _ in range(num_workers)
		)

		reset_c_flags()
		obj_vals = [i[0].objective_value for i in res]
		# self.objective_value = min([i[0].objective_value for i in res])
		# index_opt = obj_vals.index(self.objective_value)
		# self.grover_iterations = res[index_opt][1]
		# self.runtime = res[index_opt][-2]
		self.final_state = self.global_opt
		total_incumbent = [j for i in range(num_workers) for j in res[i][-1]]
		# print(total_incumbent)
		total_incumbent.sort(key = lambda x: x[1], reverse = False)
		counter = 1
		while True:
			try:
				if total_incumbent[counter][0] < total_incumbent[counter - 1][0]:
					total_incumbent.pop(counter)
					counter -= 1
				counter += 1
			except:
				break

		if verify:
			self.verify_solution()

		return total_incumbent

	def local_search(self, distance = 2, callback = None, stop_time = 1 << 20, max_worse_acceptances: int = 10,
	                 stopping_condition: int = STOPATFIRST, verify = False):
		assert stopping_condition in [STOPATFIRST, STOPATBEST]
		if not self.initialized: self.manual_initial(0, [0] * self.n)
		t1 = time()

		self.mod[0].max_worse_acceptances = max_worse_acceptances
		self.mod[0].stopping_condition = stopping_condition
		self.mod[0].distance = distance
		self.mod[0].stopping_time = stop_time
		self.mod[0].stop_val = -1

		self.final_state = run_local_search(self, callback)
		print(self.final_state)
		# self.runtime = time() - t1
		# self.objective_value = self.final_state.objective_value

		if verify:
			self.verify_solution()

	def quantum_local_search(self, distance, callback = None, num_workers = 1):
		Parallel(n_jobs = num_workers, backend = "threading")(
			delayed(run_quantum_local_search)(
				self.initial_state,
				self.constraint,
				self.objective,
				distance,
				callback
			) for _ in range(num_workers)
		)

	def approximate_benchmarking(self, samples = 1024, M = 100):
		deltas = []
		incumbents = []

		total_iterations = 0
		set_seed(int(time()))
		threshold = copy(self.initial_state)

		while True:
			state = approximate_state(self.n, self.n / 4)
			state.opt_sampler(self.objective, self.constraint, threshold, samples)
			print(state)

			r, it, rounds = state.QSearch(M)
			total_iterations += 2 * it + 1
			deltas.append(state.delta)
			del state
			if r is None:
				break
			else:
				del threshold
				threshold = r
				incumbents.append((-threshold.objective_value, total_iterations))
			# del threshold
		del threshold
		return total_iterations, deltas, incumbents

	def exact_benchmark(self, M):
		set_bias_wrapper(self.n / 4)
		if self.stgen is None:
			self.stgen = exact_simulator(self)
			self.stgen.generate_gurobi_model()

		inc = self.stgen.QMaxSearch(M)
		return inc

	@property
	def objective_value(self):
		return self.mod[0].global_opt[0].tot_profit * self.sense

	@property
	def oracle_calls(self):
		return self.mod[0].qtg_applications

	@property
	def runtime(self):
		return self.mod[0].runtime

	@property
	def solution(self):
		print("profit ", self.mod[0].initial_state[0].tot_profit)
		print("feasible ", self.mod[0].initial_state[0].feasible)
		print_state(self.mod[0].initial_state)
		print()
		return 0

	# ============================================================
	# Thread Isolation Properties (Phase 4)
	# ============================================================

	@property
	def seed(self):
		"""Get/set the random seed for reproducibility.

		Set before calling solve(). If None (default), a random seed is generated.
		After solve(), use seed_used to get the actual seed that was used.
		"""
		return self._seed

	@seed.setter
	def seed(self, value):
		if value is not None and not isinstance(value, int):
			raise TypeError("seed must be an integer or None")
		self._seed = value

	@property
	def seed_used(self):
		"""Get the actual seed used in the most recent solve() call.

		This is especially useful when no seed was set (auto-generated),
		as it allows reproducing results by setting seed = seed_used.
		Returns None if solve() has not been called.
		"""
		return self._seed_used

	@property
	def num_threads(self):
		"""Get/set the number of threads for parallel solving.

		Set before calling solve(). If None (default), auto-detects CPU cores.
		Can also be set via CBQS_THREADS environment variable.
		"""
		return self._num_threads

	@num_threads.setter
	def num_threads(self, value):
		if value is not None:
			if not isinstance(value, int) or value < 1:
				raise ValueError("num_threads must be a positive integer or None")
		self._num_threads = value

	# ============================================================
	# Post-Solve Verification (Phase 7)
	# ============================================================

	def verify_solution(self):
		"""Verify that the current solution satisfies all constraints
		and the reported objective value matches recomputation.

		Returns True if the solution is valid, False otherwise.
		Emits UserWarning on violations but does not raise exceptions.
		Sets self._verified to True or False accordingly.
		"""
		if self.mod[0].global_opt is NULL:
			warnings.warn(
				"No solution to verify: solve() has not been called",
				UserWarning, stacklevel=2
			)
			self._verified = False
			return False

		verified = True

		# Reconstruct a state_py from the C-level global_opt for evaluation
		cdef int n_bits = self.mod[0].global_opt[0].vector.bits
		arr = [sw_tstbit(self.mod[0].global_opt[0].vector, i) for i in range(n_bits)]
		cdef long long obj_val = self.mod[0].global_opt[0].tot_profit
		st = state_py(obj_val, arr)

		# Check constraint satisfaction using existing C evaluation
		constraints_ok = self.constraint.eval_con(st)
		if not constraints_ok:
			warnings.warn(
				"Post-solve verification FAILED: solution violates one or more constraints",
				UserWarning, stacklevel=2
			)
			verified = False

		# Recompute objective value and compare with reported value
		# eval_obj returns raw value (negated for MAXIMIZE); apply sense to get user-facing value
		recomputed_obj = self.objective.eval_obj(st) * self.sense
		reported_obj = self.objective_value
		EPSILON = 1e-9
		if abs(recomputed_obj - reported_obj) > EPSILON:
			warnings.warn(
				f"Post-solve verification FAILED: reported objective {reported_obj} "
				f"does not match recomputed {recomputed_obj}",
				UserWarning, stacklevel=2
			)
			verified = False

		self._verified = verified
		return verified