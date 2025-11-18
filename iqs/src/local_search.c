//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"

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
//	printf("move is tabu\n");
	sw_set_inplace(cur_best_tabu->vector, state2->vector); // copy assignment to current best
	cur_best_tabu->tot_profit = objective;
	cur_best_tabu->feasible = feasible;
}

static inline int aspiration(state_t *new_sol, state_t *global_opt) {
	// for tabu moves: if better than global opt: accept
//	int accepted = 0;
//	int greater_objective = new_sol->tot_profit < global_opt->tot_profit;
//	if (new_sol->feasible && !global_opt->feasible) accepted = 1;
//	if (new_sol->feasible && global_opt->feasible && greater_objective) accepted = 1;
//	if (!new_sol->feasible && !global_opt->feasible && greater_objective) accepted = 1;
//	if (!accepted) return 0;
//
//	sw_set_inplace(global_opt->vector, new_sol->vector); // copy assignment to current best
//	global_opt->tot_profit = new_sol->tot_profit;
//	global_opt->feasible = new_sol->feasible;
	return 0;
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
			int j = rand() % (i + 1);  // random index from 0..i
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

typedef struct {
	double progress[NUMThreads];
	int stat;
} dat_t;

void *print_status(void *args) {
	dat_t *progress = (dat_t *) args;
	while (!progress->stat) {
		printf("\r");
		for (int i = 0; i < NUMThreads; i++) {
			printf("| %6.1f%% |", progress->progress[i] * 100);
		}
		usleep(1000000);
	}
	return NULL;
}

void *explore_neighbourhood(void *args) {
	local_search_data_t *dat = (local_search_data_t *) args;
	int C = dat->con->num_constraints;
	int64_t steps[C];
	memset(steps, 0, C * sizeof(int64_t));

	int bits[dat->d];

	state_t *cur_best = copy_state(dat->sol);
	state_t *cur_best_tabu = copy_state(dat->sol); // current best tabu move
	cur_best->tot_profit = INT64_MAX;
	cur_best_tabu->tot_profit = INT64_MAX;

	state_t *new_sol = copy_state(dat->sol);

	for (int mov = dat->start_move; mov < dat->end_move; ++mov) {
		// stop, if first better solution was found
		if (*dat->stopping_criterion) break;
		dat->count_states++; // store how many states were investigated by thread

		int *comb = dat->moves[mov].flips;
		int k = dat->moves[mov].num_flips;
		// flip bits
		for (int i = 0; i < k; ++i) {
			bits[i] = sw_tstbit(new_sol->vector, comb[i]);// current bit
			if (bits[i]) sw_clrbit(new_sol->vector, comb[i]);
			else sw_setbit(new_sol->vector, comb[i]);
		}

		int64_t totals[C];
		array_t inv = sw_init(C * dat->size_ful);
		memset(totals, 0, C * sizeof(int64_t));
		int *changed_con = calloc(MINSIZE, sizeof(int));
		int num_con_changes = 0;

        for (int i = 0; i < C; ++i){
            totals[i] = constraint_violation(dat->con, new_sol, i);
        }
//		for (int i = 0; i < k; ++i) {
//			adjusted_constraint_violation(dat->con, comb[i], dat->con->positive_indices, dat->con->num_positive_indices,
//			                              dat->con->positive_offsets, new_sol,
//			                              POSITIVE, totals, dat->ful_con, &changed_con, &num_con_changes, &inv);
//			adjusted_constraint_violation(dat->con, comb[i], dat->con->negative_indices, dat->con->num_negative_indices,
//			                              dat->con->negative_offsets, new_sol,
//			                              NEGATIVE, totals, dat->ful_con, &changed_con, &num_con_changes, &inv);
//		}
		free(changed_con);
		sw_clear(inv);

		// compute with new solution
		// is the new solution feasible ?
		int64_t total_violation = 0;

		for (int cnstr = 0; cnstr < C; ++cnstr) {
			// only sum up violations
			total_violation -= dat->remainings[cnstr] - totals[cnstr] < 0 ? dat->remainings[cnstr] - totals[cnstr] : 0;
//			total_violation -= totals[cnstr] < 0 ? totals[cnstr] : 0;
		}
		int feasible = (total_violation == 0);

		// first try to find a feasible solution, by minimizing the constraints violation
		if (!(dat->initial_feasible)) {
			if (total_violation < cur_best->tot_profit && !feasible) {
				update_state(cur_best, cur_best_tabu, new_sol, total_violation, 0, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
//				*dat->stopping_criterion = 1; // stop every thread, as new solution is found
			}
			if (feasible) {
				dat->initial_feasible = feasible;
				update_state(cur_best, cur_best_tabu, new_sol, objective_value(dat->obj, new_sol),
				             1, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
//				*dat->stopping_criterion = 1; // stop every thread, as new solution is found
			}
		} else {
			int *changes = calloc(MINSIZE, sizeof(int));
			int num_cahnges = 0;
//			int64_t objective = objective_value_improved(dat->obj, new_sol, k, comb, dat->ful, &changes, &num_cahnges);
            int64_t objective = objective_value(dat->obj, new_sol);

			if (objective < cur_best->tot_profit && feasible) {
				update_state(cur_best, cur_best_tabu, new_sol, objective, 1, dat->tabu_list, mov);
				if (move_is_tabu(dat->tabu_list, mov)) dat->tabu_move_index = mov;
				else dat->move_index = mov;
//				*dat->stopping_criterion = 1; // stop every thread, as new solution is found
			}
			free(changes);
		}

		// if cur_best is better than sol: stop all threads
		if (cur_best->tot_profit < dat->sol->tot_profit) *dat->stopping_criterion = dat->stopping_condition;

		// unflip bits
		for (int i = 0; i < k; ++i) {
			if (bits[i]) sw_setbit(new_sol->vector, comb[i]);
			else sw_clrbit(new_sol->vector, comb[i]);
		}
		// dat->progress[dat->id] += 1. / (dat->end_move - dat->start_move);
	}
	free_state(new_sol, 1);
	dat->cur_best = cur_best;
	dat->cur_best_tabu = cur_best_tabu;
	return NULL;
}

int accept_best_routine(state_t *new_sol, state_t *global_opt, new_constraints_t *con, new_constraints_t *obj,
                        int d, int *initial_feasible, int size_ful,
                        move_t *moves, int num_moves, tabu_list_t *tabu_list,
                        int *accept_worse_counter, int max_worse_acceptances,
                        int stopping_criterion, int *neighbourhood_counter) {

	int C = con->num_constraints;

	state_t *cur_best = copy_state(new_sol);
	state_t *cur_best_tabu = copy_state(new_sol);
	cur_best->tot_profit = INT64_MAX;
	cur_best_tabu->tot_profit = INT64_MAX;

	array_t ful = sw_init(obj->num_clauses[0]);
	array_t ful_con = sw_init(C * size_ful);

	int64_t remainings[C];
	for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, new_sol, i);
	prepare_constraints(con, new_sol, &ful_con);
	prepare(obj, new_sol, &ful); // prepare for optimized computation of objective value

	dat_t prog_data;
	// memset(prog_data.progress, 0, NUMThreads * sizeof(double));
	// prog_data.stat = 0;
	// pthread_t progress_thread;
	// pthread_create(&progress_thread, NULL, print_status, (void *)&prog_data);
	local_search_data_t data[NUMThreads];
	pthread_t threads[NUMThreads];
	int stop_at_first = 0;
	for (int i = 0; i < NUMThreads; ++i) {
		data[i].con = con;
		data[i].obj = obj;
		data[i].moves = moves;
		data[i].remainings = remainings;
		data[i].initial_feasible = *initial_feasible;
		data[i].ful_con = &ful_con;
		data[i].ful = &ful;
		data[i].cur_best = NULL;
		data[i].cur_best_tabu = NULL;
		data[i].tabu_list = tabu_list;
		data[i].sol = new_sol;
		data[i].size_ful = size_ful;
		data[i].d = d;
		data[i].start_move = i * num_moves / NUMThreads;
		data[i].end_move = (i + 1) * num_moves / NUMThreads;
		data[i].progress = prog_data.progress;
		data[i].id = i;
		data[i].stopping_criterion = &stop_at_first;
		data[i].stopping_condition = stopping_criterion;
		data[i].count_states = 0;
	}
	for (int i = 0; i < NUMThreads; ++i) {
		pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
	}
	int accepted_index = -1;
	for (int i = 0; i < NUMThreads; ++i) {
		pthread_join(threads[i], NULL);
		int acc = 0;
		int acc_tab = 0;
		if (data[i].cur_best != NULL) {
			acc = accept_move(cur_best, data[i].cur_best, global_opt);
			free_state(data[i].cur_best, 1);
		}
		if (data[i].cur_best != NULL) {
			// tabu aspiration:
			// - gives feasible solution if others dont
			// - gives best ever found solution
			acc_tab = aspiration(data[i].cur_best_tabu, global_opt);
			if (acc_tab) acc = accept_move(cur_best, data[i].cur_best_tabu, global_opt);
			free_state(data[i].cur_best_tabu, 1);
		}
		if (acc || acc_tab) accepted_index = acc * data[i].move_index + acc_tab * data[i].tabu_move_index;
		*neighbourhood_counter += data[i].count_states;
	}
	//prog_data.stat = 1;
	//pthread_join(progress_thread, NULL);

	int accepted = accept_move(new_sol, cur_best, global_opt);
	int accepted_tabu = aspiration(cur_best_tabu, global_opt);
	if (accepted_tabu) accept_move(new_sol, global_opt, global_opt);

	int new_move_index = -1;
	if (accepted || accepted_tabu) {
		// determine index of move
		new_move_index = -1;
	} else {
		if (*accept_worse_counter == max_worse_acceptances) return 0; // stop the entire search
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
	sw_clear(ful);
	sw_clear(ful_con);
	return accepted || accepted_tabu;
}

int local_search(state_t *cur_sol,
                 new_constraints_t *con,
                 new_constraints_t *obj,
                 int distance,
                 int stopping_time,
                 solver_t solver,
                 int64_t stop_val,
                 callback_t callback,
                 int max_worse_acceptances,
                 int stopping_criterion) {

	struct timespec t1, t2;
	clock_gettime(CLOCK_MONOTONIC, &t1);

	int n = cur_sol->vector.bits;
	int C = con->num_constraints;

	array_t ful = sw_init(obj->num_clauses[0]);
	int max_constraint_clauses = 0;
	for (int i = 0; i < C; ++i) {
		if (con->num_clauses[i] > max_constraint_clauses) {
			max_constraint_clauses = con->num_clauses[i];
		}
	}

	array_t ful_con = sw_init(C * max_constraint_clauses);

	int64_t remainings[C];
	for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, cur_sol, i);
	prepare_constraints(con, cur_sol, &ful_con);

	int initial_feasible = eval_constraints(con, cur_sol, n);
	printf("init = %d\n", initial_feasible);
	state_t *global_opt = copy_state(cur_sol);

	int num_moves = 0;
	move_t *moves = move_list(distance, n, &num_moves, true);
//	for (int i = 0; i < num_moves; ++i) {
//		printf("%d: ", moves[i].num_flips);
//		for (int j = 0; j < moves[i].num_flips; ++j) {
//			printf("%d ", moves[i].flips[j]);
//		}
//		printf("\n");
//	}

	tabu_list_t tabu_list;
	tabu_list.max_moves = 10;
	tabu_list.head = 0;
	tabu_list.moves = malloc(tabu_list.max_moves * sizeof(int));
	for (int i = 0; i < tabu_list.max_moves; ++i) {
		tabu_list.moves[i] = -1;
	}

	clock_gettime(CLOCK_MONOTONIC, &t2);
	double preprocessing_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
	int break_condition = 1;
	int worse_acceptance_counter = 0;
	int counter = 0;
	while (break_condition) {
		int neighbourhood_counter = 0;
		break_condition = accept_best_routine(cur_sol, global_opt, con, obj, distance, &initial_feasible,
		                                      max_constraint_clauses, moves, num_moves, &tabu_list,
		                                      &worse_acceptance_counter, max_worse_acceptances,
		                                      stopping_criterion, &neighbourhood_counter);
		clock_gettime(CLOCK_MONOTONIC, &t2);
		double time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
//		printf("%p\n", callback);
//        print_state(cur_sol);
//		printf("\n");
//		if (callback) callback(cur_sol->tot_profit, 0, time, preprocessing_time);
		printf("%d %d %lld %lld %f %d,\n", counter, break_condition, cur_sol->tot_profit, global_opt->tot_profit, time,
		       neighbourhood_counter);
		if (time > stopping_time || (cur_sol->tot_profit <= stop_val) && (stop_val != -1)) return 0;
		counter++;
	}

	accept_move(cur_sol, global_opt, global_opt);

	free_move_list(moves, num_moves);
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
	int C = con->num_constraints;
	int64_t remainings[C];
	for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, cur_sol, i);
	prepare_constraints(con, cur_sol, &ful_con);


	array_t ful = sw_init(obj->num_clauses[0]);
	prepare(obj, cur_sol, &ful); // prepare for optimized computation of objective value
	int64_t init_val = objective_value(obj, cur_sol);

	size_t feasible_state_counter = 0;
	state_t *st = malloc(num_moves * sizeof(state_t));
	for (int i = 0; i < num_moves; ++i) {
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
		if (move_is_tabu(&tabu_list, i)) include_state = 0;
		else {
			int64_t total_violation = 0;

			int64_t totals[C];
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
			for (int cnstr = 0; cnstr < C; ++cnstr) {
				// only sum up violations
				total_violation -= remainings[cnstr] - totals[cnstr] < 0 ? remainings[cnstr] - totals[cnstr] : 0;
			}

//			for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
//				int64_t viol = constraint_violation(con, &st[feasible_state_counter], cnstr);
//				total_violation -= (viol < 0) * viol;
//			}
			feasible = (total_violation <= 0);
			// for non feasible solutions, objective value is constraint violation
			if (!feasible) {
				objective = total_violation;
//			} else { objective = objective_value(obj, &st[feasible_state_counter]); }
			} else {
				int *changes = calloc(MINSIZE, sizeof(int));
				int num_cahnges = 0;
				objective = objective_value(obj, cur_sol);
//				objective = init_val + objective_value_improved(
//						obj,
//						&st[feasible_state_counter],
//						moves[i].num_flips,
//						moves[i].flips,
//						&ful,
//						&changes,
//						&num_cahnges);
				free(changes);
			}
		}

		include_state &= (feasible && !cur_sol->feasible) |
		                 (((!feasible) && !cur_sol->feasible) | (feasible && cur_sol->feasible)) &
		                 (objective < cur_sol->tot_profit);

		if (include_state) {
			st[feasible_state_counter].feasible = feasible;
			st[feasible_state_counter].tot_profit = objective;
			feasible_state_counter++;
		} else {
			sw_clear(st[feasible_state_counter].vector);
		}
	}
	sw_clear(ful);
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
		                 (((!bnb[i].feasible) && !cur_sol->feasible) | (bnb[i].feasible && cur_sol->feasible)) &
		                 (bnb[i].tot_profit < cur_sol->tot_profit);

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

	size_t num_moves = 0;
	move_t *moves = move_list(k, cur_sol->vector.bits, &num_moves, false);

	tabu_list_t tabu_list;
	tabu_list.max_moves = 10;
	tabu_list.head = 0;
	tabu_list.moves = malloc(tabu_list.max_moves * sizeof(int));
	for (int i = 0; i < tabu_list.max_moves; ++i) tabu_list.moves[i] = -1;

	size_t M = (size_t) (22.5 * sqrt((double) num_moves));
//	printf("M = %zu\n", M);

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
		struct timespec t1, t2;
		clock_gettime(CLOCK_MONOTONIC, &t1);
		state_t *qlsqs = quantum_local_search_states(obj, con, moves, num_moves, start, &tabu_list, &num_states,
		                                             NULL);

//	for (int i = 0; i < num_states; ++i) {
//		print_state(&qlsqs[i]);
//		printf("\n");
//	}

//	    clock_gettime(CLOCK_MONOTONIC, &t2);
//	    printf("gen time = %f\n", (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);
		while (m_tot < M) {
			// recompute states, since, the neighbourhood changes after every accepted state
			size_t *mapping = malloc(
					num_moves * sizeof(size_t)); // map the indices of the superposition ot the indices of the moves
			size_t new_number = 0;

//			clock_gettime(CLOCK_MONOTONIC, &t1);
			state_t *new_states = updated_local(qlsqs, num_states, &new_number, start, &tabu_list, mapping);
//			clock_gettime(CLOCK_MONOTONIC, &t2);
//			printf("update = %f\n", (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);

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
				int accept = ((start->feasible && cur_sol->feasible) || (!start->feasible && !cur_sol->feasible)) &&
				             (start->tot_profit < cur_sol->tot_profit) ||
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
				((cur_sol->feasible && global_opt->feasible) || (!cur_sol->feasible && !global_opt->feasible)) &&
				(cur_sol->tot_profit < global_opt->tot_profit) ||
				(cur_sol->feasible && !global_opt->feasible);
		if (accept_global) {
			free_state(global_opt, 1);
			global_opt = copy_state(cur_sol);
			if (callback) callback(-global_opt->tot_profit, *total_oracle_applications, 0, 0);
//			printf("%zu %lld\n", *total_oracle_applications, global_opt->tot_profit);
		}
		clock_gettime(CLOCK_MONOTONIC, &t2);
//		printf("total = %f\n", (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);

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

//	state_t temp = *cur_sol;
//	*cur_sol = *global_opt;
//	*global_opt = temp;
	free_state(global_opt, 1);

	return 0;
}

//-32 0.066667 1 10000
//-16 0.066667 1 01000
//-8 0.066667 1 00100
//-24 0.066667 1 01100
//-20 0.066667 1 01010
//-18 0.066667 1 01001
//-12 0.066667 1 00110
//-10 0.066667 1 00101
