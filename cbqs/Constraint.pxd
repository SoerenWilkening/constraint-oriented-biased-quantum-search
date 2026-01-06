from libc.stdint cimport uint64_t, uint32_t, int64_t
from .Expression cimport expression_t, Expression
from .state cimport state_py, state_t

cdef extern from "src/constraint.h":
	ctypedef struct new_constraints_t:
		size_t num_constraints;  # number of constraints
		size_t *num_clauses;  # how many clauses per constraint
		size_t *clause_offset;  # offset, to correctly locate factor and length_clause given C and c
		int64_t *factors;  # store the factor of a clause
		size_t *clause_length;  # how many variables per clause
		size_t *variable_offset;  # where is the first index of the variables of a clause given constraint C
		size_t * variables;
		int * sense;
		int64_t *rhs;

		unsigned int *positive_indices;
		unsigned int *negative_indices;
		unsigned int *positive_offsets;
		unsigned int *negative_offsets;
		unsigned int *num_positive_indices;
		unsigned int *num_negative_indices;

	new_constraints_t init_new_constraint();

	new_constraints_t copy_new_constraint(new_constraints_t *con);

	void free_constraints(new_constraints_t *con);

	void print_new_constraint(new_constraints_t *con);

	void preprocessing(int n, new_constraints_t *con);

	void preprocessing_sparse(int n, new_constraints_t *con);

	void add_expression_to_constraints(new_constraints_t *con, expression_t *expr);

	int eval_constraints(new_constraints_t *con, state_t *sol, int max_item);
	int num_satisfied_constrains(new_constraints_t *con, state_t *sol);
	int64_t objective_value(new_constraints_t *obj, state_t *sol);


cdef class new_constraint:
	cdef new_constraints_t con;
	cdef int num_constraints;
	cdef void add(self, Expression expr)

cdef process_constraints(new_constraints_t *con, int n, int enforce_density)