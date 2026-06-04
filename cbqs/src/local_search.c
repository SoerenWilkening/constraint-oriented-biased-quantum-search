//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"
#include "solver_ctx.h"
#include "prng.h"
#include "arena.h"

/*
 * Local Search Algorithm
 *
 * Implements iterative k-flip neighborhood search for combinatorial optimization.
 * The algorithm repeatedly evaluates all k-flip neighbors of the current solution
 * (where k is controlled by the 'distance' parameter), accepts the best improving
 * move, and terminates when no improvement is found for max_worse_acceptances
 * consecutive iterations.
 *
 * Key components:
 *   - explore_neighbourhood(): Evaluates all k-flip neighbors in parallel across
 *     threads. Each thread handles a slice of the move list, using incremental
 *     constraint evaluation (adjusted_constraint_violation) for efficiency.
 *   - accept_best_routine(): Collects thread results, selects the best non-tabu
 *     move (preferring feasible moves, then best objective), updates the solution.
 *   - local_search(): Main loop driving iteration, termination, and timing.
 *
 * Cycling prevention: A tabu list marks recently-flipped variables, preventing
 * the algorithm from immediately reversing a move.
 *
 * Thread model: explore_neighbourhood() runs in parallel via pthreads.
 * Each worker thread owns its own scratch buffers. The shared global_opt is
 * updated under mutex protection (update_lock).
 */

/* MEM-02: Reference the mutex defined in SearchLib.c for global_opt protection */
extern cbqs_mutex_t update_lock;
extern cbqs_once_t update_lock_once;
extern void update_lock_init(void);

/**
 * Arena-based array_t initialization.
 * Like sw_init but allocates from arena instead of malloc.
 * Falls back to sw_init if arena is NULL.
 */
static inline array_t sw_init_arena(size_t B, arena_t *arena) {
    if (arena == NULL) {
        return sw_init(B);
    }
    array_t A;
    A.bits = B;
    size_t numbits = (B >> 6) + 1;
    A.n = numbits;
    A.part = (part_length_t*)arena_alloc(arena, A.n * sizeof(part_length_t), 8);
    if (A.part != NULL) {
        memset(A.part, 0, A.n * sizeof(part_length_t));
    }
    return A;
}

static inline int move_is_tabu(tabu_list_t *tabu_list, int move) {
	if (tabu_list->head == -1) return 0;
	for (int i = 0; i < tabu_list->max_moves; ++i) {
		if (move == tabu_list->moves[i]) return 1;
	}
	return 0;
}

static inline void
update_state(state_t *cur_best, state_t *cur_best_tabu, state_t *state2, int64_t objective, int feasible,
             tabu_list_t *tabu, int move) {
	if (!move_is_tabu(tabu, move)) {
		sw_set_inplace(cur_best->vector, state2->vector); // copy assignment to current best
		cur_best->tot_profit = objective;
		cur_best->feasible = feasible;
		return;
	}
	sw_set_inplace(cur_best_tabu->vector, state2->vector); // copy assignment to current best
	cur_best_tabu->tot_profit = objective;
	cur_best_tabu->feasible = feasible;
}

static inline int accept_move(state_t *new_sol, state_t *cur_sol, state_t *global_opt) {
	int accepted = 0;
	int greater_objective = new_sol->tot_profit > cur_sol->tot_profit;
	if (!new_sol->feasible && cur_sol->feasible) accepted = 1;
	if (new_sol->feasible && cur_sol->feasible && greater_objective) accepted = 1;
	if (!new_sol->feasible && !cur_sol->feasible && greater_objective) accepted = 1;
	if (!accepted) return 0;

	sw_set_inplace(new_sol->vector, cur_sol->vector); // copy assignment to current best
	new_sol->tot_profit = cur_sol->tot_profit;
	new_sol->feasible = cur_sol->feasible;

	int acc_glob = 0;
	greater_objective = global_opt->tot_profit > cur_sol->tot_profit;
	if (!global_opt->feasible && cur_sol->feasible) acc_glob = 1;
	if (global_opt->feasible && cur_sol->feasible && greater_objective) acc_glob = 1;
	if (!global_opt->feasible && !cur_sol->feasible && greater_objective) acc_glob = 1;
	if (!acc_glob) return accepted;

	sw_set_inplace(global_opt->vector, cur_sol->vector); // copy assignment to current best
	global_opt->tot_profit = cur_sol->tot_profit;
	global_opt->feasible = cur_sol->feasible;

	return accepted;
}


move_t *move_list(int d, int n, int *num_moves, int with_shuffle) {
	int count = 0;
	int *comb = malloc(d * sizeof(int));
	for (int k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int i = 0; i < k; ++i) comb[i] = i;
		while (1) {
			int i = k - 1;
			while (i >= 0 && comb[i] == n - k + i) i--;
			count++;
			if (i < 0) break; // All combinations done
			comb[i]++;
			for (int j = i + 1; j < k; ++j) comb[j] = comb[j - 1] + 1;
		}
	}
	move_t *moves = malloc(count * sizeof(move_t));
	count = 0;
	free(comb);
	comb = malloc(d * sizeof(int));

	for (int k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int i = 0; i < k; ++i) comb[i] = i;
		while (1) {
			moves[count].num_flips = k;
			moves[count].flips = malloc(k * sizeof(int));
			memcpy(moves[count].flips, comb, k * sizeof(int));
			count++;

			int i = k - 1;
			while (i >= 0 && comb[i] == n - k + i) i--;
			if (i < 0) break; // All combinations done
			comb[i]++;
			for (int j = i + 1; j < k; ++j) comb[j] = comb[j - 1] + 1;
		}
	}
	free(comb);

	// shuffle moves if wanted
	if (with_shuffle) {
		// Shuffle with Fisher-Yates algorithm
		for (int i = count - 1; i > 0; i--) {
			int j = prng_next_int(i + 1);  // random index from 0..i
			move_t temp = moves[i];
			moves[i] = moves[j];
			moves[j] = temp;
		}
	}
	*num_moves = count;
	return moves;
}

void free_move_list(move_t *move_list, int num_moves) {
	for (int i = 0; i < num_moves; ++i) free(move_list[i].flips);
	free(move_list);
}

/*
 * explore_neighbourhood -- Evaluate a slice of k-flip neighbors in a worker thread.
 *
 * Each thread processes moves[start_move..end_move), flipping the indicated variable
 * bits, computing the new objective via incremental evaluation (adjusted_constraint_violation),
 * and tracking the best non-tabu and best tabu moves found. Uses per-thread scratch
 * buffers to avoid contention.
 *
 * After processing all assigned moves, stores the best candidates in dat->cur_best
 * and dat->cur_best_tabu for the main thread to collect.
 */
void *explore_neighbourhood(void *args) {
	local_search_data_t *dat = (local_search_data_t *) args;

	/* Initialize thread-local PRNG from master state */
	if (dat->ctx != NULL) {
		prng_seed_thread(&dat->ctx->master_prng, dat->id);
	}

	uint32_t C = dat->con->num_constraints;

	/* Use pre-allocated per-thread scratch buffers instead of VLAs */
	int *bits = dat->thread_bits;

	state_t *cur_best = copy_state(dat->sol);
	state_t *cur_best_tabu = copy_state(dat->sol); // current best tabu move
	cur_best->tot_profit = INT64_MAX;
	cur_best_tabu->tot_profit = INT64_MAX;

	state_t *new_sol = copy_state(dat->sol);

	for (int mov = dat->start_move; mov < dat->end_move; ++mov) {
		// stop, if first better solution was found
		if (*dat->stopping_criterion) break;

		/* Periodic stop check (every 256 moves) using solver context */
		if ((mov & 255) == 0 && dat->ctx != NULL && solver_ctx_should_stop(dat->ctx)) break;

		dat->count_states++; // store how many states were investigated by thread

		int *comb = dat->moves[mov].flips;
		int k = dat->moves[mov].num_flips;
		// flip bits
		for (int i = 0; i < k; ++i) {
			bits[i] = sw_tstbit(new_sol->vector, comb[i]);// current bit
			if (bits[i]) sw_clrbit(new_sol->vector, comb[i]);
			else sw_setbit(new_sol->vector, comb[i]);
		}

		/* Use pre-allocated per-thread scratch buffer instead of VLA */
		int64_t *totals = dat->thread_totals;
		memset(totals, 0, C * sizeof(int64_t));

		/* Incremental constraint evaluation using adjusted_constraint_violation()
		 * instead of full constraint_violation() loop (INCR-02).
		 * Pattern mirrors quantum_local_search_states(). */
		int use_arena = (dat->ctx != NULL && dat->ctx->arena != NULL);
		array_t inv;
		int *changed_con;
		if (use_arena) {
			inv = sw_init_arena(dat->con->total_clauses, dat->ctx->arena);
			changed_con = (int*)arena_alloc(dat->ctx->arena, MINSIZE * sizeof(int), 4);
			if (changed_con) memset(changed_con, 0, MINSIZE * sizeof(int));
		} else {
			inv = sw_init(dat->con->total_clauses);
			changed_con = calloc(MINSIZE, sizeof(int));
		}
		int num_con_changes = 0;

		for (int fi = 0; fi < k; ++fi) {
			adjusted_constraint_violation(dat->con, comb[fi],
				dat->con->positive_indices, dat->con->num_positive_indices,
				dat->con->positive_offsets, new_sol,
				POSITIVE, totals, &dat->ful_con, &changed_con, &num_con_changes, &inv);
			adjusted_constraint_violation(dat->con, comb[fi],
				dat->con->negative_indices, dat->con->num_negative_indices,
				dat->con->negative_offsets, new_sol,
				NEGATIVE, totals, &dat->ful_con, &changed_con, &num_con_changes, &inv);
		}
		if (!use_arena) {
			free(changed_con);
			sw_clear(inv);
		}

		// compute with new solution
		// is the new solution feasible ?
		int64_t total_violation = 0;

		for (uint32_t cnstr = 0; cnstr < C; ++cnstr) {
			// only sum up violations — use remainings baseline with incremental delta
			total_violation -= dat->remainings[cnstr] - totals[cnstr] < 0 ? dat->remainings[cnstr] - totals[cnstr] : 0;
		}
		int feasible = (total_violation == 0);

		// first try to find a feasible solution, by minimizing the constraints violation
		if (!(dat->initial_feasible)) {
			if (total_violation < cur_best->tot_profit && !feasible) {
				update_state(cur_best, cur_best_tabu, new_sol, total_violation, 0, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
			}
			if (feasible) {
				dat->initial_feasible = feasible;
				update_state(cur_best, cur_best_tabu, new_sol, objective_value(dat->obj, new_sol),
				             1, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
			}
		} else {
			/* Arena-based allocation for changes array */
			int *changes;
			if (use_arena) {
				changes = (int*)arena_alloc(dat->ctx->arena, MINSIZE * sizeof(int), 4);
				if (changes) memset(changes, 0, MINSIZE * sizeof(int));
			} else {
				changes = calloc(MINSIZE, sizeof(int));
			}
            int64_t objective = objective_value(dat->obj, new_sol);

			if (objective < cur_best->tot_profit && feasible) {
				update_state(cur_best, cur_best_tabu, new_sol, objective, 1, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
			}
			/* Free only if not using arena */
			if (!use_arena) {
				free(changes);
			}
		}

		// if cur_best is better than sol: stop all threads
		if (cur_best->tot_profit < dat->sol->tot_profit) *dat->stopping_criterion = dat->stopping_condition;

		// unflip bits
		for (int i = 0; i < k; ++i) {
			if (bits[i]) sw_setbit(new_sol->vector, comb[i]);
			else sw_clrbit(new_sol->vector, comb[i]);
		}
	}
	free_state(new_sol, 1);
	dat->cur_best = cur_best;
	dat->cur_best_tabu = cur_best_tabu;
	return NULL;
}

/*
 * accept_best_routine -- Select and apply the best improving move from the neighborhood.
 *
 * Spawns worker threads to explore the full k-flip neighborhood via explore_neighbourhood(),
 * then collects results and selects the overall best move. Selection criteria:
 *   1. Feasibility first: a feasible move beats an infeasible one
 *   2. Among same-feasibility moves: best (lowest) objective wins
 *   3. Non-tabu moves preferred; tabu moves used only if no non-tabu improvement exists
 *
 * After selecting the best move, updates new_sol in place and checks whether the
 * global optimum should be updated (under mutex protection).
 *
 * Returns: 1 if an improving move was accepted, 0 if stuck (triggers termination check).
 */
int accept_best_routine(solver_ctx_t *ctx, state_t *new_sol, state_t *global_opt, new_constraints_t *con, new_constraints_t *obj,
                        int d, int *initial_feasible, int size_ful,
                        move_t *moves, int num_moves, tabu_list_t *tabu_list,
                        int *accept_worse_counter, int max_worse_acceptances,
                        int stopping_criterion, int *neighbourhood_counter,
                        int64_t *remainings_in, array_t *ful_con_in) {

	/* Ensure the shared update_lock mutex is initialised before first use */
	cbqs_call_once(&update_lock_once, update_lock_init);

	uint32_t C = con->num_constraints;

	state_t *cur_best = copy_state(new_sol);
	state_t *cur_best_tabu = copy_state(new_sol);
	cur_best->tot_profit = INT64_MAX;
	cur_best_tabu->tot_profit = INT64_MAX;

	array_t ful = sw_init(obj->num_clauses[0]);
	/* Use caller-provided remainings and ful_con (INCR-02) */
	int64_t *remainings = remainings_in;
	array_t ful_con = sw_set(*ful_con_in);
	prepare(obj, new_sol, &ful); // prepare for optimized computation of objective value

	/* Get thread count from solver context (default to 4 if no ctx) */
	int num_threads = (ctx != NULL) ? ctx->num_threads_used : 4;

	double *progress_arr = calloc(num_threads, sizeof(double));

	/* Dynamically allocate thread data arrays */
	local_search_data_t *data = malloc(num_threads * sizeof(local_search_data_t));
	cbqs_thread_t *threads = malloc(num_threads * sizeof(cbqs_thread_t));
	int stop_at_first = 0;
	for (int i = 0; i < num_threads; ++i) {
		data[i].con = con;
		data[i].obj = obj;
		data[i].moves = moves;
		data[i].remainings = malloc(C * sizeof(int64_t));
        memcpy(data[i].remainings, remainings, C * sizeof(int64_t));
		data[i].initial_feasible = *initial_feasible;
		data[i].ful_con = sw_set(ful_con);
		data[i].ful = sw_set(ful);
		data[i].cur_best = NULL;
		data[i].cur_best_tabu = NULL;
		data[i].tabu_list = tabu_list;
		data[i].sol = new_sol;
		data[i].size_ful = size_ful;
		data[i].d = d;
		data[i].start_move = i * num_moves / num_threads;
		data[i].end_move = (i + 1) * num_moves / num_threads;
		data[i].progress = progress_arr;
		data[i].id = i;
		data[i].stopping_criterion = &stop_at_first;
		data[i].stopping_condition = stopping_criterion;
		data[i].count_states = 0;
		data[i].ctx = ctx;  /* Pass solver context to thread worker */

		/* Allocate per-thread scratch buffers (replaces VLAs) */
		data[i].thread_totals = malloc(C * sizeof(int64_t));
		data[i].thread_bits = malloc(d * sizeof(int));
		data[i].num_constraints = C;

		if (data[i].thread_totals == NULL || data[i].thread_bits == NULL) {
			/* Handle allocation failure - free already allocated and return */
			for (int j = 0; j <= i; ++j) {
				free(data[j].remainings);
				free(data[j].thread_totals);
				free(data[j].thread_bits);
				sw_clear(data[j].ful_con);
				sw_clear(data[j].ful);
			}
			free(data);
			free(threads);
			free(progress_arr);
			free_state(cur_best, 1);
			free_state(cur_best_tabu, 1);
			sw_clear(ful);
			sw_clear(ful_con);
			return -1;  /* Allocation failure */
		}
	}
	// Create all threads first - data must remain valid while threads run
	for (int i = 0; i < num_threads; ++i) {
		cbqs_thread_create(&threads[i], explore_neighbourhood, (void *) &data[i]);
	}
	int accepted_index = -1;
	for (int i = 0; i < num_threads; ++i) {
		cbqs_thread_join(&threads[i]);

		// NOW safe to cleanup - thread has completed
		free(data[i].remainings);
		free(data[i].thread_totals);
		free(data[i].thread_bits);
		sw_clear(data[i].ful_con);
		sw_clear(data[i].ful);

		int acc = 0;
		int acc_tab = 0;
		if (data[i].cur_best != NULL) {
			/* MEM-02: Protect global_opt writes with trylock (non-blocking) */
			if (cbqs_mutex_trylock(&update_lock) == 0) {
				acc = accept_move(cur_best, data[i].cur_best, global_opt);
				cbqs_mutex_unlock(&update_lock);
			} else {
				acc = 0;
				/* Lock contended -- merge thread-local cur_best without touching global_opt */
				if (data[i].cur_best->tot_profit < cur_best->tot_profit) {
					sw_set_inplace(cur_best->vector, data[i].cur_best->vector);
					cur_best->tot_profit = data[i].cur_best->tot_profit;
					cur_best->feasible = data[i].cur_best->feasible;
					acc = 1;
				}
			}
			free_state(data[i].cur_best, 1);
		}
		if (data[i].cur_best_tabu != NULL) {
			if (acc_tab) acc = accept_move(cur_best, data[i].cur_best_tabu, global_opt);
			free_state(data[i].cur_best_tabu, 1);
		}
		if (acc || acc_tab) accepted_index = acc * data[i].move_index + acc_tab * data[i].tabu_move_index;
		*neighbourhood_counter += data[i].count_states;
	}
	/* Reset arena for next iteration - reclaims all arena allocations */
	if (ctx != NULL) {
		solver_ctx_arena_reset(ctx);
	}

	/* Free dynamic allocations */
	free(data);
	free(threads);
	free(progress_arr);

	/* MEM-02: Protect global_opt writes with trylock (non-blocking) */
	int accepted;
	if (cbqs_mutex_trylock(&update_lock) == 0) {
		accepted = accept_move(new_sol, cur_best, global_opt);
		cbqs_mutex_unlock(&update_lock);
	} else {
		/* Lock contended -- skip global_opt update, only update local state */
		accepted = 0;
		if (cur_best->tot_profit < new_sol->tot_profit) {
			sw_set_inplace(new_sol->vector, cur_best->vector);
			new_sol->tot_profit = cur_best->tot_profit;
			new_sol->feasible = cur_best->feasible;
			accepted = 1;
		}
	}
	if (!accepted) {
		if (*accept_worse_counter == max_worse_acceptances) {
			/* MEM-01 FIX: Clean up before early return */
			free_state(cur_best, 1);
			free_state(cur_best_tabu, 1);
			sw_clear(ful);
			sw_clear(ful_con);
			return 0; // stop the entire search
		}
		accepted = 1;
		// no better solution found:
		// accept best-worse solution
		// only acept a number of worse solutions
		sw_set_inplace(new_sol->vector, cur_best->vector); // copy assignment to current best
		new_sol->tot_profit = cur_best->tot_profit;
		new_sol->feasible = cur_best->feasible;
		*accept_worse_counter += 1;
	}
	// add move to tabu list
	tabu_list->moves[tabu_list->head] = accepted_index;
	tabu_list->head = (tabu_list->head + 1) % tabu_list->max_moves;

	free_state(cur_best, 1);
	free_state(cur_best_tabu, 1);  /* MEM-01 FIX: was missing before */
	sw_clear(ful);
	sw_clear(ful_con);
	return accepted;
}

/*
 * local_search -- Main loop driving iterative neighborhood exploration.
 *
 * Algorithm:
 *   1. Generate the full k-flip move list (all combinations of 1..distance variable flips)
 *   2. Initialize a tabu list (size 10) and compute initial constraint remainings
 *   3. Loop:
 *      a. Call accept_best_routine() to explore neighborhood and apply best move
 *      b. Invoke callback (if any)
 *      c. Check termination: time limit, target objective, or max non-improving iterations
 *      d. Refresh constraint remainings for the updated solution
 *   4. Accept the final best solution into global_opt
 *
 * Termination conditions (any triggers exit):
 *   - Wall-clock time exceeds mod->stopping_time
 *   - Objective reaches mod->stop_val (if set)
 *   - max_worse_acceptances consecutive non-improving iterations
 *   - Solver context stop flag set (for multi-worker coordination)
 *
 * Thread model: This function runs as a single worker. Multiple workers can run
 * local_search independently in parallel; they share mod->global_opt protected by
 * update_lock mutex.
 *
 * Reads:  cur_sol->vector.bits,
 *         mod->con->num_constraints, mod->con->num_clauses[],
 *         mod->obj->num_clauses[],
 *         mod->distance, mod->stopping_time, mod->stop_val,
 *         mod->max_worse_acceptances, mod->stopping_condition,
 *         mod->global_opt (passed to accept_best_routine)
 * Writes: mod->runtime, mod->global_opt (mutex-protected),
 *         cur_sol (single-thread ownership)
 */
int local_search(solver_ctx_t *ctx, state_t *cur_sol, model_t *mod, callback_t callback) {

	uint64_t start_ns = cbqs_monotonic_ns();

	int n = cur_sol->vector.bits;
	uint32_t C = mod->con->num_constraints;

	array_t ful = sw_init(mod->obj->num_clauses[0]);
	uint32_t max_constraint_clauses = 0;
	for (uint32_t i = 0; i < C; ++i) {
		if (mod->con->num_clauses[i] > max_constraint_clauses) {
			max_constraint_clauses = mod->con->num_clauses[i];
		}
	}

	array_t ful_con = sw_init(C * max_constraint_clauses);

	int initial_feasible = cur_sol->feasible;

	int num_moves = 0;
	move_t *moves = move_list(mod->distance, n, &num_moves, true);

	tabu_list_t tabu_list;
	tabu_list.max_moves = 10;
	tabu_list.head = 0;
	tabu_list.moves = malloc(tabu_list.max_moves * sizeof(int));
	for (int i = 0; i < tabu_list.max_moves; ++i) {
		tabu_list.moves[i] = -1;
	}

	/* INCR-02: Compute remainings[] and ful_con once before the iteration loop.
	 * These are passed to accept_best_routine and refreshed after each iteration. */
	int64_t *remainings = malloc(C * sizeof(int64_t));
	for (uint32_t i = 0; i < C; ++i) remainings[i] = constraint_violation(mod->con, cur_sol, i);
	prepare_constraints(mod->con, cur_sol, &ful_con);

	int break_condition = 1;
	int worse_acceptance_counter = 0;
	while (break_condition) {
		/* Check solver context stop flag */
		if (ctx != NULL && solver_ctx_should_stop(ctx)) break;

		int neighbourhood_counter = 0;
		break_condition = accept_best_routine(ctx, cur_sol, mod->global_opt, mod->con, mod->obj, mod->distance, &initial_feasible,
		                                      max_constraint_clauses, moves, num_moves, &tabu_list,
		                                      &worse_acceptance_counter, mod->max_worse_acceptances,
                                              mod->stopping_condition, &neighbourhood_counter,
                                              remainings, &ful_con);
		uint64_t end_ns = cbqs_monotonic_ns();
		double time = (double)(end_ns - start_ns) / 1e9;
        mod->runtime = time;
		if (callback) callback();
		if (time > mod->stopping_time || ((cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1))) break;

		/* Refresh remainings[] and ful_con for the (possibly changed) cur_sol */
		for (uint32_t i = 0; i < C; ++i) remainings[i] = constraint_violation(mod->con, cur_sol, i);
		memset(ful_con.part, 0, ful_con.n * sizeof(part_length_t));
		prepare_constraints(mod->con, cur_sol, &ful_con);
	}

	accept_move(cur_sol, mod->global_opt, mod->global_opt);

	free_move_list(moves, num_moves);
	free(tabu_list.moves);  /* MEM-01 FIX: was missing */
	free(remainings);
	sw_clear(ful_con);
	sw_clear(ful);

	return 0;
}

state_t *quantum_local_search_states(
		new_constraints_t *obj,
		new_constraints_t *con,
		move_t *moves, size_t num_moves,
		state_t *cur_sol,
		tabu_list_t *tabu_list,
		size_t *num_states,
		size_t *mapping) {

	array_t ful_con = sw_init(con->total_clauses);
	uint32_t C = con->num_constraints;

	/* Heap-allocated arrays instead of VLAs */
	int64_t *remainings = malloc(C * sizeof(int64_t));
	if (remainings == NULL) {
		sw_clear(ful_con);
		return NULL;  /* Allocation failure */
	}
	for (uint32_t i = 0; i < C; ++i) remainings[i] = constraint_violation(con, cur_sol, i);
	prepare_constraints(con, cur_sol, &ful_con);


	array_t ful = sw_init(obj->num_clauses[0]);
	prepare(obj, cur_sol, &ful); // prepare for optimized computation of objective value

	size_t feasible_state_counter = 0;
	state_t *st = malloc(num_moves * sizeof(state_t));
	for (size_t i = 0; i < num_moves; ++i) {
		st[feasible_state_counter].tot_profit = 0LL;
		st[feasible_state_counter].prob = 1. / ((double) num_moves);
		st[feasible_state_counter].vector = sw_init(cur_sol->vector.bits);
		sw_set_inplace(st[feasible_state_counter].vector, cur_sol->vector);
		for (int j = 0; j < moves[i].num_flips; ++j)
			sw_flpbit(st[feasible_state_counter].vector, moves[i].flips[j]); // flip bits

		// the oracle will look for the following states:
		// -> states, which moves are not tabu
		// -> if cur_col is not feasible:
		// -> -> if new sol is not fesible, but constraint violation lower than the one of cur_sol
		// -> -> new sol is feasible
		// -> else
		// -> -> new sol is feasible and objective value is better
		int feasible = 0;
		int include_state = 1;
		int64_t objective = 0;
		if (move_is_tabu(tabu_list, i)) include_state = 0;
		else {
			int64_t total_violation = 0;

			/* Heap-allocated instead of VLA */
			int64_t *totals = malloc(C * sizeof(int64_t));
			if (totals == NULL) {
				sw_clear(st[feasible_state_counter].vector);
				continue;  /* Skip this iteration on alloc failure */
			}
			array_t inv = sw_init(con->total_clauses);
			memset(totals, 0, C * sizeof(int64_t));
			int *changed_con = calloc(MINSIZE, sizeof(int));
			int num_con_changes = 0;


			for (int j = 0; j < moves[i].num_flips; ++j) {
				adjusted_constraint_violation(con, moves[i].flips[j], con->positive_indices, con->num_positive_indices,
				                              con->positive_offsets, &st[feasible_state_counter],
				                              POSITIVE, totals, &ful_con, &changed_con, &num_con_changes, &inv);
				adjusted_constraint_violation(con, moves[i].flips[j], con->negative_indices, con->num_negative_indices,
				                              con->negative_offsets, &st[feasible_state_counter],
				                              NEGATIVE, totals, &ful_con, &changed_con, &num_con_changes, &inv);
			}
			free(changed_con);
			sw_clear(inv);
			for (uint32_t cnstr = 0; cnstr < C; ++cnstr) {
				// only sum up violations
				total_violation -= remainings[cnstr] - totals[cnstr] < 0 ? remainings[cnstr] - totals[cnstr] : 0;
			}

			feasible = (total_violation <= 0);
			// for non feasible solutions, objective value is constraint violation
			if (!feasible) {
				objective = total_violation;
			} else {
				objective = objective_value(obj, cur_sol);
			}
			free(totals);  /* Free heap-allocated totals array */
		}

		include_state &= (feasible && !cur_sol->feasible) |
		                 ((((!feasible) && !cur_sol->feasible) | (feasible && cur_sol->feasible)) &
		                 (objective < cur_sol->tot_profit));

		if (include_state) {
			st[feasible_state_counter].feasible = feasible;
			st[feasible_state_counter].tot_profit = objective;
			feasible_state_counter++;
		} else {
			sw_clear(st[feasible_state_counter].vector);
		}
	}
	sw_clear(ful);
	sw_clear(ful_con);
	free(remainings);  /* Free heap-allocated remainings array */
	*num_states = feasible_state_counter;
	st = (state_t *) realloc(st, feasible_state_counter * sizeof(state_t));
	return st;
}


state_t *updated_local(state_t *bnb, size_t number_states,
                 size_t *new_number, state_t *cur_sol, tabu_list_t *tabu_list,
                 size_t *mapping) {
	state_t *up = calloc(number_states, sizeof(state_t));
	size_t a = 0;

	for (size_t i = 0; i < number_states; ++i) {
		int include_state = 1;
		if (move_is_tabu(tabu_list, i)) include_state = 0;
		include_state &= (bnb[i].feasible && !cur_sol->feasible) |
		                 ((((!bnb[i].feasible) && !cur_sol->feasible) | (bnb[i].feasible && cur_sol->feasible)) &
		                 (bnb[i].tot_profit < cur_sol->tot_profit));

		if (include_state) {
			mapping[a] = i;
			up[a].tot_profit = bnb[i].tot_profit;
			up[a].vector = sw_set(bnb[i].vector);
			up[a].feasible = bnb[i].feasible;
			up[a].prob = bnb[i].prob;
			a++;
		}
	}
	*new_number = a;
	if (a == 0) {
		free_state(up, number_states);
		return NULL;
	}
	up = realloc(up, a * sizeof(state_t));
	return up;
}


int quantum_local_search(new_constraints_t *obj,
                         new_constraints_t *con,
                         state_t *cur_sol, int k,
                         size_t *total_oracle_applications,
                         callback_t callback) {
	state_t *global_opt = copy_state(cur_sol);

	int num_moves = 0;
	move_t *moves = move_list(k, cur_sol->vector.bits, &num_moves, false);

	tabu_list_t tabu_list;
	tabu_list.max_moves = 10;
	tabu_list.head = 0;
	tabu_list.moves = malloc(tabu_list.max_moves * sizeof(int));
	for (int i = 0; i < tabu_list.max_moves; ++i) tabu_list.moves[i] = -1;

	size_t M = (size_t) (22.5 * sqrt((double) num_moves));

	int worse_acceptances = 0;
	// outer loop does the iterative searching until break condition is met
	while (worse_acceptances < 10) {

		// apply qsearch to improve solution
		// only stop, one the best solution found, was better then the current solution
		// starting state is the worst possible state with assignment of current solution
		// used, so that the best solution in neighbourhood can be found, even if it is worst than current solution
		state_t *start = copy_state(cur_sol);
		start->feasible = 0;
		start->tot_profit = INT64_MAX;
		size_t m_tot = 0;

		size_t index_of_best = 0;

		size_t num_states = 0;
		uint64_t qls_start_ns = cbqs_monotonic_ns();
		state_t *qlsqs = quantum_local_search_states(obj, con, moves, num_moves, start, &tabu_list, &num_states,
		                                             NULL);

		while (m_tot < M) {
			// recompute states, since, the neighbourhood changes after every accepted state
			size_t *mapping = malloc(
					num_moves * sizeof(size_t)); // map the indices of the superposition ot the indices of the moves
			size_t new_number = 0;

			state_t *new_states = updated_local(qlsqs, num_states, &new_number, start, &tabu_list, mapping);

			size_t iterations = 0;
			size_t rounds = 0;
			size_t measured_index = 0;
			state_t *qs = QSearch(new_states, new_number, &iterations, &rounds, M, &measured_index);

			*total_oracle_applications += 2 * iterations + rounds;
			m_tot += iterations;
			size_t index = mapping[measured_index];

			free_state(new_states, new_number);
			free(mapping);

			if (qs != NULL) {
				index_of_best = index;
				// better solution was found
				state_t temp = *start;
				*start = *qs;
				*qs = temp;
				free_state(qs, 1);
				// check, if new found solution is better than current solution, as we can then stop
				int accept = (((start->feasible && cur_sol->feasible) || (!start->feasible && !cur_sol->feasible)) &&
				             (start->tot_profit < cur_sol->tot_profit)) ||
				             (start->feasible && !cur_sol->feasible);
				if (accept) {
					temp = *cur_sol;
					*cur_sol = *start;
					*start = temp;
					free_state(start, 1);
					start = NULL;
					break;
				}
			} else { break; }
		}
		free_state(qlsqs, num_states);

		// if found cur sol is better than global opt: adjust
		int accept_global =
				(((cur_sol->feasible && global_opt->feasible) || (!cur_sol->feasible && !global_opt->feasible)) &&
				(cur_sol->tot_profit < global_opt->tot_profit)) ||
				(cur_sol->feasible && !global_opt->feasible);
		if (accept_global) {
			free_state(global_opt, 1);
			global_opt = copy_state(cur_sol);
			if (callback) callback();
		}
		uint64_t qls_end_ns = cbqs_monotonic_ns();
		double qls_elapsed_sec = (double)(qls_end_ns - qls_start_ns) / 1e9;
		(void)qls_elapsed_sec;

		if (start != NULL) {
			// if start did not provide a better solution, still accept it as worse solution
			state_t temp = *cur_sol;
			*cur_sol = *start;
			*start = temp;
			free_state(start, 1);
			start = NULL;
			worse_acceptances++;
		}

		// adjust the tabu list
		tabu_list.moves[tabu_list.head] = index_of_best;
		tabu_list.head += 1;
		tabu_list.head %= tabu_list.max_moves;
	}
	free_move_list(moves, num_moves);
	free(tabu_list.moves);

	free_state(global_opt, 1);

	return 0;
}
