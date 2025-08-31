#ifndef METAL_FUNCTIONS_H
#define METAL_FUNCTIONS_H

typedef struct {
	int   tot_profit;
	uint  feasible;
	uint  n;
	uint  bits;
	uint  x_offset;
} state_32_t;

typedef struct{
	size_t num_constraints; // number of constraints
	device size_t *num_clauses;    // how many clauses per constraint
	device size_t *clause_offset; // offset, to correctly locate factor and length_clause given C and c
	device int32_t *factors;       // store the factor of a clause
	device size_t *clause_length;  // how many variables per clause
	device size_t *variable_offset;// where is the first index of the variables of a clause given constraint C
	device size_t *variables;      //

	int allocated_factors;
	int allocated_variables;

	device int *sense;
	device int32_t *rhs;

	// faster access for sampling routine
	device unsigned int *positive_indices;
	device unsigned int *negative_indices;
	device unsigned int *positive_offsets;
	device unsigned int *negative_offsets;
	device unsigned int *num_positive_indices;
	device unsigned int *num_negative_indices;
} new_constraints_t;

#endif