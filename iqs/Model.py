from .Expression import Variable, Expression
from .Constants import *
from .SearchLib import state_py, constraints, run_ctg
import os

class Model:

	def __init__(self):
		self.objective: constraints  = constraints()
		self.constraint: constraints = constraints()

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.solver = SATISFY

		self.runtime: float = 0
		self.grover_iterations: int = 0
		self.quantum_cycles: int = 0
		self.objective_value: int = 0
		self.final_state: state_py | None = None
		self.improved : bool = False

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

	def set_objective(self, objective: Expression | int | None = None, sense : int = MAXIMIZE) -> None:
		if sense not in [MINIMIZE, MAXIMIZE]:
			raise TypeError
		self.solver = OPTIMIZE

		expr = objective.merge_expression_terms().index_list() + [sense, 0]

		self.objective += expr

	def add_constraint(self, constraint: Expression | int | None = None) -> None:
		expr = constraint.merge_expression_terms().adjust_expression().index_list()
		self.constraint += expr

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	def solve(self, M: int = 0, bias: float | int = -1, stop_val: int = -1, callback = None) -> None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		if self.solver == SATISFY: self.objective += [[0], MAXIMIZE, 0]

		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == 0: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4

		res = run_ctg(self.initial_state, self.constraint, self.objective, M, 0, self.solver, stop_val, callback)
		self.improved = res[1].objective_value() != self.initial_state.objective_value()
		if self.solver == SATISFY: self.improved = res[1].objective_value() == len(self.constraint)

		self.objective_value = res[1].objective_value()
		self.runtime = res[2]
		self.grover_iterations = res[0]
		self.quantum_cycles = res[0]
		self.final_state = res[1]
