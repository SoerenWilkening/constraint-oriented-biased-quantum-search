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
		if isinstance(other, int): return Expression([[other], [1, self]])
		if isinstance(other, Variable): return Expression([[1, self], [1, other]])
		if isinstance(other, Expression):
			other.expression.append([1, self])
			return other

	def __radd__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int): return Expression([[other], [1, self]])

	def __sub__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int): return Expression([[-other], [1, self]])
		if isinstance(other, Variable): return Expression([[1, self], [-1, other]])

	def __rsub__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int): return Expression([[other], [-1, self]])

	def __mul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int): return Expression([[other, self]])
		if isinstance(other, Variable): return Expression([[1, self, other]])
		if isinstance(other, Expression):
			for i in range(len(other.expression)):
				other.expression[i].append(self)
			return other

	def __rmul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int): return Expression([[other, self]])

class Expression:
	def __init__(self, literal_1):
		self.expression = literal_1

	def __str__(self):
		for i in self:
			print("[", end="")
			for j in i:
				print(f"{j}, ", end="")
			print("], ", end="")
		if isinstance(self.expression[-2], int):
			if self.expression[-2] == LOWER: print("< ", end = "")
			elif self.expression[-2] == LOWER: print("> ", end = "")
			else: print("= ", end = "")
			print(self.expression[-1], end = "")
		return ""

	def __add__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			self.expression.append([other])
			return self
		if isinstance(other, Variable):
			self.expression.append([1, other])
			return self
		if isinstance(other, Expression):
			for i in other:
				self.expression.append(i)
			return self

	def __radd__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			self.expression.append([other])
			return self
		if isinstance(other, Variable):
			self.expression.append([1, other])
			return self
		if isinstance(other, Expression):
			for i in other:
				self.expression.append(i)
			return self

	def __mul__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			for i in range(len(self.expression)):
				self.expression[i][0] *= other
		if isinstance(other, Variable):
			for i in range(len(self.expression)):
				self.expression[i].append(other)
			return self
		if isinstance(other, Expression):
			raise TypeError("Not allowed operation!")

	def __le__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			self.expression.append(LOWER)
			self.expression.append(other)
			return self

	def __ge__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			self.expression.append(GREATER)
			self.expression.append(other)
			return self

	def __eq__(self, other):
		if isinstance(other, float): raise TypeError("Not allowed type!")
		if isinstance(other, int):
			self.expression.append(EQUAL)
			self.expression.append(other)
			return self

	def __iter__(self):
		return (i for i in self.expression if not isinstance(i, int))

	def __len__(self):
		return len([i for i in self.expression if not isinstance(i, int)])


	def sum_constants_in_expression(self):
		pop_it = False
		constant_index = 0
		try:
			for i in range(len(self)):
				if len(self.expression[i]) == 1:
					if pop_it:
						self.expression[constant_index][0] += self.expression[i][0]
						self.expression.pop(i)
					if not pop_it:
						pop_it = True
						constant_index = i
		except: pass
		return self