#include "Expression.h"
#include "dyn_expr.h"

int len_literal(expression_t *expr, int clause) {
	return dyn_expr_len_literal(expr)[clause];
}

int compare_tuples(const void *a, const void *b) {
	const int64_t *tupleA = (const int64_t *)a;
	const int64_t *tupleB = (const int64_t *)b;

	for (int i = 1; i < MAX_VARS_PER_TERM; i++) {
		int64_t valA = tupleA[i];
		int64_t valB = tupleB[i];

		if (valA != valB) {
			// Treat PAD as greater than any real value
			if (valA == -1) return 1;
			if (valB == -1) return -1;
			return (valA < valB) ? -1 : 1;
		}
	}
	return 0;
}

void sort_expression(expression_t *expr) {
	int64_t *lits = dyn_expr_literals(expr);
	qsort(lits, expr->expr_size, sizeof(int64_t) * MAX_VARS_PER_TERM, compare_tuples);
}

size_t expr_index(size_t lit, int ind) {
	return MAX_VARS_PER_TERM * lit + ind;
}

void merge_expression(expression_t *expr) {
	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	// sum up all the constants
	for (size_t i = 0; i < expr->expr_size; ++i) {
		if (lens[i] == 1) {
			for (size_t j = i + 1; j < expr->expr_size; ++j) {
				if (lens[j] == 1) {
					lits[expr_index(i, 0)] += lits[expr_index(j, 0)];
					lits[expr_index(j, 0)] = 0;
					lens[j] = 0;
				}
			}
			break;
		}
	}
}

int merge_duplicate_variable_terms(expression_t *expr) {
	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);
	int found_dup = 0;

	/* Sort variable indices within each term so that
	   e.g. [coeff, 3, 1] becomes [coeff, 1, 3]. */
	for (size_t i = 0; i < expr->expr_size; i++) {
		int ll = lens[i];
		if (ll < 3) continue;  /* 0 or 1 vars -- nothing to sort */
		int num_vars = ll - 1;
		/* Simple insertion sort on the variable indices (positions 1..ll-1) */
		for (int j = 1; j < num_vars; j++) {
			int64_t key = lits[expr_index(i, j + 1)];
			int k = j;
			while (k > 0 && lits[expr_index(i, k)] > key) {
				lits[expr_index(i, k + 1)] = lits[expr_index(i, k)];
				k--;
			}
			lits[expr_index(i, k + 1)] = key;
		}
	}

	/* Sort all terms by variable indices (compare_tuples skips coeff at [0]) */
	sort_expression(expr);

	/* Refresh pointers after sort (sort_expression uses dyn_expr_literals) */
	lits = dyn_expr_literals(expr);
	lens = dyn_expr_len_literal(expr);

	/* Linear scan: merge adjacent terms with identical variable indices */
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] < 2) continue;  /* skip constants and zeroed terms */
		for (size_t j = i + 1; j < expr->expr_size; j++) {
			if (lens[j] < 2) continue;
			if (lens[j] != lens[i]) break;  /* different length -> different vars */
			/* Compare variable indices (positions 1..len-1) */
			int same = 1;
			for (int k = 1; k < lens[i]; k++) {
				if (lits[expr_index(i, k)] != lits[expr_index(j, k)]) {
					same = 0;
					break;
				}
			}
			if (!same) break;  /* sorted, so no more matches */
			/* Merge: add j's coefficient to i, zero out j */
			lits[expr_index(i, 0)] += lits[expr_index(j, 0)];
			lits[expr_index(j, 0)] = 0;
			lens[j] = 0;
			found_dup = 1;
		}
	}

	return found_dup;
}

void print_expression(expression_t *expr) {
	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	for (size_t cls = 0; cls < expr->expr_size; ++cls) {
		if (lens[cls] != 0) {
			for (int i = 0; i < len_literal(expr, (int)cls); ++i) {
				printf("%lld ", (long long)lits[expr_index(cls, i)]);
			}
			printf("\n");
		}
	}
}

expression_t *init_expression(void) {
    return dyn_expr_init();
}

void free_expression(expression_t *expr) {
    dyn_expr_free(expr);
}

void copy_expression_contents(expression_t *dest, expression_t *src) {
    dyn_expr_copy(dest, src);
}

void add_constant(expression_t *expr, int64_t constant) {
    dyn_expr_add_constant(expr, constant);
}

void add_variable(expression_t *expr, int64_t index) {
    dyn_expr_add_variable(expr, index);
}

void add_expression(expression_t *expr1, expression_t *expr2) {
    int64_t *lits = dyn_expr_literals(expr2);
    int *lens = dyn_expr_len_literal(expr2);
    for (size_t i = 0; i < expr2->expr_size; i++) {
        int64_t coeff = lits[i * MAX_VARS_PER_TERM];
        int num_vars = lens[i] - 1;
        if (num_vars > 0) {
            dyn_expr_add_term(expr1, coeff, &lits[i * MAX_VARS_PER_TERM + 1], num_vars);
        } else {
            dyn_expr_add_constant(expr1, coeff);
        }
    }
}

void sub_constant(expression_t *expr, int64_t constant) {
    dyn_expr_add_constant(expr, -constant);
}

void sub_variable(expression_t *expr, int64_t index) {
    dyn_expr_add_term(expr, -1, &index, 1);
}

void sub_expression(expression_t *expr1, expression_t *expr2) {
    int64_t *lits = dyn_expr_literals(expr2);
    int *lens = dyn_expr_len_literal(expr2);
    for (size_t i = 0; i < expr2->expr_size; i++) {
        int64_t coeff = -lits[i * MAX_VARS_PER_TERM];
        int num_vars = lens[i] - 1;
        if (num_vars > 0) {
            dyn_expr_add_term(expr1, coeff, &lits[i * MAX_VARS_PER_TERM + 1], num_vars);
        } else {
            dyn_expr_add_constant(expr1, coeff);
        }
    }
}

void multiply_constant(expression_t *expr, int64_t constant) {
    int64_t *lits = dyn_expr_literals(expr);
    for (size_t i = 0; i < expr->expr_size; i++) {
        lits[i * MAX_VARS_PER_TERM] *= constant;
    }
}

void multiply_variable(expression_t *expr, int64_t index) {
    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);
    for (size_t i = 0; i < expr->expr_size; i++) {
        int current_len = lens[i];
        if (current_len < MAX_VARS_PER_TERM) {
            lits[i * MAX_VARS_PER_TERM + current_len] = index;
            lens[i]++;
        }
        // If already at max variables, silently ignore (existing behavior)
    }
}

void add_sense_to_expression(expression_t *expr, int sense) {
    dyn_expr_set_sense(expr, sense);
}

void add_rhs_to_expression(expression_t *expr, int64_t rhs) {
    dyn_expr_set_rhs(expr, rhs);
}

// maybe no need to implement "multiply_expression"
expression_t *multiply_expressions(expression_t *expr1, expression_t *expr2) {
	expression_t *new = init_expression();
	for (size_t index = 0; index < expr2->expr_size; index++) {
		expression_t *step = init_expression();
		add_expression(step, expr1);

		int64_t *lits = dyn_expr_literals(expr2);
		multiply_constant(step, lits[expr_index(index, 0)]);
		for (int i = 1; i < len_literal(expr2, (int)index); ++i) {
			multiply_variable(step, lits[expr_index(index, i)]);
		}
		add_expression(new, step);
		free_expression(step);
	}
	return new;
}
