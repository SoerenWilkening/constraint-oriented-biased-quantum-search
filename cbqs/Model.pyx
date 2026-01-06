from copy import copy
from time import time
from warnings import warn

import numpy as np
from joblib import Parallel, delayed
from .CircuitBackendBinder import circuit
from .Constants import *
from .Expression import Variable
from .Expression cimport Expression
from .state import state_py
from .Constraint import new_constraint
from .Constraint cimport add_expression_to_constraints, process_constraints
from .Expression cimport expression_t
from .branching import set_seed, set_bias_wrapper, set_factors_wrapper, set_obj_dependence_wrapper
from .SearchLib import (run_sampling, run_local_search, run_quantum_local_search, run_general_greedy, reset_c_flags)
from .StateGenerator import exact_simulator
from .state_sampler import approximate_state

cdef class Model:
	cdef model_t *mod
	cdef int gpu_imported

	cdef public object sparsity
	cdef public object stgen
	cdef public object global_opt
	cdef public object calls
	cdef public object met
	cdef public object objective
	cdef public object constraint
	cdef public object obj_expr
	cdef public object con_expr
	cdef public object sense
	cdef public object n
	cdef public object variables
	cdef public object initial_state
	cdef public object solver
	cdef public object runtime
	cdef public object feasible
	cdef public object grover_iterations
	cdef public object quantum_cycles
	cdef public object objective_value
	cdef public object final_state
	cdef public object improved
	cdef public object gpu_compiled
	cdef public object constraints_compiled
	cdef public object circuit

	def __cinit__(self):
		self.mod = init_model()
		self.gpu_imported = False

	def __init__(self):
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

		self.solver = SATISFY

		self.runtime: float = 0
		self.feasible = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		self.objective_value: list[int] | int = 0
		self.final_state: list[state_py] | state_py | list | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False

		self.constraints_compiled: bool = False

		self.circuit: circuit | None = None

	def __copy__(self):
		new_m = Model()
		new_m.objective = copy(self.objective)
		new_m.constraint = copy(self.constraint)
		new_m.initial_state = copy(self.initial_state)
		new_m.solver = self.solver
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
		self.runtime: float = 0
		self.quantum_cycles: int = 0
		self.objective_value: int = 0
		self.final_state: state_py | None = None
		self.improved: bool = False
		self.global_opt = None

	def add_variable(self, index: int = 0, name: str = "x", bound: int = 1) -> int | Variable | Expression:
		if bound > 1:
			number = int(np.floor(np.log2(bound))) + 1
			x = self.add_variables(number, name = name)
			expr = sum(2 ** i * x[list(x.keys())[i]] for i in range(number))
			self.add_constraint(expr <= bound)
			return expr

		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x", bound = 1) -> dict:
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

	def set_objective(self, Expression objective = None, sense: int = MAXIMIZE) -> None:
		if sense not in [MINIMIZE, MAXIMIZE]:
			raise TypeError

		self.sense = sense
		self.solver = OPTIMIZE
		expr = objective
		expr.merge()
		if sense == MINIMIZE:
			expr = expr <= 0
		else:
			expr = expr >= 0

		self.obj_expr.append(expr)
		add_expression_to_constraints(self.mod.obj, <expression_t *> objective.expr)
		self.objective.add_expression(expr)

	def add_constraint(self, Expression constraint = None) -> None:
		expr = constraint
		expr.merge()
		add_expression_to_constraints(self.mod.con, <expression_t *> constraint.expr)
		self.constraint.add_expression(expr)
		self.con_expr.append(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		# f = self.constraint.eval_con_from_array(assignment)
		# if not f:
		# 	pass
		self.initial_state = state_py(P, assignment)


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

	def close(self, enforce_density = False):
		if not self.constraints_compiled:
			self.objective.process(self.n)
			process_constraints(self.mod.obj, self.n, enforce_density)
			process_constraints(self.mod.con, self.n, enforce_density)
			self.sparsity = self.constraint.process(self.n, enforce_density)
			print_model(self.mod)
			# print("processed con")
			# self.circuit = circuit()
			# self.circuit.compile()
			# print(self.circuit)
			set_bias_wrapper(self.n / 4)
			self.constraints_compiled = True

	def general_greedy(self):
		if self.initial_state is not None:
			self.initial_state = None
			# del self.initial_state
		self.manual_initial(0, [0] * self.n)
		run_general_greedy(self.initial_state, self.constraint, self.objective)

	def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1, stop_val: int = -1, callback = None,
	          max_delta = 7, reset_delta = True, depth_look_ahead = 0, num_workers: int = 12,
	          results = "min", bfs = False,
	          ignore_constraint_search = False,
	          manual_bias: list[float] | None = None,
	          bias_factor = 1.,
	          manual_bias_factor = 0.,
	          look_ahead_factor = 0.,
	          monte_calor_estimate = False
	          ) -> list | None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		if not self.constraints_compiled:
			raise ValueError("No constraints compiled")

		assert results in ["min", "average"]

		self.calls += 1

		if self.solver == SATISFY:
			if M != -1: warn("Defined M will be ignored when solving SAT")
			if bias != -1: warn("Defined bias will be ignored when solving SAT")
			if stop_val != -1: warn("Defined stop_val will be ignored when solving SAT")

		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == -1: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4
		set_bias_wrapper(bias)
		set_factors_wrapper(manual_bias_factor, 0, bias_factor, look_ahead_factor)
		if manual_bias is not None: set_obj_dependence_wrapper(manual_bias)

		# if bfs:
		# 	s = exact_simulator(self)
		# 	s.generate_gurobi_model()
		# 	s.stategen()
		# 	print(len(s.bfs))
		# 	run_bfs(self.initial_state, self.constraint, self.objective, M, depth_look_ahead, self.solver,
		# 	        stop_val, callback, max_delta, reset_delta)
		# 	return
		# self.global_opt: state_py = copy(self.initial_state)

		not_stop = [1]

		res = Parallel(n_jobs = num_workers, backend = "threading")(
			delayed(run_sampling)(
				self.initial_state,
				self.constraint,
				self.objective,
				M,
				stopping_time,
				depth_look_ahead,
				self.solver,
				stop_val, callback, max_delta, reset_delta,
				self.global_opt,
				not_stop,
				ignore_constraint_search,
				monte_calor_estimate
			) for _ in range(num_workers)
		)

		reset_c_flags()
		obj_vals = [i[0].objective_value for i in res]
		self.objective_value = min([i[0].objective_value for i in res])
		index_opt = obj_vals.index(self.objective_value)
		self.grover_iterations = res[index_opt][1]
		self.runtime = res[index_opt][-2]
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


		return total_incumbent

	def local_search(self, distance = 2, callback = None, stop_time = 1 << 20, max_worse_acceptances: int = 10,
	                 stopping_condition: int = STOPATFIRST):
		assert stopping_condition in [STOPATFIRST, STOPATBEST]
		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		t1 = time()
		self.final_state = run_local_search(self.initial_state, self.constraint, self.objective, distance, stop_time,
		                                    self.solver, -1,
		                                    callback, max_worse_acceptances, stopping_condition)
		self.runtime = time() - t1
		self.objective_value = self.final_state.objective_value

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
