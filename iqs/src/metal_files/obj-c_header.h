//
// Created by Sören Wilkening on 30.08.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_OBJ_C_HEADER_H
#define IMPROVED_QUANTUM_SEARCH_OBJ_C_HEADER_H

#include <stdlib.h>

typedef struct {
	unsigned int n;
	unsigned int bits;
	uint32_t *part;
} array_32_t;

typedef struct {
	int32_t tot_profit;
	array_32_t vector;
	int feasible;
} state_32_t;

typedef struct{
	size_t num_constraints; // number of constraints
	size_t *num_clauses;    // how many clauses per constraint
	size_t *clause_offset; // offset, to correctly locate factor and length_clause given C and c
	int32_t *factors;       // store the factor of a clause
	size_t *clause_length;  // how many variables per clause
	size_t *variable_offset;// where is the first index of the variables of a clause given constraint C
	size_t *variables;      //

	int allocated_factors;
	int allocated_variables;

	int *sense;
	int32_t *rhs;

	// faster access for sampling routine
	unsigned int *positive_indices;
	unsigned int *negative_indices;
	unsigned int *positive_offsets;
	unsigned int *negative_offsets;
	unsigned int *num_positive_indices;
	unsigned int *num_negative_indices;
} new_constraints_t;

#endif //IMPROVED_QUANTUM_SEARCH_OBJ_C_HEADER_H
