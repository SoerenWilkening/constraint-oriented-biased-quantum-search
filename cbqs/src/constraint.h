#ifndef CONSTRAINT
#define CONSTRAINT

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include "definitions.h"
#include "state.h"
#include "Expression.h"

// Max variables per clause in constraint storage (independent of Expression storage)
#define CONSTRAINT_VARS_PER_CLAUSE 4

// create constraint_list in the follwoing way:
//  -> linear implementation of tensor
//  -> given C constraints and m clauses per constraint with k variables per clause
//  -> 1d arrays representing:
//      -> num_clauses: length = C: how many clauses in constraint
//      -> clauses_offset: given C, what is the index of clause cl
//      -> factors: length <= C * m, stores all factors of all clauses in constraints
//          -> given C, value for clause cl is stored at clauses_offset[C] + cl
//      -> length_clause: length <= C * m, stores the number of variables of every clause.
//          -> given C, value for clause cl is stored at clauses_offset[C] + cl
//      -> variables_offset: length <= C * m, given C and cl, what is the first index of the variables fot that clause
//      -> variables: length <= C * m * k
//      -> senses: length = C,
//      -> rhs: length = C

#define MINARRAYSIZE 50000

typedef struct{
	uint32_t num_constraints; // number of constraints
    uint32_t *num_clauses;    // how many clauses per constraint
    uint32_t *clause_offset; // offset, to correctly locate factor and length_clause given C and c
    int64_t *factors;       // store the factor of a clause
	uint32_t *clause_length;  // how many variables per clause
	uint32_t *variable_offset;// where is the first index of the variables of a clause given constraint C
	uint32_t *variables;      //

	int total_clauses;
	int total_variables;

    size_t allocated_factors;
	size_t allocated_variables;

	int *sense;
	int64_t *rhs;

	// faster access for sampling routine
	uint32_t *positive_indices;
	uint32_t *negative_indices;
	uint32_t *positive_offsets;
	uint32_t *negative_offsets;
	uint32_t *num_positive_indices;
	uint32_t *num_negative_indices;
	uint32_t positive_array_length;
	uint32_t negative_array_length;
  
    uint32_t *neg_rows;
    uint32_t *neg_cols;
    uint32_t *pos_rows;
    uint32_t *pos_cols;
    
    int sparsity;
    
    size_t nnz_pos;
    size_t nnz_neg;
  
	uint32_t array_length;
} new_constraints_t;


// instead of creating a constraint and add it to the list of constraints,
// an expression will be passed to the constraint data
// an expression always refers to one constraint
new_constraints_t init_new_constraint(void);

new_constraints_t copy_new_constraint(new_constraints_t *con);

static inline size_t first_clause_index(new_constraints_t *con, size_t C) {
	if (C == 0) return 0;
	return con->clause_offset[C - 1];
}

static inline size_t first_variable_index(size_t cls, size_t clause_offset) {
	if (cls == 0) return clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1);
	return clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1) + (CONSTRAINT_VARS_PER_CLAUSE - 1) * cls;
}

static inline size_t variable_index(size_t cls, size_t k, size_t clause_offset) {
	return first_variable_index(cls, clause_offset) + k;
}


void free_constraints(new_constraints_t *con);

void print_new_constraint(new_constraints_t *con);

void add_expression_to_constraints(new_constraints_t *con, expression_t *expr);

void preprocessing(int n, new_constraints_t *con);

int64_t get_index(uint32_t *columns, uint32_t *rows, int item, int cnstr, size_t nnz, int C);

void preprocessing_sparse( int n, new_constraints_t *con);

int eval_constraints(new_constraints_t *con, state_t *sol, int max_item);
int num_satisfied_constrains(new_constraints_t *con, state_t *sol);
int64_t objective_value(new_constraints_t *obj, state_t *sol);


int64_t prepare(new_constraints_t *obj, state_t *sol, array_t *ful);

#define MINSIZE 2048

int64_t objective_value_improved(new_constraints_t *obj, // objective function
                                 state_t *new,    // new state
                                 int NumChanges,  // how many bits were flipped
                                 int *ChangedBits,// which bits were flipped
                                 array_t *ful,  // are terms of objective fulfilled
                                 int **changes,
                                 int *num_changes
);

int constraint_violation(new_constraints_t *con, state_t *sol, size_t cnstr);
int prepare_constraints(new_constraints_t *con, state_t *sol, array_t *ful);
int adjusted_constraint_violation(
		new_constraints_t *con, int item,
		const unsigned int *indices,
		const unsigned int *num_indices,
		const unsigned int *offsets, state_t *cur_sol,
		int negative,
		int64_t *ret_total,
		const array_t *ful,
//		int * fulfill,
		int **changes,
		int *num_changes,
		array_t *inv
//		int *investigated
);

#endif
