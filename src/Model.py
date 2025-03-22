from .Expression import Variable, Expression
from .Constants import *

class Model:

	def __init__(self):
		self.objective: Expression | None = None
		self.constraint: Expression | None = None

		self.n: int = 0
		self.variables = {}

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

	def set_objective(self, objective: Expression | int | None = None) -> None:
		self.objective = objective.sum_constants_in_expression()

	def add_constraint(self, constraint: Expression | int | None = None) -> None:
		self.constraint = constraint.sum_constants_in_expression()
		print(self.constraint)

