#include "solver.h"

// implementations of classical sampling search and benchmarking =======================================================
static inline int evaluation(new_constraints_t *con, int64_t *potentials, int item,
                             const unsigned int *indices,
                             const unsigned int *num_indices,
                             const unsigned int *offsets, state_t *cur_sol, int negative, int64_t *ret_total) {
	size_t C = con->num_constraints;
	int feasible = 1;
	// check, if assignment does not exceed potentials
	for (int cnstr = 0; cnstr < C; cnstr++) {
		int64_t total = 0;
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++) {
			int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
			size_t clause_index = clause_offset + index;

			int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
			int is_closed = 1;
			for (int i = 0; i < con->clause_length[clause_index]; i++) {
				size_t var = con->variables[variable_index(index, i, clause_offset)];
				if (var < item) assigned &= sw_tstbit(cur_sol->vector, var);
				if (var > item) {
				    is_closed = 0;
				    break;
				}
			}
			if (negative == POSITIVE && is_closed || negative == NEGATIVE)
				total += labs(con->factors[clause_index]) * assigned;
		}
		ret_total[cnstr] = total;
		if (potentials[cnstr] < total) feasible = 0;
	}
    if (!feasible) return 0;
	return 1;
}

static inline int update_potentials(new_constraints_t *con, int64_t *potentials, int item,
                                    const unsigned int *indices,
                                    const unsigned int *num_indices,
                                    const unsigned int *offsets, state_t *cur_sol,
                                    int bit, int negative, int direction, int64_t *ret_total) {
	// careful: destinction between positive and negative coefficients
	// for non-linear clauses with negative coefficients there are two ways, s.t. potential has to be subtracted:
	//  -> consideres item is set to 0 or previous assignments of clause are set to 0
	// for positive coefficients subtraction is only possible if considered item is set to 1 AND all previous assignments
	// are set to 1
	// update potentials has to be called 3 times

	size_t C = con->num_constraints;
	// revert the constraints rhs accordingly
	for (int cnstr = 0; cnstr < C; cnstr++) {
		potentials[cnstr] += direction * ret_total[cnstr];
//        int64_t total = 0;
//		size_t clause_offset = first_clause_index(con, cnstr);
//		for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++) {
//			unsigned int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
//			size_t clause_index = clause_offset + index;
//
//			// only if all previous items are assigned to 1, adjust rhs
//			int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
//			int is_closed = 1; // check, if there are unassigned variables within the clause
//			for (int i = 0; i < con->clause_length[clause_index]; i++) {
//				size_t var = con->variables[variable_index(index, i, clause_offset)];
//				if (var < item) assigned *= sw_tstbit(cur_sol->vector, var);
//				if (var > item) is_closed = 0;
//			}
//			if (negative == POSITIVE && is_closed || negative == NEGATIVE)
//				total += direction * labs(con->factors[clause_index]) * assigned;
//		}
////		printf("%lld %lld\n", total, direction * ret_total[cnstr]);
//		potentials[cnstr] += total;
	}
	return 1;
}

// look ahead to evaluate all possible solutions from certain position up to certain depth
//int look_ahead_correct( int index, int next_assignment, int depth, int *count_solutions, int64_t *potentials,
//                int **S_plus, int64_t **S_plus_value, int *num_plus,
//                int **S_minus, int64_t **S_minus_value, int *num_minus){
int look_ahead_correct(int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total) {
	// check, if assignment does not exceed potentials
//    if (next_assignment) sw_setbit(cur_sol->vector, index); // set assignment to 1
//    else sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)

	int bool_;
	if (next_assignment) sw_setbit(cur_sol->vector, index); // set assignment to 1
	else sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)

	if (next_assignment)
		bool_ = evaluation(con, potentials, index,
		                   con->positive_indices,
		                   con->num_positive_indices,
		                   con->positive_offsets, cur_sol,
		                   POSITIVE, ret_total);
	else
		bool_ = evaluation(con, potentials, index,
		                   con->negative_indices,
		                   con->num_negative_indices,
		                   con->negative_offsets, cur_sol,
		                   NEGATIVE, ret_total);

	if (bool_) {
		if (index == depth) (*count_solutions)++;
		else {
			if (next_assignment) {
				update_potentials(con, potentials, index,
				                  con->positive_indices,
				                  con->num_positive_indices,
				                  con->positive_offsets,
				                  cur_sol, next_assignment, POSITIVE, PLAIN, ret_total);
				sw_setbit(cur_sol->vector, index); // set assignment to 1
			} else {
				update_potentials(con, potentials, index,
				                  con->negative_indices,
				                  con->num_negative_indices,
				                  con->negative_offsets,
				                  cur_sol, next_assignment, NEGATIVE, PLAIN, ret_total);
				sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
			}

            int64_t *sub_ret1 = calloc(con->num_constraints, sizeof(int64_t));
		    int64_t *sub_ret2 = calloc(con->num_constraints, sizeof(int64_t));
			int b1 = look_ahead_correct(index + 1, 0, depth, count_solutions, con, potentials, cur_sol, sub_ret1);
			int b2 = look_ahead_correct(index + 1, 1, depth, count_solutions, con, potentials, cur_sol, sub_ret2);
			free(sub_ret1);
            free(sub_ret2);
//            if (!b1 && !b2) (*count_solutions)++;
			// reset potentials for proper use in sampling algorithm
			if (next_assignment)
				update_potentials(con, potentials, index,
				                  con->positive_indices,
				                  con->num_positive_indices,
				                  con->positive_offsets,
				                  cur_sol, next_assignment, POSITIVE, INVERSE, ret_total);
			else
				update_potentials(con, potentials, index,
				                  con->negative_indices,
				                  con->num_negative_indices,
				                  con->negative_offsets,
				                  cur_sol, next_assignment, NEGATIVE, INVERSE, ret_total);

		}
	}
	sw_clrbit(cur_sol->vector, index); // reset assignment to 0
//    if (bool_) return 1;
	return 0;
}

int64_t min_value(const int64_t *arr, int n) {
	int64_t mini = INT64_MAX;
	for (int i = 0; i < n; i++) {
		mini = (arr[i] < mini) ? arr[i] : mini;
	}
	return mini;
}

int64_t max_value(const int64_t *arr, int n) {
	int64_t mini = 0;
	for (int i = 0; i < n; i++) {
		mini += arr[i];
	}
	return mini;
}


int initial_state_preparation(state_t *new_sol, state_t *cur_sol,
                              new_constraints_t *con,
//                              const unsigned int *positive_indices, const unsigned int *num_positive_indices,
//                              const unsigned int *positive_offsets,
//                              const unsigned int *negative_indices, const unsigned int *num_negative_indices,
//                              const unsigned int *negative_offsets,
                              int depth_look_ahead,
                              int *break_item
) {
	int n = cur_sol->vector.bits;
	int64_t potentials[con->num_constraints];

	// reset constraint rhs to initial values
	memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

	// initialize new solution
	new_sol->tot_profit = cur_sol->tot_profit;
	sw_set_ui_0(new_sol->vector);

	int i;
	int64_t ret_total1[con->num_constraints];
	int64_t ret_total2[con->num_constraints];
    memset(ret_total1, 0, con->num_constraints * sizeof(int64_t));
    memset(ret_total2, 0, con->num_constraints * sizeof(int64_t));
    int updated = 1;
	for (i = 0; i < n; i++) {
//        int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?

		// Initialize new bit to be 0
		sw_clrbit(new_sol->vector, i);
		int new_bit = 0;

		// check, if assignment does not exceed potentials
		// if depth look ahead is 0, it will check only the next assignment
		int count[2] = {0, 0};
		// look ahead to the left side
		look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2);
		// look ahead to the right side
        look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1);

		// If all the constraints ar fulfilled by both assignments, "go to the right"
		if (count[0] > 0 && count[1] > 0) {
			sw_setbit(new_sol->vector, i);
			new_bit = 1;
			*break_item += updated;
		} else{
		    updated = 0;
		}
		// we are forced to go left, when only count[0] leads to a feasible solution
		// count[0] > 0 does not need to be checked, since both == 0 was checked prior
		if (count[0] != 0 && count[1] == 0) {
			// but if left don't lead to feasible solution: break
			sw_clrbit(new_sol->vector, i);
			new_bit = 0;
		}
		// we are forced to go right, when only count[1] leads to feasible solution
		if (count[0] == 0 && count[1] != 0) {
			// but if right don't lead to feasible solution: break
			sw_setbit(new_sol->vector, i);
			new_bit = 1;
		}
		if (new_bit) {
			update_potentials(con, potentials, i,
			                  con->positive_indices,
			                  con->num_positive_indices,
			                  con->positive_offsets, new_sol,
			                  new_bit, POSITIVE, PLAIN, ret_total2);
		} else
			update_potentials(con, potentials, i,
			                  con->negative_indices,
			                  con->num_negative_indices,
			                  con->negative_offsets, new_sol,
			                  new_bit, NEGATIVE, PLAIN, ret_total1);
	}

	cur_sol->tot_profit = 0; // solution might be infeasible
	sw_clear(cur_sol->vector);
	cur_sol->vector = sw_set(new_sol->vector);

	return min_value(potentials, con->num_constraints);
}


int CSearch_opt(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful
) {

	int64_t potentials[con->num_constraints];
	int64_t ret_total1[con->num_constraints];
	int64_t ret_total2[con->num_constraints];
    memset(ret_total1, 0, con->num_constraints * sizeof(int64_t));
    memset(ret_total2, 0, con->num_constraints * sizeof(int64_t));
	for (int l = 0; l < 4 * j * j + 1; l++) {
		// Store which bit from the previous solution is flipped
		int NumChanges = 0;
		int *ChangedBits = calloc(n, sizeof(int));

		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		for (i = 0; i < n; i++) {
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = ((double) (rand() % 123456)) / 123455.;

			// Initialize new bit to be 0
			sw_clrbit(new_sol->vector, i);
			int new_bit = 0;

			// check, if assignment does not exceed potentials
			// if depth look ahead is 0, it will check only the next assignment
			int count[2] = {0, 0};
			// look ahead to the left side
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1);
			// look ahead to the right side
			look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0, &BranchingStats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
			}
			if (count[0] == 0 && count[1] == 0) break;
			// we are forced to go left, when only count[0] leads to a feasible solution
			// count[0] > 0 does not need to be checked, since both == 0 was checked prior
			if (count[1] == 0) {
				// but if left don't lead to feasible solution: break
				sw_clrbit(new_sol->vector, i);
				new_bit = 0;
			}
			// we are forced to go right, when only count[1] leads to feasible solution
			if (count[0] == 0) {
				// but if right don't lead to feasible solution: break
				sw_setbit(new_sol->vector, i);
				new_bit = 1;
			}

			// was a bit flipped?
			if (bit != new_bit) ChangedBits[NumChanges++] = i;

			int all_positive;
			if (new_bit) {
				update_potentials(con, potentials, i,
				                  con->positive_indices,
				                  con->num_positive_indices,
				                  con->positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN, ret_total2);
			} else
				update_potentials(con, potentials, i,
				                  con->negative_indices,
				                  con->num_negative_indices,
				                  con->negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN, ret_total1);
		}
		// if the previous loop broke earlier, determine all bit changes
		for (int mn = i; mn < n; mn++) if (sw_tstbit(cur_sol->vector, i)) ChangedBits[NumChanges++] = mn;
//        printf("%lld %lld\n", potentials[0], potentials[1]);
		int as1 = (i == n);
//		if (i == n) as1 = eval_constraints(con, new_sol, n);
		if (as1) for (int k = 0; k < con->num_constraints; ++k) as1 &= potentials[k] >= 0;

		int NumChangedTerms = 0;
		int *ChangedTerms = calloc(MINSIZE, sizeof(int));
		int64_t val = cur_sol->tot_profit;
		if (as1) val = objective_value(obj, new_sol);
//		if (as1) val = objective_value_improved(obj, new_sol, NumChanges, ChangedBits, ful,&ChangedTerms, &NumChangedTerms);

		if (as1 && cur_sol->tot_profit > val) {
			// If solution is updated, change the array of fulfilled terms
//            for (int term = 0; term < NumChangedTerms; term++) Fulfilled[ChangedTerms[term]] = 1 - Fulfilled[ChangedTerms[term]];
            for (int term = 0; term < NumChangedTerms; term++) sw_flpbit(*ful, ChangedTerms[term]);
			cur_sol->tot_profit = val;
			sw_clear(cur_sol->vector);
			cur_sol->vector = sw_set(new_sol->vector);

			free(ChangedTerms);
			free(ChangedBits);
			return 1;
		}
		free(ChangedTerms);
		free(ChangedBits);
	}
	return 0;
}


int CSearch_opt_sat(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                    new_constraints_t *con, new_constraints_t *obj,
                    int depth_look_ahead, int direction, array_t *ful
) {

	int64_t potentials[con->num_constraints];
	int64_t ret_total1[con->num_constraints];
	int64_t ret_total2[con->num_constraints];
    memset(ret_total1, 0, con->num_constraints * sizeof(int64_t));
    memset(ret_total2, 0, con->num_constraints * sizeof(int64_t));
	for (int l = 0; l < 4 * j * j + 1; l++) {
		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		int both_infeasible = 0;
		for (i = 0; i < n; i++) {
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = ((double) (rand() % 123456)) / 123455.;

			// Initialize new bit to be 0
			sw_clrbit(new_sol->vector, i);
			int new_bit = 0;

			// check, if assignment does not exceed potentials
			// if depth look ahead is 0, it will check only the next assignment
			int count[2] = {0, 0};

            // look ahead to the left side
            look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1);
            // look ahead to the right side
            look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0 || count[0] == 0 && count[1] == 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0, &BranchingStats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
				if (count[0] == 0 && count[1] == 0) both_infeasible = 1;
			}
			// we are forced to go left, when only count[0] leads to a feasible solution
			// count[0] > 0 does not need to be checked, since both == 0 was checked prior
			if (count[0] != 0 && count[1] == 0) {
				// but if left don't lead to feasible solution: break
				sw_clrbit(new_sol->vector, i);
				new_bit = 0;
			}
			// we are forced to go right, when only count[1] leads to feasible solution
			if (count[0] == 0 && count[1] != 0) {
				// but if right don't lead to feasible solution: break
				sw_setbit(new_sol->vector, i);
				new_bit = 1;
			}
			if (new_bit) {
				update_potentials(con, potentials, i,
				                  con->positive_indices,
				                  con->num_positive_indices,
				                  con->positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN, ret_total2);
			} else
				update_potentials(con, potentials, i,
				                  con->negative_indices,
				                  con->num_negative_indices,
				                  con->negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN, ret_total1);
		}
		// if the previous loop broke earlier, determine all bit changes
		int64_t val = min_value(potentials, con->num_constraints);
		int64_t val_max = max_value(potentials, con->num_constraints);

		if ((cur_sol->tot_profit < val && direction == 1) || // maximize, if constraint is violated
		    (cur_sol->tot_profit > val_max && direction == -1 &&
		     val > 0)) { // minimize otherwise, but keep constraints satisfied
			cur_sol->tot_profit = val;
			if (direction == 1 && val > 0) cur_sol->tot_profit = val_max;
			sw_clear(cur_sol->vector);
			cur_sol->vector = sw_set(new_sol->vector);

			return 1;
		}
	}
	return 0;
}


int CSearch_sat(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful
) {

	int64_t potentials[con->num_constraints];
	int64_t ret_total1[con->num_constraints];
	int64_t ret_total2[con->num_constraints];
    memset(ret_total1, 0, con->num_constraints * sizeof(int64_t));
    memset(ret_total2, 0, con->num_constraints * sizeof(int64_t));
	for (int l = 0; l < 4 * j * j + 1; l++) {
		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		for (i = 0; i < n; i++) {
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = ((double) (rand() % 123456)) / 123455.;

			// Initialize new bit to be 0
			sw_clrbit(new_sol->vector, i);
			int new_bit = 0;

			// check, if assignment does not exceed potentials
			// if depth look ahead is 0, it will check only the next assignment
			int count[2] = {0, 0};
			// look ahead to the left side
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1);
			// look ahead to the right side
			look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0, &BranchingStats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
			}
			// we are forced to go left, when only count[0] leads to a feasible solution
			// count[0] > 0 does not need to be checked, since both == 0 was checked prior
			if (count[0] != 0 && count[1] == 0 || count[0] == 0 && count[1] == 0) {
				// but if left don't lead to feasible solution: break
				sw_clrbit(new_sol->vector, i);
				new_bit = 0;
			}
			// we are forced to go right, when only count[1] leads to feasible solution
			if (count[0] == 0 && count[1] != 0) {
				// but if right don't lead to feasible solution: break
				sw_setbit(new_sol->vector, i);
				new_bit = 1;
			}

			if (new_bit) {
				update_potentials(con, potentials, i,
				                  con->positive_indices,
				                  con->num_positive_indices,
				                  con->positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN, ret_total2);
			} else
				update_potentials(con, potentials, i,
				                  con->negative_indices,
				                  con->num_negative_indices,
				                  con->negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN, ret_total1);
		}
		int64_t val = -num_satisfied_constrains(con, new_sol);
		if (cur_sol->tot_profit > val) {
			// If solution is updated, change the array of fulfilled terms
			cur_sol->tot_profit = val;
			sw_clear(cur_sol->vector);
			cur_sol->vector = sw_set(new_sol->vector);

			return 1;
		}
	}
	return 0;
}