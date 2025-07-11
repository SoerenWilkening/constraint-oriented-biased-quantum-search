//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"

int generate_combinations_iterative(state_t *new_sol, new_constraints_t *con, new_constraints_t *obj,
                                    int n, int d, int64_t *threshold, int *initial_feasible, array_t *fulfilled,
									array_t *fulfilled_con, int size_ful, int64_t *remainings) {

	int C = con->num_constraints;
	int64_t steps[C];
	memset(steps, 0, C * sizeof(int64_t));

	int *comb = malloc(d * sizeof(int));
	int bits[d];

	for (int k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int i = 0; i < k; ++i) comb[i] = i;

		// perform local search
		while (1) {
			// flip bits
			for (int i = 0; i < k; ++i) {
				bits[i] = sw_tstbit(new_sol->vector, comb[i]);// current bit
				if (bits[i]) sw_clrbit(new_sol->vector, comb[i]);
				else sw_setbit(new_sol->vector, comb[i]);
			}

			int64_t totals[C];
			array_t inv = sw_init(C * size_ful);
			memset(totals, 0, C * sizeof(int64_t));
			int *changed_con = calloc(MINSIZE, sizeof(int));
			int num_con_changes = 0;

			for (int i = 0; i < k; ++i) {
				adjusted_constraint_violation(con,comb[i], con->positive_indices, con->num_positive_indices, con->positive_offsets, new_sol,
											  POSITIVE, totals, fulfilled_con, &changed_con, &num_con_changes, &inv);
				adjusted_constraint_violation(con,comb[i], con->negative_indices, con->num_negative_indices, con->negative_offsets, new_sol,
				                              NEGATIVE, totals, fulfilled_con, &changed_con, &num_con_changes, &inv);
			}
			sw_clear(inv);

			// compute with new solution
			// is the new solution feasible ?
			int64_t total_violation = 0;

			for (int cnstr = 0; cnstr < C; ++cnstr) {
				// only sum up violations
				total_violation += remainings[cnstr] - totals[cnstr] < 0 ? remainings[cnstr] - totals[cnstr] : 0;
			}
			int feasible = (total_violation >= 0);

			// first try to find a feasible solution, by minimizing the constraints violation
			if (!(*initial_feasible)) {
				if (total_violation > *threshold && !feasible) {
					*threshold = total_violation;

					// accept changed constraints
					for (int i = 0; i < num_con_changes; ++i) {
						sw_flpbit(*fulfilled_con, changed_con[i]);
//						fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					}
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] -= totals[cnstr];
					free(comb);
					free(changed_con);
					return 1;
				}
				if (feasible) {
					*initial_feasible = feasible;
					*threshold = objective_value(obj, new_sol);

					prepare(obj, new_sol, fulfilled); // prepare for optimized computation of objective value
					new_sol->tot_profit = *threshold;

					// accept changed constraints
//					for (int i = 0; i < num_con_changes; ++i) fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					for (int i = 0; i < num_con_changes; ++i) sw_flpbit(*fulfilled_con, changed_con[i]);
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] -= totals[cnstr];
					free(comb);
					free(changed_con);
					return 2;
				}
			} else {
				int *changes = calloc(MINSIZE, sizeof(int));
				int num_cahnges = 0;
				int64_t objective = objective_value_improved(obj, new_sol, k, comb, fulfilled, &changes, &num_cahnges);

				if (objective < *threshold && feasible) {
					*threshold = objective;
					// apply changes to objective
//					for (int i = 0; i < num_cahnges; ++i) fulfilled[changes[i]] = 1 - fulfilled[changes[i]];
					for (int i = 0; i < num_cahnges; ++i) sw_flpbit(*fulfilled, changes[i]);

					// accept changed constraints
//					for (int i = 0; i < num_con_changes; ++i) fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					for (int i = 0; i < num_con_changes; ++i) sw_flpbit(*fulfilled_con, changed_con[i]);
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] -= totals[cnstr];
					new_sol->tot_profit = objective;
					free(comb);
					free(changes);
					free(changed_con);
					return 2;
				}
				free(changes);
			}
			free(changed_con);

			// unflip bits
			for (int i = 0; i < k; ++i) {
				if (bits[i]) sw_setbit(new_sol->vector, comb[i]);
				else sw_clrbit(new_sol->vector, comb[i]);
			}

			// Generate next combination
			int i = k - 1;
			while (i >= 0 && comb[i] == n - k + i) i--;
			if (i < 0) break; // All combinations done

			comb[i]++;
			for (int j = i + 1; j < k; ++j)
				comb[j] = comb[j - 1] + 1;
		}
	}

	free(comb);
	return 0;
}


int local_search(state_t *cur_sol,
                 new_constraints_t *con,
                 new_constraints_t *obj,
                 int distance,
                 int stopping_time,
                 solver_t solver,
                 int64_t stop_val,
                 callback_t callback) {

	struct timespec t1, t2;
	clock_gettime(CLOCK_MONOTONIC, &t1);

	int n = cur_sol->vector.bits;
	int C = con->num_constraints;

	array_t ful = sw_init(obj->num_clauses[0]);

	int max_constraint_clauses = 0;
	for (int i = 0; i < C; ++i) if (con->num_clauses[C] > max_constraint_clauses) max_constraint_clauses = con->num_clauses[C];

	array_t ful_con = sw_init(C * max_constraint_clauses);

	state_t *new_sol = copy_state(cur_sol);
	int break_item = 0;
	int pot_eval = initial_state_preparation(new_sol, cur_sol, con, 0, &break_item);
	free_state(new_sol, 1);

	int64_t remainings[C];
	for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, cur_sol, i);
	prepare_constraints(con, cur_sol, &ful_con);

	int64_t thre = pot_eval;
	int initial_feasible = eval_constraints(con, cur_sol, n);
	if (initial_feasible) {
		thre = objective_value(obj, cur_sol);
		cur_sol->tot_profit = thre;
		prepare(obj, cur_sol, &ful); // prepare for optimized computation of objective value
	}
	int break_condition = 1;
	while (break_condition) {
		break_condition = generate_combinations_iterative(cur_sol, con, obj, n, distance, &thre, &initial_feasible, &ful,
		                                                  &ful_con, max_constraint_clauses, remainings);
		clock_gettime(CLOCK_MONOTONIC, &t2);
		printf(" %lld %f\n", thre, (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);
	}
	sw_clear(ful_con);
	sw_clear(ful);

	return 0;
}



// instance 1000 0
//-2541824465 0.811937 -2541824465 0.747621 -2541824465 0.733215 -2541824465 0.729911
//-2541840041 1.451326 -2541840041 1.369981 -2541840041 1.331356 -2541840041 1.336487
//-2541853166 2.256461 -2541853166 2.079619 -2541853166 2.023245 -2541853166 2.021711
//-2541877731 2.941164 -2541877731 2.717657 -2541877731 2.621373 -2541877731 2.622210
//-2541946861 5.138395 -2541946861 4.790753 -2541946861 4.616239 -2541946861 4.639479
//-2541959467 5.889666 -2541959467 5.526042 -2541959467 5.307099 -2541959467 5.346986
//-2541992340 6.551404 -2541992340 6.145888 -2541992340 5.918960 -2541992340 5.951085