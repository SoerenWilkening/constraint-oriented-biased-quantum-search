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
	array_t *ful, *ful_con;
	int64_t *remainings;
	state_t *cur_best;
	tabu_list_t *tabu_list;
	int move_index;
	int tabu_move_index;
	double *progress;
	int id;
} local_search_data_t;

#define NUMThreads 6

int local_search(state_t *cur_sol,
                 new_constraints_t *con,
                 new_constraints_t *obj,
				 int distance,
                 int stopping_time,
                 solver_t solver,
                 int64_t stop_val,
                 callback_t callback,
                 int max_worse_acceptances);

#endif //IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H
