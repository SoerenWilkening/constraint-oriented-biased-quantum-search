#include "constraint.h"


new_constraints_t init_new_constraint() {
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

	if (con->positive_indices != NULL) {
		free(con->positive_indices);
		free(con->positive_offsets);
		free(con->negative_indices);
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
	printf("constraints -> %zu\n", con->num_constraints);
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cls = 0; cls < con->num_clauses[cnstr]; ++cls) {
			size_t clause_index = clause_offset + cls;
			printf("%zu: [%lld ", clause_index, con->factors[clause_index]);
			for (int k = 0; k < con->clause_length[clause_index]; ++k) {
				printf("%zu ", con->variables[variable_index(cls, k, clause_offset)]);
			}
			printf("]\n");
		}
		if (con->sense[cnstr] == LOWER) printf("< ");
		printf("%lld\n", con->rhs[cnstr]);
	}

	size_t n = 0;
	size_t C = con->num_constraints;
	for (int i = 0; i < con->allocated_variables; ++i) if (con->variables[i] + 1 > n) n = con->variables[i] + 1;

//	printf("negative coefficients\n");
//	for (int item = 0; item < n; item++) {
//		for (int cnstr = 0; cnstr < C; cnstr++) {
//			printf("%d: %d-> ", item, cnstr);
//			for (int cls = 0; cls < con->num_negative_indices[item * C + cnstr]; cls++) {
//				printf("%u ", con->negative_indices[con->negative_offsets[item * C + cnstr] + cls]);
//			}
//			printf("\n");
//		}
//	}
//	printf("positive coefficients\n");
//	for (int item = 0; item < n; item++) {
//		for (int cnstr = 0; cnstr < C; cnstr++) {
//			printf("%d: %d-> ", item, cnstr);
//			for (int cls = 0; cls < con->num_positive_indices[item * C + cnstr]; cls++) {
//				printf("%u ", con->positive_indices[con->positive_offsets[item * C + cnstr] + cls]);
//			}
//			printf("\n");
//		}
//	}
}

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
	    printf("\r %f %%", (double) item / n * 100);

		for (int cnstr = 0; cnstr < C; cnstr++) {
			size_t clause_offset = first_clause_index(con, cnstr);
			unsigned int npi = 0;
			unsigned int nni = 0;
			for (int cls = 0; cls < con->num_clauses[cnstr]; cls++) {
				size_t clause_index = clause_offset + cls;
				int64_t factor = con->factors[clause_index];
				size_t prev_var = -1;
				for (int k = 0; k < con->clause_length[clause_index]; k++) {
					size_t var = con->variables[variable_index(cls, k, clause_offset)];

					if (item == var && var != prev_var) {
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
	printf("\r");
	con->positive_indices = realloc(con->positive_indices, con->positive_array_length * sizeof(uint32_t));
	con->negative_indices = realloc(con->negative_indices, con->negative_array_length * sizeof(uint32_t));
}


int64_t get_index(uint32_t *columns, uint32_t *rows, int item, int cnstr, size_t nnz, int C){
    
    size_t left = 0;
    size_t right = nnz;
    uint32_t target = item * C + cnstr;
    
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
//	    printf("\r %f %%", (double) item / n * 100);
        
        for (int cnstr = 0; cnstr < C; cnstr++) {
            size_t clause_offset = first_clause_index(con, cnstr);
            unsigned int npi = 0;
            unsigned int nni = 0;
            for (int cls = 0; cls < con->num_clauses[cnstr]; cls++) {
                size_t clause_index = clause_offset + cls;
                int64_t factor = con->factors[clause_index];
                size_t prev_var = -1;
                for (int k = 0; k < con->clause_length[clause_index]; k++) {
                    size_t var = con->variables[variable_index(cls, k, clause_offset)];
                    
                    if (item == var && var != prev_var) {
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
//    printf("\r");
    con->positive_indices = realloc(con->positive_indices, con->positive_array_length * sizeof(uint32_t));
    con->negative_indices = realloc(con->negative_indices, con->negative_array_length * sizeof(uint32_t));
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
	    printf("\r%f", (double) cls / expr->expr_size);
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
			con->total_variables += MAXCLAUSESIZE - 1;
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
	printf("\r");
	if (C > 0) con->clause_offset[C] = con->clause_offset[C - 1] + clause_counter;
	else con->clause_offset[C] = clause_counter;
	con->num_clauses[C] = clause_counter;

	con->rhs[C] = expr->rhs;
	con->sense[C] = expr->sense;
}

int eval_constraint(new_constraints_t *con, state_t *sol, int max_item, size_t cnstr) {
	int64_t total = 0;
	size_t clause_offset = first_clause_index(con, cnstr);
	for (int cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < con->clause_length[clause_index]; ++k) {
			size_t var = con->variables[variable_index(cl, k, clause_offset)];
			if (var > max_item) {
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
		if (max_item == sol->vector.bits && total != con->rhs[cnstr]) return 0;
		if (con->sense[cnstr] == LOWER && total > con->rhs[cnstr]) return 0;
	}
	return 1;
}

int eval_constraints(new_constraints_t *con, state_t *sol, int max_item) {
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		if (!eval_constraint(con, sol, max_item, cnstr)) return 0;
	}
	return 1;
}

int num_satisfied_constrains(new_constraints_t *con, state_t *sol) {
	int count = 0;
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		if (eval_constraint(con, sol, sol->vector.bits, cnstr)) count++;
	}
	return count;
}

int64_t objective_value(new_constraints_t *obj, state_t *sol) {
	// compute objective value of given solution
	int64_t total = 0;
	int cnstr = 0;
	size_t clause_offset = first_clause_index(obj, cnstr);
	for (int cl = 0; cl < obj->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < obj->clause_length[clause_index]; ++k) {
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
	int cnstr = 0;
	size_t clause_offset = first_clause_index(obj, cnstr);
	for (int cl = 0; cl < obj->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < obj->clause_length[clause_index]; ++k) {
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
	for (int cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
		size_t clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < con->clause_length[clause_index]; ++k) {
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

//int prepare_constraints(new_constraints_t *con, state_t *sol, int *fulfilled) {
int prepare_constraints(new_constraints_t *con, state_t *sol, array_t *ful) {
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
			size_t clause_index = clause_offset + cl;

			// check, if every item of a clause is assigned
			int assigned = 1;
			for (int k = 0; k < con->clause_length[clause_index]; ++k) {
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
	for (int cnstr = 0; cnstr < C; cnstr++) {
		int64_t total = 0;
		size_t clause_offset = first_clause_index(con, cnstr);
		int ind = item * C + cnstr;
//        printf("%d %d\n", con->sparsity, SPARSE);
        if (con->sparsity == SPARSE) {
            if (negative == NEGATIVE){
                ind = get_index(con->neg_cols, con->neg_rows, item, cnstr, con->nnz_neg, C);
            }else{
                ind = get_index(con->pos_cols, con->pos_rows, item, cnstr, con->nnz_pos, C);
            }
        }
        if (ind != -1){
		    for (int cls = 0; cls < num_indices[ind]; cls++) {
		    	int index = indices[offsets[ind] + cls]; // index of the clause of constraint cnstr

		    	size_t clause_index = clause_offset + index;

		    	if (!sw_tstbit(*inv, clause_index)) {
		    		int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
		    		for (int i = 0; i < con->clause_length[clause_index]; i++) {
		    			size_t var = con->variables[variable_index(index, i, clause_offset)];
		    			assigned &= sw_tstbit(cur_sol->vector, var);
		    		}
		    		if (negative == POSITIVE) {
		    			if (assigned == 1 && sw_tstbit(*ful, clause_index) == 0) {
		    				total += labs(con->factors[clause_index]);
//		    				if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
//		    				(*changes)[count++] = clause_index;
		    			}
		    			if (assigned == 0 && sw_tstbit(*ful, clause_index) == 1) {
		    				total -= labs(con->factors[clause_index]);
//		    				if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
//		    				(*changes)[count++] = clause_index;
		    			}
		    		}
		    		if (negative == NEGATIVE) {
		    			if ((1 - assigned) == 1 && sw_tstbit(*ful, clause_index) == 0) {
		    				total += labs(con->factors[clause_index]);
//		    				if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
//		    				(*changes)[count++] = clause_index;
		    			}
		    			if ((1 - assigned) == 0 && sw_tstbit(*ful, clause_index) == 1) {
		    				total -= labs(con->factors[clause_index]);
//		    				if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
//		    				(*changes)[count++] = clause_index;
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


int64_t objective_value_improved(new_constraints_t *obj, // objective function
                                 state_t *new,    // new state
                                 int NumChanges,  // how many bits were flipped
                                 int *ChangedBits,// which bits were flipped
                                 array_t *ful,  // are terms of objective fulfilled
                                 int **changes,
                                 int *num_changes
) {
	int NTerms = obj->num_clauses[0]; // number terms
	array_t inv = sw_init(NTerms);
	int n = new->vector.bits;
	int64_t total = 0;
	int count = 0;

	// go trough negative coefficients
	for (int i = 0; i < NumChanges; i++) { // go through all changes
		int item = ChangedBits[i]; // changed item
		for (int cls = 0; cls < obj->num_negative_indices[item]; cls++) {
			int assigned = 1;
			int clause_index = obj->negative_indices[obj->negative_offsets[item] + cls];
			if (!sw_tstbit(inv, clause_index)) {
				// if term was fulfilled: has to be unfulfilled
//				if (Fulfilled[clause_index]) {
				if (sw_tstbit(*ful, clause_index)) {
					total -= obj->factors[clause_index];
					if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
					(*changes)[count++] = clause_index;
				} else {
					for (int j = 0; j < obj->clause_length[clause_index]; j++) {
						size_t var = obj->variables[variable_index(clause_index, j, 0)];
						assigned &= sw_tstbit(new->vector, var);
					}
					if (assigned) {
						total += obj->factors[clause_index];
						if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
						(*changes)[count++] = clause_index;
					}
				}
			}
			sw_setbit(inv, clause_index);
		}
	}
	// go trough positive coefficients
	for (int item = 0; item < n; item++) {
		for (int cls = 0; cls < obj->num_positive_indices[item]; cls++) {
			int assigned = 1;
			int clause_index = obj->positive_indices[obj->positive_offsets[item] + cls];
			if (!sw_tstbit(inv, clause_index)) {
				// if term was fulfilled: has to be unfulfilled
				if (sw_tstbit(*ful, clause_index)) {
					if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
					total -= obj->factors[clause_index];
					(*changes)[count++] = clause_index;
				} else {
					for (int j = 0; j < obj->clause_length[clause_index]; j++) {
						size_t var = obj->variables[variable_index(clause_index, j, 0)];
						assigned &= sw_tstbit(new->vector, var);
					}
					total += obj->factors[clause_index] * assigned;
					if (assigned) {
						if ((count & (MINSIZE - 1)) == 0 && count > 0) *changes = realloc(*changes, (count + MINSIZE) * sizeof(int));
						(*changes)[count++] = clause_index;
					}
				}
			}
			sw_setbit(inv, clause_index);
		}
	}
	sw_clear(inv);
	*num_changes = count;
	return new->tot_profit + total;
}