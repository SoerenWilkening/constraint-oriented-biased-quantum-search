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
#include "solver_ctx.h"
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

int ctg(solver_ctx_t *ctx, model_t *mod, state_t *cur_sol, callback_t callback, incumbents_t *incumbents);

#endif
