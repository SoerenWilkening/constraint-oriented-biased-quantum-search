#ifndef SEARCHLIB_H
#define SEARCHLIB_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <signal.h>
#include "solver.h"
#include "constraint.h"
#include "quantum_search.h"
#include "model.h"

//typedef int solver_t;
int compare(int64_t obj, int64_t thr, int sense);

void reset_flag();

int ctg(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, int stopping_time, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback, int *break_item,
                state_t *global_opt, int ignore_constraint_search);

int bfs(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback);
#endif