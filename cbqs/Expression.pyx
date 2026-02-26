import math
import warnings
import os
from .Constants import *

# int64 range constants for overflow detection
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1

def _validate_numeric(value, context=""):
	"""Validate a numeric value for use as coefficient or constant.

	Rejects NaN, Inf, and values outside int64_t range.
	Called before passing values to C layer.
	"""
	if isinstance(value, float):
		if math.isnan(value):
			raise ValueError(
				f"NaN not allowed as coefficient{' in ' + context if context else ''}"
			)
		if math.isinf(value):
			raise ValueError(
				f"Inf not allowed as coefficient{' in ' + context if context else ''}"
			)
		raise TypeError(
			f"Float coefficients not allowed; use int{' in ' + context if context else ''}"
		)
	if isinstance(value, int) and not isinstance(value, bool):
		if value < _INT64_MIN or value > _INT64_MAX:
			raise OverflowError(
				f"Coefficient {value} outside int64 range [{_INT64_MIN}, {_INT64_MAX}]"
			)

# Deprecation warning control for Expression mutation behavior change
_CBQS_SUPPRESS_DEPRECATION = os.environ.get('CBQS_SUPPRESS_DEPRECATION', '').lower() in ('1', 'true', 'yes')
_deprecation_warned = False

def _warn_expression_immutability():
	"""Emit one-time deprecation warning about Expression immutability change."""
	global _deprecation_warned
	if not _CBQS_SUPPRESS_DEPRECATION and not _deprecation_warned:
		_deprecation_warned = True
		warnings.warn(
			"Expression operators now return new objects instead of mutating self. "
			"Use += for in-place mutation (e.g., expr += 5). "
			"This matches Python numeric semantics. "
			"Set CBQS_SUPPRESS_DEPRECATION=1 to suppress this warning.",
			DeprecationWarning,
			stacklevel=3  # Points to user's code
		)


class Variable:
	"""A binary or integer decision variable.

	Variables are the building blocks of expressions. They are created
	via ``Model.add_variable()`` or ``Model.add_variables()`` rather than
	instantiated directly. Arithmetic operators (``+``, ``*``) on
	variables produce ``Expression`` objects.

	Parameters
	----------
	index : int
		Non-negative integer index uniquely identifying this variable.
	name : str
		Display name (auto-generated as ``"x{index}"`` if ``"__"``).
	lb : int
		Lower bound (typically 0 for binary variables).
	ub : int
		Upper bound (typically 1 for binary variables).
	vtype : int
		Variable type constant (e.g., ``INTEGER``).

	Attributes
	----------
	index : int
		Variable index.
	name : str
		Display name.
	lb : int
		Lower bound.
	ub : int
		Upper bound.
	vtype : int
		Variable type.
	"""

	def __init__(self, index = 0, name = "__", lb = 0, ub = 1, vtype = INTEGER):
		if not isinstance(index, int) or isinstance(index, bool):
			raise TypeError(f"Variable index must be int, got {type(index).__name__}")
		if index < 0:
			raise ValueError(f"Variable index {index} must be non-negative")
		if not isinstance(lb, int) or isinstance(lb, bool):
			raise TypeError(f"Variable lower bound must be int, got {type(lb).__name__}")
		if not isinstance(ub, int) or isinstance(ub, bool):
			raise TypeError(f"Variable upper bound must be int, got {type(ub).__name__}")
		if ub < lb:
			raise ValueError(
				f"Variable bounds inconsistent: upper ({ub}) < lower ({lb})"
			)
		self.vtype = vtype
		self.index = index
		self.name = name
		if name == "__": self.name = f"x{index}"
		self.lb, self.ub = lb, ub

	def __str__(self):
		return f"{self.name}"

	def __add__(self, other):
		"""Create an Expression by adding this variable to another operand.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to add.

		Returns
		-------
		Expression
			A new expression representing ``self + other``.
		"""
		_validate_numeric(other)
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
		"""Create an Expression by adding another operand to this variable.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to add.

		Returns
		-------
		Expression
			A new expression representing ``other + self``.
		"""
		_validate_numeric(other)
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
		"""Create an Expression by multiplying this variable by a coefficient.

		Parameters
		----------
		other : int, Variable, or Expression
			The multiplier.

		Returns
		-------
		Expression
			A new expression representing ``self * other``.
		"""
		_validate_numeric(other)
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
		"""Create an Expression by multiplying a coefficient by this variable.

		Parameters
		----------
		other : int, Variable, or Expression
			The multiplier.

		Returns
		-------
		Expression
			A new expression representing ``other * self``.
		"""
		_validate_numeric(other)
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
	"""A linear or polynomial expression over binary decision variables.

	Expressions represent mathematical formulas used as objectives and
	constraints in the ``Model``. They are built using Python arithmetic
	operators on ``Variable`` objects:

	- ``x[0] + x[1]`` creates a sum expression
	- ``3 * x[0]`` creates a scaled variable term
	- ``x[0] * x[1]`` creates a product (quadratic) term
	- ``expr <= 5`` converts to a less-than-or-equal constraint

	Binary operators (``+``, ``*``) return **new** Expression objects
	without modifying the originals. In-place operators (``+=``, ``*=``)
	mutate the expression for efficiency.

	The underlying data is stored in a C ``expression_t`` struct for
	performance. Expressions should not be created directly; use
	``Variable`` arithmetic or ``Model.add_variable()`` instead.
	"""

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
		"""Create a copy of this expression.

		Copies the expression terms by adding them to a new Expression.
		The copy is independent and can be modified without affecting
		the original.

		Returns
		-------
		Expression
			A new Expression with the same terms.
		"""
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
		"""Create a fully independent deep copy of this expression.

		Copies the underlying C ``expression_t`` data so the new
		expression shares no memory with the original. Also preserves
		the constraint sense and right-hand side if set.

		Parameters
		----------
		memo : dict
			Memo dictionary for the copy module.

		Returns
		-------
		Expression
			A new, fully independent Expression.
		"""
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
		new = multiply_expressions(<expression_t *> self.expr, <expression_t *> other.expr)
		add_expression(ne.expr, new)
		free_expression(new)

	def merge(self):
		"""Merge duplicate terms in this expression by summing coefficients.

		Scans all terms and combines any that reference the same variable
		indices. For example, ``3*x0 + 5*x0`` becomes ``8*x0``. Operates
		on the underlying C structure in place.

		Returns
		-------
		Expression
			Returns self for method chaining.
		"""
		merge_expression(self.expr)
		return self

	cdef c_liste(self):
		l = [
			[self.expr[0].literals[MAXCLAUSESIZE * j + i] for i in range(self.expr[0].len_literal[j])]
			for j in range(self.expr[0].expr_size) if self.expr[0].len_literal[j] != 0
		]
		if self.sense != -2:
			l += [self.sense, self.rhs]
		return l

	def __iter__(self):
		return self.c_liste().__iter__()

	def __add__(self, other):
		"""Return a new Expression representing ``self + other``.

		Does not modify the original expression. Supported operand types
		are ``int``, ``Variable``, and ``Expression``.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to add.

		Returns
		-------
		Expression
			A new expression representing the sum.
		"""
		_validate_numeric(other)

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
		"""Return a new Expression representing ``other + self``.

		Called when the left operand does not support addition with
		an Expression. Does not modify the original expression.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to add.

		Returns
		-------
		Expression
			A new expression representing the sum.
		"""
		_validate_numeric(other)

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
		"""Add *other* to this expression in place.

		Mutates the expression directly, avoiding a copy. Use ``+=``
		for efficiency when the original is no longer needed.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to add.

		Returns
		-------
		Expression
			Returns self (mutated).
		"""
		_validate_numeric(other)
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
		"""Subtract *other* from this expression in place.

		Mutates the expression directly, avoiding a copy. Use ``-=``
		for efficiency when the original is no longer needed.

		Parameters
		----------
		other : int, Variable, or Expression
			The value to subtract.

		Returns
		-------
		Expression
			Returns self (mutated).
		"""
		_validate_numeric(other)
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
		"""Return a new Expression representing ``self * other``.

		Does not modify the original expression. For scalar (int)
		multiplication, all term coefficients are scaled. For
		variable multiplication, creates product terms.

		Parameters
		----------
		other : int, Variable, or Expression
			The multiplier.

		Returns
		-------
		Expression
			A new expression representing the product.
		"""
		cdef Expression result
		_validate_numeric(other)

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
		"""Return a new Expression representing ``other * self``.

		Called when the left operand does not support multiplication
		with an Expression. Does not modify the original expression.

		Parameters
		----------
		other : int, Variable, or Expression
			The multiplier.

		Returns
		-------
		Expression
			A new expression representing the product.
		"""
		cdef Expression result
		_validate_numeric(other)

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
		"""Multiply this expression by *other* in place.

		Mutates the expression directly, avoiding a copy. Use ``*=``
		for efficiency when the original is no longer needed.

		Parameters
		----------
		other : int, Variable, or Expression
			The multiplier.

		Returns
		-------
		Expression
			Returns self (mutated).
		"""
		_validate_numeric(other)
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
		"""Create a less-than-or-equal constraint: ``expr <= rhs``.

		Converts this expression into a constraint that can be passed
		to ``Model.add_constraint()``. Modifies the expression in place
		by setting its sense and right-hand side.

		Parameters
		----------
		other : int
			The right-hand side value.

		Returns
		-------
		Expression
			This expression with constraint metadata attached.

		Examples
		--------
		>>> x = model.add_variables(3)
		>>> model.add_constraint(x[0] + x[1] + x[2] <= 2)
		"""
		_validate_numeric(other)
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
		"""Create a greater-than-or-equal constraint: ``expr >= rhs``.

		Converts this expression into a constraint by negating coefficients
		and adjusting the right-hand side. The result can be passed to
		``Model.add_constraint()``.

		Parameters
		----------
		other : int
			The right-hand side value.

		Returns
		-------
		Expression
			This expression with constraint metadata attached.

		Examples
		--------
		>>> x = model.add_variables(3)
		>>> model.add_constraint(x[0] + x[1] >= 1)
		"""
		_validate_numeric(other)
		if isinstance(other, int):
			potential = 0

			multiply_constant(self.expr, -1)
			for i in range(self.expr[0].expr_size):
				if self.expr[0].literals[MAXCLAUSESIZE * i] < 0:
					potential -= self.expr[0].literals[MAXCLAUSESIZE * i]

			add_sense_to_expression(self.expr, LOWER)
			add_rhs_to_expression(self.expr, -other + potential)
			self.sense = LOWER  # originally GREATER
			self.rhs = -other + potential
			return self

	def __eq__(self, other):
		"""Create an equality constraint: ``expr == rhs``.

		Converts this expression into an equality constraint. The result
		can be passed to ``Model.add_constraint()``.

		Parameters
		----------
		other : int
			The right-hand side value.

		Returns
		-------
		Expression
			This expression with constraint metadata attached.

		Examples
		--------
		>>> x = model.add_variables(3)
		>>> model.add_constraint(x[0] + x[1] + x[2] == 2)
		"""
		_validate_numeric(other)
		if isinstance(other, int):
			add_sense_to_expression(self.expr, EQUAL)
			add_rhs_to_expression(self.expr, other)
			self.sense = EQUAL
			self.rhs = other
			return self
