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

int look_ahead_correct(int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total);

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
