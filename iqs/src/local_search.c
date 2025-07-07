//
// Created by Sören Wilkening on 07.07.25.
//

#include "local_search.h"

int generate_combinations_iterative(state_t *new_sol, new_constraints_t *con, new_constraints_t *obj,
									 int n, int d, int64_t *threshold, int *initial_feasible) {
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
			int feasible = eval_constraints(con, new_sol, n);
			int64_t total_violation = 0;
			// first try to find a feasible solution, by minimizing the constraints violation
			if (!(*initial_feasible)){
//				if (!feasible) {
					for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
						int viol = constraint_violation(con, new_sol, cnstr);
//						printf("%d %d\n", cnstr, viol);
						// only sum up violations
						total_violation += viol < 0 ? viol: 0;
					}
//				}
				if (total_violation > *threshold && !feasible) {
					*threshold = total_violation;
					free(comb);
					return 1;
				}
				if (feasible) {
//					printf("feasible now!!\n");
					*initial_feasible = feasible;
					*threshold = objective_value(obj, new_sol);
					free(comb);
					return 1;
				}
			}else{
				int64_t objective = objective_value(obj, new_sol);
				if (objective < *threshold && feasible){
					*threshold = objective;
					free(comb);
					return 1;
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
                 callback_t callback){

	int n = cur_sol->vector.bits;
	int64_t thre = -INT64_MAX;
	int initial_feasible = eval_constraints(con, cur_sol, n);
	int break_condition = 1;
	while (break_condition){
		sw_print(cur_sol->vector);
		printf(" %lld\n", thre);
		break_condition = generate_combinations_iterative(cur_sol, con, obj, n, distance, &thre, &initial_feasible);
	}
	sw_print(cur_sol->vector);
	printf(" %lld\n", thre);

	return 0;
}
