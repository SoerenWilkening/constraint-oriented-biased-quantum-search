#include "solver.h"

// implementations of classical sampling search and benchmarking =======================================================
static inline int evaluation(new_constraints_t *con, int64_t *potentials, int item,
                             const unsigned int *indices,
                             const unsigned int *num_indices,
                             const unsigned int *offsets, state_t *cur_sol, int negative) {
	size_t C = con->num_constraints;
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
				if (var < item) assigned *= sw_tstbit(cur_sol->vector, var);
				if (var > item) is_closed = 0;
			}
			if (negative == POSITIVE && is_closed || negative == NEGATIVE)
				total += labs(con->factors[clause_index]) * assigned;
		}
		if (potentials[cnstr] < total) return 0;
	}
	return 1;
}

static inline int update_potentials(new_constraints_t *con, int64_t *potentials, int item,
                                    const unsigned int *indices,
                                    const unsigned int *num_indices,
                                    const unsigned int *offsets, state_t *cur_sol,
                                    int bit, int negative, int direction) {
	// careful: destinction between positive and negative coefficients
	// for non-linear clauses with negative coefficients there are two ways, s.t. potential has to be subtracted:
	//  -> consideres item is set to 0 or previous assignments of clause are set to 0
	// for positive coefficients subtraction is only possible if considered item is set to 1 AND all previous assignments
	// are set to 1
	// update potentials has to be called 3 times

	size_t C = con->num_constraints;
	// revert the constraints rhs accordingly
	for (int cnstr = 0; cnstr < C; cnstr++) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++) {
			unsigned int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
			size_t clause_index = clause_offset + index;

			// only if all previous items are assigned to 1, adjust rhs
			int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
			int is_closed = 1; // check, if there are unassigned variables within the clause
			for (int i = 0; i < con->clause_length[clause_index]; i++) {
				size_t var = con->variables[variable_index(index, i, clause_offset)];
				if (var < item) assigned *= sw_tstbit(cur_sol->vector, var);
				if (var > item) is_closed = 0;
			}
			if (negative == POSITIVE && is_closed || negative == NEGATIVE)
				potentials[cnstr] += direction * labs(con->factors[clause_index]) * assigned;
		}
	}
	return 1;
}

// look ahead to evaluate all possible solutions from certain position up to certain depth
//int look_ahead_correct( int index, int next_assignment, int depth, int *count_solutions, int64_t *potentials,
//                int **S_plus, int64_t **S_plus_value, int *num_plus,
//                int **S_minus, int64_t **S_minus_value, int *num_minus){
int look_ahead_correct(int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       const unsigned int *positive_indices, const unsigned int *num_positive_indices,
                       const unsigned int *positive_offsets,
                       const unsigned int *negative_indices, const unsigned int *num_negative_indices,
                       const unsigned int *negative_offsets,
                       state_t *cur_sol) {
	// check, if assignment does not exceed potentials
//    if (next_assignment) sw_setbit(cur_sol->vector, index); // set assignment to 1
//    else sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)

	int bool_;
	if (next_assignment) sw_setbit(cur_sol->vector, index); // set assignment to 1
	else sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)

	if (next_assignment)
		bool_ = evaluation(con, potentials, index, positive_indices, num_positive_indices, positive_offsets, cur_sol,
		                   POSITIVE);
	else
		bool_ = evaluation(con, potentials, index, negative_indices, num_negative_indices, negative_offsets, cur_sol,
		                   NEGATIVE);

	if (bool_) {
		if (index == depth) (*count_solutions)++;
		else {
			if (next_assignment) {
				update_potentials(con, potentials, index, positive_indices, num_positive_indices, positive_offsets,
				                  cur_sol, next_assignment, POSITIVE, PLAIN);
				sw_setbit(cur_sol->vector, index); // set assignment to 1
			} else {
				update_potentials(con, potentials, index, negative_indices, num_negative_indices, negative_offsets,
				                  cur_sol, next_assignment, NEGATIVE, PLAIN);
				sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
			}

			int b1 = look_ahead_correct(index + 1, 0, depth, count_solutions, con, potentials, positive_indices,
			                            num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                            negative_offsets, cur_sol);
			int b2 = look_ahead_correct(index + 1, 1, depth, count_solutions, con, potentials, positive_indices,
			                            num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                            negative_offsets, cur_sol);
//            if (!b1 && !b2) (*count_solutions)++;
			// reset potentials for proper use in sampling algorithm
			if (next_assignment)
				update_potentials(con, potentials, index, positive_indices, num_positive_indices, positive_offsets,
				                  cur_sol, next_assignment, POSITIVE, INVERSE);
			else
				update_potentials(con, potentials, index, negative_indices, num_negative_indices, negative_offsets,
				                  cur_sol, next_assignment, NEGATIVE, INVERSE);
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

int initial_state_preparation(state_t *new_sol, state_t *cur_sol,
                              new_constraints_t *con,
                              const unsigned int *positive_indices, const unsigned int *num_positive_indices,
                              const unsigned int *positive_offsets,
                              const unsigned int *negative_indices, const unsigned int *num_negative_indices,
                              const unsigned int *negative_offsets,
                              int depth_look_ahead
) {
	int n = cur_sol->vector.bits;
	int64_t potentials[con->num_constraints];

	// reset constraint rhs to initial values
	memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

	// initialize new solution
	new_sol->tot_profit = cur_sol->tot_profit;
	sw_set_ui_0(new_sol->vector);

	int i;
	for (i = 0; i < n; i++) {
//        int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?

		// Initialize new bit to be 0
		sw_clrbit(new_sol->vector, i);
		int new_bit = 0;

		// check, if assignment does not exceed potentials
		// if depth look ahead is 0, it will check only the next assignment
		int count[2] = {0, 0};
		// look ahead to the left side
		look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices,
		                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
		                   negative_offsets, new_sol);
		// look ahead to the right side
		if (count[1] != 0)
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);

		// If all the constraints ar fulfilled by both assignments, "go to the right"
		if (count[0] > 0 && count[1] > 0) {
			sw_setbit(new_sol->vector, i);
			new_bit = 1;
		}
		double random_num = ((double) (rand() % 123456)) / 123455.;
//		if (count[0] == 0 && count[1] == 0) {
//            if (random_num > 0.05) {
//                sw_setbit(new_sol->vector, i);
//                new_bit = 1;
//            } else { sw_clrbit(new_sol->vector, i); }
//        }
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
		int all_positive;
		if (new_bit) {
			update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol,
			                  new_bit, POSITIVE, PLAIN);
		} else
			update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol,
			                  new_bit, NEGATIVE, PLAIN);
//        printf("%d %lld %lld\n", new_bit, potentials[0], potentials[1]);
	}

	cur_sol->tot_profit = 0; // solution might be infeasible
	sw_clear(cur_sol->vector);
	cur_sol->vector = sw_set(new_sol->vector);

	return min_value(potentials, con->num_constraints);
}


int CSearch_opt(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                const unsigned int *positive_indices, const unsigned int *num_positive_indices,
                const unsigned int *positive_offsets,
                const unsigned int *negative_indices, const unsigned int *num_negative_indices,
                const unsigned int *negative_offsets,
                int **Indices, int *NumIndices, int *Fulfilled,
                int depth_look_ahead, int direction
) {

	int64_t potentials[con->num_constraints];
	for (int l = 0; l < 4 * j * j; l++) {
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
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);
			// look ahead to the right side
			look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
			}
			if(count[0] == 0 && count[1] == 0) break;
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
				update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN);
			} else
				update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN);
		}
		// if the previous loop broke earlier, determine all bit changes
		for (int mn = i; mn < n; mn++) ChangedBits[NumChanges++] = mn;
//        printf("%lld %lld\n", potentials[0], potentials[1]);
		int as1 = eval_constraints(con, new_sol, n);

		int NumChangedTerms = 0;
		int *ChangedTerms = calloc(NTerms, sizeof(int));
		int64_t val = objective_value(obj, new_sol);

		if (as1 && cur_sol->tot_profit > val) {
			// If solution is updated, change the array of fulfilled terms
//            for (int term = 0; term < NumChangedTerms; term++) Fulfilled[ChangedTerms[term]] = 1 - Fulfilled[ChangedTerms[term]];
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
                    const unsigned int *positive_indices, const unsigned int *num_positive_indices,
                    const unsigned int *positive_offsets,
                    const unsigned int *negative_indices, const unsigned int *num_negative_indices,
                    const unsigned int *negative_offsets,
                    int **Indices, int *NumIndices, int *Fulfilled,
                    int depth_look_ahead, int direction
) {

	int64_t potentials[con->num_constraints];
	for (int l = 0; l < 4 * j * j; l++) {
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
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);
			// look ahead to the right side
			look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
			}
		    if (count[0] == 0 && count[1] == 0) {
                if (random_num > 0.9) {
                    sw_setbit(new_sol->vector, i);
                    new_bit = 1;
                } else { sw_clrbit(new_sol->vector, i); }
//                sw_setbit(new_sol->vector, i);
//				new_bit = 0;
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
				update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN);
			} else
				update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN);
		}
		// if the previous loop broke earlier, determine all bit changes
//		int as1 = eval_constraints(con, new_sol, n);
		int64_t val = min_value(potentials, con->num_constraints);

		if (direction * cur_sol->tot_profit <  direction * val && (direction == 1 || direction == -1 && val > 0)) {
//			printf("%lld %lld %d\n", potentials[0], potentials[1], eval_constraints(con, new_sol, n));
			// If solution is updated, change the array of fulfilled terms
			cur_sol->tot_profit = val;
			sw_clear(cur_sol->vector);
			cur_sol->vector = sw_set(new_sol->vector);

			return 1;
		}
	}
	return 0;
}


int CSearch_sat(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
                new_constraints_t *con, new_constraints_t *obj,
                const unsigned int *positive_indices, const unsigned int *num_positive_indices,
                const unsigned int *positive_offsets,
                const unsigned int *negative_indices, const unsigned int *num_negative_indices,
                const unsigned int *negative_offsets,
                int **Indices, int *NumIndices, int *Fulfilled,
                int depth_look_ahead, int direction
) {

	int64_t potentials[con->num_constraints];
	for (int l = 0; l < 4 * j * j; l++) {
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
			fflush(stdout);
			look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);
			// look ahead to the right side
			look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices,
			                   num_positive_indices, positive_offsets, negative_indices, num_negative_indices,
			                   negative_offsets, new_sol);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
				if (random_num > BranchingFunction(i, bit, 0, 0)) {
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
				update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol,
				                  new_bit, POSITIVE, PLAIN);
			} else
				update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol,
				                  new_bit, NEGATIVE, PLAIN);
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