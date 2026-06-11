#include "solver.h"
#undef branching_stats  /* Use active_stats pointer for phase-aware branching */
#include "prng.h"
#include "incr_eval.h"  /* bd 0o8.2 (exact win A): incremental depth-0 marginals */

// implementations of classical sampling search and benchmarking =======================================================
/*
 * evaluation -- charge the clauses decided by assigning `item`, against the
 * remaining constraint potentials.
 *
 * bd h8d: clause-closure is keyed on the TRAVERSAL ORDER, not the natural
 * variable index. `rank` is the inverse permutation of the traversal order
 * (rank[var] = position at which `var` is assigned); rank == NULL means the
 * traversal is natural (identity), where position order == index order and
 * the original `var < item` / `var > item` tests are exact. A clause member
 * is "already assigned" iff it comes BEFORE `item` in traversal order:
 *   - POSITIVE arm (item := 1): a clause counts against the potential only
 *     when `item` is its LAST member in traversal order (is_closed) and all
 *     earlier members are 1.
 *   - NEGATIVE arm (item := 0): a pre-charged negative clause is refunded at
 *     the FIRST zero in traversal order, i.e. when every earlier member is 1
 *     (`assigned`); is_closed is irrelevant.
 * The rank path must scan the WHOLE clause: clause members are stored in
 * construction order (ascending for every model built through the Python
 * path, but NOT rank-sorted), so a traversal-earlier member may appear after
 * a traversal-later one and an early `break` would mis-compute `assigned`
 * for the NEGATIVE arm. The natural path keeps the original early-break
 * unchanged (bit-for-bit with the pre-h8d code).
 */
static inline int evaluation(new_constraints_t *con, int64_t *potentials, int item,
                             const unsigned int *indices,
                             const unsigned int *rows,
                             const unsigned int *cols,
                             const unsigned int nnz,
                             const unsigned int *num_indices,
                             const unsigned int *offsets, state_t *cur_sol, int negative,
                             int64_t *ret_total, const int *rank) {
	size_t C = con->num_constraints;
	int feasible = 1;
	const int rank_item = (rank != NULL) ? rank[item] : 0;
	const size_t nbits = (size_t)cur_sol->vector.bits;
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
                    if (rank == NULL) {
                        /* natural traversal: original closure test, bit-for-bit */
                        if (var < (size_t)item) assigned &= sw_tstbit(cur_sol->vector, var);
                        if (var > (size_t)item) {
                            is_closed = 0;
                            break;
                        }
                    } else {
                        /* reordered traversal: closure keyed on rank (bd h8d) */
                        if (var == (size_t)item) continue;
                        if (var < nbits && rank[var] < rank_item) {
                            assigned &= sw_tstbit(cur_sol->vector, var);
                        } else {
                            is_closed = 0;
                            /* POSITIVE charge is dead once unclosed; NEGATIVE
                             * still needs `assigned` over ALL earlier members */
                            if (negative == POSITIVE) break;
                        }
                    }
                }
                if ((negative == POSITIVE && is_closed) || negative == NEGATIVE)
                    total += llabs(con->factors[clause_index]) * assigned;
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
 * Algorithm: Starting at traversal POSITION `pos`, tentatively assigns
 * `next_assignment` (0 or 1) to the variable visited at that position and
 * evaluates whether constraint potentials remain non-negative (feasibility
 * check). If feasible and `pos < depth_pos`, recurses on the NEXT POSITION in
 * traversal order trying both 0 and 1. Each time the recursion reaches
 * `depth_pos` with a feasible assignment, `count_solutions` is incremented.
 *
 * bd h8d: positions, not natural indices. With a non-identity `order` the old
 * natural-successor recursion (index+1) walked variables that were already
 * assigned (corrupting their bits via the exit reset) and skipped the actual
 * upcoming ones. With order == NULL position == index and the behavior is
 * identical to the original.
 *
 * Parameters:
 *   pos             -- traversal position being assigned (variable = order[pos])
 *   next_assignment -- 0 or 1 to try for this variable
 *   depth_pos       -- position to look ahead to (== pos: check only this one)
 *   count_solutions -- [out] incremented for each feasible completion found
 *   con             -- constraint data with preprocessed indices
 *   potentials      -- remaining capacity for each constraint (modified and restored)
 *   cur_sol         -- current partial solution (bits set/cleared during recursion)
 *   ret_total       -- scratch array for constraint evaluation results
 *   order           -- traversal order (order[k] = variable; NULL = identity)
 *   rank            -- inverse of `order` (NULL = natural-equivalent traversal);
 *                      forwarded to evaluation() for closure consistency
 *
 * Purpose: Prunes the branching tree early by detecting that no feasible completion
 * exists beyond a certain depth, avoiding wasted exploration of infeasible subtrees.
 * The count of feasible completions is used by the sampling algorithm to bias the
 * branching probability toward assignments that have more feasible continuations.
 */
int look_ahead_correct(int pos, int next_assignment, int depth_pos, int *count_solutions, new_constraints_t *con,
                       int64_t *potentials,
                       state_t *cur_sol, int64_t *ret_total, const int *order, const int *rank) {
	const int index = (order != NULL) ? order[pos] : pos;
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
                           POSITIVE, ret_total, rank);
    }
	else {
        bool_ = evaluation(con, potentials, index,
                           con->negative_indices,
                           con->neg_rows,
                           con->neg_cols,
                           con->nnz_neg,
                           con->num_negative_indices,
                           con->negative_offsets, cur_sol,
                           NEGATIVE, ret_total, rank);
    }

	if (bool_) {
		if (pos == depth_pos) (*count_solutions)++;
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
			(void)look_ahead_correct(pos + 1, 0, depth_pos, count_solutions, con, potentials, cur_sol, sub_ret1, order, rank);
			(void)look_ahead_correct(pos + 1, 1, depth_pos, count_solutions, con, potentials, cur_sol, sub_ret2, order, rank);
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
		// look ahead to the left side (natural traversal: no order/rank)
		look_ahead_correct(i, 1, imin(i + mod->depth_look_ahead, n - 1), &count[1], mod->con, potentials, mod->initial_state, ret_total2, NULL, NULL);
		// look ahead to the right side
        look_ahead_correct(i, 0, imin(i + mod->depth_look_ahead, n - 1), &count[0], mod->con, potentials, mod->initial_state, ret_total1, NULL, NULL);

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


/*
 * opt_sample_count -- classical sample budget for one Grover round of j iterations.
 *
 * The faithful classical simulation of a Grover round draws 4j^2+1 candidate
 * states and returns the first improver, so its success probability is
 * 1-(1-p)^(4j^2+1) where p is the single-candidate improvement probability.
 * This is the O(n*j^2) classical wall-time that makes large-n (large-j) solves
 * intractable (bd 0o8): with j_max ~ n^2/32 a single stuck round is ~n^5.
 *
 * When ctx->opt_sample_cap > 0 the count is clamped to `cap`, bounding a round
 * at O(n*cap) instead of O(n*j^2). This does NOT touch the oracle accounting:
 * the 2j+1 charge is applied in ctg BEFORE search_function (SearchLib.c), so j,
 * the cap-j clamp, and ctx->oracle_count are all unchanged (CLAUDE.md §1.2).
 * The only effect is the per-round classical success probability for rare
 * improvers (p < ~1/cap): capping treats them as non-improving, an APPROXIMATE
 * sampler (the bd 0o8 word) whose deviation is measured by the success-law test
 * and tunable via `cap`. cap==0 reproduces the exact unbounded rejection sim.
 *
 * Computed in int64: the legacy `4 * j * j + 1` with int j is signed-overflow
 * UB for j > ~23170 (reachable at n >= ~860), so this also fixes a latent bug.
 * For j <= 23170 (every committed test/baseline) the value is identical to the
 * legacy int computation, so cap==0 stays bit-for-bit faithful (§8).
 */
static inline int64_t opt_sample_count(const solver_ctx_t *ctx, int j) {
	int64_t L = 4LL * (int64_t) j * (int64_t) j + 1;
	int64_t cap = ctx->opt_sample_cap;
	if (cap > 0 && L > cap) return cap;
	return L;
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
	int *ChangedBits = malloc(n * sizeof(int));
	if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL || ChangedBits == NULL) {
		free(potentials);
		free(ret_total1);
		free(ret_total2);
		free(ChangedBits);
		return 0;  /* allocation failure - treat as no improvement found */
	}

	/* Pre-allocate reusable sample state */
	state_t *new_sol = init_state(0, NULL, n);
	if (new_sol == NULL) {
		free(potentials); free(ret_total1); free(ret_total2); free(ChangedBits);
		return 0;
	}

    int64_t l;
	int64_t Leff = opt_sample_count(ctx, j);  /* bd 0o8: cap O(n*j^2) sim work */
	int *var_order = ctx->active_stats->variable_order;
	const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
	/* bd 0o8.2 (exact win A): at depth 0 the two per-variable look_ahead_correct
	 * re-scans are replaced by O(C) incremental marginal reads; incr_create returns
	 * NULL for k-ary (clause length > 2) models, which fall back to the dense path.
	 * CBQS_NO_INCR=1 forces the dense path (kill-switch / equivalence A-B; cached once). */
	static int incr_disabled = -1;
	if (incr_disabled < 0) incr_disabled = getenv("CBQS_NO_INCR") ? 1 : 0;
	incr_state_t *st = (depth_look_ahead == 0 && !incr_disabled) ? incr_create(con, n, var_order, var_rank) : NULL;
	for (l = 0; l < Leff; l++) {
		if (st) incr_reset(st);
		// Reset reusable state instead of alloc/free
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);

		// Store which bit from the previous solution is flipped
		int NumChanges = 0;
		// M0g (bd 8an.1.7): count both-feasible "free" decisions for f(n).
		int NumFree = 0;

		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, C * sizeof(int64_t));
        memset(ret_total1, 0, C * sizeof(int64_t));
        memset(ret_total2, 0, C * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;

		int i;
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
			if (st) {
				/* bd 0o8.2: O(C) incremental reads == the two dense look-aheads.
				 * POS arm -> ret_total2/count[1], NEG arm -> ret_total1/count[0]. */
				incr_marginal(st, i, potentials, ret_total2, &count[1], ret_total1, &count[0]);
			} else {
				// look ahead to the left side (position space, bd h8d)
				look_ahead_correct(k, 0, imin(k + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
				// look ahead to the right side
				look_ahead_correct(k, 1, imin(k + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);
			}

			/* M2a (bd 8an.3.1): classify this decision for the per-phase
			 * touch fraction — pure counters, no behavior change. The
			 * both-feasible "free" class accumulates via NumFree (M0g
			 * opt_free_sum), flushed per candidate below. */
			ctx->opt_decisions++;
			if (count[0] == 0 && count[1] == 0)      ctx->opt_bothinf++;
			else if (count[0] == 0 || count[1] == 0) ctx->opt_forced++;

			// only counts needs to be checked, since they also include bool_plus and bool_minus
			// If all the constraints ar fulfilled by both assignments, "branch"
			if (count[0] > 0 && count[1] > 0) {
                sw_setbit(new_sol->branch, i);
				NumFree++;  // M0g (bd 8an.1.7): bias-decided "free" variable for f(n)
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

			// bd 0o8.2: fold this variable's finalized bit into the incremental accumulators
			if (st) incr_commit(st, i, new_bit);

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
		// M0g (bd 8an.1.7, NORTHSTAR §9): record this candidate's realized
		// Hamming radius (NumChanges) and free-decision count (NumFree) into the
		// per-worker, race-free diagnostics. Runs for EVERY candidate (before the
		// accept/return below) so the distribution is unbiased by acceptance.
		ctx->opt_candidates += 1;
		ctx->opt_flip_sum   += (uint64_t) NumChanges;
		ctx->opt_flip_sumsq += (uint64_t) NumChanges * (uint64_t) NumChanges;
		ctx->opt_free_sum   += (uint64_t) NumFree;
		int as1 = (k == n);
		if (as1) for (uint32_t ci = 0; ci < con->num_constraints; ++ci) {
		    if (con->sense[ci] == EQUAL) as1 &= potentials[ci] == 0;
		    else as1 &= potentials[ci] >= 0;
		}

		int64_t val = cur_sol->tot_profit;
		if (as1) val = objective_value_incremental(obj, cur_sol, new_sol,
		                                          cur_sol->tot_profit,
		                                          ChangedBits, NumChanges);
		if (as1 && cur_sol->tot_profit > val) {
			cur_sol->tot_profit = val;
			sw_set_inplace(cur_sol->vector, new_sol->vector);
			sw_set_inplace(cur_sol->branch, new_sol->branch);
			cur_sol->feasible = as1;

            free_state(new_sol, 1);
            free(ChangedBits);
            *samples += (int) l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
			if (st) incr_free(st);
			return 1;
		}
	}
	*samples += (int) l;
	free_state(new_sol, 1);
	free(ChangedBits);
	free(potentials);
	free(ret_total1);
	free(ret_total2);
	if (st) incr_free(st);
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

	/* Pre-allocate reusable sample state */
	state_t *new_sol = init_state(0, NULL, n);
	if (new_sol == NULL) {
		free(potentials); free(ret_total1); free(ret_total2);
		return 0;
	}

    int64_t l;
	int64_t Leff = opt_sample_count(ctx, j);  /* bd 0o8: cap O(n*j^2) sim work */
	int *var_order = ctx->active_stats->variable_order;
	const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
	for (l = 0; l < Leff; l++) {
		// Reset reusable state
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);

		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, C * sizeof(int64_t));
        memset(ret_total1, 0, C * sizeof(int64_t));
        memset(ret_total2, 0, C * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;

		int i;
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

            // look ahead to the left side (position space, bd h8d)
            look_ahead_correct(k, 0, imin(k + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
            // look ahead to the right side
            look_ahead_correct(k, 1, imin(k + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);

			/* M2a (bd 8an.3.1): classify this decision — pure counters, no
			 * behavior change. NOTE: in opt_sat the both-infeasible class is
			 * ALSO bias-consulted (the branch below), unlike sat/opt. */
			ctx->optsat_decisions++;
			if (count[0] > 0 && count[1] > 0)        ctx->optsat_free++;
			else if (count[0] == 0 && count[1] == 0) ctx->optsat_bothinf++;
			else                                     ctx->optsat_forced++;

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
			    total_violation += potentials[cnstr] != con->rhs[cnstr] ? llabs(potentials[cnstr]) : 0;
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
            sw_set_inplace(cur_sol->vector, new_sol->vector);
		    cur_sol->tot_profit = total_violation;
		    cur_sol->feasible = 1;
		    *samples += (int) l;
		    free_state(new_sol, 1);
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
		    sw_set_inplace(cur_sol->vector, new_sol->vector);
		    sw_set_inplace(cur_sol->branch, new_sol->branch);
		    cur_sol->tot_profit = total_violation;
		    cur_sol->feasible = 0;
            free_state(new_sol, 1);
            *samples += (int) l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
            return 1;
        }
	}
	*samples += (int) l;
	free_state(new_sol, 1);
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

	/* Pre-allocate reusable sample state */
	state_t *new_sol = init_state(0, NULL, n);
	if (new_sol == NULL) {
		free(potentials); free(ret_total1); free(ret_total2);
		return 0;
	}

    int64_t l;
	int64_t Leff = opt_sample_count(ctx, j);  /* bd 0o8: cap O(n*j^2) sim work */
	int *var_order = ctx->active_stats->variable_order;
	const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
	for (l = 0; l < Leff; l++) {
		// Reset reusable state
        sw_set_ui_0(new_sol->vector);
        sw_set_ui_0(new_sol->branch);

		// reset constraint rhs to initial values
		memcpy(potentials, con->rhs, C * sizeof(int64_t));
        memset(ret_total1, 0, C * sizeof(int64_t));
        memset(ret_total2, 0, C * sizeof(int64_t));

		// initialize new solution
		new_sol->tot_profit = cur_sol->tot_profit;

		int i;
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
			// look ahead to the left side (position space, bd h8d)
			look_ahead_correct(k, 0, imin(k + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
			// look ahead to the right side
			look_ahead_correct(k, 1, imin(k + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);

			/* M2a (bd 8an.3.1): classify this decision — pure counters, no
			 * behavior change. In sat the both-infeasible class is handled as
			 * forced-to-0 below, but it is counted as its own class. */
			ctx->sat_decisions++;
			if (count[0] > 0 && count[1] > 0)        ctx->sat_free++;
			else if (count[0] == 0 && count[1] == 0) ctx->sat_bothinf++;
			else                                     ctx->sat_forced++;

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
			sw_set_inplace(cur_sol->vector, new_sol->vector);
			sw_set_inplace(cur_sol->branch, new_sol->branch);

            free_state(new_sol, 1);
            *samples += (int) l;
			free(potentials);
			free(ret_total1);
			free(ret_total2);
            return 1;
        }
	}
	*samples += (int) l;
	free_state(new_sol, 1);
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
        const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
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
            // look ahead to the left side (position space, bd h8d)
            look_ahead_correct(k, 0, imin(k + 0, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
            // look ahead to the right side
            look_ahead_correct(k, 1, imin(k + 0, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);

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
		const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
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

            // look ahead to the left side (position space, bd h8d)
            look_ahead_correct(k, 0, imin(k, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
            // look ahead to the right side
            look_ahead_correct(k, 1, imin(k, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);

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
			    total_violation += potentials[cnstr] != con->rhs[cnstr] ? llabs(potentials[cnstr]) : 0;
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
        const int *var_rank = ctx->active_stats->variable_rank;  /* bd h8d */
        int k;
        for (k = 0; k < n; k++) {
            i = var_order ? var_order[k] : k;
            int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
            double random_num = prng_next_double();

            int new_bit = 0;

            // check, if assignment does not exceed potentials
            // if depth look ahead is 0, it will check only the next assignment
            int count[2] = {0, 0};
            // look ahead to the left side (position space, bd h8d)
            look_ahead_correct(k, 0, imin(k, n - 1), &count[0], con, potentials, new_sol, ret_total1, var_order, var_rank);
            // look ahead to the right side
            look_ahead_correct(k, 1, imin(k, n - 1), &count[1], con, potentials, new_sol, ret_total2, var_order, var_rank);

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
