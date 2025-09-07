from libc.stdint cimport uint64_t, uint32_t, int64_t
from libc.stdlib cimport calloc, free, srand
from .Expression cimport expression_t
from .Expression cimport Expression
from .Constants import *

# typedef of the array_t structure to be usable in cython scripts
#
cdef extern from "src/intarray.h":
	ctypedef struct array_t:
		int n
		int bits
		uint64_t *part

	int sw_tstbit(array_t A, size_t B)

# Functions to manipulate states and execute the QSearch algorithm
#
cdef extern from "src/SearchLib.h":
	ctypedef void (*callback_t)(int64_t, size_t, double, double)

	ctypedef struct state_t:
		int64_t tot_profit
		double prob
		array_t vector
		array_t branch

	state_t *init_state(int64_t ObjVal, int *array, int n)
	state_t *copy_state(state_t *state)
	void print_state(state_t *state)
	void free_state(state_t *state, size_t numStates)

	state_t *read_states(char ** name, int num_files, size_t *NumberStatesFinal, int n)
	state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense)
	state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M, size_t *measured_index)
	int ctg(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, int stopping_time,
	        size_t *qtg_applications, int depth_look_ahead, int solver, int64_t stop_val, callback_t callback,
	        int *break_item) nogil

	int bfs(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, size_t *qtg_applications,
	        int depth_look_ahead, int solver, int64_t stop_val, callback_t callback) nogil

	int initial_state_preparation(state_t *new_sol, state_t *cur_sol,
	                              new_constraints_t *con,
	                              new_constraints_t *obj,
	                              int depth_look_ahead,
	                              int *break_item
	                              );

cdef extern from "src/constraint.h":
	ctypedef struct new_constraints_t:
		size_t num_constraints;  # number of constraints
		size_t *num_clauses;  # how many clauses per constraint
		size_t *clause_offset;  # offset, to correctly locate factor and length_clause given C and c
		int64_t *factors;  # store the factor of a clause
		size_t * clause_length;  # how many variables per clause
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

	void add_expression_to_constraints(new_constraints_t *con, expression_t *expr);

	int eval_constraints(new_constraints_t *con, state_t *sol, int max_item);
	int num_satisfied_constrains(new_constraints_t *con, state_t *sol);
	int64_t objective_value(new_constraints_t *obj, state_t *sol);

	# old implementation, get rid of in the future
	int true
	int false
# int undetermined

# Extern C written functions to set parameters for the biasing strategy
#
cdef extern from "src/Branching.h":
	ctypedef struct BranchingStats_t:
		double a, b, c;
		double bias;
		double *obj_dependent;
		double *constraint_dependent;

	cdef BranchingStats_t BranchingStats;
	void set_factors(double objective_factor, double constraint_factor, double bias_factor, double look_factor);
	void set_bias(double bias);
	void set_obj_dependence(double *dependence, int n);
	void set_constraint_dependence(double *dependence, int n);


cdef extern from "src/local_search.h":
	int local_search(state_t *cur_sol,
	                 new_constraints_t *con,
	                 new_constraints_t *obj,
	                 int distance,
	                 int stopping_time,
	                 int solver,
	                 int64_t stop_val,
	                 callback_t callback,
	                 int max_worse_acceptances,
	                 int stopping_criterion) nogil

	int quantum_local_search(new_constraints_t *obj,
	                         new_constraints_t *con,
	                         state_t *cur_sol, int k,
	                         size_t *total_oracle_applications,
                            callback_t callback) nogil

cdef class new_constraint:
	cdef new_constraints_t con;
	cdef int num_constraints;
	cdef void add(self, Expression expr)