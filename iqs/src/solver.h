#ifndef SOLVER_H
#define SOLVER_H


#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "intarray.h"
#include "definitions.h"
#include "Branching.h"
#include "constraint.h"
#include "state.h"

int update_potentials(new_constraints_t *con, int64_t *potentials, int item,
                                    const unsigned int *indices,
                                    const unsigned int *num_indices,
                                    const unsigned int *offsets, state_t *cur_sol,
                                    int bit, int negative, int direction, int64_t *ret_total);

int look_ahead_correct(int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total);

int initial_state_preparation(state_t *new_sol, state_t *cur_sol,
                              new_constraints_t *con,
                              new_constraints_t *obj,
                              int depth_look_ahead, int *break_item
);

int CSearch_opt(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful
);

int CSearch_opt_sat(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                    new_constraints_t *con, new_constraints_t *obj,
                    int depth_look_ahead, int direction, array_t *ful
);

int CSearch_sat(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful
);


double CSearch_opt_monte_carlo_sampler( state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error);

double CSearch_opt_sat_monte_carlo_sampler(state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj, double error, int direction);

double CSearch_sat_monte_carlo_sampler(state_t *cur_sol, new_constraints_t *con, double error);

#endif // SOLVER_H