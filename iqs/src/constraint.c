#include "constraint.h"


new_constraints_t init_new_constraint() {
	new_constraints_t con;

	con.num_constraints = 0;
	con.num_clauses = calloc(0, sizeof(size_t));
	con.clause_offset = calloc(MINARRAYSIZE, sizeof(size_t));
	con.factors = calloc(MINARRAYSIZE, sizeof(int64_t));
	con.clause_length = calloc(MINARRAYSIZE, sizeof(size_t));
	con.variable_offset = calloc(MINARRAYSIZE, sizeof(size_t));
	con.variables = calloc(MINARRAYSIZE, sizeof(size_t));
	con.sense = calloc(0, sizeof(int));
	con.rhs = calloc(0, sizeof(int64_t));

	return con;
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

size_t first_variable_index(size_t cls, size_t clause_index) {
	if (cls == 0) return clause_index * (MAXCLAUSESIZE - 1);
	return clause_index * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}

size_t variable_index(size_t cls, size_t k, size_t clause_index) {
	return first_variable_index(cls, clause_index) + k;
}

void print_new_constraint(new_constraints_t *con) {
	printf("constraints -> %zu\n", con->num_constraints);
	for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr) {
		for (int cls = 0; cls < con->num_clauses[cnstr]; ++cls) {
			size_t clause_index = first_clause_index(con, cnstr) + cls;
			printf("[%lld ", con->factors[clause_index]);
			for (int k = 0; k < con->clause_length[clause_index]; ++k) {
				printf("%zu ", con->variables[variable_index(cls, k, clause_index)]);
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
	con->sense = realloc(con->sense, con->num_constraints * sizeof(int));
	con->rhs = realloc(con->rhs, con->num_constraints * sizeof(int64_t));


	int clause_counter = 0;

	size_t C = con->num_constraints - 1;
	size_t clause_offset = first_clause_index(con, C);

	for (int cls = 0; cls < expr->expr_size; ++cls) {
		if (expr->len_literal[cls] != 0) {
			for (int i = 1; i < expr->len_literal[cls]; ++i) {
				con->variables[variable_index(clause_counter, i - 1, clause_offset)] = expr->literals[expr_index(cls, i)];
			}
			con->clause_length[clause_offset + clause_counter] = expr->len_literal[cls] - 1;
			con->factors[clause_offset + clause_counter++] = expr->literals[expr_index(cls, 0)];
		}
	}

	if (C > 0) con->clause_offset[C] = con->clause_offset[C - 1] + clause_counter;
	else con->clause_offset[C] = clause_counter;
	con->num_clauses[C] = clause_counter;

	con->rhs[C] = expr->rhs;
	con->sense[C] = expr->sense;
}

int eval_constraint(new_constraints_t *con, state_t *sol, int max_item, size_t cnstr) {
	int64_t total = 0;
	for (int cl = 0; cl < con->num_clauses[cnstr]; ++cl) {
		size_t clause_index = first_clause_index(con, cnstr) + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < con->clause_length[clause_index]; ++k) {
			size_t var = con->variables[variable_index(cl, k, clause_index)];
			if (var > max_item) {
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
	for (int cl = 0; cl < obj->num_clauses[cnstr]; ++cl) {
		size_t clause_index = first_clause_index(obj, cnstr) + cl;

		// check, if every item of a clause is assigned
		int assigned = 1;
		for (int k = 0; k < obj->clause_length[clause_index]; ++k) {
			size_t var = obj->variables[variable_index(cl, k, clause_index)];
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





























// old implementation: get rid of it in the future
constraint_list_t init_con_list() {
	constraint_list_t con_list;
	con_list.num_constraints = 0;
	con_list.constraints = malloc(sizeof(constraint_t));
	con_list.constraints->sense = MAXIMIZE;
	return con_list;
}

constraint_t init_con() {
	constraint_t con;
	con.num_literals = 0;
	con.sense = -2;
	con.rhs = 0;
	con.first_non_closed = 0;
	con.rhs_adapted = 0;
	con.literals = malloc(0);
	return con;
}

lit_t init_literal(int64_t *literal, int len_literal) {
	lit_t lit;
	lit.variables = calloc(len_literal - 1, sizeof(int64_t));
	lit.factor = literal[0];
	for (int i = 0; i < len_literal - 1; i++) {
		lit.variables[i] = literal[i + 1];
	}
	lit.len_literal = len_literal;

	return lit;
}

constraint_t *add_constraint(constraint_list_t *con_list) {
	con_list->num_constraints += 1;
	con_list->constraints = realloc(con_list->constraints, con_list->num_constraints * sizeof(constraint_t));
	con_list->constraints[con_list->num_constraints - 1] = init_con();
	return &con_list->constraints[con_list->num_constraints - 1];
}

void add_literal(constraint_t *con, int64_t *literal, int len_literal) {
	con->literals = realloc(con->literals, (con->num_literals + 1) * sizeof(lit_t));
	con->literals[con->num_literals] = init_literal(literal, len_literal);
	con->num_literals++;
}

void add_sense(constraint_t *con, int sense) {
	con->sense = sense;
}

void add_rhs(constraint_t *con, int64_t rhs) {
	con->rhs += rhs;
	con->rhs_adapted += rhs;
	con->first_non_closed = 0;
}

void reset_rhs_adapted(constraint_list_t *con) {
	for (int i = 0; i < con->num_constraints; i++) {
		con->constraints[i].rhs_adapted = con->constraints[i].rhs;
	}
}

void print_constraints(constraint_list_t *cons) {
	for (int i = 0; i < cons->num_constraints; i++) {
		for (int j = 0; j < cons->constraints[i].num_literals; j++) {
			printf("[");
			printf("%lld ", cons->constraints[i].literals[j].factor);
			for (int k = 0; k < cons->constraints[i].literals[j].len_literal - 1; k++) {
				printf("%d ", cons->constraints[i].literals[j].variables[k]);
			}
			printf("] ");
		}
		if (cons->constraints[i].sense == LOWER || cons->constraints[i].sense == MAXIMIZE) printf("< ");
		else if (cons->constraints[i].sense == EQUAL) printf("= ");
		else printf("> ");
		printf("%lld ", cons->constraints[i].rhs_adapted);
		printf("%lld\n", cons->constraints[i].rhs);
	}
}


int eval_constraint2(constraint_t *con, state_t *assignment, int assigned, int close) {
	double total = 0;
	int open_lit = con->num_literals - con->first_non_closed;
	int first_non_closed = con->first_non_closed;

	for (int i = first_non_closed; i < con->num_literals; i++) {
		lit_t *lit = &con->literals[i];
		// is it a constant expression
		if (lit->len_literal == 1) total = total + lit->factor;
			// is it a linear expression?
		else if (lit->len_literal == 2) {
			int ass = sw_tstbit(assignment->vector, lit->variables[0]);
			// is the variable already assigned?
			if (lit->variables[0] < assigned) {
				// is it a negative coefficient?
				if (lit->factor < 0) {
					total = total - lit->factor * (1 - ass);
				} else {
					total = total + lit->factor * ass;
				}
				// the variable is not "open" anymore
				if (close) con->first_non_closed = i + 1;
				open_lit--;
			}
			if (lit->variables[0] > assigned) break;
		}
			// is it a quadratic expression?
		else {
			// are both variables assigned already?
			if ((lit->variables[0] < assigned) && (lit->variables[1] < assigned)) {
				int ass1 = sw_tstbit(assignment->vector, lit->variables[0]);
				int ass2 = sw_tstbit(assignment->vector, lit->variables[1]);
				// is it a negative coefficient?
				if (lit->factor < 0) {
					total = total - lit->factor * (1 - ass1 * ass2);
				} else {
					total = total + lit->factor * ass1 * ass2;
				}
				if (close) con->first_non_closed = i + 1;
				open_lit--;
			}
			if ((lit->variables[0] > assigned) && (lit->variables[1] > assigned)) break;
		}
	}
	// keep old value for evaluation
	double rhs = con->rhs;

	// update rhs based on already assigned variables
//    if(close) con->rhs_adapted = con->rhs_adapted - total;

	if (con->sense == EQUAL) {
		if (open_lit > 0) return total <= rhs;
		else return total == rhs;
	} else if (con->sense == LOWER) return total <= rhs;
	else return total >= rhs;
}


int quantum_feasibility2(constraint_list_t *con, state_t *assignment, int assigned, int close) {
	if (assigned == 0) return true;
	for (int i = 0; i < con->num_constraints; i++) {
		if (!eval_constraint2(&con->constraints[i], assignment, assigned, close)) {
			return false;
		}
	}
	return true;
}

int
count_satisfyed_constraints(constraint_list_t *con, state_t *assignment, int assigned, int close, int allowed_false) {
	if (assigned == 0) return 0;
	int count = 0;
	int false_cons = 0;
	for (int i = 0; i < con->num_constraints; i++) {
		if (eval_constraint2(&con->constraints[i], assignment, assigned, close)) count++;
		else {
			false_cons++;
			if (false_cons > allowed_false) return count;
		}
//        count += eval_constraint2(&con->constraints[i], assignment, assigned, close);
	}
	return count;
}

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