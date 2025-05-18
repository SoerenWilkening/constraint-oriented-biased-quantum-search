#include "constraint.h"


new_constraints_t init_new_constraint() {
	new_constraints_t con;

	con.num_constraints = 0;
	con.num_clauses = calloc(0, sizeof(size_t));
	con.clause_offset = calloc(0, sizeof(size_t));
	con.factors = calloc(MINARRAYSIZE, sizeof(int64_t));
	con.clause_length = calloc(MINARRAYSIZE, sizeof(size_t));
	con.variable_offset = calloc(MINARRAYSIZE, sizeof(size_t));
	con.variables = calloc(MINARRAYSIZE, sizeof(size_t));
	con.sense = calloc(0, sizeof(int));
	con.rhs = calloc(0, sizeof(int64_t));

    con.allocated_factors = MINARRAYSIZE;
	con.allocated_variables = MINARRAYSIZE;

	return con;
}

new_constraints_t copy_new_constraint(new_constraints_t *con){
    new_constraints_t new_con = init_new_constraint();
    new_con.num_constraints = con->num_constraints;

	new_con.rhs = realloc(new_con.rhs, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.rhs, con->rhs, con->num_constraints * sizeof(int64_t));

	new_con.sense = realloc(new_con.sense, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.sense, con->sense, con->num_constraints * sizeof(int));

	new_con.num_clauses = realloc(new_con.num_clauses, con->num_constraints * sizeof(int64_t));
	memcpy(new_con.num_clauses, con->num_clauses, con->num_constraints * sizeof(size_t));

	memcpy(new_con.clause_offset, con->clause_offset, con->num_constraints * sizeof(size_t));
	memcpy(new_con.factors, con->factors, MINARRAYSIZE * sizeof(int64_t));
	memcpy(new_con.clause_length, con->clause_length, MINARRAYSIZE * sizeof(size_t));
	memcpy(new_con.variable_offset, con->variable_offset, MINARRAYSIZE * sizeof(size_t));
	memcpy(new_con.variables, con->variables, MINARRAYSIZE * sizeof(size_t));


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
}

size_t first_clause_index(new_constraints_t *con, size_t C) {
	if (C == 0) return 0;
	return con->clause_offset[C - 1];
}

size_t first_variable_index(size_t cls, size_t clause_offset) {
	if (cls == 0) return clause_offset * (MAXCLAUSESIZE - 1);
	return clause_offset * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}

size_t variable_index(size_t cls, size_t k, size_t clause_offset) {
	return first_variable_index(cls, clause_offset) + k;
}

void print_new_constraint(new_constraints_t *con) {
	printf("constraints -> %zu\n", con->num_constraints);
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cls = 0; cls < con->num_clauses[cnstr]; ++cls) {
			size_t clause_index = clause_offset + cls;
			printf("[%lld ", con->factors[clause_index]);
			for (int k = 0; k < con->clause_length[clause_index]; ++k) {
				printf("%zu ", con->variables[variable_index(cls, k, clause_offset)]);
			}
			printf("] ");
		}
		if (con->sense[cnstr] == LOWER) printf("< ");
		printf("%lld\n", con->rhs[cnstr]);
	}
}

void add_expression_to_constraints(new_constraints_t *con, expression_t *expr) {

	// always occupy MAXClAUSELENGTH - 1 for variables

    con->num_constraints++;
	con->num_clauses = realloc(con->num_clauses, con->num_constraints * sizeof(size_t));
	con->clause_offset = realloc(con->clause_offset, con->num_constraints * sizeof(size_t));
	con->sense = realloc(con->sense, con->num_constraints * sizeof(int));
	con->rhs = realloc(con->rhs, con->num_constraints * sizeof(int64_t));

	int clause_counter = 0;

	size_t C = con->num_constraints - 1;
	size_t clause_offset = first_clause_index(con, C);
//    printf("start\n");
//	fflush(stdout);
	for (int cls = 0; cls < expr->expr_size; ++cls) {
		if (expr->len_literal[cls] != 0) {
//		    printf("vars\n");
//	        fflush(stdout);
			for (int i = 1; i < expr->len_literal[cls]; ++i) {
				int index = variable_index(clause_counter, i - 1, clause_offset);
				if (con->allocated_variables < index){
					con->variables = realloc(con->variables, (index + MINARRAYSIZE) * sizeof(size_t));
					con->allocated_variables = index + MINARRAYSIZE;
				}
				con->variables[index] = expr->literals[expr_index(cls, i)];
			}
//			printf("factors\n");
//	        fflush(stdout);
			if (con->allocated_factors < clause_offset + clause_counter){
				con->clause_length = realloc(con->clause_length, (clause_offset + clause_counter + MINARRAYSIZE) * sizeof(size_t));
				con->factors = realloc(con->factors, (clause_offset + clause_counter + MINARRAYSIZE) * sizeof(size_t));
				con->allocated_factors = clause_offset + clause_counter + MINARRAYSIZE;
			}
//			printf("allocated\n");
//	        fflush(stdout);
			con->clause_length[clause_offset + clause_counter] = expr->len_literal[cls] - 1;
			con->factors[clause_offset + clause_counter] = expr->literals[expr_index(cls, 0)];
//			printf("done\n");
//	        fflush(stdout);
			clause_counter++;
		}
	}

//    printf("end\n");
//	fflush(stdout);
	if (C > 0) con->clause_offset[C] = con->clause_offset[C - 1] + clause_counter;
	else con->clause_offset[C] = clause_counter;
	con->num_clauses[C] = clause_counter;
//	printf("done\n");
//	fflush(stdout);

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
			int bit = sw_tstbit(sol->vector, var);
			assigned *= bit;
		}
//		printf("assign = %d %lld\n", assigned, con->factors[clause_index]);
		if (con->factors[clause_index] < 0) {
			total -= con->factors[clause_index] * (1 - assigned) * (assigned != 2);
		} else {
			total += con->factors[clause_index] * assigned * (assigned != 2);
		}
	}
//	printf(" con = %zu total = %lld, %lld\n", cnstr, total, con->rhs[cnstr]);
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
			int bit = sw_tstbit(sol->vector, var);
			assigned *= bit;
		}
		total += obj->factors[clause_index] * assigned;
	}
	return total;
}


//int64_t objective_value_improved(new_constraints_t *obj, // objective function
//                                 state_t *new, // new state
//                                 int NumChanges, // how many bits were flipped
//                                 int *ChangedBits, // which bits were flipped
//                                 int **Indices, // objective term indices involving every item
//                                 int *NumIndices, // in how many terms every item occours
//                                 int *Fulfilled, // are terms of objective fulfilled
//                                 int *ChangedTerms,
//                                 int *NumChangedTerms
//) {
//	int Count = 0;
//	int NTerms = obj->num_clauses[0]; // number terms
//	int *investigated = calloc(NTerms,
//	                           sizeof(int)); // was the term evaluated already? (important for quadratic functions)
//	// For every changed bit, change, if the respective term changes and adjust the total profit
//	for (int ChangeIndex = 0; ChangeIndex < NumChanges; ChangeIndex++) {
//		int item = ChangedBits[ChangeIndex];
//		for (int term = 0; term < NumIndices[item]; term++) {
//			int literal = Indices[item][term];
//			lit_t *lit = &obj->constraints[0].literals[literal];
//			if (!investigated[literal]) {
//				int assign = 1;
//				// check every item of respective term
//				for (int lits = 0; lits < lit->len_literal - 1; lits++) {
//					if (!sw_tstbit(new->vector, lit->variables[lits]))
//						assign = 0;
//				}
//				if (Fulfilled[literal] && !assign) {
//					new->tot_profit -= lit->factor;
//				}
//				if (!Fulfilled[literal] && assign) {
//					new->tot_profit += lit->factor;
//				}
//				if (assign != Fulfilled[literal]) ChangedTerms[Count++] = literal;
//			}
//			// to avoid considering the same term multiple times
//			investigated[literal] = 1;
//		}
//	}
//	*NumChangedTerms = Count;
//	free(investigated);
//	return new->tot_profit;
//}














int64_t ObjVal(state_t *state, constraint_list_t *obj) {
	int64_t val = 0;
	for (int i = 0; i < obj->constraints->num_literals; i++) {
		lit_t *lit = &obj->constraints->literals[i];
		// is it a linear expression?
		if (lit->len_literal == 2) {
			int ass = sw_tstbit(state->vector, lit->variables[0]);
			val += lit->factor * ass;
		} else {
			int ass1 = sw_tstbit(state->vector, lit->variables[0]);
			int ass2 = sw_tstbit(state->vector, lit->variables[1]);
			val += lit->factor * ass1 * ass2;
		}
	}
	return val;
}

int64_t ChangedObjVal(constraint_list_t *obj, // objective function
                      state_t *new, // new state
                      int NumChanges, // how many bits were flipped
                      int *ChangedBits, // which bits were flipped
                      int **Indices, // objective term indices involving every item
                      int *NumIndices, // in how many terms every item occours
                      int *Fulfilled, // are terms of objective fulfilled
                      int *ChangedTerms,
                      int *NumChangedTerms
) {
	int Count = 0;
	int NTerms = obj->constraints[0].num_literals; // number terms
	int *investigated = calloc(NTerms,
	                           sizeof(int)); // was the term evaluated already? (important for quadratic functions)
	// For every changed bit, change, if the respective term changes and adjust the total profit
	for (int ChangeIndex = 0; ChangeIndex < NumChanges; ChangeIndex++) {
		int item = ChangedBits[ChangeIndex];
		for (int term = 0; term < NumIndices[item]; term++) {
			int literal = Indices[item][term];
			lit_t *lit = &obj->constraints[0].literals[literal];
			if (!investigated[literal]) {
				int assign = 1;
				// check every item of respective term
				for (int lits = 0; lits < lit->len_literal - 1; lits++) {
					if (!sw_tstbit(new->vector, lit->variables[lits]))
						assign = 0;
				}
				if (Fulfilled[literal] && !assign) {
					new->tot_profit -= lit->factor;
				}
				if (!Fulfilled[literal] && assign) {
					new->tot_profit += lit->factor;
				}
				if (assign != Fulfilled[literal]) ChangedTerms[Count++] = literal;
			}
			// to avoid considering the same term multiple times
			investigated[literal] = 1;
		}
	}
	*NumChangedTerms = Count;
	free(investigated);
	return new->tot_profit;
}