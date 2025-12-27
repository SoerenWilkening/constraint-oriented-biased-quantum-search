from libc.stdint cimport uint64_t, uint32_t, int64_t
from libc.stdlib cimport calloc, free, srand
# from .Expression cimport expression_t

from .Constraint cimport new_constraint
from .Constraint cimport new_constraints_t
from .state cimport *
from .branching cimport StateProbability
from .branching import set_bias_wrapper, set_seed
from .Constants import *

# Functions to manipulate states and execute the QSearch algorithm
#
cdef extern from "src/SearchLib.h":
	ctypedef void (*callback_t)(int64_t, size_t, double, double)

	ctypedef struct incumbents_t:
		state_t *states;
		int *search_stage;
		int allocated;
		int head;
		int num_states;
		int *initial_samples;

	void reset_flag();

	state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M, size_t *measured_index)

	incumbents_t *init_incumbents(int n, state_t *st);
	void print_incumbents(incumbents_t *incumbents);
	void free_incumbents(incumbents_t *incumbents);

	int ctg(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, int stopping_time,
	        size_t *qtg_applications, int depth_look_ahead, int solver, int64_t stop_val, callback_t callback,
	        state_t *global_opt, int ignore_constraint_search, incumbents_t *incumbent) nogil

	int bfs(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, size_t *qtg_applications,
	        int depth_look_ahead, int solver, int64_t stop_val, callback_t callback) nogil

	int initial_state_preparation(state_t *new_sol, state_t *cur_sol,
	                              new_constraints_t *con,
	                              new_constraints_t *obj,
	                              int depth_look_ahead,
	                              int *break_item
	                              );

	double CSearch_opt_monte_carlo_sampler(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error, int initial_samples) nogil
	double CSearch_opt_sat_monte_carlo_sampler(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error, int direction, int initial_samples) nogil
	double CSearch_sat_monte_carlo_sampler(state_t *cur_sol, new_constraints_t *con, double error, int initial_samples) nogil



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

cdef class incumbents:
	cdef incumbents_t *incumbent