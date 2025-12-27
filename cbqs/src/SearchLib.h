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
//#include "model.h"

typedef struct {
  state_t *states;
  int *initial_samples; // count of samples required to find first good solution
  int *search_stage;
  int allocated;
  int head;
  int num_states;
} incumbents_t;

#define number_incumbents 1024

incumbents_t *init_incumbents(int n, state_t *initial);

void print_incumbents(incumbents_t *incumbents);

void free_incumbents(incumbents_t *incumbents);

int compare(int64_t obj, int64_t thr, int sense);

void reset_flag();

int ctg(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, int stopping_time, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback,
                state_t *global_opt, int ignore_constraint_search, incumbents_t *incumbents);

int bfs(   state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, int M, size_t *qtg_applications,
                int depth_look_ahead, solver_t solver,  int64_t stop_val, callback_t callback);
#endif