//
// Created by Sören Wilkening on 07.07.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H
#define IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include "intarray.h"
#include "definitions.h"
#include "Branching.h"
#include "constraint.h"
#include "state.h"
#include "solver.h"
#include "model.h"
#include "quantum_search.h"
#include "solver_ctx.h"

typedef struct {
	int num_flips;
	int *flips;
} move_t;

typedef struct {
	int max_moves; // how many moves are stored in tabu list
	int head;      // current not-used slot (overrites previous move)
	int *moves;    // store index of moves
} tabu_list_t;

typedef struct {
	state_t *sol;
	new_constraints_t *con, *obj;
	int d, size_ful, initial_feasible, start_move, end_move;
	move_t *moves;
	array_t ful, ful_con;
	int64_t *remainings;
	state_t *cur_best;
	state_t *cur_best_tabu;
	tabu_list_t *tabu_list;
	int move_index;
	int tabu_move_index;
	double *progress;
	int id;
	int *stopping_criterion;
	int stopping_condition;
	int count_states;
	solver_ctx_t *ctx;  /* Solver context for stop flag checking */

	/* Per-thread scratch buffers (replaces VLAs) */
	int64_t *thread_totals;     /* Replaces totals[C] in explore_neighbourhood */
	int *thread_bits;           /* Replaces bits[d] in explore_neighbourhood */
	size_t num_constraints;     /* C value for buffer sizing */
} local_search_data_t;

int local_search(solver_ctx_t *ctx, state_t *cur_sol, model_t *mod, callback_t callback);


int quantum_local_search(new_constraints_t *obj,
                         new_constraints_t *con,
						 state_t *cur_sol, int k,
						 size_t *total_oracle_applications,
                         callback_t callback);

#endif //IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H
