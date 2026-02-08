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
	def __cinit__(self):
		self.con = init_new_constraint()
		self.num_constraints = 0

	def __str__(self):
		print_new_constraint(&self.con)
		return ""

	def __dealloc__(self):
		free_constraints(&self.con)

	def __copy__(self):
		new_con = new_constraint()
		new_con.con = copy_new_constraint(&self.con)
		new_con.num_constraints = self.num_constraints
		return new_con

	def __len__(self):
		return self.num_constraints

	cdef void add(self, Expression expr):
		self.num_constraints += 1
		add_expression_to_constraints(&self.con, <expression_t *> expr.expr)

	def process(self, int n, enforce_density = False):
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
		self.add(expr)

	def eval_con(self, state: state_py):
		return eval_constraints(&self.con, state.state, state.state[0].vector.bits)

	def eval_con_from_array(self, array: list):
		st = state_py(0, array)
		res = self.eval_con(st)
		del st
		return res

	def eval_obj(self, state: state_py):
		return objective_value(&self.con, state.state)