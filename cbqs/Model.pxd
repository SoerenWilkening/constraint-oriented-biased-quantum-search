# from copy import copy
# from time import time
# from warnings import warn
#
# import numpy as np
# from joblib import Parallel, delayed
# from .CircuitBackendBinder import circuit
# from .Constants import *
# from .Expression import Variable, Expression
# from .state import state_py
# from Constraint import new_constraint
# from .branching import set_seed, set_bias_wrapper, set_factors_wrapper, set_obj_dependence_wrapper
# from .SearchLib import (run_sampling, run_bfs, run_local_search, run_quantum_local_search, run_general_greedy, reset_c_flags)
# from .StateGenerator import exact_simulator
# from .state_sampler import approximate_state

from .Constraint cimport new_constraints_t
from .state cimport state_t

cdef extern from "src/model.h":
	ctypedef struct model_t:
		double runtime
		new_constraints_t *obj;
		new_constraints_t *con;
		state_t *initial_state
		state_t *global_opt
		size_t M
		int n
		int stopping_time
		int stop_val
		int depth_look_ahead
		int num_workers
		int ignore_constraint_search
		double *manual_bias
		double bias_factor
		double manual_bias_factor
		double look_ahead_factor
		int monte_carlo_estimate
		int reset_delta
		int max_delta

	model_t *init_model();

	void free_model(model_t *mod);

	void print_model(model_t *mod)