from libc.stdint cimport uint64_t, uint32_t, int64_t
from libc.stdlib cimport calloc, free, srand
# from .Expression cimport expression_t
from .Constraint cimport new_constraints_t
from .state cimport *
# StateProbability declared below via direct extern from Branching.h
from .Model cimport Model, model_t

# Solver context for per-solve state management
cdef extern from "src/solver_ctx.h":
	# Match the C definition: struct solver_ctx {...}; typedef struct solver_ctx solver_ctx_t;
	cdef struct solver_ctx:
		# Only expose fields we need to access from Cython
		unsigned long long seed  # uint64_t - Master seed (0 = auto-generate)
		unsigned long long seed_used  # uint64_t - Actual seed used after init
		int num_threads  # Thread count (0 = auto-detect)
		int num_threads_used  # Actual thread count used after init
		int worker_id  # 0-based portfolio worker index (decorrelates PRNG stream)
		size_t oracle_count  # never-reset per-worker cumulative oracle charge (faithful metric)
		double runtime  # bd lif: per-worker wall-clock telemetry (replaces racy shared mod->runtime)
		int64_t callback_value  # bd 4uf: this worker's newest feasible incumbent (internal tot_profit), set by ctg before each callback
		# M0g (bd 8an.1.7, NORTHSTAR §9): per-worker opt-phase branching diagnostics
		unsigned long long opt_candidates  # uint64_t - # candidates CSearch_opt generated
		unsigned long long opt_flip_sum     # uint64_t - Σ realized Hamming radius
		unsigned long long opt_flip_sumsq   # uint64_t - Σ (realized radius)²
		unsigned long long opt_free_sum     # uint64_t - Σ both-feasible free decisions
		# M2a (bd 8an.3.1, NORTHSTAR §4/§12): per-phase decision-touch counters
		# (free + bothinf + forced == decisions; opt's free == opt_free_sum above)
		unsigned long long sat_decisions
		unsigned long long sat_free
		unsigned long long sat_bothinf
		unsigned long long sat_forced
		unsigned long long optsat_decisions
		unsigned long long optsat_free
		unsigned long long optsat_bothinf
		unsigned long long optsat_forced
		unsigned long long opt_decisions
		unsigned long long opt_bothinf
		unsigned long long opt_forced
	ctypedef solver_ctx solver_ctx_t
	const int64_t SOLVER_CTX_CALLBACK_VALUE_UNSET  # bd 4uf sentinel: callback site did not set a per-worker value
	solver_ctx_t* solver_ctx_create()
	void solver_ctx_free(solver_ctx_t* ctx)
	void solver_ctx_request_stop(solver_ctx_t* ctx)
	void solver_ctx_set_bias(solver_ctx_t* ctx, double bias)
	void solver_ctx_set_branching_weights(solver_ctx_t* ctx, const double* weights, int n)
	void solver_ctx_set_branching_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_bias_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_look_ahead_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_init_prng(solver_ctx_t* ctx)
	void solver_ctx_set_worker_id(solver_ctx_t* ctx, int worker_id)

	# Phase-specific setters (M1)
	void solver_ctx_set_sat_bias(solver_ctx_t* ctx, double bias)
	void solver_ctx_set_opt_sat_bias(solver_ctx_t* ctx, double bias)
	void solver_ctx_set_opt_bias(solver_ctx_t* ctx, double bias)

	void solver_ctx_set_sat_branching_weights(solver_ctx_t* ctx, const double* weights, int n)
	void solver_ctx_set_opt_sat_branching_weights(solver_ctx_t* ctx, const double* weights, int n)
	void solver_ctx_set_opt_branching_weights(solver_ctx_t* ctx, const double* weights, int n)

	void solver_ctx_set_sat_branching_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_opt_sat_branching_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_opt_branching_factor(solver_ctx_t* ctx, double factor)

	void solver_ctx_set_sat_bias_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_opt_sat_bias_factor(solver_ctx_t* ctx, double factor)
	void solver_ctx_set_opt_bias_factor(solver_ctx_t* ctx, double factor)

	# Variable ordering (M4/M5)
	void solver_ctx_set_variable_order(solver_ctx_t* ctx, const double* priorities, int n)
	void solver_ctx_set_default_order(solver_ctx_t* ctx, int n)

	# Consolidated parameter setter
	void solver_ctx_set_predicted_params(solver_ctx_t* ctx, double bias,
	                                      double branching_factor, double bias_factor,
	                                      const double* weights,
	                                      const double* variable_order, int n)

# StateProbability from Branching.h (relocated from branching.pxd)
cdef extern from "src/Branching.h":
	double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold)

# Functions to manipulate states and execute the QSearch algorithm
#
cdef extern from "src/SearchLib.h":
	ctypedef void (*callback_t)(void *)  # M0e: opaque ctx (solver_ctx_t* or NULL) for oracle-stamping

	ctypedef struct incumbents_t:
		state_t *states;
		int *search_stage;
		int allocated;
		int head;
		int num_states;
		int *initial_samples;

	state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M, size_t *measured_index)

	incumbents_t *init_incumbents(int n, state_t *st);
	void print_incumbents(incumbents_t *incumbents);
	void free_incumbents(incumbents_t *incumbents);

	int ctg(solver_ctx_t *ctx, model_t *mod, state_t *cur_sol, callback_t callback, incumbents_t *incumbents) nogil

	int initial_state_preparation(model_t *mod);

	double CSearch_opt_monte_carlo_sampler(solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error, int initial_samples) nogil
	double CSearch_opt_sat_monte_carlo_sampler(solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error, int direction, int initial_samples) nogil
	double CSearch_sat_monte_carlo_sampler(solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, double error, int initial_samples) nogil


cdef extern from "src/local_search.h":
	int local_search(solver_ctx_t *ctx, state_t *cur_sol, model_t *mod, callback_t callback) nogil

	int quantum_local_search(new_constraints_t *obj,
	                         new_constraints_t *con,
	                         state_t *cur_sol, int k,
	                         size_t *total_oracle_applications,
                            callback_t callback) nogil

cdef class incumbents:
	cdef incumbents_t *incumbent
	cdef solver_ctx_t *ctx  # Solver context for monte carlo sampler calls
	cdef void _set_ctx(self, solver_ctx_t* ctx)
