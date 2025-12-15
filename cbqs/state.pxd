from libc.stdint cimport uint64_t, uint32_t, int64_t
import numpy as np
from libc.stdlib cimport calloc, free, srand
import os, sys

cdef extern from "src/intarray.h":
	ctypedef struct array_t:
		int n
		int bits
		uint64_t *part

	int sw_tstbit(array_t A, size_t B)

	void sw_flpbit(array_t A, size_t B);

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
	state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense)

cdef class state_py:
	cdef state_t *state
	cdef size_t num_states
	cdef int[:] arr
	cdef int64_t objval
