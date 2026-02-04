from libc.stdint cimport uint64_t, uint32_t, int64_t
from libc.stdlib cimport calloc, free, srand
from .Constraint cimport new_constraints_t
from .state cimport state_t

cdef extern from "src/model.h":
	ctypedef struct model_t:
		double runtime;
		new_constraints_t *obj;
		new_constraints_t *con;
		state_t *initial_state;
		state_t *global_opt;
		size_t M;
		int break_item;
		int n;
		int stopping_time;
		int stop_val;
		int depth_look_ahead;
		int num_workers;
		int ignore_constraint_search;
		double *manual_bias;
		double bias_factor;
		double manual_bias_factor;
		double look_ahead_factor;
		int monte_carlo_estimate;
		int reset_delta;
		int max_delta;
		int solver
		int qtg_applications
		int max_worse_acceptances;
		int stopping_condition;
		int distance;

	model_t *init_model();

	void free_model(model_t *mod);

	void print_model(model_t *mod)


cdef class Model:
	cdef model_t *mod
	cdef int gpu_imported
	cdef int initialized

	cdef public object sparsity
	cdef public object stgen
	cdef public object global_opt
	cdef public object calls
	cdef public object met
	cdef public object objective
	cdef public object constraint
	cdef public object obj_expr
	cdef public object con_expr
	cdef public object sense
	cdef public object n
	cdef public object variables
	cdef public object initial_state
	cdef public object solver
	cdef public object feasible
	cdef public object grover_iterations
	cdef public object quantum_cycles
	# cdef public object objective_value
	cdef public object final_state
	cdef public object improved
	cdef public object gpu_compiled
	cdef public object constraints_compiled
	cdef public object circuit