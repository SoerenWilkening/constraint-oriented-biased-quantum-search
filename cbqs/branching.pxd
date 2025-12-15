from .state cimport state_t
from libc.stdlib cimport calloc, free, srand
import numpy as np

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

	double StateProbability(state_t *state, state_t *threshold);