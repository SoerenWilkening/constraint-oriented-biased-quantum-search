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
	cdef expression_t *expr
	cdef int sense
	cdef int rhs

	def __cinit__(self):
		self.expr = <expression_t *> init_expression()
		self.sense = -2
		self.rhs = -2

	def __str__(self):
		for i in range(self.expr[0].expr_size):
			print(self.expr[0].literals[3 * i + 0], self.expr[0].literals[3 * i + 1], self.expr[0].literals[3 * i + 2])
		return ""

	cdef add_expr(self, other: Expression2):
		add_expression(<expression_t *> self.expr, <expression_t *> other.expr)

	def merge(self):
		merge_expression(self.expr)
		return self

	cdef c_liste(self):
		l = [
			[self.expr[0].literals[3 * j + i] for i in range(self.expr[0].len_literal[j])]
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
			self.sense = EQUAL
			self.rhs = other + potential
			return self








# class Expression:
#
# 	# TODO:
# 	#  dont use append to save time
# 	def __init__(self, literal):
# 		self.expression = [0 for _ in range(100_000)]
# 		self.length = 1
# 		self.expression[0] = literal
#
#
# 	def __str__(self):
# 		# print(self.expression)
# 		for i in self:
# 			print("[", end="")
# 			for j in i:
# 				print(f"{j}, ", end="")
# 			print("], ", end="")
# 		if isinstance(self.expression[-2], int):
# 			if self.expression[-2] == LOWER: print("< ", end = "")
# 			elif self.expression[-2] == LOWER: print("> ", end = "")
# 			else: print("= ", end = "")
# 			print(self.expression[-1], end = "")
# 		return ""
#
# 	def __add__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			self.expression[self.length] = [other]
# 			self.length += 1
# 			return self
# 		if isinstance(other, Variable):
# 			self.expression[self.length] = [1, other]
# 			self.length += 1
# 			return self
# 		if isinstance(other, Expression):
# 			# print("add expression")
# 			for i in other:
# 				# print(i)
# 				self.expression[self.length] = i
# 				self.length += 1
# 				# self.expression.append(i)
# 			return self
#
# 	def __radd__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			self.expression[self.length] = [other]
# 			self.length += 1
# 			return self
# 		if isinstance(other, Variable):
# 			self.expression[self.length] = [1, other]
# 			self.length += 1
# 			return self
# 		if isinstance(other, Expression):
# 			# print("add expression")
# 			for i in other:
# 				# print(i)
# 				self.expression[self.length] = i
# 				self.length += 1
# 			# self.expression.append(i)
# 			return self
#
# 	def __mul__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			for i in range(len(self)):
# 				self.expression[i][0] *= other
# 		if isinstance(other, Variable):
# 			for i in range(len(self)):
# 				self.expression[i].append(other)
# 			return self
# 		if isinstance(other, Expression):
# 			raise TypeError("Not allowed operation!")
#
# 	def __le__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			self.expression[self.length] = LOWER
# 			self.expression[self.length + 1] = other
# 			self.length += 2
# 			return self
#
# 	def __ge__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			self.expression[self.length] = GREATER
# 			self.expression[self.length + 1] = other
# 			self.length += 2
# 			return self
#
# 	def __eq__(self, other):
# 		if isinstance(other, float): raise TypeError("Not allowed type!")
# 		if isinstance(other, int):
# 			self.expression[self.length] = EQUAL
# 			self.expression[self.length + 1] = other
# 			self.length += 2
# 			return self
#
# 	def __iter__(self):
# 		return (i for i in self.expression if not isinstance(i, int))
#
# 	def __len__(self):
# 		return self.length
# 		# return len([i for i in self.expression if not isinstance(i, int)])
#
# 	def merge_expression_terms(self):
# 		self.expression = self.expression[:self.length]
# 		pop_it = False
# 		constant_index = 0
# 		# sum all the constant factors
# 		try:
# 			for i in range(len(self)):
# 				if self.literaL_length[i] == 1:
# 					if pop_it:
# 						self.expression[constant_index][0] += self.expression[i][0]
# 						self.expression.pop(i)
# 						i -= 1
# 					if not pop_it:
# 						pop_it = True
# 						constant_index = i
# 		except: pass
#
# 		# merge the remaining terms (x1 + x1 -> 2 * x1)
# 		try:
# 			for i in range(len(self)):
# 				term1 = self.expression[i]
# 				# print(*term1, end = " ")
# 				try:
# 					for j in range(i + 1, len(self)):
# 						term2 = self.expression[j]
# 						# print(*term2)
# 						if term1 == term2:
# 							self.expression[i][0] += term2[0]
# 							self.expression.pop(j)
# 							j -= 1
# 				except: continue
# 		except:
# 			pass
# 		return self
#
# 	def index_list(self):
# 		return [
# 			[j if isinstance(j, int) else j.index for j in i] for i in self.expression if not isinstance(i, int)
# 		] + [i for i in [self.expression[-2], self.expression[-1]] if isinstance(self.expression[-2], int)]
#
# 	def adjust_expression(self):
# 		for i in range(len(self)):
# 			try:
# 				if len(self.expression[i]) == 1:
# 					self.expression[-1] -= self.expression[i][0]
# 					self.expression.pop(i)
# 			except:
# 				continue
#
# 		if self.expression[-2] == GREATER:
# 			self.expression[-2] = LOWER
# 			self.expression[-1] *= -1
# 			for i in self:
# 				i[0] *= -1
#
# 		potential = 0
# 		for i in self:
# 			# print(i)
# 			if i[0] < 0: potential -= i[0]
# 		self.expression[-1] += potential
#
# 		return self