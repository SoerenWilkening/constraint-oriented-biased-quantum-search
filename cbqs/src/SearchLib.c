//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"
#include "solver_ctx.h"
#undef branching_stats  /* Use explicit phase-specific field names */
#include "prng.h"
#include "platform.h"
#include <stdio.h>   /* fprintf */
#include <stdlib.h>  /* abort */
/* Intentionally NOT <Python.h>: this file uses no Python C-API symbol
 * (callback_t is a plain void(*)(void) from definitions.h). Including it made
 * MSVC's pyconfig.h auto-link pragma demand pythonXY.lib, breaking the C-test
 * link with LNK1104 (bd 8an.1.10). Do not re-add it. */

cbqs_mutex_t update_lock;
cbqs_once_t update_lock_once = CBQS_ONCE_INIT;
void update_lock_init(void) {
    cbqs_mutex_init(&update_lock);
}

incumbents_t *init_incumbents(int n, state_t *initial){
    incumbents_t *init = malloc(sizeof(incumbents_t));
    init->head = 0;
    init->allocated = number_incumbents;
    init->num_states = 0;
    init->search_stage = malloc(number_incumbents * sizeof(int));
    init->states = init_large_state(n, number_incumbents);
    init->initial_samples = malloc(number_incumbents * sizeof(int));
    copy_state_inplace(&init->states[0], initial);
    return init;
}

void increase_incumbents(incumbents_t *incumbents){
    if (incumbents->head + 1 < incumbents->allocated) return;
    incumbents->states = increse_large_state(incumbents->states, incumbents->allocated, incumbents->allocated + number_incumbents);
    incumbents->search_stage = realloc(incumbents->search_stage, (incumbents->allocated + number_incumbents) * sizeof(int));
    incumbents->initial_samples = realloc(incumbents->initial_samples, (incumbents->allocated + number_incumbents) * sizeof(int));
    incumbents->allocated += number_incumbents;
}

void print_incumbents(incumbents_t *incumbents){
    for (int i = 0; i < incumbents->head + 1; ++i) {
        printf("%d %d | ", incumbents->search_stage[i], incumbents->initial_samples[i]);
        print_state(&incumbents->states[i]);
        printf("\n");
    }
}

void free_incumbents(incumbents_t *incumbents){
    /* Free ALL allocated slots: init_large_state/increse_large_state sw_init() every
       slot's vector+branch, and slots are reused in place (copy_state_inplace). num_states
       tracks recorded incumbents (stays 0 if none were recorded), so freeing num_states
       leaks the entire pre-allocated pool -- bd 8an.1.13 */
    free_state(incumbents->states, incumbents->allocated);
    free(incumbents->search_stage);
    free(incumbents->initial_samples);
    free(incumbents);
}

/* Global pointer to active solver context for signal handler access.
 * This is needed because signal handlers cannot receive user data.
 * Only one solve can be active with signal handling at a time. */
static solver_ctx_t *g_active_ctx = NULL;

static void handle_signal(int signum) {
    if (g_active_ctx != NULL) {
        solver_ctx_request_stop(g_active_ctx);
    }
}


/*
 * ctg(ctx, mod, cur_sol, callback, incumbents)
 *
 * Reads:  mod->obj->num_clauses[], mod->con->num_constraints,
 *         mod->solver, mod->M, mod->depth_look_ahead,
 *         mod->stopping_time, mod->stop_val,
 *         mod->ignore_constraint_search, mod->con->sense[],
 *         cur_sol->vector.bits, cur_sol->tot_profit, cur_sol->feasible
 *
 * Writes: ctx->oracle_count (per-worker, never reset -- the faithful oracle
 *             metric; replaces the racy shared mod->qtg_applications),
 *         mod->runtime (unprotected -- telemetry only; no longer gates),
 *         mod->global_opt->tot_profit (mutex-protected via update_lock),
 *         mod->global_opt->vector (mutex-protected via update_lock),
 *         mod->global_opt->feasible (mutex-protected via update_lock),
 *         cur_sol->tot_profit (unprotected -- thread-local),
 *         cur_sol->vector (unprotected),
 *         cur_sol->branch (unprotected),
 *         cur_sol->feasible (unprotected),
 *         incumbents->states[], incumbents->head, incumbents->search_stage[],
 *         incumbents->initial_samples[]
 */
int ctg(solver_ctx_t *ctx, model_t *mod, state_t *cur_sol, callback_t callback, incumbents_t *incumbents) {
	/* Ensure update_lock is initialised before any workers spawn. */
	cbqs_call_once(&update_lock_once, update_lock_init);

	/* Never-reset cumulative oracle accumulator for THIS ctg call. Replaces the
	 * old m_tot, which reset to 0 on every improvement and so could only bound
	 * work *between* improvements -- it could never cap cumulative oracles
	 * (NORTHSTAR §11). The loop now terminates on total_oracles >= mod->M. */
	size_t total_oracles = 0;
	int n = cur_sol->vector.bits;
	int rounds = 0;
	double c = 6. / 5;

	/* Function pointer for CSearch_* functions - all now take ctx as first parameter */
	int (*search_function)(solver_ctx_t *, state_t *, int, new_constraints_t *, new_constraints_t *, int, int, array_t *, int *);
 
	array_t fulfilled_objective_terms = sw_init(mod->obj->num_clauses[0]);

	uint64_t t1_ns = cbqs_monotonic_ns();

	int res;

    int feasible = eval_constraints(mod->con, cur_sol, n);

	int stage = 1;
	if (mod->solver == SATISFY) {
	    search_function = CSearch_sat;
	    ctx->active_stats = &ctx->branching_stats_sat;
	}
	if (mod->solver == OPTIMIZE && !feasible) {
	    search_function = CSearch_opt_sat; // opt_sat
	    ctx->active_stats = &ctx->branching_stats_opt_sat;
	}
	if (mod->solver == OPTIMIZE && feasible) {
	    prepare(mod->obj, cur_sol, &fulfilled_objective_terms);
	    stage = 3;
	    search_function = CSearch_opt;
	    ctx->active_stats = &ctx->branching_stats_opt;
	}
	if (mod->solver == OPTIMIZE && mod->ignore_constraint_search) {
	    stage = 3;
	    cur_sol->tot_profit = objective_value(mod->obj, cur_sol);
        mod->global_opt->tot_profit = 0;
	    search_function = CSearch_opt;
	    ctx->active_stats = &ctx->branching_stats_opt;
	}
	int direction = 1;
	int updated = feasible;

	// Start sampling after initial_state_preparation
	double total_time = 0;
	int samples = 0;

	/* Register this context for signal handler access */
	g_active_ctx = ctx;
	cbqs_install_interrupt_handler(handle_signal);

	/* Gate purely on the never-reset oracle budget; the wall-clock stop
	 * (total_time < mod->stopping_time) is deliberately removed (NORTHSTAR §11)
	 * so termination is in oracle units, not seconds. mod->M carries T(n).
	 * The `mod->M > 0` guard keeps a non-positive budget a no-op (matching the
	 * old `m_tot < mod->M` behavior): without it, (size_t)(-1) == SIZE_MAX would
	 * make a raw-API caller that left mod->M == -1 loop near-unboundedly. */
	while (mod->M > 0 && total_oracles < (size_t) mod->M) {
		if (solver_ctx_should_stop(ctx)) {
			cbqs_install_interrupt_handler(NULL);
			g_active_ctx = NULL;
			return 0;
		}

		int m = ceil(pow(c, rounds));
		int j;
		if (stage == 2) j = 1; // when improving constraint tightness, use only small constant number of grover iterations
		else j = prng_next_int(m + 1);
		/* Charge 2j+1 oracles. total_oracles gates termination (never resets);
		 * ctx->oracle_count is the per-worker, race-free metric that replaces
		 * the racy shared mod->qtg_applications (CLAUDE.md §1.2). */
		total_oracles += 2 * j + 1;
		ctx->oracle_count += 2 * j + 1;
		res = search_function(
				ctx, cur_sol, j, mod->con, mod->obj,
                mod->depth_look_ahead, direction, &fulfilled_objective_terms,
				&samples
		);
        total_time = (cbqs_monotonic_ns() - t1_ns) / 1e9;
        mod->runtime = total_time;
		rounds++;

		/* Periodic stop check (every 256 iterations) */
		if ((rounds & 255) == 0 && solver_ctx_should_stop(ctx)) break;

		if (res) {

            // first found feasible solution
            if (mod->solver == OPTIMIZE && !feasible && cur_sol->feasible){
                stage = 2;
                cur_sol->tot_profit = objective_value(mod->obj, cur_sol);
                direction = -1;
                feasible = 1;
                ctx->active_stats = &ctx->branching_stats_opt_sat;  // stays opt_sat
            }
            
            // add solution to incumbent list
            increase_incumbents(incumbents);
            incumbents->search_stage[incumbents->head] = stage;
            incumbents->initial_samples[incumbents->head] = samples + 1;
            copy_state_inplace(&incumbents->states[incumbents->head + 1], cur_sol);
            incumbents->head++;
            samples = 0;
            
			// update global_opt if better solution is found
			cbqs_mutex_lock(&update_lock);
			if (mod->global_opt->tot_profit > cur_sol->tot_profit){
			    copy_state_inplace(mod->global_opt, cur_sol);

				/* Pass ctx so the Cython wrapper can oracle-stamp this incumbent
				 * with ctx->oracle_count (per-worker, never-reset; M0e). */
				if (callback && mod->global_opt->feasible) callback(ctx);
			}
			cbqs_mutex_unlock(&update_lock);
			/* Restart the Grover schedule on improvement (rounds -> 0). NOTE:
			 * total_oracles is intentionally NOT reset here -- that reset is the
			 * exact bug (old m_tot) that let cumulative oracles exceed mod->M. */
			rounds = 0;
			if ((mod->solver == SATISFY && cur_sol->tot_profit == - (int64_t) mod->con->num_constraints) || (feasible && (cur_sol->tot_profit <= mod->stop_val && mod->stop_val != -1))) {
				break;
			}
		}
        // improve violations before optimizing, then switch exploit->explore.
        // M0f: the switch fires once this worker has spent opt_switch_oracles
        // cumulative oracles (ctx->oracle_count, per-worker & race-free from
        // M0d), replacing the hardcoded counter>10. The explicit `feasible &&`
        // is LOAD-BEARING: the old counter only incremented while feasible
        // (so counter>10 implied feasibility), but ctx->oracle_count counts
        // from run start regardless of feasibility -- without this guard the
        // switch could run CSearch_opt on an infeasible point (NORTHSTAR §5
        // phase-machine coupling). opt_switch_oracles==SIZE_MAX => disabled.
        if (mod->solver == OPTIMIZE && feasible && !updated
                && (size_t) ctx->oracle_count >= mod->opt_switch_oracles) {
            /* §2.1 FAIL LOUD (survives -DNDEBUG, unlike assert): never enter
             * CSearch_opt before a feasible point exists. The `feasible &&`
             * guard above makes this unreachable in correct operation; if it
             * ever trips, the phase machine is corrupt -- crash, don't optimize
             * an infeasible state. */
            if (!cur_sol->feasible) {
                fprintf(stderr, "ctg: opt-switch reached with infeasible "
                                "cur_sol (NORTHSTAR §5 phase-machine coupling)\n");
                abort();
            }
            stage = 3;
            search_function = CSearch_opt;
            cur_sol->tot_profit = objective_value(mod->obj, cur_sol);
	        prepare(mod->obj, cur_sol, &fulfilled_objective_terms);
            updated = 1;
            ctx->active_stats = &ctx->branching_stats_opt;
        }
	}
	incumbents->search_stage[incumbents->head] = -1; // last step, no better incumbents found
	incumbents->initial_samples[incumbents->head] = 0; // last step, no better incumbents found

	sw_clear(fulfilled_objective_terms);

	/* Clear signal handler context */
	cbqs_install_interrupt_handler(NULL);
	g_active_ctx = NULL;

	return feasible;
}
