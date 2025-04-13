from .Constants import *
import numpy as np

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
			expr = Expression2()
			add_constant(expr.expr, other)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression2()
			add_variable(expr.expr, other.index)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression2):
			other += self
			# add_variable(<expression_t *>other.expr, self.index)
			return other

	def __radd__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression2()
			add_constant(expr.expr, other)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression2()
			add_variable(expr.expr, other.index)
			add_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression2):
			other += self
			return other

	def __mul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression2()
			add_constant(expr.expr, other)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression2()
			add_variable(expr.expr, other.index)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression2):
			other *= self
			return other

	def __rmul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			expr = Expression2()
			add_constant(expr.expr, other)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Variable):
			expr = Expression2()
			add_variable(expr.expr, other.index)
			multiply_variable(expr.expr, self.index)
			return expr
		if isinstance(other, Expression2):
			other *= self
			return other


cdef class Expression2:

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

	cdef add_expr(self, Expression2 other):
		add_expression(<expression_t *> self.expr, <expression_t *> other.expr)

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

	def linear_vector_form(self, n):
		array = [0] * n
		for i in range(self.expr[0].expr_size):
			if self.expr[0].len_literal[i] == 2:
				index = self.expr[0].literals[3 * i + 1]
				array[index] = self.expr[0].literals[3 * i]
		return array

	def linear_matrix_form(self, n):
		array = [0] * n * n
		for i in range(self.expr[0].expr_size):
			if self.expr[0].len_literal[i] == 2:
				index = self.expr[0].literals[3 * i + 1] # linear terms occupy the diagonal matrix entries
				array[n * index + index] = self.expr[0].literals[3 * i]

			if self.expr[0].len_literal[i] == 3:
				index1 = self.expr[0].literals[3 * i + 1]
				index2 = self.expr[0].literals[3 * i + 2]
				array[n * index2 + index1] = self.expr[0].literals[3 * i]

		return array

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
		if isinstance(other, Expression2):
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
		if isinstance(other, Expression2):
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

	def __rmul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			multiply_constant(self.expr, other)
			return self
		if isinstance(other, Variable):
			multiply_variable(self.expr, other.index)
			return self

	def __le__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			potential = 0
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[3 * i] < 0:
					potential -= self.expr[0].literals[3 * i]

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
				if self.expr[0].literals[3 * i] < 0:
					potential -= self.expr[0].literals[3 * i]

			add_sense_to_expression(self.expr, LOWER)
			add_rhs_to_expression(self.expr, -other + potential)
			self.sense = LOWER # originally GREATER
			self.rhs = -other + potential
			return self

	def __eq__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			potential = 0
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[3 * i] < 0:
					potential -= self.expr[0].literals[3 * i]

			add_sense_to_expression(self.expr, EQUAL)
			add_rhs_to_expression(self.expr, other + potential)
			self.sense = EQUAL
			self.rhs = other + potential
			return self