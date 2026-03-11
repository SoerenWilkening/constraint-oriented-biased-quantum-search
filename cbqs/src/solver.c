#include "solver.h"
#undef branching_stats  /* Use active_stats pointer for phase-aware branching */
#include "prng.h"

// implementations of classical sampling search and benchmarking =======================================================
static inline int evaluation(new_constraints_t *con, int64_t *potentials, int item,
                             const unsigned int *indices,
                             const unsigned int *rows,
                             const unsigned int *cols,
                             const unsigned int nnz,
                             const unsigned int *num_indices,
                             const unsigned int *offsets, state_t *cur_sol, int negative, int64_t *ret_total) {
	size_t C = con->num_constraints;
	int feasible = 1;
	// check, if assignment does not exceed potentials
	for (size_t cnstr = 0; cnstr < C; cnstr++) {
		int64_t total = 0;
		size_t clause_offset = first_clause_index(con, cnstr);
        int64_t ind = (int64_t)(item * C + cnstr);
        if (con->sparsity == SPARSE) ind = get_index(cols, rows, item, cnstr, nnz, C);

        if (ind != -1) {
            for (uint32_t cls = 0; cls < num_indices[ind]; cls++) {
                uint32_t index = indices[offsets[ind] + cls]; // index of the clause of constraint cnstr
                size_t clause_index = clause_offset + index;
                
                int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
                int is_closed = 1;
                for (uint32_t i = 0; i < con->clause_length[clause_index]; i++) {
                    size_t var = con->variables[variable_index(index, i, clause_offset)];
                    if (var < (size_t)item) assigned &= sw_tstbit(cur_sol->vector, var);
                    if (var > (size_t)item) {
                        is_closed = 0;
                        break;
                    }
                }
                if ((negative == POSITIVE && is_closed) || negative == NEGATIVE)
                    total += labs(con->factors[clause_index]) * assigned;
            }
        }
        ret_total[cnstr] = total;
        if (potentials[cnstr] < total) feasible = 0;
    }
    if (!feasible) return 0;
	return 1;
}

int update_potentials(new_constraints_t *con, int64_t *potentials, int direction, int64_t *ret_total) {
	// careful: destinction between positive and negative coefficients
	// for non-linear clauses with negative coefficients there are two ways, s.t. potential has to be subtracted:
	//  -> consideres item is set to 0 or previous assignments of clause are set to 0
	// for positive coefficients subtraction is only possible if considered item is set to 1 AND all previous assignments
	// are set to 1
	// update potentials has to be called 3 times

	size_t C = con->num_constraints;
	// revert the constraints rhs accordingly
	for (size_t cnstr = 0; cnstr < C; cnstr++) potentials[cnstr] += direction * ret_total[cnstr];
	return 1;
}

/*
 * look_ahead_correct -- Recursively check if a partial variable assignment can lead
 *                       to a feasible solution by exploring future assignments.
 *
 * Algorithm: Starting at variable `index`, tentatively assigns `next_assignment` (0 or 1)
 * and evaluates whether constraint potentials remain non-negative (feasibility check).
 * If feasible and `index < depth`, recurses on the next variable trying both 0 and 1.
 * Each time the recursion reaches `depth` with a feasible assignment, `count_solutions`
 * is incremented.
 *
 * Parameters:
 *   index           -- current variable being assigned
 *   next_assignment -- 0 or 1 to try for this variable
 *   depth           -- how far ahead to look (0 = check only this variable)
 *   count_solutions -- [out] incremented for each feasible completion found
 *   con             -- constraint data with preprocessed indices
 *   potentials      -- remaining capacity for each constraint (modified and restored)
 *   cur_sol         -- current partial solution (bits set/cleared during recursion)
 *   ret_total       -- scratch array for constraint evaluation results
 *
 * Purpose: Prunes the branching tree early by detecting that no feasible completion
 * exists beyond a certain depth, avoiding wasted exploration of infeasible subtrees.
 * The count of feasible completions is used by the sampling algorithm to bias the
 * branching probability toward assignments that have more feasible continuations.
 */
int look_ahead_correct(int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total) {
	// check, if assignment does not exceed potentials
	if (next_assignment) sw_setbit(cur_sol->vector, index); // set assignment to 1
	else sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)

	int bool_;
	if (next_assignment) {
        bool_ = evaluation(con, potentials, index,
                           con->positive_indices,
                           con->pos_rows,
                           con->pos_cols,
                           con->nnz_pos,
                           con->num_positive_indices,
                           con->positive_offsets, cur_sol,
                           POSITIVE, ret_total);
    }
	else {
        bool_ = evaluation(con, potentials, index,
                           con->negative_indices,
                           con->neg_rows,
                           con->neg_cols,
                           con->nnz_neg,
                           con->num_negative_indices,
                           con->negative_offsets, cur_sol,
                           NEGATIVE, ret_total);
    }

	if (bool_) {
		if (index == depth) (*count_solutions)++;
		else {
			if (next_assignment) {
				update_potentials(con, potentials, PLAIN, ret_total);
				sw_setbit(cur_sol->vector, index); // set assignment to 1
			} else {
				update_potentials(con, potentials, PLAIN, ret_total);
				sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
			}

            int64_t *sub_ret1 = calloc(con->num_constraints, sizeof(int64_t));
		    int64_t *sub_ret2 = calloc(con->num_constraints, sizeof(int64_t));
			(void)look_ahead_correct(index + 1, 0, depth, count_solutions, con, potentials, cur_sol, sub_ret1);
			(void)look_ahead_correct(index + 1, 1, depth, count_solutions, con, potentials, cur_sol, sub_ret2);
			free(sub_ret1);
            free(sub_ret2);
			// reset potentials for proper use in sampling algorithm
			
            update_potentials(con, potentials, INVERSE, ret_total);

		}
	}
	sw_clrbit(cur_sol->vector, index); // reset assignment to 0
	return 0;
}

int64_t min_value(const int64_t *arr, size_t n) {
	int64_t mini = INT64_MAX;
	for (size_t i = 0; i < n; i++) {
		mini = (arr[i] < mini) ? arr[i] : mini;
	}
	return mini;
}

int64_t max_value(const int64_t *arr, size_t n) {
	int64_t mini = 0;
	for (size_t i = 0; i < n; i++) {
		mini += arr[i];
	}
	return mini;
}


/*
 * initial_state_preparation -- Construct an initial solution using greedy sampling
 *                              with branching probabilities and look-ahead.
 *
 * Algorithm: Assigns variables left-to-right (index 0 to n-1). For each variable:
 *   1. Evaluate constraint potentials for assignment=0 and assignment=1
 *   2. Run look_ahead_correct() for both assignments to count feasible continuations
 *   3. Combine feasibility counts with branching probability (from BranchingFunction)
 *   4. Choose assignment probabilistically, biased toward more-feasible directions
 *   5. Update constraint potentials and mark the variable as branched
 *
 * If neither assignment is feasible at any point, the break_item is recorded and
 * the remaining variables are assigned without branching.
 *
 * Data flow: potentials[] tracking -> evaluation() -> look_ahead_correct() ->
 *            probabilistic selection -> update_potentials() -> next variable
 *
 * This function runs once on the main thread during model setup (before parallel
 * solve workers start). It populates mod->initial_state with the greedy solution
 * and mod->global_opt with the best solution found.
 *
 * Reads:  mod->initial_state->vector.bits, mod->con->num_constraints,
 *         mod->con->rhs[], mod->depth_look_ahead,
 *         mod->obj (for objective_value)
 * Writes: mod->initial_state (vector, tot_profit, branch, feasible),
 *         mod->break_item, mod->global_opt (vector, tot_profit, feasible)
 *         (All unprotected -- called during single-threaded setup before solve)
 */
int initial_state_preparation(model_t *mod) {

	int n = mod->initial_state->vector.bits;
	size_t C = mod->con->num_constraints;

	int64_t *potentials = malloc(C * sizeof(int64_t));
	int64_t *ret_total1 = malloc(C * sizeof(int64_t));
	int64_t *ret_total2 = malloc(C * sizeof(int64_t));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		return -1;  /* allocation failure */
	}

    // reset constraint rhs to initial values
    memcpy(potentials, mod->con->rhs, C * sizeof(int64_t));

	// initialize new solution
    mod->initial_state->tot_profit = -INT32_MAX;
	sw_set_ui_0(mod->initial_state->vector);

	int i;
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));
    int updated = 1;
	for (i = 0; i < n; i++) {

		// Initialize new bit to be 0

		sw_clrbit(mod->initial_state->vector, i);
		sw_clrbit(mod->initial_state->branch, i);
		int new_bit = 0;

		// check, if assignment does not exceed potentials
		// if depth look ahead is 0, it will check only the next assignment
		int count[2] = {0, 0};
		// look ahead to the left side
		look_ahead_correct(i, 1, min(i + mod->depth_look_ahead, n - 1), &count[1], mod->con, potentials, mod->initial_state, ret_total2);
		// look ahead to the right side
        look_ahead_correct(i, 0, min(i + mod->depth_look_ahead, n - 1), &count[0], mod->con, potentials, mod->initial_state, ret_total1);

		// If all the constraints ar fulfilled by both assignments, "go to the right"
		if (count[0] > 0 && count[1] > 0) {
			sw_setbit(mod->initial_state->vector, i);
			new_bit = 1;
            mod->break_item += updated;
		} else{
		    sw_clrbit(mod->initial_state->vector, i);
		    updated = 0;
		}
		// we are forced to go left, when only count[0] leads to a feasible solution
		// count[0] > 0 does not need to be checked, since both == 0 was checked prior
		if (count[0] != 0 && count[1] == 0) {
			// but if left don't lead to feasible solution: break
			sw_clrbit(mod->initial_state->vector, i);
			new_bit = 0;
		}
		// we are forced to go right, when only count[1] leads to feasible solution
		else if (count[0] == 0 && count[1] != 0) {
			// but if right don't lead to feasible solution: break
			sw_setbit(mod->initial_state->vector, i);
			new_bit = 1;
		}
		if (new_bit) update_potentials(mod->con, potentials, PLAIN, ret_total2);
		else update_potentials(mod->con, potentials, PLAIN, ret_total1);
	}

    mod->initial_state->feasible = eval_constraints(mod->con, mod->initial_state, mod->initial_state->vector.bits);
	mod->initial_state->tot_profit = 0;

	if (mod->initial_state->feasible) {
		mod->initial_state->tot_profit = objective_value(mod->obj, mod->initial_state);
	} else {
		int64_t *remainings = malloc(C * sizeof(int64_t));
		if (remainings == NULL) {
			free(potentials);
			free(ret_total1);
			free(ret_total2);
			return -1;  /* allocation failure */
		}
		for (size_t i = 0; i < C; ++i) remainings[i] = constraint_violation(mod->con, mod->initial_state, i);
        mod->initial_state->tot_profit = 0;
		for (size_t i = 0; i < C; ++i) if (remainings[i] < 0) mod->initial_state->tot_profit -= remainings[i];
		free(remainings);
	}

    mod->global_opt->tot_profit = mod->initial_state->tot_profit;
    mod->global_opt->feasible = mod->initial_state->feasible;
    sw_set_inplace(mod->global_opt->vector, mod->initial_state->vector);

	int64_t result = min_value(potentials, C);
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	return result;
}


int CSearch_opt(solver_ctx_t *ctx, state_t *cur_sol, int j,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful,
                int *samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
	int64_t *potentials = malloc(C * sizeof(int64_t));
	int64_t *ret_total1 = malloc(C * sizeof(int64_t));
	int64_t *ret_total2 = malloc(C * sizeof(int64_t));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		return 0;  /* allocation failure - treat as no improvement found */
	}
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));
    int l;
	for (l = 0; l < 4 * j * j + 1; l++) {
        state_t *new_sol = copy_state(cur_sol);
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);
        
		// Store which bit from the previous solution is flipped
		int NumChanges = 0;
		int *ChangedBits = calloc(n, sizeof(int));

		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		int *var_order = ctx->active_stats->variable_order;
		int k;
		for (k = 0; k < n; k++) {
			i = var_order ? var_order[k] : k;
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = prng_next_double();

			// Initialize new bit to be 0
			sw_clrbit(new_sol->vector, i);
			sw_clrbit(new_sol->branch, i);
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
                sw_setbit(new_sol->branch, i);
				if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
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

				if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
			else update_potentials(con, potentials, PLAIN, ret_total1);
		}
		// if the previous loop broke earlier, determine all bit changes
		for (int mn = k; mn < n; mn++) {
			int vi = var_order ? var_order[mn] : mn;
			if (sw_tstbit(cur_sol->vector, vi)) ChangedBits[NumChanges++] = vi;
		}
		int as1 = (k == n);
		if (as1) for (uint32_t ci = 0; ci < con->num_constraints; ++ci) {
		    if (con->sense[ci] == EQUAL) as1 &= potentials[ci] == 0;
		    else as1 &= potentials[ci] >= 0;
		}

		int64_t val = cur_sol->tot_profit;
		if (as1) val = objective_value(obj, new_sol);
		if (as1 && cur_sol->tot_profit > val) {
			cur_sol->tot_profit = val;
			sw_clear(cur_sol->vector);
			sw_clear(cur_sol->branch);
			cur_sol->vector = sw_set(new_sol->vector);
			cur_sol->branch = sw_set(new_sol->branch);
			cur_sol->feasible = as1;

			free(ChangedBits);
            free_state(new_sol, 1);
            *samples += l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
			return 1;
		}
		free(ChangedBits);
        free_state(new_sol, 1);
	}
	*samples += l;
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	return 0;
}


int CSearch_opt_sat(solver_ctx_t *ctx, state_t *cur_sol, int j,
                    new_constraints_t *con, new_constraints_t *obj,
                    int depth_look_ahead, int direction, array_t *ful,
                    int *samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
	int64_t *potentials = malloc(C * sizeof(int64_t));
	int64_t *ret_total1 = malloc(C * sizeof(int64_t));
	int64_t *ret_total2 = malloc(C * sizeof(int64_t));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		return 0;  /* allocation failure */
	}
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));
    int l;
	for (l = 0; l < 4 * j * j + 1; l++) {
        state_t *new_sol = copy_state(cur_sol);
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);
        
		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		int *var_order = ctx->active_stats->variable_order;
		int k;
		for (k = 0; k < n; k++) {
			i = var_order ? var_order[k] : k;
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = prng_next_double();

			// Initialize new bit to be 0
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
			if ((count[0] > 0 && count[1] > 0) || (count[0] == 0 && count[1] == 0)) {
                sw_setbit(new_sol->branch, i);
				if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
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
			if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
			else update_potentials(con, potentials, PLAIN, ret_total1);
		}
		// if the previous loop broke earlier, determine all bit changes

        // this method is only called, when no feasible solution was found yet:
        // so we minimize either the constraint violation, or compute the objcetive value
        int64_t total_violation = 0;

		for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
			// only sum up violations
			if (con->sense[cnstr] == EQUAL) {
			    // ehen equality, the total violation is the difference from protentials being unequal 0
			    total_violation += potentials[cnstr] != con->rhs[cnstr] ? labs(potentials[cnstr]) : 0;
			}else total_violation -= potentials[cnstr] < 0 ? potentials[cnstr] : 0;
		}
		int feasible = (total_violation == 0);

        if (direction == 1 && feasible){
            // was not feasible before, but now
            total_violation = 0;
            for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
			    // only sum up potentials
			    total_violation += potentials[cnstr]; // all are >= 0
		    }
            sw_clear(cur_sol->vector);
		    cur_sol->vector = sw_set(new_sol->vector);
		    cur_sol->tot_profit = total_violation;
		    cur_sol->feasible = 1;
		    *samples += l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
		    return 1;
        }
        if (direction == -1){
            // other direction, minimize remaining capacity
            total_violation = 0;
		    for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
			    // only sum up potentials
			    total_violation += potentials[cnstr]; // all are >= 0
		    }
        }
        //                                              \/ no feas sol    \/ preserves feasibility
		if ((cur_sol->tot_profit > total_violation) && (direction == 1 || feasible)){ // lower violation was found
		    sw_clear(cur_sol->vector);
		    sw_clear(cur_sol->branch);
		    cur_sol->vector = sw_set(new_sol->vector);
		    cur_sol->branch = sw_set(new_sol->branch);
		    cur_sol->tot_profit = total_violation;
		    cur_sol->feasible = 0;
            free_state(new_sol, 1);
            *samples += l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
            return 1;
        }
        free_state(new_sol, 1);
	}
	*samples += l;
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	return 0;
}


int CSearch_sat(solver_ctx_t *ctx, state_t *cur_sol, int j,
                new_constraints_t *con, new_constraints_t *obj,
                int depth_look_ahead, int direction, array_t *ful,
                int *samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
	int64_t *potentials = malloc(C * sizeof(int64_t));
	int64_t *ret_total1 = malloc(C * sizeof(int64_t));
	int64_t *ret_total2 = malloc(C * sizeof(int64_t));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		return 0;  /* allocation failure */
	}
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));
    int l;
	for (l = 0; l < 4 * j * j + 1; l++) {
        state_t *new_sol = copy_state(cur_sol);
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);
        
		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;
		int *var_order = ctx->active_stats->variable_order;
		int k;
		for (k = 0; k < n; k++) {
			i = var_order ? var_order[k] : k;
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = prng_next_double();

			// Initialize new bit to be 0
			sw_clrbit(new_sol->vector, i);
			sw_clrbit(new_sol->branch, i);
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
                sw_setbit(new_sol->branch, i);
				if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
			}
			// we are forced to go left, when only count[0] leads to a feasible solution
			// count[0] > 0 does not need to be checked, since both == 0 was checked prior
			if ((count[0] != 0 && count[1] == 0) || (count[0] == 0 && count[1] == 0)) {
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

			if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
			else update_potentials(con, potentials, PLAIN, ret_total1);
		}
		int64_t val = -num_satisfied_constrains(con, new_sol);
		if (cur_sol->tot_profit > val) {
			// If solution is updated, change the array of fulfilled terms
			cur_sol->tot_profit = val;
			sw_clear(cur_sol->vector);
			sw_clear(cur_sol->branch);
			cur_sol->vector = sw_set(new_sol->vector);
			cur_sol->branch = sw_set(new_sol->branch);
            
            free_state(new_sol, 1);
            *samples += l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
            return 1;
        }
        free_state(new_sol, 1);
	}
	*samples += l;
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	return 0;
}














double CSearch_opt_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj,
    double error, int initial_samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
    int64_t *potentials = malloc(C * sizeof(int64_t));
    int64_t *ret_total1 = malloc(C * sizeof(int64_t));
    int64_t *ret_total2 = malloc(C * sizeof(int64_t));
    if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
        free(potentials);
        free(ret_total1);
        free(ret_total2);
        return 0.0;  /* allocation failure */
    }
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));

    int counter = 1;
    double estimate = 1. / initial_samples;
    double prev = estimate;
    int samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));
    for (int l = initial_samples; l < samples; l++) {
        state_t *new_sol = init_state(0, NULL, cur_sol->vector.bits);
        
        // reset constraint rhs to initial values
        memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));
        
        // initialize new solution
        new_sol->tot_profit = cur_sol->tot_profit;
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);

        int i;
        int *var_order = ctx->active_stats->variable_order;
        int k;
        for (k = 0; k < n; k++) {
            i = var_order ? var_order[k] : k;
            int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
            double random_num = prng_next_double();

            // Initialize new bit to be 0
            int new_bit = 0;

            // check, if assignment does not exceed potentials
            // if depth look ahead is 0, it will check only the next assignment
            int count[2] = {0, 0};
            // look ahead to the left side
            look_ahead_correct(i, 0, min(i + 0, n - 1), &count[0], con, potentials, new_sol, ret_total1);
            // look ahead to the right side
            look_ahead_correct(i, 1, min(i + 0, n - 1), &count[1], con, potentials, new_sol, ret_total2);

            // only counts needs to be checked, since they also include bool_plus and bool_minus
            // If all the constraints ar fulfilled by both assignments, "branch"
            if (count[0] > 0 && count[1] > 0) {
                if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
                    sw_setbit(new_sol->vector, i);
                    new_bit = 1;
                } else { sw_clrbit(new_sol->vector, i); }

            }else sw_clrbit(new_sol->branch, i);
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

            if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
            else update_potentials(con, potentials, PLAIN, ret_total1);
        }
        // if the previous loop broke earlier, determine all bit changes
        int as1 = (k == n);
        if (as1)
            for (uint32_t k = 0; k < con->num_constraints; ++k) {
                if (con->sense[k] == EQUAL) as1 &= potentials[k] == 0;
                else as1 &= potentials[k] >= 0;
            }
        
        int64_t val = cur_sol->tot_profit;
        if (as1) val = objective_value(obj, new_sol);
        
        if (as1 && cur_sol->tot_profit > val) {
            // put good state into list of good states
            // If solution is updated, change the array of fulfilled terms
            counter++;
        }
        free_state(new_sol, 1);
        estimate = ((double) counter) / (l + 1);
        if (estimate > 0) samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));
        if ((l > 10000) && (fabs(prev - estimate) < estimate * 0.01)) break;
        prev = estimate;
    }

    free(potentials);
    free(ret_total1);
    free(ret_total2);
    return estimate;
}

double CSearch_opt_sat_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, new_constraints_t *obj,
    double error, int direction, int initial_samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
	int64_t *potentials = malloc(C * sizeof(int64_t));
	int64_t *ret_total1 = malloc(C * sizeof(int64_t));
	int64_t *ret_total2 = malloc(C * sizeof(int64_t));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		return 0.0;  /* allocation failure */
	}
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));

    int counter = 1;
    double estimate = 1. / initial_samples;
    double prev = estimate;
    int samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));

	for (int l = initial_samples; l < samples; l++) {
        state_t *new_sol = init_state(0, NULL, cur_sol->vector.bits);
		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;
		sw_set_ui_0(new_sol->vector);

		int i;

        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);

		int *var_order = ctx->active_stats->variable_order;
		int k;
		for (k = 0; k < n; k++) {
			i = var_order ? var_order[k] : k;
			int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
			double random_num = prng_next_double();

			// Initialize new bit to be 0
			int new_bit = 0;

			// check, if assignment does not exceed potentials
			// if depth look ahead is 0, it will check only the next assignment
			int count[2] = {0, 0};

            // look ahead to the left side
            look_ahead_correct(i, 0, min(i, n - 1), &count[0], con, potentials, new_sol, ret_total1);
            // look ahead to the right side
            look_ahead_correct(i, 1, min(i, n - 1), &count[1], con, potentials, new_sol, ret_total2);

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if ((count[0] > 0 && count[1] > 0) || (count[0] == 0 && count[1] == 0)) {
                sw_setbit(new_sol->branch, i);
				if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
					sw_setbit(new_sol->vector, i);
					new_bit = 1;
				} else { sw_clrbit(new_sol->vector, i); }
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
			if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
			else update_potentials(con, potentials, PLAIN, ret_total1);
		}
        // this method is only called, when no feasible solution was found yet:
        // so we minimize either the constraint violation, or compute the objcetive value
        int64_t total_violation = 0;

		for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
			// only sum up violations
			if (con->sense[cnstr] == EQUAL) {
			    // ehen equality, the total violation is the difference from protentials being unequal 0
			    total_violation += potentials[cnstr] != con->rhs[cnstr] ? labs(potentials[cnstr]) : 0;
			}else total_violation -= potentials[cnstr] < 0 ? potentials[cnstr] : 0;
		}
		int feasible = (total_violation == 0);

        if (direction == 1 && feasible){
            // was not feasible before, but now
            counter++;
        }
        if (direction == -1){
            // other direction, minimize remaining capacity
            total_violation = 0;
		    for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
			    // only sum up potentials
			    total_violation += potentials[cnstr]; // all are >= 0
		    }
        }
        //                                              \/ no feas sol    \/ preserves feasibility
		if ((cur_sol->tot_profit > total_violation) && (direction == 1 || feasible)){ // lower violation was found
            // good state
            counter++;
		}
        estimate = ((double) counter) / (l + 1.);
        if (estimate > 0) samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));
        if ((l > 10000) && (fabs(prev - estimate) < estimate * 0.05)) break;
        prev = estimate;
        free_state(new_sol, 1);
	}
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	return estimate;
}


double CSearch_sat_monte_carlo_sampler(
    solver_ctx_t *ctx, state_t *cur_sol, new_constraints_t *con, double error, int initial_samples
) {
    int n = cur_sol->vector.bits;
	size_t C = con->num_constraints;
    int64_t *potentials = malloc(C * sizeof(int64_t));
    int64_t *ret_total1 = malloc(C * sizeof(int64_t));
    int64_t *ret_total2 = malloc(C * sizeof(int64_t));
    if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
        free(potentials);
        free(ret_total1);
        free(ret_total2);
        return 0.0;  /* allocation failure */
    }
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));

    int counter = 1;
    double estimate = 1. / initial_samples;
    int samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));

    for (int l = initial_samples; l < samples; l++) {

        state_t *new_sol = init_state(0, NULL, cur_sol->vector.bits);
        
        // reset constraint rhs to initial values
        memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));
        
        // initialize new solution
        new_sol->tot_profit = cur_sol->tot_profit;
        
        int i;
        int *var_order = ctx->active_stats->variable_order;
        int k;
        for (k = 0; k < n; k++) {
            i = var_order ? var_order[k] : k;
            int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
            double random_num = prng_next_double();

            int new_bit = 0;

            // check, if assignment does not exceed potentials
            // if depth look ahead is 0, it will check only the next assignment
            int count[2] = {0, 0};
            // look ahead to the left side
            look_ahead_correct(i, 0, min(i, n - 1), &count[0], con, potentials, new_sol, ret_total1);
            // look ahead to the right side
            look_ahead_correct(i, 1, min(i, n - 1), &count[1], con, potentials, new_sol, ret_total2);

            // only counts needs to be checked, since they also include bool_plus and bool_minus
            // If all the constraints ar fulfilled by both assignments, "branch"
            if (count[0] > 0 && count[1] > 0) {
                sw_setbit(new_sol->branch, i);
                if (random_num > BranchingFunction(i, bit, 0, 0, ctx->active_stats)) {
                    sw_setbit(new_sol->vector, i);
                    new_bit = 1;
                } else { sw_clrbit(new_sol->vector, i); }
            }
            // we are forced to go left, when only count[0] leads to a feasible solution
            // count[0] > 0 does not need to be checked, since both == 0 was checked prior
            if ((count[0] != 0 && count[1] == 0) || (count[0] == 0 && count[1] == 0)) {
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

            if (new_bit) update_potentials(con, potentials, PLAIN, ret_total2);
            else update_potentials(con, potentials, PLAIN, ret_total1);
        }
        int64_t val = -num_satisfied_constrains(con, new_sol);
        if (cur_sol->tot_profit > val) {
            // If solution is updated, change the array of fulfilled terms
            counter++;
        }
        estimate = ((double) counter) / (l + 1);
        if (estimate > 0) samples = (int) ((1. - estimate) / (estimate * pow(error, 2)));
        free_state(new_sol, 1);
    }
    free(potentials);
    free(ret_total1);
    free(ret_total2);
    return estimate;
}