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
#include <limits.h>  /* INT_MAX (oracle-budget clamp, bd 8an.1.17) */
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
 *         ctx->runtime (per-worker wall-clock telemetry; replaces the racy
 *             shared mod->runtime, reduced max-over-workers in solve() -- bd lif),
 *         ctx->callback_value (per-worker incumbent value, set immediately
 *             before each callback invocation -- bd 4uf / NORTHSTAR §11 M0e.
 *             The callback fires OUTSIDE update_lock on every feasible
 *             worker-local incumbent; the Python wrapper must read the value
 *             from ctx, never from mod->global_opt, on this path),
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

	/* bd 0o8: publish the model-level classical-sample cap onto this worker's
	 * ctx so CSearch_{sat,opt_sat,opt} can bound the O(n·j²) sim cost of large-j
	 * rounds (opt_sample_count in solver.c). Per-worker write, race-free. 0 ==
	 * unbounded (exact rejection sim). The 2j+1 oracle charge below is untouched. */
	ctx->opt_sample_cap = (int64_t) mod->opt_sample_cap;

	/* Function pointer for CSearch_* functions - all now take ctx as first parameter */
	int (*search_function)(solver_ctx_t *, state_t *, int, new_constraints_t *, new_constraints_t *, int, int, array_t *, int *);
 
	array_t fulfilled_objective_terms = sw_init(mod->obj->num_clauses[0]);

	uint64_t t1_ns = cbqs_monotonic_ns();

	/* bd 0o8.3: arm the per-worker mid-round wall deadline from the opt-in cap
	 * mod->stopping_time (seconds). stopping_time <= 0 leaves deadline_ns == 0
	 * (OFF -- the strict no-op for faithful/exact runs). Uses the SAME t1_ns basis
	 * as the between-rounds `total_time < mod->stopping_time` check below, so the
	 * in-round interrupt and the between-rounds stop agree. The truncated round is
	 * an approximate OUTCOME (RUN-POLICY-waived); the 2j+1 charge is unaffected.
	 * Per-worker write from the read-only mod->stopping_time -- no shared mod->
	 * write (race-free, like ctx->opt_sample_cap). */
	ctx->deadline_ns = (mod->stopping_time > 0)
	    ? t1_ns + (uint64_t)(mod->stopping_time * 1e9)
	    : 0;

	int res;

    int feasible = eval_constraints(mod->con, cur_sol, n);

	/* bd 47j: publish that verdict onto the state itself. eval_constraints
	 * RETURNS feasibility but does not write cur_sol->feasible (constraint.c:497),
	 * and cur_sol was copied from mod->initial_state, whose flag is 0 for every
	 * manual_initial()/cold solve() start (init_state, state.c:23). So a start
	 * that satisfies every constraint carried feasible == 0 -- an internally
	 * inconsistent state: the local `feasible` says 1 while the state says 0.
	 * run_sampling reads this field into the per-worker final incumbent
	 * (value, feasible) that metric.instance_feasible falls back on, and the
	 * `if (callback && cur_sol->feasible)` history gate reads it too.
	 * NO-OP on every other OPTIMIZE path: the WARM start
	 * (initial_state_preparation, solver.c:309) already set the identical
	 * eval_constraints verdict, and an infeasible start writes back the 0 that
	 * was already there. SATISFY is EXCLUDED and stays bit-for-bit: CSearch_sat
	 * never writes cur_sol->feasible, so the flag is 0 for the whole run there
	 * (Model.pyx:932 documents it as unreliable in that mode and derives
	 * feasibility from tot_profit) -- writing it would newly open the
	 * `if (callback && cur_sol->feasible)` history gate for SATISFY solves. */
	if (mod->solver == OPTIMIZE) cur_sol->feasible = feasible;

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
	    /* bd 47j: recompute the objective, as EVERY other stage-3 entry does
	     * (the ignore_constraint_search entry below, the first-feasible fixup
	     * and the opt-switch in the loop). This one did not, so it inherited
	     * `cur_sol->tot_profit` verbatim from mod->initial_state -- i.e. the
	     * caller-supplied `P` of manual_initial(P, assignment) (Model.pyx).
	     * That value is what CSearch_opt compares against to accept a move
	     * (`cur_sol->tot_profit > val`, solver.c:521), what global_opt is
	     * seeded with below, and what Model.pyx:1001 reports as
	     * result.objective -- so a wrong P silently reported a wrong objective
	     * AND could kill the whole opt phase. Now that the seed below stamps
	     * that state feasible, an unvalidated P would be reported as a
	     * CONFIDENTLY feasible wrong answer; recomputing removes the hazard.
	     * Provable no-op on both canonical protocols: cold is P == 0 with
	     * objective_value(0^n) == 0 (every clause needs an assigned variable,
	     * constraint.c:512-528), and the WARM start already carries exactly
	     * this value (initial_state_preparation, solver.c:312-314). */
	    cur_sol->tot_profit = objective_value(mod->obj, cur_sol);
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
	/* bd 47j: seed the shared incumbent from an already-feasible start.
	 *
	 * global_opt is handed to ctg by Model.manual_initial/solve() as
	 * init_state(P, assignment, n) -- tot_profit == P and the hardcoded
	 * feasible == 0 sentinel (state.c:23) -- and the ONLY other write is the
	 * `if (res)` site below, i.e. it requires an accepted, strictly-improving
	 * move. A start that is feasible AND optimal (e.g. the cold 0^n start of a
	 * MINIMIZE model with a `<=` constraint: 0 <= rhs, and no non-negative-cost
	 * item can lower the objective) never produces one, so solve() returned that
	 * start's vector -- verified clean by eval_constraints -- while reporting
	 * feasible=False off the untouched sentinel (bd 47j).
	 *
	 * Recording it here makes global_opt's flag and vector agree BEFORE the
	 * search loop, and goes through the SAME acceptance rule as every other
	 * write, so:
	 *   - a WARM start is a strict no-op: initial_state_preparation already
	 *     copied (vector, tot_profit, feasible) into global_opt (solver.c:328-330),
	 *     so neither dominance cell fires and tot_profit compares equal;
	 *   - an infeasible start is a strict no-op (cell 1 needs c->feasible);
	 *   - a late-arriving portfolio worker cannot REGRESS an incumbent another
	 *     worker already improved -- the rule rejects the start state then.
	 * No oracle is charged (CLAUDE.md §1.2: this is a classical bookkeeping
	 * write, the same uncharged eval_constraints the entry test above already
	 * performs) and NO callback fires: history stays the accepted-improvement
	 * stream that benchmarks.baselines.warm_repair_history anchors at oracle 0.
	 * (warm_repair_history DOES guard against a double seed -- baselines.py:435
	 * leaves a history already stamped at oracle 0 verbatim -- so emitting here
	 * would not double-count. It is excluded because it would change
	 * result.history / result.worker_histories, both §8-listed structures, for
	 * every run with a feasible start INCLUDING runs that already report
	 * feasible=True; that is a separate change owing its own frozen-table A/B.
	 * Consequence, flagged loudly: metric.compute_primal_integral still scores
	 * this class +inf off the empty history while result.feasible now says
	 * True. That divergence is NOT new -- it is exactly the warm
	 * feasible-greedy-never-improved case warm_repair_history was written for
	 * -- but it now also covers cold feasible starts. See the bd follow-up.)
	 *
	 * ignore_constraint_search is EXCLUDED: that legacy path deliberately
	 * resets the acceptance bound with an UNLOCKED shared write
	 * (`mod->global_opt->tot_profit = 0` above), which the seed would both
	 * subvert and race; and "feasible" is meaningless on a path that ignores
	 * the constraints. Strict no-op there. */
	if (mod->solver == OPTIMIZE && !mod->ignore_constraint_search) {
		cbqs_mutex_lock(&update_lock);
		if (global_opt_superseded_by(mod->global_opt, cur_sol, 1)) {
			copy_state_inplace(mod->global_opt, cur_sol);
		}
		cbqs_mutex_unlock(&update_lock);
	}

	int direction = 1;
	int updated = feasible;

	// Start sampling after initial_state_preparation
	double total_time = 0;
	int samples = 0;

	/* Register this context for signal handler access */
	g_active_ctx = ctx;
	cbqs_install_interrupt_handler(handle_signal);

	/* Primary gate: the never-reset oracle budget (mod->M carries T(n)), so
	 * termination is in ORACLE units, not seconds (NORTHSTAR §11). The wall-clock
	 * stop (total_time < mod->stopping_time) is OFF by default (stopping_time <= 0)
	 * and opt-in ONLY for the TRAINING search, where bounded wall-time matters and
	 * reproducibility/faithfulness is explicitly waived (a truncated solve records a
	 * machine-dependent trajectory). It is checked BETWEEN rounds (total_time is set
	 * at the end of the previous iteration), so it cannot interrupt a single
	 * in-progress large-j round. The `mod->M > 0` guard keeps a non-positive budget a
	 * no-op (matching the old `m_tot < mod->M` behavior): without it,
	 * (size_t)(-1) == SIZE_MAX would make a raw-API caller that left mod->M == -1
	 * loop near-unboundedly. */
	while (mod->M > 0 && total_oracles < (size_t) mod->M
	       && (mod->stopping_time <= 0 || total_time < mod->stopping_time)) {
		if (solver_ctx_should_stop(ctx)) {
			cbqs_install_interrupt_handler(NULL);
			g_active_ctx = NULL;
			return 0;
		}

		/* bd w29 (M5 / 71e): continuous oracle-indexed opt-radius DECAY lever.
		 * A FAITHFUL between-round classical write of the opt-phase state-prep
		 * angle: evaluated HERE (top of the between-round loop, BEFORE the 2j+1
		 * charge below) and held CONSTANT through the round's Grover iterations
		 * (the inner sampler reads stats->bias only; Branching.h /
		 * quantum_search.c / approximate_state_sampler.c are byte-unchanged).
		 * Keyed ONLY on the non-quantum-internal, T(n)-normalized between-round
		 * signal total_oracles/mod->M in [0,1] (NORTHSTAR §1.5; mirrors
		 * opt_switch_oracles = round(alpha*T(n))) — NEVER on a per-candidate /
		 * sample / rejected-candidate count (that would be an unpriced uncharged
		 * angle and change the inner sampler). Applies ONLY in the opt phase
		 * (stage == 3, where ctx->active_stats == &ctx->branching_stats_opt and
		 * the bias IS the realized-radius lever); sat/opt_sat biases are
		 * untouched. enabled == 0 is the strict no-op (the static lever path).
		 * When r_start == r_end the eval returns r_start exactly => bias ==
		 * radius_to_bias(n, r_start), reproducing the static arm bit-for-bit. The
		 * 2j+1 oracle charge below NEVER reads stats->bias, so both A/B arms run
		 * to the identical T(n) cap and the lever is priced by the equal-T(n)
		 * A/B by construction (CLAUDE.md §1.1/§1.2). */
		if (ctx->opt_radius_schedule.enabled && stage == 3) {
			/* ratio is the fraction of the TOTAL T(n) budget (it counts the
			 * sat/opt_sat oracles spent before opt began), so r_start is fully
			 * realized only on a WARM start (the canonical default, where opt is
			 * reached at ratio~0); the realized decay range is reduced by the
			 * n/instance-dependent pre-opt consumption on a cold start. Run the
			 * A/B warm (run_w29_decay_probe seeds general_greedy). */
			double ratio = (double) total_oracles / (double) mod->M;
			double r = opt_radius_schedule_eval(&ctx->opt_radius_schedule, ratio);
			/* radius_to_bias(n,r): bit-identical IEEE-double arithmetic to the
			 * Python harness (phase_params.radius_to_bias, SearchLib.pyx) — the
			 * r_start==r_end bit-for-bit negative control is the cross-language
			 * drift guard (tests/test_opt_radius_schedule.{c,py}). */
			ctx->branching_stats_opt.bias = (double) n / r - 2.0;
		}

		/* bd 8an.1.17: cap the Grover iteration count to the REMAINING oracle
		 * budget BEFORE charging, so 2*j+1 <= remaining and the cumulative count
		 * lands at <= mod->M (== T(n) for a stage-3 terminal round) instead of
		 * overshooting by a whole unbounded round. The :159 loop guard ensures
		 * total_oracles < mod->M, so remaining >= 1. A SHORTER Grover round is a
		 * faithful (QTG-implementable, A/B-priceable) round, NOT a mid-flight
		 * abort (NORTHSTAR §1.1/§1.2, §6). The clamp also bounds the O(j^2)
		 * classical sample cost and kills the int overflow of
		 * m = ceil((6/5)^rounds) at ~118 stuck rounds (m is forced <= j_max). */
		size_t remaining = mod->M - total_oracles;   /* >= 1 by the :159 loop guard */
		int m = (int) ceil(pow(c, rounds));
		int j;
		if (stage == 2) {
			/* opt_sat uses a fixed small Grover count (j=1, cost 3) for
			 * constraint tightening; it cannot be shortened, so if one such round
			 * will not fit the remaining budget, stop before charging rather than
			 * overshoot. */
			if (remaining < 3) break;
			j = 1;
		} else {
			/* Clamp m to j_max = floor((remaining-1)/2) so 2*j+1 <= 2*j_max+1 <=
			 * remaining. Compute j_max in size_t (mod->M is size_t and a raw-API
			 * caller may leave it huge) and bound it to INT_MAX-1 before the cast
			 * so prng_next_int's int argument m+1 is always a valid positive int. */
			size_t j_max_sz = (remaining - 1) / 2;
			if (j_max_sz > (size_t)(INT_MAX - 1)) j_max_sz = (size_t)(INT_MAX - 1);
			int j_max = (int) j_max_sz;
			if (m < 0 || m > j_max) m = j_max;
			j = prng_next_int(m + 1);
		}
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
        /* Per-worker wall-clock telemetry. Was `mod->runtime = total_time`, an
         * unlocked write to a SHARED field that every threading worker raced on
         * (last-writer-wins; CLAUDE.md §5, bd lif). ctx->runtime is per-worker so
         * the write is race-free without locking, exactly like ctx->oracle_count;
         * solve() reduces it max-over-workers into mod->runtime post-fan-out. */
        ctx->runtime = total_time;
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

            /* bd 4uf (NORTHSTAR §11 M0e): PER-WORKER incumbent logging. Fire the
             * callback for every feasible incumbent THIS worker finds — outside
             * update_lock and independent of the shared mod->global_opt. The old
             * site lived inside the critical section below, gated on beating
             * global_opt: a wall-time race that dropped worker-local improvements
             * not dominated on the per-worker oracle axis, making the merged
             * best-of-P trajectory (and the §6 PI) scheduling-dependent. Moving
             * it out also removes the GIL-under-update_lock inversion hazard —
             * which is only safe because the Python wrapper reads the value from
             * ctx->callback_value (per-worker, same-thread write→read), never
             * from mod->global_opt (that would be an unlocked cross-thread read
             * racing copy_state_inplace below). cur_sol->feasible is the exact
             * predicate the old gate used (global_opt->feasible was copied from
             * cur_sol); it correctly excludes stage-1 violation states and
             * stage-2 slack states (slack travels with feasible==0), and the
             * first-feasible objective recompute above precedes this site, so
             * the first logged value is the true first-feasible objective. */
            if (callback && cur_sol->feasible) {
                ctx->callback_value = cur_sol->tot_profit;
                callback(ctx);
            }

			// update global_opt if better solution is found
			/* bd 47j: feasibility-dominant acceptance in OPTIMIZE (legacy
			 * tot_profit comparison in SATISFY). See global_opt_superseded_by. */
			cbqs_mutex_lock(&update_lock);
			if (global_opt_superseded_by(mod->global_opt, cur_sol,
			                             mod->solver == OPTIMIZE)){
			    copy_state_inplace(mod->global_opt, cur_sol);
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
