from .Expression import Variable, Expression
from .Constants import *
from .SearchLib import state_py, constraints

class Model:

	def __init__(self):
		self.objective: constraints  = constraints()
		self.constraint: constraints = constraints()

		self.n: int = 0
		self.variables = {}

		self.initial_state = None

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
		self.objective += objective.sum_constants_in_expression().index_list() + [sense, 0]

	def add_constraint(self, constraint: Expression | int | None = None) -> None:
		self.constraint += constraint.sum_constants_in_expression().index_list()

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	def solve(self, M: int = 0, bias: float | int = -1) -> bool:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == 0: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4

		print(self.initial_state)

		return False

