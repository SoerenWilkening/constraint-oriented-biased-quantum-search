#ifndef CONSTRAINT
#define CONSTRAINT

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "definitions.h"
#include "state.h"
#include "Expression.h"

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
	size_t num_constraints; // number of constraints
    size_t *num_clauses;    // how many clauses per constraint
    size_t *clause_offset; // offset, to correctly locate factor and length_clause given C and c
    int64_t *factors;       // store the factor of a clause
	size_t *clause_length;  // how many variables per clause
	size_t *variable_offset;// where is the first index of the variables of a clause given constraint C
	size_t *variables;      //

    int allocated_factors;
	int allocated_variables;

	int *sense;
	int64_t *rhs;

	// faster access for sampling routine
	unsigned int *positive_indices;
	unsigned int *negative_indices;
	unsigned int *positive_offsets;
	unsigned int *negative_offsets;
	unsigned int *num_positive_indices;
	unsigned int *num_negative_indices;
} new_constraints_t;


// instead of creating a constraint and add it to the list of constraints,
// an expression will be passed to the constraint data
// an expression always refers to one constraint
new_constraints_t init_new_constraint();

new_constraints_t copy_new_constraint(new_constraints_t *con);

static inline size_t first_clause_index(new_constraints_t *con, size_t C) {
	if (C == 0) return 0;
	return con->clause_offset[C - 1];
}

static inline size_t first_variable_index(size_t cls, size_t clause_offset) {
	if (cls == 0) return clause_offset * (MAXCLAUSESIZE - 1);
	return clause_offset * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}

static inline size_t variable_index(size_t cls, size_t k, size_t clause_offset) {
	return first_variable_index(cls, clause_offset) + k;
}

//inline size_t first_clause_index(new_constraints_t *con, size_t C);
//
//inline size_t first_variable_index(size_t cls, size_t clause_offset);
//
//inline size_t variable_index(size_t cls, size_t k, size_t clause_offset);

void free_constraints(new_constraints_t *con);

void print_new_constraint(new_constraints_t *con);

void add_expression_to_constraints(new_constraints_t *con, expression_t *expr);

void preprocessing(int n, new_constraints_t *con);

int eval_constraints(new_constraints_t *con, state_t *sol, int max_item);
int num_satisfied_constrains(new_constraints_t *con, state_t *sol);
int64_t objective_value(new_constraints_t *obj, state_t *sol);


int64_t prepare(new_constraints_t *obj, state_t *sol, array_t *ful);





#define MINSIZE 2048






//// OLD IMPLEMENTAIOTN
//typedef struct{
////    long double *literal; // in the form of [value, index] (linear) or [value, index1, index2] (quadratic)
//    int64_t factor;
//    int *variables;
//    int len_literal; // 2 for linear, 3 for quadratic expression, ...
//} lit_t;

//
//typedef struct {
//    lit_t *literals;
//    int num_literals;
//    int sense;
//    int64_t rhs;
//
//    int first_non_closed;
//    int64_t rhs_adapted;
//
//    int evaluated;
//} constraint_t;
//
//typedef struct {
//    constraint_t *constraints;
//    int num_constraints;
//} constraint_list_t;
//
//constraint_list_t init_con_list();
//
//constraint_t init_con();
//lit_t init_literal(int64_t *literal, int len_literal);

//void add_constraint(constraint_list_t *con_list, constraint_t *con);
//constraint_t *add_constraint(constraint_list_t *con_list);
//void add_literal(constraint_t *con, int64_t *literal, int len_literal);
//void add_sense(constraint_t *con, int sense);
//void add_rhs(constraint_t *con, int64_t rhs);
//void add_digits(constraint_t *con, int digits);
//
//void reset_rhs_adapted(constraint_list_t *con);
//
//void print_constraints(constraint_list_t *cons);

//int eval_constraint2(constraint_t *con, state_t *assignment, int assigned, int close);
//int quantum_feasibility2(constraint_list_t *con, state_t *assignment, int assigned, int close);
//int count_satisfyed_constraints(constraint_list_t *con, state_t *assignment, int assigned, int close, int allowed_false);
//
//int64_t ObjVal(state_t *state, constraint_list_t *obj);
//
//int64_t ChangedObjVal(  constraint_list_t *obj, // objective function
//                            state_t *new, // new state
//                            int NumChanges, // how many bits were flipped
//                            int *ChangedBits, // which bits were flipped
//                            int **Indices, // objective term indices involving every item
//                            int *NumIndices, // in how many terms every item occours
//                            int *Fulfilled, // are terms of objective fulfilled
//                            int *ChangedTerms,
//                            int *NumChangedTerms
//                            );

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
		array_t *ful,
//		int * fulfill,
		int **changes,
		int *num_changes,
		array_t *inv
//		int *investigated
);

#endif
