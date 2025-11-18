from .Constants import *


class Variable:
	def __init__(self, index = 0, name = "__", lb = 0, ub = 1, vtype = INTEGER):
		self.vtype = vtype
		self.index = index
		self.name = name
		if name == "__": self.name = f"x{index}"
		self.lb, self.ub = lb, ub

	def __str__(self):
		return f"{self.name}"

	def __add__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression()
			add_constant(expr.expr, other)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression()
			add_variable(expr.expr, other.index)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression):
			other += self
			# add_variable(<expression_t *>other.expr, self.index)
			return other

	def __radd__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression()
			add_constant(expr.expr, other)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression()
			add_variable(expr.expr, other.index)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression):
			other += self
			return other

	def __mul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression()
			add_constant(expr.expr, other)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression()
			add_variable(expr.expr, other.index)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression):
			other *= self
			return other

	def __rmul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression()
			add_constant(expr.expr, other)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression()
			add_variable(expr.expr, other.index)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression):
			other *= self
			return other


cdef class Expression:
	def __cinit__(self):
		self.expr = <expression_t *> init_expression()
		self.sense = -2
		self.rhs = -2

	def __str__(self):
		for i in range(self.expr[0].expr_size):
			for j in range(self.expr[0].len_literal[i]):
				print(self.expr[0].literals[5 * i + j], end = " ")
			print()
		return ""

	def __copy__(self):
		ne = Expression()
		ne.add_expr(self)
		return ne

	def __dealloc__(self):
		free_expression(self.expr)
		self.expr = NULL
		del self

	cdef add_expr(self, Expression other):
		add_expression(<expression_t *> self.expr, <expression_t *> other.expr)

	cdef mul_expr(self, Expression other, Expression ne):
		new = multiply_expressions(<expression_t *> self.expr, <expression_t *> other.expr)
		add_expression(ne.expr, new)
		free_expression(new)

	def merge(self):
		merge_expression(self.expr)
		return self

	cdef c_liste(self):
		l = [
			[self.expr[0].literals[5 * j + i] for i in range(self.expr[0].len_literal[j])]
			for j in range(self.expr[0].expr_size) if self.expr[0].len_literal[j] != 0
		]
		# print("l = ", l)
		if self.sense != -2:
			l += [self.sense, self.rhs]
		return l

	def __iter__(self):
		return self.c_liste().__iter__()

	def __add__(self, other):
		# cdef expression_t *temp
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			add_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			add_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			self.add_expr(other)
			return self

	def __radd__(self, other):
		# cdef expression_t *temp
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			add_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			add_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			self.add_expr(other)
			return self

	def __mul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			multiply_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			multiply_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			ne = Expression()
			self.mul_expr(other, ne)
			del self
			return ne

	def __rmul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			multiply_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			multiply_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			ne = Expression()
			self.mul_expr(other, ne)
			del self
			return ne

	def __le__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			potential = 0
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[5 * i] < 0:
					potential -= self.expr[0].literals[5 * i]

			add_sense_to_expression(self.expr, LOWER)
			add_rhs_to_expression(self.expr, other + potential)
			self.sense = LOWER
			self.rhs = other + potential
			return self

	def __ge__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			potential = 0

			multiply_constant(self.expr, -1)
			# negate_expression(self.expr)
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[5 * i] < 0:
					potential -= self.expr[0].literals[5 * i]

			add_sense_to_expression(self.expr, LOWER)
			add_rhs_to_expression(self.expr, -other + potential)
			self.sense = LOWER  # originally GREATER
			self.rhs = -other + potential
			return self

	def __eq__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			# potential = 0
			# for i in range(self.expr[0].expr_size):
			# 	if self.expr[0].literals[5 * i] < 0:
			# 		potential -= self.expr[0].literals[5 * i]

			add_sense_to_expression(self.expr, EQUAL)
			add_rhs_to_expression(self.expr, other)
			self.sense = EQUAL
			# self.rhs = other + potential
			self.rhs = other
			return self
