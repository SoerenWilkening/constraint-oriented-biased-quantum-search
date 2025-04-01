# import os
# import sys
from time import time

import numpy as np
from joblib import Parallel, delayed

from iqs.Metal_executor import Executor
from .Constants import *
from .Expression import Variable, Expression2
from .SearchLib import state_py, constraints, run_ctg, set_seed, set_bias_wrapper

from warnings import warn
#
# sys.stderr = open(os.devnull, 'w')  # Suppress stderr


class Model:

	def __init__(self):
		self.gpu_imported: bool = False

		self.gpu_executor: Executor | None = None

		self.calls = 0
		self.met = None
		self.objective: constraints = constraints()
		self.constraint: constraints = constraints()

		self.linear_obj_form = []
		self.linear_con_form = []

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.solver = SATISFY

		self.runtime: float = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		self.objective_value: list[int] | int = 0
		self.final_state: list[state_py] | state_py | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False
		set_seed(time())

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

	def add_variable(self, index: int = 0, name: str = "x") -> Variable:
		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x") -> dict:
		x = {}
		for i in range(n):
			x[self.n + i] = Variable(self.n + i, f"{name}{self.n + i}")
			self.variables[self.n + i] = x[self.n + i]
		self.n += n

		return x

	def set_objective(self, objective: Expression2 | int | None = None, sense: int = MAXIMIZE) -> None:
		if sense not in [MINIMIZE, MAXIMIZE]:
			raise TypeError
		self.solver = OPTIMIZE
		expr = objective
		expr.merge()

		self.linear_obj_form += expr.linear_matrix_form(self.n)
		# self.linear_obj_form += expr.linear_vector_form(self.n)

		self.objective += list(expr) + [sense, 0]

	def add_constraint(self, constraint: Expression2 | int | None = None) -> None:
		expr = constraint
		expr.merge()
		self.linear_con_form += expr.linear_vector_form(self.n)
		# print(self.linear_con_form)
		self.constraint += list(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	def compile(self):
		self.gpu_compiled = True
		self.gpu_executor = Executor(self.n, self.n / 4, int(time()), self.linear_con_form, self.linear_obj_form,
		                             len(self.constraint.liste()), self.constraint.liste(), self.objective.liste(),
		                             self.solver)

	def solve(self, M: int = -1, bias: float | int = -1, stop_val: int = -1, callback = None, arch = "cpu",
	          num_threads = 12) -> float | None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		self.calls += 1
		set_seed(time() + 10 * self.calls)
		if self.solver == SATISFY: self.objective += [[0], MAXIMIZE, 0]

		if self.solver == SATISFY:
			if M != -1: warn("Defined M will be ignored when solving SAT")
			if bias != -1: warn("Defined bias will be ignored when solving SAT")
			if stop_val != -1: warn("Defined stop_val will be ignored when solving SAT")

		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == -1: M = self.n ** 2 // 16
		if bias != -1: bias = self.n / 4
		set_bias_wrapper(bias)


		if arch == "gpu":
			raise TypeError("needs some fixing, currently doesnt seems to work properly!")

			# print("compile now")
			if not self.gpu_compiled:
				self.compile()

			# print("compiled")

			t1 = time()
			initial = self.initial_state.integer_liste()
			initial = initial[: min(len(initial), int(np.ceil(self.n / 32)))]

			res, oracle, t = self.gpu_executor.gpu_qmax_search(self.n, M, 0, initial, callback)
			self.objective_value = res
			self.runtime = t
			self.grover_iterations = oracle
			self.quantum_cycles = oracle
			return

		t1 = time()
		if num_threads == 1:
			res = [run_ctg(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)]
		else:
			res = Parallel(n_jobs = num_threads, backend = "threading", batch_size = 1)(
				delayed(run_ctg)(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)
				for _ in range(num_threads)
			)

		# for i in res: print(*i)
		self.runtime = time() - t1 # stores classical runtime of all the complete execution
		self.objective_value = max(i[0].objective_value() for i in res)
		self.grover_iterations = min(list(i[1] for i in res if i[0].objective_value() == self.objective_value))
		for i in res:
			if i[0].objective_value() == self.objective_value:
				self.final_state = i[0]
				break

		# t1 = time()
		# res = run_ctg(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)
		# print("time single process ", time() - t1)
	# res = run_ctg(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)

	# self.improved = res[1].objective_value() != self.initial_state.objective_value()
	# # if self.solver == SATISFY: self.improved = res[1].objective_value() == len(self.constraint)
	#
	# self.objective_value = res[1].objective_value()
	# self.runtime = res[2]
	# self.grover_iterations = res[0]
	# self.quantum_cycles = res[0]
	# self.final_state = res[1]
