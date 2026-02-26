#include "constraint.h"
#include <inttypes.h>


new_constraints_t init_new_constraint(void) {
	new_constraints_t con;

	con.num_constraints = 0;
	con.factors = calloc(MINARRAYSIZE, sizeof(int64_t));
	con.num_clauses = calloc(1, sizeof(uint32_t));
	con.clause_offset = calloc(1, sizeof(uint32_t));
	con.clause_length = calloc(MINARRAYSIZE, sizeof(uint32_t));
	con.variable_offset = calloc(MINARRAYSIZE, sizeof(uint32_t));
	con.variables = calloc(MINARRAYSIZE, sizeof(uint32_t));
	con.sense = calloc(1, sizeof(int));
	con.rhs = calloc(1, sizeof(int64_t));

	con.total_clauses = 0;
	con.total_variables = 0;

	con.allocated_factors = MINARRAYSIZE;
	con.allocated_variables = MINARRAYSIZE;

	con.positive_indices = NULL;
	con.positive_offsets = NULL;
	con.negative_indices = NULL;
	con.negative_offsets = NULL;
	con.num_positive_indices = NULL;
	con.num_negative_indices = NULL;
    
    con.pos_cols = NULL;
    con.pos_rows = NULL;
    con.neg_cols = NULL;
    con.neg_rows = NULL;

	return con;
}

new_constraints_t copy_new_constraint(new_constraints_t *con) {
	new_constraints_t new_con = init_new_constraint();
	new_con.num_constraints = con->num_constraints;

	new_con.rhs = realloc(new_con.rhs, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.rhs, con->rhs, con->num_constraints * sizeof(int64_t));

	new_con.sense = realloc(new_con.sense, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.sense, con->sense, con->num_constraints * sizeof(int));

	new_con.num_clauses = realloc(new_con.num_clauses, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.num_clauses, con->num_clauses, con->num_constraints * sizeof(uint32_t));

	memcpy(new_con.clause_offset, con->clause_offset, con->num_constraints * sizeof(uint32_t));
	memcpy(new_con.factors, con->factors, MINARRAYSIZE * sizeof(int64_t));
	memcpy(new_con.clause_length, con->clause_length, MINARRAYSIZE * sizeof(uint32_t));
	memcpy(new_con.variable_offset, con->variable_offset, MINARRAYSIZE * sizeof(uint32_t));
	memcpy(new_con.variables, con->variables, MINARRAYSIZE * sizeof(uint32_t));


	return new_con;
}

void free_constraints(new_constraints_t *con) {
	free(con->num_clauses);
	free(con->clause_offset);
	free(con->factors);
	free(con->clause_length);
	free(con->variable_offset);
	free(con->variables);
	free(con->sense);
	free(con->rhs);

	/* Use positive_offsets as guard: always allocated if preprocessing() ran */
	if (con->positive_offsets != NULL) {
		free(con->positive_indices);  /* May be NULL if array_length was 0 */
		free(con->positive_offsets);
		free(con->negative_indices);  /* May be NULL if array_length was 0 */
		free(con->negative_offsets);
		free(con->num_positive_indices);
		free(con->num_negative_indices);
	}
    if (con->pos_rows){
        free(con->neg_cols);
        free(con->pos_rows);
        free(con->pos_cols);
        free(con->neg_rows);
    }
}

void print_new_constraint(new_constraints_t *con) {
	printf("constraints -> %u\n", con->num_constraints);
	for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (uint32_t cls = 0; cls < con->num_clauses[cnstr]; ++cls) {
			size_t clause_index = clause_offset + cls;
			printf("%zu: [%" PRId64 " ", clause_index, con->factors[clause_index]);
			for (uint32_t k = 0; k < con->clause_length[clause_index]; ++k) {
				printf("%u ", con->variables[variable_index(cls, k, clause_offset)]);
			}
			printf("]\n");
		}
		if (con->sense[cnstr] == LOWER) printf("< ");
		printf("%" PRId64 "\n", con->rhs[cnstr]);
	}

}

/*
 * preprocessing -- Build dense index structures for constraint evaluation.
 *
 * Purpose: For each (variable, constraint) pair, build arrays that map to the
 * clause indices where that variable appears. This allows the sampling solver
 * to evaluate the effect of assigning a variable in O(k) time (where k is the
 * number of clauses containing it) instead of scanning all clauses.
 *
 * Data structures built (all 1D arrays, indexed by item * C + cnstr):
 *   positive_indices[]      -- clause indices for positive-coefficient terms
 *   positive_offsets[]      -- offset into positive_indices for each (item, cnstr)
 *   num_positive_indices[]  -- count of positive clause entries per (item, cnstr)
 *   negative_indices[]      -- clause indices for negative-coefficient terms
 *   negative_offsets[]      -- offset into negative_indices for each (item, cnstr)
 *   num_negative_indices[]  -- count of negative clause entries per (item, cnstr)
 *
 * Separation into positive/negative is needed because the branching direction
 * (assign 0 vs 1) has opposite effects on positive and negative terms when
 * computing constraint potential updates.
 *
 * Called once during model.close() on the main thread before any parallel solve.
 *
 * Reads:  con->num_constraints, con->num_clauses[], con->clause_length[],
 *         con->variables[], con->factors[]
 * Writes: All index arrays above, con->sparsity = DENSE, con->array_length
 */
void preprocessing(
		int n,
		new_constraints_t *con
) {
    con->sparsity = DENSE;
    int size_steps = 1 << 14;
	uint64_t C = con->num_constraints;

	con->positive_indices = calloc(size_steps, sizeof(uint32_t));
	con->negative_indices = calloc(size_steps, sizeof(uint32_t));
	con->positive_offsets = malloc((uint64_t) n * C * sizeof(uint32_t));
	con->negative_offsets = malloc((uint64_t) n * C * sizeof(uint32_t));
	con->num_positive_indices = malloc((uint64_t) n * C * sizeof(uint32_t));
	con->num_negative_indices = malloc((uint64_t) n * C * sizeof(uint32_t));

	con->positive_array_length = 0;
	con->negative_array_length = 0;
	con->array_length = n * C;
	// preprocess the constraints for usage in the sampling routine
	// go through every item and collect all the constraint indices containing the items
	// sort indices by positive and negative coefficients
	// an item can appear more than once in a constraint (linear + quadratic terms ...)
	// simplifications can be made:
	//  - in a clause, items are always sorted in ascending order
	//  - non-linear factors only come into play, if the last non-assigned item is investigated
	//      -> only store index of clause for last item
	// for every constraint, for every item an array is needed to store all the clauses
	// categorize for positive and negative constraints
	// improvement: use 1d-array implementations:
	//      - positive_indices      -> 1d array storing indices
	//                              -> length not fixed
	//      - positive_offsets      -> 1d array storing location of values in "positive_indices" given (item, cnstr)
	//                              -> length fixed
	//      - num_positive_indices  -> 1d array storing number of values in "positive_indices" at location from
	//                              -> given (item, cnstr)
	//                              -> length fixed

	size_t counter_positive = 0;
	size_t counter_negative = 0;
	for (int item = 0; item < n; item++) {
		for (uint64_t cnstr = 0; cnstr < C; cnstr++) {
			size_t clause_offset = first_clause_index(con, cnstr);
			unsigned int npi = 0;
			unsigned int nni = 0;
			for (uint32_t cls = 0; cls < con->num_clauses[cnstr]; cls++) {
				size_t clause_index = clause_offset + cls;
				int64_t factor = con->factors[clause_index];
				size_t prev_var = SIZE_MAX;
				for (uint32_t k = 0; k < con->clause_length[clause_index]; k++) {
					size_t var = con->variables[variable_index(cls, k, clause_offset)];

					if ((size_t)item == var && var != prev_var) {
						if (factor < 0) {
							// add index to "negative_indices"
							if ((counter_negative & (size_steps - 1)) == 0 && counter_negative > 0)
							    con->negative_indices = realloc(con->negative_indices, (counter_negative + size_steps) * sizeof(uint32_t));
							con->negative_indices[counter_negative++] = cls;
							nni++;
							con->negative_array_length++;
						} else {
							// add index to "positive_indices"
							if ((counter_positive & (size_steps - 1)) == 0 && counter_positive > 0)
							    con->positive_indices = realloc(con->positive_indices, (counter_positive + size_steps) * sizeof(uint32_t));
							con->positive_indices[counter_positive++] = cls;
							npi++;
							con->positive_array_length++;
						}
					}
					prev_var = var;
				}
			}
			con->num_negative_indices[item * C + cnstr] = nni;
			con->negative_offsets[item * C + cnstr] = counter_negative - nni;
			con->num_positive_indices[item * C + cnstr] = npi;
			con->positive_offsets[item * C + cnstr] = counter_positive - npi;
		}
	}
	if (con->positive_array_length == 0) {
		free(con->positive_indices);
		con->positive_indices = NULL;
	} else {
		uint32_t *new_pos = realloc(con->positive_indices, con->positive_array_length * sizeof(uint32_t));
		if (new_pos != NULL) {
			con->positive_indices = new_pos;
		}
		/* If realloc fails, keep original (over-allocated but not leaked) */
	}

	if (con->negative_array_length == 0) {
		free(con->negative_indices);
		con->negative_indices = NULL;
	} else {
		uint32_t *new_neg = realloc(con->negative_indices, con->negative_array_length * sizeof(uint32_t));
		if (new_neg != NULL) {
			con->negative_indices = new_neg;
		}
	}
}


int64_t get_index(const uint32_t *columns, const uint32_t *rows, int item, size_t cnstr, size_t nnz, size_t C){

    size_t left = 0;
    size_t right = nnz;
    uint32_t target = (uint32_t)(item * C + cnstr);
    
    while (left < right) {
        size_t mid = left + (right - left) / 2;
        
        uint32_t key = columns[mid] * C + rows[mid];
        
        if (key < target) {
            left = mid + 1;
        } else if (key > target) {
            right = mid;
        } else {
            return mid;  // found
        }
    }
    
    return -1;
}


/*
 * preprocessing_sparse -- Build sparse (CSR-like) index structures for constraint evaluation.
 *
 * Same purpose as preprocessing(), but for sparse constraint matrices where most
 * (variable, constraint) pairs have no entries. Used when clause density is low:
 * 10 * total_clauses <= n * num_constraints.
 *
 * Instead of allocating n * C entries for offsets/counts (which would be mostly zeros),
 * this version stores only the non-zero (item, constraint) pairs using row/column arrays:
 *   pos_rows[], pos_cols[]  -- (row=constraint, col=variable) for positive terms
 *   neg_rows[], neg_cols[]  -- same for negative terms
 *
 * Lookup during solving uses binary search via get_index() on the sorted row/column
 * structure, trading O(1) dense access for O(log nnz) sparse access with much less
 * memory when constraints are sparse.
 */
void preprocessing_sparse(
    int n,
    new_constraints_t *con
) {
    con->sparsity = SPARSE;
    int size_steps = 1 << 14;
    uint64_t C = con->num_constraints;
    
    con->positive_indices = calloc(size_steps, sizeof(uint32_t));
    con->negative_indices = calloc(size_steps, sizeof(uint32_t));
    con->positive_offsets = malloc(size_steps * sizeof(uint32_t));
    con->negative_offsets = malloc(size_steps * sizeof(uint32_t));
    con->num_positive_indices = malloc(size_steps * sizeof(uint32_t));
    con->num_negative_indices = malloc(size_steps * sizeof(uint32_t));
    con->neg_cols = malloc(size_steps * sizeof(uint32_t));
    con->pos_rows = malloc(size_steps * sizeof(uint32_t));
    con->pos_cols = malloc(size_steps * sizeof(uint32_t));
    con->neg_rows = malloc(size_steps * sizeof(uint32_t));
    con->nnz_pos = 0;
    con->nnz_neg = 0;
    
    con->positive_array_length = 0;
    con->negative_array_length = 0;
    con->array_length = n * C;
    // preprocess the constraints for usage in the sampling routine
    // go through every item and collect all the constraint indices containing the items
    // sort indices by positive and negative coefficients
    // an item can appear more than once in a constraint (linear + quadratic terms ...)
    // simplifications can be made:
    //  - in a clause, items are always sorted in ascending order
    //  - non-linear factors only come into play, if the last non-assigned item is investigated
    //      -> only store index of clause for last item
    // for every constraint, for every item an array is needed to store all the clauses
    // categorize for positive and negative constraints
    // improvement: use 1d-array implementations:
    //      - positive_indices      -> 1d array storing indices
    //                              -> length not fixed
    //      - positive_offsets      -> 1d array storing location of values in "positive_indices" given (item, cnstr)
    //                              -> length fixed
    //      - num_positive_indices  -> 2d array storing number of values in "positive_indices" at location from
    //                              -> given (item, cnstr)
    //                              -> length fixed
    
    size_t counter_positive = 0;
    size_t counter_negative = 0;
    for (int item = 0; item < n; item++) {
        for (uint64_t cnstr = 0; cnstr < C; cnstr++) {
            size_t clause_offset = first_clause_index(con, cnstr);
            unsigned int npi = 0;
            unsigned int nni = 0;
            for (uint32_t cls = 0; cls < con->num_clauses[cnstr]; cls++) {
                size_t clause_index = clause_offset + cls;
                int64_t factor = con->factors[clause_index];
                size_t prev_var = SIZE_MAX;
                for (uint32_t k = 0; k < con->clause_length[clause_index]; k++) {
                    size_t var = con->variables[variable_index(cls, k, clause_offset)];

                    if ((size_t)item == var && var != prev_var) {
                        if (factor < 0) {
                            // add index to "negative_indices"
                            if ((counter_negative & (size_steps - 1)) == 0 && counter_negative > 0)
                                con->negative_indices = realloc(con->negative_indices, (counter_negative + size_steps) * sizeof(uint32_t));
                            con->negative_indices[counter_negative++] = cls;
                            nni++;
                            con->negative_array_length++;
                        } else {
                            // add index to "positive_indices"
                            if ((counter_positive & (size_steps - 1)) == 0 && counter_positive > 0)
                                con->positive_indices = realloc(con->positive_indices, (counter_positive + size_steps) * sizeof(uint32_t));
                            con->positive_indices[counter_positive++] = cls;
                            npi++;
                            con->positive_array_length++;
                        }
                    }
                    prev_var = var;
                }
            }
            if (nni != 0) {
                if ((con->nnz_neg & (size_steps - 1)) == 0 && con->nnz_neg > 0){
                    // allocate more memory
                    con->neg_cols = realloc(con->neg_cols, (con->nnz_neg + size_steps) * sizeof(unsigned int));
                    con->neg_rows = realloc(con->neg_rows, (con->nnz_neg + size_steps) * sizeof(unsigned int));
                    con->num_negative_indices = realloc(con->num_negative_indices, (con->nnz_neg + size_steps) * sizeof(unsigned int));
                    con->negative_offsets = realloc(con->negative_offsets, (con->nnz_neg + size_steps) * sizeof(unsigned int));
                }
                con->neg_cols[con->nnz_neg] = item;
                con->neg_rows[con->nnz_neg] = cnstr;
                con->num_negative_indices[con->nnz_neg] = nni;
                con->negative_offsets[con->nnz_neg] = counter_negative - nni;
                con->nnz_neg++;
            }
            if (npi != 0) {
                if ((con->nnz_pos & (size_steps - 1)) == 0 && con->nnz_pos > 0){
                    con->pos_cols = realloc(con->pos_cols, (con->nnz_pos + size_steps) * sizeof(unsigned int));
                    con->pos_rows = realloc(con->pos_rows, (con->nnz_pos + size_steps) * sizeof(unsigned int));
                    con->num_positive_indices = realloc(con->num_positive_indices, (con->nnz_pos + size_steps) * sizeof(unsigned int));
                    con->positive_offsets = realloc(con->positive_offsets, (con->nnz_pos + size_steps) * sizeof(unsigned int));
                }
                con->pos_cols[con->nnz_pos] = item;
                con->pos_rows[con->nnz_pos] = cnstr;
                con->num_positive_indices[con->nnz_pos] = npi;
                con->positive_offsets[con->nnz_pos] = counter_positive - npi;
                con->nnz_pos++;
            }
        }
    }
    if (con->positive_array_length == 0) {
        free(con->positive_indices);
        con->positive_indices = NULL;
    } else {
        uint32_t *new_pos = realloc(con->positive_indices, con->positive_array_length * sizeof(uint32_t));
        if (new_pos != NULL) {
            con->positive_indices = new_pos;
        }
        /* If realloc fails, keep original (over-allocated but not leaked) */
    }

    if (con->negative_array_length == 0) {
        free(con->negative_indices);
        con->negative_indices = NULL;
    } else {
        uint32_t *new_neg = realloc(con->negative_indices, con->negative_array_length * sizeof(uint32_t));
        if (new_neg != NULL) {
            con->negative_indices = new_neg;
        }
    }
}



void add_expression_to_constraints(new_constraints_t *con, expression_t *expr) {

	// always occupy MAXClAUSELENGTH - 1 for variables
	con->num_constraints++;
	if (con->num_constraints > 1) {
		con->num_clauses = realloc(con->num_clauses, con->num_constraints * sizeof(uint32_t));
		con->clause_offset = realloc(con->clause_offset, con->num_constraints * sizeof(uint32_t));
		con->sense = realloc(con->sense, con->num_constraints * sizeof(uint32_t));
		con->rhs = realloc(con->rhs, con->num_constraints * sizeof(int64_t));
	}

	size_t clause_counter = 0;

	size_t C = con->num_constraints - 1;
	size_t clause_offset = first_clause_index(con, C);
	for (size_t cls = 0; cls < expr->expr_size; ++cls) {
		int lenght = expr->len_literal[cls];
		if (lenght != 0) {
			for (int i = 1; i < lenght; ++i) {
				size_t index = variable_index(clause_counter, i - 1, clause_offset);
				if (con->allocated_variables <= index) {
					size_t new_size = index + MINARRAYSIZE;
					con->variables = realloc(con->variables, new_size * sizeof(uint32_t));
					con->allocated_variables = index + MINARRAYSIZE;
				}
				con->variables[index] = expr->literals[expr_index(cls, i)];
			}
			con->total_variables += CONSTRAINT_VARS_PER_CLAUSE - 1;
			if (con->allocated_factors <= clause_offset + clause_counter) {
				con->clause_length = realloc(con->clause_length,
				                             (clause_offset + clause_counter + MINARRAYSIZE) * sizeof(uint32_t));
				con->factors = realloc(con->factors, (clause_offset + clause_counter + MINARRAYSIZE) * sizeof(uint64_t));
				con->allocated_factors = clause_offset + clause_counter + MINARRAYSIZE;
			}
			con->clause_length[clause_offset + clause_counter] = lenght - 1;
			con->factors[clause_offset + clause_counter] = expr->literals[expr_index(cls, 0)];
			clause_counter++;
			con->total_clauses++;
		}
	}
	if (C > 0) con->clause_offset[C] = con->clause_offset[C - 1] + clause_counter;
	else con->clause_offset[C] = clause_counter;
	con->num_clauses[C] = clause_counter;

	con->rhs[C] = expr->rhs;
	con->sense[C] = expr->sense;
}

int eval_constraint(new_constraints_t *con, state_t *sol, int max_item, size_t cnstr) {
	size_t s_max_item = (size_t)max_item;
	int64_t total = 0;
	size_t clause_offset = first_clause_index(con, cnstr);
	for (uint32_t cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (uint32_t k = 0; k < con->clause_length[clause_index]; ++k) {
			size_t var = con->variables[variable_index(cl, k, clause_offset)];
			if (var > s_max_item) {
				// variable product is not closed -> clause doesn't contribute to satifyability,
				// since remaining assignments can always set clause to 0
				assigned = 2;
				break;
			}
			assigned *= sw_tstbit(sol->vector, var);
		}
		if (con->factors[clause_index] < 0) {
			total -= con->factors[clause_index] * (1 - assigned) * (assigned != 2);
		} else {
			total += con->factors[clause_index] * assigned * (assigned != 2);
		}
	}
	if (con->sense[cnstr] == LOWER && total > con->rhs[cnstr]) return 0;
	if (con->sense[cnstr] == EQUAL) {
		if (s_max_item == sol->vector.bits && total != con->rhs[cnstr]) return 0;
		if (con->sense[cnstr] == LOWER && total > con->rhs[cnstr]) return 0;
	}
	return 1;
}

int eval_constraints(new_constraints_t *con, state_t *sol, int max_item) {
	for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		if (!eval_constraint(con, sol, max_item, cnstr)) return 0;
	}
	return 1;
}

int num_satisfied_constrains(new_constraints_t *con, state_t *sol) {
	int count = 0;
	for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		if (eval_constraint(con, sol, sol->vector.bits, cnstr)) count++;
	}
	return count;
}

int64_t objective_value(new_constraints_t *obj, state_t *sol) {
	// compute objective value of given solution
	int64_t total = 0;
	uint32_t cnstr = 0;
	size_t clause_offset = first_clause_index(obj, cnstr);
	for (uint32_t cl = 0; cl < obj->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (uint32_t k = 0; k < obj->clause_length[clause_index]; ++k) {
			size_t var = obj->variables[variable_index(cl, k, clause_offset)];
			assigned &= sw_tstbit(sol->vector, var);
		}
		total += obj->factors[clause_index] * assigned;
	}
	return total;
}

int64_t prepare(new_constraints_t *obj, state_t *sol, array_t *ful) {
	// compute objective value of given solution
	int64_t total = 0;
	uint32_t cnstr = 0;
	size_t clause_offset = first_clause_index(obj, cnstr);
	for (uint32_t cl = 0; cl < obj->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (uint32_t k = 0; k < obj->clause_length[clause_index]; ++k) {
			size_t var = obj->variables[variable_index(cl, k, clause_offset)];
			assigned &= sw_tstbit(sol->vector, var);
		}
		if (assigned) {
			sw_setbit(*ful, clause_index);
			total += obj->factors[clause_index];
		}
	}
	return total;
}

int constraint_violation(new_constraints_t *con, state_t *sol, size_t cnstr) {
	int64_t total = 0;
	size_t clause_offset = first_clause_index(con, cnstr);
	for (uint32_t cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (uint32_t k = 0; k < con->clause_length[clause_index]; ++k) {
			size_t var = con->variables[variable_index(cl, k, clause_offset)];
			assigned &= sw_tstbit(sol->vector, var);
		}
		if (con->factors[clause_index] < 0) {
			total -= con->factors[clause_index] * (1 - assigned);
		} else {
			total += con->factors[clause_index] * assigned;
		}
	}
	return con->rhs[cnstr] - total;
}

int prepare_constraints(new_constraints_t *con, state_t *sol, array_t *ful) {
	for (uint32_t cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (uint32_t cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
			size_t clause_index = clause_offset + cl;

			// check, if every item of a clause is assigned
			int assigned = 1;
			for (uint32_t k = 0; k < con->clause_length[clause_index]; ++k) {
				size_t var = con->variables[variable_index(cl, k, clause_offset)];
				assigned &= sw_tstbit(sol->vector, var);
			}
			if (con->factors[clause_index] < 0 && (1 - assigned) == 1) {
				sw_setbit(*ful, clause_index);
			}
			if (con->factors[clause_index] >= 0 && assigned == 1) {
				sw_setbit(*ful, clause_index);
			}
		}
	}
	return 0;
}


// implementations of classical sampling search and benchmarking =======================================================
int adjusted_constraint_violation(
		new_constraints_t *con, int item,
		const unsigned int *indices,
		const unsigned int *num_indices,
		const unsigned int *offsets, state_t *cur_sol,
		int negative,
		int64_t *ret_total,
		const array_t *ful,
		int **changes,
		int *num_changes,
		array_t *inv
) {
	int count = *num_changes;
	size_t C = con->num_constraints;
	// check, if assignment does not exceed potentials
	for (size_t cnstr = 0; cnstr < C; cnstr++) {
		int64_t total = 0;
		size_t clause_offset = first_clause_index(con, cnstr);
		int64_t ind = (int64_t)(item * C + cnstr);
        if (con->sparsity == SPARSE) {
            if (negative == NEGATIVE){
                ind = get_index(con->neg_cols, con->neg_rows, item, cnstr, con->nnz_neg, C);
            }else{
                ind = get_index(con->pos_cols, con->pos_rows, item, cnstr, con->nnz_pos, C);
            }
        }
        if (ind != -1){
		    for (uint32_t cls = 0; cls < num_indices[ind]; cls++) {
		    	uint32_t index = indices[offsets[ind] + cls]; // index of the clause of constraint cnstr

		    	size_t clause_index = clause_offset + index;

		    	if (!sw_tstbit(*inv, clause_index)) {
		    		int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
		    		for (uint32_t i = 0; i < con->clause_length[clause_index]; i++) {
		    			size_t var = con->variables[variable_index(index, i, clause_offset)];
		    			assigned &= sw_tstbit(cur_sol->vector, var);
		    		}
		    		if (negative == POSITIVE) {
		    			if (assigned == 1 && sw_tstbit(*ful, clause_index) == 0) {
		    				total += labs(con->factors[clause_index]);
		    			}
		    			if (assigned == 0 && sw_tstbit(*ful, clause_index) == 1) {
		    				total -= labs(con->factors[clause_index]);
		    			}
		    		}
		    		if (negative == NEGATIVE) {
		    			if ((1 - assigned) == 1 && sw_tstbit(*ful, clause_index) == 0) {
		    				total += labs(con->factors[clause_index]);
		    			}
		    			if ((1 - assigned) == 0 && sw_tstbit(*ful, clause_index) == 1) {
		    				total -= labs(con->factors[clause_index]);
		    			}
		    		}
		    	}
		    	sw_setbit(*inv, clause_index);
		    }
		    ret_total[cnstr] += total;
		}
	}
	*num_changes = count;
	return 1;
}
