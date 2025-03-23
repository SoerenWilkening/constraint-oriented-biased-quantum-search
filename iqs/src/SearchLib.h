#ifndef SEARCHLIB_H
#define SEARCHLIB_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "intarray.h"
#include "definitions.h"
#include "Branching.h"
#include "constraint.h"
#include "state.h"

#define OPTIMIZE 0
#define SATISFY 1

typedef int solver_t;

void free_state(state_t *state, size_t numStates);
int compare(long double obj, long double thr, int sense);

state_t *init_state(int64_t ObjVal, const int *array, int n);

state_t *copy_state(state_t *state);
void print_state(state_t *state);
state_t *read_states(char **name, int num_files, size_t *NumberStatesFinal, int n);
state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);
state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M);

state_t *ctg(state_t *cur_sol, constraint_list_t *con, constraint_list_t *obj, int M, int *qtg_applications, int depth_look_ahead, solver_t solver, char *store, long double stop_val);

#endif