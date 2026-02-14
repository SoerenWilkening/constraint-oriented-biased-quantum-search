from .state cimport state_t
from libc.stdlib cimport calloc, free, srand
import numpy as np

# Forward declaration for solver context
cdef extern from "src/solver_ctx.h":
	ctypedef struct solver_ctx_t:
		pass  # Opaque to Cython

cdef extern from "src/Branching.h":
	ctypedef struct BranchingStats_t:
		double *branching_weights
		int num_weights
		double branching_factor
		double bias_factor
		double bias
		double look_factor

	cdef BranchingStats_t BranchingStats

	double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold)
