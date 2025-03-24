#ifndef CONSTRAINT
#define CONSTRAINT

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "definitions.h"
#include "state.h"

typedef struct{
//    long double *literal; // in the form of [value, index] (linear) or [value, index1, index2] (quadratic)
    int64_t factor;
    int *variables;
    int len_literal; // 2 for linear, 3 for quadratic expression
} lit_t;


typedef struct {
    lit_t *literals;
    int num_literals;
    int sense;
    int64_t rhs;

    int first_non_closed;
    int64_t rhs_adapted;

    int evaluated;
} constraint_t;

typedef struct {
    constraint_t *constraints;
    int num_constraints;
} constraint_list_t;

constraint_list_t init_con_list();

constraint_t init_con();
lit_t init_literal(int64_t *literal, int len_literal);

void add_constraint(constraint_list_t *con_list, constraint_t *con);
void add_literal(constraint_t *con, int64_t *literal, int len_literal);
void add_sense(constraint_t *con, int sense);
void add_rhs(constraint_t *con, int64_t rhs);
void add_digits(constraint_t *con, int digits);

void print_constraints(constraint_list_t *cons);

int eval_constraint2(constraint_t *con, state_t *assignment, int assigned, int close);
int quantum_feasibility2(constraint_list_t *con, state_t *assignment, int assigned, int close);
int count_satisfyed_constraints(constraint_list_t *con, state_t *assignment, int assigned, int close, int allowed_false);

int64_t ObjVal(state_t *state, constraint_list_t *obj);

int64_t ChangedObjVal(  constraint_list_t *obj, // objective function
                            state_t *new, // new state
                            int NumChanges, // how many bits were flipped
                            int *ChangedBits, // which bits were flipped
                            int **Indices, // objective term indices involving every item
                            int *NumIndices, // in how many terms every item occours
                            int *Fulfilled, // are terms of objective fulfilled
                            int *ChangedTerms,
                            int *NumChangedTerms
                            );

#endif
