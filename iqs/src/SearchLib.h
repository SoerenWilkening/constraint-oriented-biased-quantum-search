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

// define callback functionality
typedef void (*callback_t)(int, size_t);

typedef int solver_t;
int compare(int64_t obj, int64_t thr, int sense);

state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M);

state_t *ctg(state_t *cur_sol, constraint_list_t *con, constraint_list_t *obj, int M, size_t *qtg_applications, int depth_look_ahead, solver_t solver, char *store, int64_t stop_val, callback_t callback);

#endif