from .Constants import *


cdef process_constraints(new_constraints_t *con, int n, int enforce_density):
	tot = 0
	for i in range(con[0].num_constraints):
		tot += con[0].num_clauses[i]

	if 10 * tot > n * con[0].num_constraints or enforce_density:
		preprocessing(n, con)
		con[0].sparsity = DENSE
		return DENSE
	else:
		preprocessing_sparse(n, con)
		con[0].sparsity = SPARSE
		return SPARSE


cdef class new_constraint:
	"""Container for constraint expressions used by the CBQS solver.

	Stores a set of constraint expressions and their preprocessed index
	structures. Constraints are added via ``Model.add_constraint()``
	rather than using this class directly. Internally manages the
	C-level ``new_constraints_t`` structure for efficient constraint
	evaluation during search.

	Attributes
	----------
	num_constraints : int
		Number of constraint expressions in this container.
	"""

	def __cinit__(self):
		self.con = init_new_constraint()
		self.num_constraints = 0

	def __str__(self):
		print_new_constraint(&self.con)
		return ""

	def __dealloc__(self):
		free_constraints(&self.con)

	def __copy__(self):
		"""Create a deep copy of this constraint set.

		Copies all underlying C data structures so the new constraint
		set is fully independent from the original.

		Returns
		-------
		new_constraint
			A new constraint set with identical contents.
		"""
		new_con = new_constraint()
		new_con.con = copy_new_constraint(&self.con)
		new_con.num_constraints = self.num_constraints
		return new_con

	def __len__(self):
		"""Return the number of constraint expressions in this container.

		Returns
		-------
		int
			Constraint count.
		"""
		return self.num_constraints

	cdef void add(self, Expression expr):
		self.num_constraints += 1
		add_expression_to_constraints(&self.con, <expression_t *> expr.expr)

	def process(self, int n, enforce_density = False):
		"""Preprocess constraints for efficient evaluation during solving.

		Builds internal index structures that map variables to the
		clauses they appear in. Automatically selects dense or sparse
		representation based on clause density (dense if
		``10 * total_clauses > n * num_constraints``).

		Parameters
		----------
		n : int
			Number of variables in the model.
		enforce_density : bool, optional
			Force dense representation regardless of sparsity analysis.
			Default: False.

		Returns
		-------
		int
			``DENSE`` or ``SPARSE`` constant indicating the chosen
			representation.
		"""
		tot = 0
		for i in range(self.con.num_constraints):
			tot += self.con.num_clauses[i]

		if 10 * tot > n * self.con.num_constraints or enforce_density:
			preprocessing(n, &self.con)
			return DENSE
		else:
			preprocessing_sparse(n, &self.con)
			return SPARSE

	def add_expression(self, expr: Expression):
		"""Add an expression as a constraint to this container.

		Parameters
		----------
		expr : Expression
			The constraint expression to add (should have a comparison
			sense set via ``<=``, ``>=``, or ``==``).
		"""
		self.add(expr)

	def eval_con(self, state: state_py):
		"""Evaluate constraint satisfaction for a given state.

		Checks all constraints against the variable assignment in
		*state* using the C evaluation engine.

		Parameters
		----------
		state : state_py
			The state (variable assignment) to evaluate.

		Returns
		-------
		int
			Constraint evaluation result (nonzero if all satisfied).
		"""
		return eval_constraints(&self.con, state.state, state.state[0].vector.bits)

	def eval_con_from_array(self, array: list):
		"""Evaluate constraint satisfaction from a Python list.

		Convenience method that creates a temporary state from the
		given assignment array and evaluates constraints against it.

		Parameters
		----------
		array : list of int
			Binary variable assignment (one entry per variable, each 0 or 1).

		Returns
		-------
		int
			Constraint evaluation result (nonzero if all satisfied).
		"""
		st = state_py(0, array)
		res = self.eval_con(st)
		del st
		return res

	def eval_obj(self, state: state_py):
		"""Evaluate the objective function value for a given state.

		Computes the objective value by evaluating the objective
		expression against the variable assignment in *state*.

		Parameters
		----------
		state : state_py
			The state (variable assignment) to evaluate.

		Returns
		-------
		int
			The objective function value.
		"""
		return objective_value(&self.con, state.state)