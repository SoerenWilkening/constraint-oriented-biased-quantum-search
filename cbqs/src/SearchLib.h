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

/*
 * global_opt_superseded_by(g, c, feasibility_aware) -- the shared-incumbent
 * acceptance rule (bd 47j). ctg calls it ONLY while holding update_lock.
 * Lives in the header (not ctg's .o) so the rule is directly unit-testable:
 * it is a pure predicate and every branch must be pinned (CLAUDE.md §2.2).
 *
 * Legacy rule (every call site before bd 47j): the bare `g->tot_profit >
 * c->tot_profit`, i.e. pure minimisation of the internal tot_profit. That is
 * correct on the OBJECTIVE axis (MAXIMIZE negates the factors, so a smaller
 * tot_profit is always better -- Model.pyx objective_value = tot_profit*sense)
 * but it is BLIND to feasibility, and global_opt is born with the
 * `init_state` (state.c:23) `feasible = 0` sentinel. A start state that is
 * already feasible therefore never became the incumbent unless some move
 * STRICTLY improved it, so the flag tracked "an improvement was accepted",
 * not "the returned solution is feasible" (bd 47j).
 *
 * OPTIMIZE rule (feasibility_aware != 0): feasibility dominates the objective,
 * the same lexicographic order local_search.c's accept_move already uses
 * (local_search.c:95-98):
 *   - infeasible incumbent, feasible candidate  -> ALWAYS take the candidate;
 *   - feasible incumbent, infeasible candidate  -> NEVER regress (the legacy
 *     rule could overwrite a feasible global_opt with an infeasible state
 *     whose tot_profit is a *slack*, not an objective -- solver.c:688-692 --
 *     silently flipping global_opt->feasible back to 0);
 *   - same feasibility class                    -> the legacy comparison.
 * The comparison stays STRICT in every cell, so ties keep the incumbent.
 *
 * SATISFY (feasibility_aware == 0) keeps the legacy comparison BIT-FOR-BIT:
 * tot_profit carries -num_satisfied_constraints and feasibility is derived
 * from it, not from the flag, which Model.pyx:932 documents as unreliable in
 * that mode. Adding the dominance cells there would freeze the incumbent.
 * (CORRECTION to an earlier version of this comment, which asserted
 * "cur_sol->feasible is never written on the CSearch_sat path" as if the flag
 * were therefore constant 0: CSearch_sat indeed never writes it, but
 * initial_state_preparation does, for EVERY solver mode, and run_sampling
 * copies the initial state into cur_sol -- so a WARM SATISFY start carries
 * feasible == 1 for the whole run. Measured on ca97941 and here: a warm
 * SATISFY solve logs len(history) == 1, a cold one 0. The flag is thus a
 * STALE START-TIME verdict that nothing maintains during a SATISFY run, which
 * is the real reason acceptance must not be keyed on it here.)
 */
static inline int global_opt_superseded_by(const state_t *g, const state_t *c,
                                           int feasibility_aware) {
	if (feasibility_aware) {
		if (!g->feasible && c->feasible) return 1;
		if (g->feasible && !c->feasible) return 0;
	}
	return g->tot_profit > c->tot_profit;
}

int ctg(solver_ctx_t *ctx, model_t *mod, state_t *cur_sol, callback_t callback, incumbents_t *incumbents);

#endif
