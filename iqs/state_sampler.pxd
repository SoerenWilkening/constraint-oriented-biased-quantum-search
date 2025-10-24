from .SearchLib cimport new_constraints_t, state_t
from .SearchLib cimport state_py, new_constraint
from .SearchLib import set_bias_wrapper

cdef extern from "approximate_state_sampler.h":
	ctypedef struct approximate_state_t:
		pass

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
	cdef c_opt_sampler(self, new_constraint obj , new_constraint con, state_py cur_sol, int samples)