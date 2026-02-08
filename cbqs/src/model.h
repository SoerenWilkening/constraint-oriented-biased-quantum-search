//
// Created by Sören Wilkening on 08.09.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_MODEL_H
#define IMPROVED_QUANTUM_SEARCH_MODEL_H
#include "state.h"
#include "constraint.h"

typedef struct {
	double runtime;
	new_constraints_t *obj;
    new_constraints_t *con;
	state_t *initial_state;
	state_t *global_opt;
	size_t M;
    int break_item;
	int n;
	int stopping_time;
	int stop_val;
	int depth_look_ahead;
	int num_workers;
	int ignore_constraint_search;
	double *manual_bias;
	double bias_factor;
	double manual_bias_factor;
	double look_ahead_factor;
	int monte_carlo_estimate;
	int reset_delta;
	int max_delta;
    int solver;
    int qtg_applications;
    int max_worse_acceptances;
    int stopping_condition;
    int distance;
} model_t;

model_t *init_model(void);

void free_model(model_t *mod);

void print_model(model_t *mod);

#endif //IMPROVED_QUANTUM_SEARCH_MODEL_H
