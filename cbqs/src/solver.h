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

/*
 * potentials_total_violation(con, potentials) -- the stage-1 constraint-violation
 * sum CSearch_opt_sat minimises, and the predicate its `feasible` verdict is
 * derived from (`total_violation == 0`).
 *
 * `potentials[c]` is `con->rhs[c] - LHS_c(assignment)` (memcpy of con->rhs at
 * the top of every candidate, then update_potentials subtracts each assigned
 * clause's contribution with direction PLAIN == -1, solver.c). So:
 *   - inequality (LOWER, incl. the negated-LOWER encoding of `>=`): satisfied
 *     iff LHS <= rhs iff potentials >= 0, and the shortfall is -min(0, p);
 *   - EQUAL: satisfied iff LHS == rhs iff potentials == 0 -- the SAME predicate
 *     CSearch_opt's `as1` uses (solver.c) and the one constraint.c's
 *     eval_constraint means -- and the violation magnitude is |p|.
 *
 * Lives in the header (not solver.c's .o) so the rule is directly unit-testable
 * as a pure predicate (CLAUDE.md §2.2), like SearchLib.h's
 * global_opt_superseded_by. Shared by CSearch_opt_sat and its Monte-Carlo twin
 * so the two can never drift (CLAUDE.md §2.7).
 */
static inline int64_t potentials_total_violation(const new_constraints_t *con,
                                                 const int64_t *potentials) {
	int64_t total_violation = 0;
	for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		if (con->sense[cnstr] == EQUAL) {
			total_violation += llabs(potentials[cnstr]);
		} else {
			total_violation -= potentials[cnstr] < 0 ? potentials[cnstr] : 0;
		}
	}
	return total_violation;
}

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
