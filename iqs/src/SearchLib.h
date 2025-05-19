#ifndef SEARCHLIB_H
#define SEARCHLIB_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <signal.h>
#include "solver.h"
#include "constraint.h"

// define callback functionality
typedef void (*callback_t)(int64_t, size_t, double, double);

//typedef int solver_t;
int compare(int64_t obj, int64_t thr, int sense);

state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M);

int ctg(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, int stopping_time, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback);
int bfs(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback);
#endif