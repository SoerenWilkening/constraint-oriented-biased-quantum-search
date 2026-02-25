from libc.stdint cimport uint64_t, uint32_t, int64_t
from .Expression cimport expression_t, Expression
from .state cimport state_py, state_t

cdef extern from "src/constraint.h":
	ctypedef struct new_constraints_t:
		uint32_t num_constraints;  # number of constraints
		uint32_t *num_clauses;  # how many clauses per constraint
		uint32_t *clause_offset;  # offset, to correctly locate factor and length_clause given C and c
		int64_t *factors;  # store the factor of a clause
		uint32_t *clause_length;  # how many variables per clause
		uint32_t *variable_offset;  # where is the first index of the variables of a clause given constraint C
		uint32_t *variables;
		int *sense;
		int64_t *rhs;

		uint32_t *positive_indices;
		uint32_t *negative_indices;
		uint32_t *positive_offsets;
		uint32_t *negative_offsets;
		uint32_t *num_positive_indices;
		uint32_t *num_negative_indices;

		uint32_t *neg_rows;
		uint32_t *neg_cols;
		uint32_t *pos_rows;
		uint32_t *pos_cols;

		int sparsity;

		size_t nnz_pos;
		size_t nnz_neg;

		uint32_t array_length;

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