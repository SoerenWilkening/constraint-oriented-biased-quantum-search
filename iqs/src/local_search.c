//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"

int generate_combinations_iterative(state_t *new_sol, new_constraints_t *con, new_constraints_t *obj,
                                    int n, int d, int64_t *threshold, int *initial_feasible, int *fulfilled) {

	int fulfilled_step[obj->num_clauses[0]]; // storing the fulfilled terms of the objective
	memcpy(fulfilled_step, fulfilled, obj->num_clauses[0] * sizeof(int));
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

			// compute with new solution
			// is the new solution feasible ?
			int64_t total_violation = 0;
			int feasible = 1;
			for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
				int viol = constraint_violation(con, new_sol, cnstr);
				// only sum up violations
				total_violation += viol < 0 ? viol : 0;
				feasible *= (viol >= 0);
			}
			// first try to find a feasible solution, by minimizing the constraints violation
			if (!(*initial_feasible)) {
				if (total_violation > *threshold && !feasible) {
					*threshold = total_violation;
					free(comb);
					return 1;
				}
				if (feasible) {
					*initial_feasible = feasible;
					*threshold = objective_value(obj, new_sol);

					prepare(obj, new_sol, fulfilled); // prepare for optimized computation of objective value
					memcpy(fulfilled_step, fulfilled, obj->num_clauses[0] * sizeof(int));

					new_sol->tot_profit = *threshold;
					free(comb);
					return 2;
				}
			} else {
//				int64_t objective =  objective_value(obj, new_sol);
				int64_t objective = objective_value_improved(obj, new_sol, k, comb, fulfilled_step);
				if (objective < *threshold && feasible) {
					*threshold = objective;
					memcpy(fulfilled, fulfilled_step, obj->num_clauses[0] * sizeof(int)); // accept adjustments
					new_sol->tot_profit = objective;
					free(comb);
					return 2;
				}else{
					// redo list adjustment, not accepted
					memcpy(fulfilled_step, fulfilled, obj->num_clauses[0] * sizeof(int));
				}
			}

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
	int C = obj->num_constraints;

	int fulfilled[obj->num_clauses[0]]; // storing the fulfilled terms of the objective
	memset(fulfilled, 0, obj->num_clauses[0] * sizeof(int));

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

	struct timespec t1, t2;
	clock_gettime(CLOCK_MONOTONIC, &t1);

	int arr[n];
	memset(arr, 0, n * sizeof(int));
	state_t *new_sol = init_state(0, arr, n);
	int break_item = 0;
	int pot_eval = initial_state_preparation(new_sol, cur_sol, con, 0, &break_item);
	free_state(new_sol, 1);
	int64_t thre = pot_eval;
	int initial_feasible = eval_constraints(con, cur_sol, n);
	if (initial_feasible) thre = objective_value(obj, cur_sol);
	int break_condition = 1;
	for (int i = 0; i < n; ++i) arr[i] = i;
	while (break_condition) {
		break_condition = generate_combinations_iterative(cur_sol, con, obj, n, distance, &thre, &initial_feasible, fulfilled);
		clock_gettime(CLOCK_MONOTONIC, &t2);
		printf("%lld %f\n", thre, (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9);
	}

	return 0;
}
