from libc.stdint cimport uint64_t, uint32_t, int64_t
from libc.stdlib cimport calloc, free, srand

cdef extern from "src/intarray.h":
	ctypedef struct array_t:
		int n
		int bits
		uint64_t *part

	int sw_tstbit(array_t A, size_t B)

	void sw_flpbit(array_t A, size_t B);

# Forward declaration for solver context
cdef extern from "src/solver_ctx.h":
	ctypedef struct solver_ctx_t:
		pass  # Opaque to Cython

	solver_ctx_t* solver_ctx_create()
	void solver_ctx_free(solver_ctx_t* ctx)

cdef extern from "src/state.h":
	ctypedef struct state_t:
		int64_t tot_profit
		double prob
		array_t vector
		array_t branch
		int feasible

	state_t *init_state(int64_t ObjVal, int *array, int n)
	state_t *copy_state(state_t *state)
	void print_state(state_t *state)

	void free_state(state_t *state, size_t numStates)

	state_t *read_states(char ** name, int num_files, size_t *NumberStatesFinal, int n)

# updated() is declared in Branching.h with solver_ctx_t parameter
cdef extern from "src/Branching.h":
	state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense)

cdef class state_py:
	cdef state_t *state
	cdef size_t num_states
	cdef int[:] arr
	cdef int64_t objval
