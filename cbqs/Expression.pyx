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
			# Return new Expression, don't mutate other
			return other + self

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
			# Return new Expression, don't mutate other
			return other + self

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
			# Return new Expression, don't mutate other
			return other * self

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
			# Return new Expression, don't mutate other
			return other * self


cdef class Expression:
	def __cinit__(self):
		self.expr = <expression_t *> init_expression()
		self.sense = -2
		self.rhs = -2

	def __str__(self):
		for i in range(self.expr[0].expr_size):
			for j in range(self.expr[0].len_literal[i]):
				print(self.expr[0].literals[MAXCLAUSESIZE * i + j], end = " ")
			print()
		return ""

	def __copy__(self):
		ne = Expression()
		ne.add_expr(self)
		return ne

	cdef Expression _deep_copy(self):
		"""Create independent copy with separate C arrays."""
		cdef Expression new_expr = Expression()
		copy_expression_contents(new_expr.expr, self.expr)
		new_expr.sense = self.sense
		new_expr.rhs = self.rhs
		return new_expr

	def __deepcopy__(self, memo):
		"""Support copy.deepcopy() - creates fully independent Expression."""
		new_expr = self._deep_copy()
		memo[id(self)] = new_expr
		return new_expr

	def __dealloc__(self):
		free_expression(self.expr)
		self.expr = NULL
		del self

	cdef add_expr(self, Expression other):
		add_expression(<expression_t *> self.expr, <expression_t *> other.expr)

	cdef mul_expr(self, Expression other, Expression ne):
		# print_expression(self.expr)
		# print_expression(other.expr)
		new = multiply_expressions(<expression_t *> self.expr, <expression_t *> other.expr)
		add_expression(ne.expr, new)
		free_expression(new)

	def merge(self):
		merge_expression(self.expr)
		return self

	cdef c_liste(self):
		l = [
			[self.expr[0].literals[MAXCLAUSESIZE * j + i] for i in range(self.expr[0].len_literal[j])]
			for j in range(self.expr[0].expr_size) if self.expr[0].len_literal[j] != 0
		]
		# print("l = ", l)
		if self.sense != -2:
			l += [self.sense, self.rhs]
		return l

	def __iter__(self):
		return self.c_liste().__iter__()

	def __add__(self, other):
		"""Return new Expression with other added. Does not modify self."""
		if isinstance(other, float): raise TypeError("Not allowed type!")

		cdef Expression result = self._deep_copy()

		if isinstance(other, int):
			add_constant(result.expr, other)
			return result
		if isinstance(other, Variable):
			add_variable(result.expr, other.index)
			return result
		if isinstance(other, Expression):
			result.add_expr(other)
			return result
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __radd__(self, other):
		"""Return new Expression with other added (reverse). Does not modify self."""
		if isinstance(other, float): raise TypeError("Not allowed type!")

		cdef Expression result = self._deep_copy()

		if isinstance(other, int):
			add_constant(result.expr, other)
			return result
		if isinstance(other, Variable):
			add_variable(result.expr, other.index)
			return result
		if isinstance(other, Expression):
			result.add_expr(other)
			return result
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __iadd__(self, other):
		"""Mutate self in place by adding other. Returns self.

		Matches Python int behavior: x += 3 mutates x.
		Use this for performance when you don't need the original.
		"""
		if isinstance(other, float):
			raise TypeError("Not allowed type!")
		if isinstance(other, int):
			add_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			add_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			self.add_expr(other)
			return self
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __isub__(self, other):
		"""Mutate self in place by subtracting other. Returns self.

		Matches Python int behavior: x -= 3 mutates x.
		Use this for performance when you don't need the original.
		"""
		if isinstance(other, float):
			raise TypeError("Not allowed type!")
		if isinstance(other, int):
			sub_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			sub_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			sub_expression(<expression_t *>self.expr, <expression_t *>other.expr)
			return self
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __mul__(self, other):
		"""Return new Expression with other multiplied. Does not modify self."""
		cdef Expression result
		if isinstance(other, float): raise TypeError("Not allowed type!")

		if isinstance(other, int):
			result = self._deep_copy()
			multiply_constant(result.expr, other)
			return result
		if isinstance(other, Variable):
			result = self._deep_copy()
			multiply_variable(result.expr, other.index)
			return result
		if isinstance(other, Expression):
			# Expression * Expression creates new via mul_expr
			ne = Expression()
			self.mul_expr(other, ne)
			return ne
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __rmul__(self, other):
		"""Return new Expression with other multiplied (reverse). Does not modify self."""
		cdef Expression result
		if isinstance(other, float): raise TypeError("Not allowed type!")

		if isinstance(other, int):
			result = self._deep_copy()
			multiply_constant(result.expr, other)
			return result
		if isinstance(other, Variable):
			result = self._deep_copy()
			multiply_variable(result.expr, other.index)
			return result
		if isinstance(other, Expression):
			# Expression * Expression creates new via mul_expr
			ne = Expression()
			self.mul_expr(other, ne)
			return ne
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __imul__(self, other):
		"""Mutate self in place by multiplying other. Returns self.

		Use this for performance when you don't need the original.
		"""
		if isinstance(other, float):
			raise TypeError("Not allowed type!")
		if isinstance(other, int):
			multiply_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			multiply_variable(self.expr, other.index)
			return self
		if isinstance(other, Expression):
			# For Expression * Expression, we need to create new result
			ne = Expression()
			self.mul_expr(other, ne)
			# Copy the result back to self
			copy_expression_contents(self.expr, ne.expr)
			return self
		raise TypeError(f"Unsupported operand type: {type(other)}")

	def __le__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			potential = 0
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[MAXCLAUSESIZE * i] < 0:
					potential -= self.expr[0].literals[MAXCLAUSESIZE * i]

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
				if self.expr[0].literals[MAXCLAUSESIZE * i] < 0:
					potential -= self.expr[0].literals[MAXCLAUSESIZE * i]

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
