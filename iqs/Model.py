from time import time
import ctypes
from .Constants import *
from .Expression import Variable, Expression2
from iqs.Metal_executor import Executor
from .SearchLib import state_py, constraints, run_ctg, set_seed, set_bias_wrapper

from .generators.metal_ilp_generator import *
from .generators.metal_sat_generator import *

import numpy as np

import sys
import os

sys.stderr = open(os.devnull, 'w')  # Suppress stderr


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
		self.grover_iterations: int = 0
		self.quantum_cycles: int = 0
		self.objective_value: int = 0
		self.final_state: state_py | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False

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

		# self.linear_obj_form += expr.linear_matrix_form(self.n)
		self.linear_obj_form += expr.linear_vector_form(self.n)

		self.objective += list(expr) + [sense, 0]

	def add_constraint(self, constraint: Expression2 | int | None = None) -> None:
		expr = constraint
		expr.merge()
		self.linear_con_form += expr.linear_vector_form(self.n)
		self.constraint += list(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	# def compile(self):
	# 	self.gpu_compiled = True
	# 	self.met = metal_executor(self.n, self.linear_obj_form, self.linear_con_form, len(self.constraint),
	# 		                     self.constraint.liste(), self.objective.liste())

	def compile(self, lp_factor = 0, lp_opt = None, num_integers = None):
		self.gpu_compiled = True
		if lp_opt is None: lp_opt = [0] * self.n
		if num_integers is None: num_integers = int(self.n / 32 + 0.9)

		if self.linear_obj_form != []:
			f = open("build/objective.txt", "w")
			for i in self.linear_obj_form: f.write(f"{i} ")
			f.close()

		if self.linear_con_form != []:
			f = open("build/constraint.txt", "w")
			for i in self.linear_con_form: f.write(f"{i} ")
			f.close()

		if self.solver == SATISFY:
			generate_sat_metal(self.n,
			                   len(self.constraint.liste()),
			                   self.constraint.liste(),
			                   lp_factor, lp_opt,
			                   True, direction = ".")
		else:
			generate_ilp_metal(self.n,
			                   len(self.constraint.liste()),
			                   self.constraint.liste(),
			                   self.objective.liste(),
			                   direction = ".")

		self.gpu_executor = Executor(self.n, self.n / 4, 42, self.linear_con_form, self.linear_obj_form)

	def solve(self, M: int = 0, bias: float | int = -1, stop_val: int = -1, callback = None, arch = "cpu") -> None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		self.calls += 1
		set_seed(time() + 10 * self.calls)
		if self.solver == SATISFY: self.objective += [[0], MAXIMIZE, 0]

		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == 0: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4
		set_bias_wrapper(bias)

		if arch == "gpu":
			# print("compile now")
			if not self.gpu_compiled:
				self.compile()

			# print("compiled")

			t1 = time()
			initial = self.initial_state.integer_liste()
			initial = initial[: min(len(initial), int(np.ceil(self.n / 32)))]

			self.gpu_executor.gpu_qmax_search(self.n, M, 0, initial)

			return

		# otherwise old cpu colde will be executed
		res = run_ctg(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)
		self.improved = res[1].objective_value() != self.initial_state.objective_value()
		if self.solver == SATISFY: self.improved = res[1].objective_value() == len(self.constraint)

		self.objective_value = res[1].objective_value()
		self.runtime = res[2]
		self.grover_iterations = res[0]
		self.quantum_cycles = res[0]
		self.final_state = res[1]
