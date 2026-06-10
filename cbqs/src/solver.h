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
#include "model.h"
#include "solver_ctx.h"

int update_potentials(new_constraints_t *con, int64_t *potentials, int direction, int64_t *ret_total);

/* bd h8d: operates in traversal-POSITION space. `order` maps position ->
 * variable (NULL = identity) and `rank` is its inverse (NULL = natural-
 * equivalent traversal); both must describe the SAME traversal the caller
 * uses, or clause-closure charging desynchronizes from the assignment prefix
 * and infeasible states are accepted as feasible. */
int look_ahead_correct(int pos, int next_assignment, int depth_pos, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total, const int *order, const int *rank);

int initial_state_preparation(model_t *mod);

int CSearch_opt(solver_ctx_t *ctx, state_t *cur_sol, int j,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful,
                int *samples
);

int CSearch_opt_sat(solver_ctx_t *ctx, state_t *cur_sol, int j,
                    new_constraints_t *con, new_constraints_t *obj,
                    int depth_look_ahead, int direction, array_t *ful,
                    int *samples
);

int CSearch_sat(solver_ctx_t *ctx, state_t *cur_sol, int j,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful,
                int *samples
);


double CSearch_opt_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj,
    double error, int initial_samples);

double CSearch_opt_sat_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj,
    double error, int direction, int initial_samples);

double CSearch_sat_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, double error, int initial_samples);

#endif // SOLVER_H
