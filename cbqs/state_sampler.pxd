from .Constraint cimport new_constraints_t, state_t
from .Constraint cimport new_constraint
from .SearchLib cimport QSearch, free_state
from .Constraint cimport new_constraint
from .state cimport state_py
# from .SearchLib import set_bias_wrapper, QSearch_wrapper

cdef extern from "approximate_state_sampler.h":
	ctypedef struct approximate_state_t:
		state_t *good;
		state_t *bad;
		size_t num_good;
		size_t num_bad;
		size_t allocated_good;
		size_t allocated_bad;
		double good_amplitude;
		double bad_amplitude;
		double delta;

	approximate_state_t *init_approximete_state(int n, double bias)
	void print_approximate_state(approximate_state_t *state)
	void free_approximate_state(approximate_state_t *state)
	int CSearch_opt_sampler(approximate_state_t *state, state_t *cur_sol,
	                        int samples,
	                        new_constraints_t *con, new_constraints_t *obj,
	                        int depth_look_ahead);



cdef class approximate_state:
	cdef approximate_state_t *state
	cdef int n
	# cdef c_opt_sampler(self, new_constraint obj , new_constraint con, state_py cur_sol, int samples)