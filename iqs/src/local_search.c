//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"

int generate_combinations_iterative(state_t *new_sol, new_constraints_t *con, new_constraints_t *obj,
                                    int n, int d, int64_t *threshold, int *initial_feasible, int *fulfilled,
									int *fulfilled_con, int size_ful, int64_t *remainings) {

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
			memset(totals, 0, C * sizeof(int64_t));
			for (int i = 0; i < k; ++i) {
				printf("item %d\n", comb[i]);
				adjusted_constraint_violation(con,comb[i], con->positive_indices, con->num_positive_indices, con->positive_offsets, new_sol,
											  POSITIVE, totals, fulfilled_con);
				adjusted_constraint_violation(con,comb[i], con->negative_indices, con->num_negative_indices, con->negative_indices, new_sol,
				                              NEGATIVE, totals, fulfilled_con);
			}

			// compute with new solution
			// is the new solution feasible ?
			int64_t total_violation = 0;
			int64_t total_violation2 = 0;
			int64_t total_violation3 = 0;

			int feasible = 1;
			int *changed_con = calloc(128, sizeof(int));
			int num_con_changes = 0;
			for (int cnstr = 0; cnstr < C; ++cnstr) {
				steps[cnstr] = improved_constraint_violation(con, new_sol, cnstr, k, comb, fulfilled_con, &changed_con, &num_con_changes, size_ful);
				int viol2 = constraint_violation(con, new_sol, cnstr);
				int64_t viol = remainings[cnstr] + steps[cnstr];
				// only sum up violations
				total_violation += viol < 0 ? viol : 0;
				total_violation2 += viol2 < 0 ? viol2 : 0;
				total_violation3 += remainings[cnstr] + totals[cnstr] < 0 ? remainings[cnstr] + totals[cnstr] : 0;
//				printf("\n%lld %lld\n", remainings[cnstr], totals[cnstr]);
				feasible *= (viol >= 0);
			}
			printf("meth1: %lld correct: %lld meth2: %lld\n", total_violation, total_violation2, total_violation3);
			return 0;
			// first try to find a feasible solution, by minimizing the constraints violation
			if (!(*initial_feasible)) {
				if (total_violation > *threshold && !feasible) {
					*threshold = total_violation;

					// accept changed constraints
					for (int i = 0; i < num_con_changes; ++i) fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] += steps[cnstr];
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
					for (int i = 0; i < num_con_changes; ++i) fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] += steps[cnstr];
					free(comb);
					free(changed_con);
					return 2;
				}
			} else {
				int *changes = calloc(128, sizeof(int));
				int num_cahnges = 0;
				int64_t objective = objective_value_improved(obj, new_sol, k, comb, fulfilled, &changes, &num_cahnges);

				if (objective < *threshold && feasible) {
					*threshold = objective;
					// apply changes to objective
					for (int i = 0; i < num_cahnges; ++i) fulfilled[changes[i]] = 1 - fulfilled[changes[i]];

					// accept changed constraints
					for (int i = 0; i < num_con_changes; ++i) fulfilled_con[changed_con[i]] = 1 - fulfilled_con[changed_con[i]];
					for (int cnstr = 0; cnstr < C; ++cnstr) remainings[cnstr] += steps[cnstr];
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

	int n = cur_sol->vector.bits;
	int C = con->num_constraints;

	// plot test
	printf("negative coefficients\n");
	for (int item = 0; item < n; item++) {
		for (int cnstr = 0; cnstr < C; cnstr++) {
			printf("%d: %d-> ", item, cnstr);
			for (int cls = 0; cls < con->num_negative_indices[item * C + cnstr]; cls++) {
				printf("%u ", con->negative_indices[con->negative_offsets[item * C + cnstr] + cls]);
			}
			printf("\n");
		}
	}
	printf("positive coefficients\n");
	for (int item = 0; item < n; item++) {
		for (int cnstr = 0; cnstr < C; cnstr++) {
			printf("%d: %d-> ", item, cnstr);
			for (int cls = 0; cls < con->num_positive_indices[item * C + cnstr]; cls++) {
				printf("%u ", con->positive_indices[con->positive_offsets[item * C + cnstr] + cls]);
			}
			printf("\n");
		}
	}

	int fulfilled[obj->num_clauses[0]]; // storing the fulfilled terms of the objective
	memset(fulfilled, 0, obj->num_clauses[0] * sizeof(int));

	int max_constraint_clauses = 0;
	for (int i = 0; i < C; ++i) if (con->num_clauses[C] > max_constraint_clauses) max_constraint_clauses = con->num_clauses[C];
	printf("%d %d\n", max_constraint_clauses, C);

	int fulfilled_con[C * max_constraint_clauses];
	memset(fulfilled_con, 0, C * max_constraint_clauses * sizeof(int));


	struct timespec t1, t2;
	clock_gettime(CLOCK_MONOTONIC, &t1);

	int arr[n];
	memset(arr, 0, n * sizeof(int));
	state_t *new_sol = init_state(0, arr, n);
	int break_item = 0;
	int pot_eval = initial_state_preparation(new_sol, cur_sol, con, 0, &break_item);
	print_state(cur_sol);

	prepare_constraints(con, cur_sol, fulfilled_con);
	for (int i = 0; i < C * max_constraint_clauses; ++i)
		printf("%d %d\n", i, fulfilled_con[i]);
	printf("\n");

	int64_t remainings[C];
	for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, cur_sol, i);

	free_state(new_sol, 1);
	int64_t thre = pot_eval;
	int initial_feasible = eval_constraints(con, cur_sol, n);
	if (initial_feasible) thre = objective_value(obj, cur_sol);
	int break_condition = 1;
	for (int i = 0; i < n; ++i) arr[i] = i;
	while (break_condition) {
		break_condition = generate_combinations_iterative(cur_sol, con, obj, n, distance, &thre, &initial_feasible, fulfilled,
		                                                  fulfilled_con, max_constraint_clauses, remainings);
		clock_gettime(CLOCK_MONOTONIC, &t2);
		printf("%lld %f\n", thre, (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);
	}

	return 0;
}
