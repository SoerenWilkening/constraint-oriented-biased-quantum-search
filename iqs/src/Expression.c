#include "Expression.h"

int min_size = 30000;

int len_literal(expression_t *expr , int clause){
	for (int i = 1; i < MAXCLAUSESIZE; ++i) {
		if (expr->literals[expr_index(clause, i)] == -1) return i;
	}
	return MAXCLAUSESIZE;
}

int compare_tuples(const void *a, const void *b) {
	const int64_t *tupleA = (const int64_t *)a;
	const int64_t *tupleB = (const int64_t *)b;

	for (int i = 1; i < MAXCLAUSESIZE; i++) {
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

void sort_expression(expression_t *expr){
	qsort(expr->literals, expr->expr_size, sizeof(int64_t) * MAXCLAUSESIZE, compare_tuples);
}

int expr_index(int lit, int ind){
	return MAXCLAUSESIZE * lit + ind;
}

void merge_expression(expression_t *expr){
	// sum up all the constants
	for (int i = 0; i < expr->expr_size; ++i) {
		if (expr->len_literal[i] == 1) {
			for (int j = i + 1; j < expr->expr_size; ++j) {
				if (expr->len_literal[j] == 1){
					expr->literals[expr_index(i, 0)] += expr->literals[expr_index(j, 0)];
					expr->literals[expr_index(j, 0)] = 0;
					expr->len_literal[j] = 0;
				}
			}
			break;
		}
	}
//	sort_expression(expr);
}

void print_expression(expression_t *expr){
	for (int cls = 0; cls < expr->expr_size; ++cls) {
		if (expr->len_literal[cls] != 0) {
			for (int i = 0; i < len_literal(expr, cls); ++i) {
//			for (int i = 0; i < expr->len_literal[cls]; ++i) {
//			for (int i = 0; i < MAXCLAUSESIZE; ++i) {
				printf("%lld ", expr->literals[expr_index(cls, i)]);
			}
			printf("\n");
		}
	}
}

expression_t *init_expression(){
    expression_t *expr = malloc(sizeof(expression_t));
    expr->literals = malloc(MAXCLAUSESIZE * min_size * sizeof(int64_t ));
	for (int i = 1; i < MAXCLAUSESIZE * min_size; ++i) expr->literals[i] = -1;
    expr->len_literal = malloc(min_size * sizeof(int));
    expr->expr_size = 0;
    return expr;
}

void free_expression(expression_t *expr){
	free(expr->literals);
	free(expr->len_literal);
	free(expr);
}

void increase(expression_t *expr){
    if (expr->expr_size % (min_size - 1) == 0 && expr->expr_size > 0){
        expr->literals = realloc(expr->literals, MAXCLAUSESIZE * (expr->expr_size + min_size) * sizeof(int64_t ));
	    for (int i = MAXCLAUSESIZE * expr->expr_size; i < MAXCLAUSESIZE * (expr->expr_size + min_size); ++i) expr->literals[i] = -1;
        expr->len_literal = realloc(expr->len_literal, (expr->expr_size + min_size) * sizeof(int));
    }
}

void add_constant(expression_t *expr, int64_t constant){
    if (constant == 0) return;
    increase(expr);

    expr->literals[expr_index(expr->expr_size, 0)] = constant;
    expr->len_literal[expr->expr_size] = 1;
    expr->expr_size++;
}

void add_variable(expression_t *expr, int64_t index){
//	printf("index = %d %d | ", expr_index(expr->expr_size, 0), expr_index(expr->expr_size, 1));
//	fflush(stdout);
	increase(expr);
	expr->literals[expr_index(expr->expr_size, 0)] = 1;
	expr->literals[expr_index(expr->expr_size, 1)] = index;
	expr->len_literal[expr->expr_size] = 2;
	expr->expr_size++;
}

void add_expression(expression_t *expr1, expression_t *expr2){
    for (int i = 0; i < expr2->expr_size; i++){
        increase(expr1);
        for (int j = 0; j < expr2->len_literal[i]; j++){
            expr1->literals[expr_index(expr1->expr_size, j)] = expr2->literals[expr_index(i, j)];
        }
        expr1->len_literal[expr1->expr_size] = expr2->len_literal[i];
       expr1->expr_size++;
    }
//    free_expression(expr2);
}

void sub_constant(expression_t *expr, int64_t constant){
    increase(expr);
    expr->literals[expr_index(expr->expr_size, 0)] = -constant;
    expr->len_literal[expr->expr_size] = 1;
    expr->expr_size++;
}

void sub_variable(expression_t *expr, int64_t index){
    increase(expr);
    expr->literals[expr_index(expr->expr_size, 0)] = -1;
    expr->literals[expr_index(expr->expr_size, 1)] = index;
    expr->len_literal[expr->expr_size] = 2;
    expr->expr_size++;
}

void sub_expression(expression_t *expr1, expression_t *expr2){
    for (int i = 0; i < expr2->expr_size; i++){
	    increase(expr1);
	    expr1->literals[expr_index(expr1->expr_size, 0)] = -1 * expr2->literals[expr_index(i, 0)];
        for (int j = 1; j < expr2->len_literal[i]; j++){
            expr1->literals[expr_index(expr1->expr_size, j)] = expr2->literals[expr_index(i, j)];
        }
        expr1->len_literal[expr1->expr_size] = expr2->len_literal[i];
        expr1->expr_size++;
    }
//    free_expression(expr2);
}

void multiply_constant(expression_t *expr, int64_t constant){
    increase(expr);
    for (int i = 0; i < expr->expr_size; i++){
        expr->literals[expr_index(i, 0)] *= constant;
    }
}

void multiply_variable(expression_t *expr, int64_t index){
    increase(expr);
    for (int i = 0; i < expr->expr_size; i++){
        expr->literals[expr_index(i, expr->len_literal[i])] = index;
        expr->len_literal[i]++;
    }
}

void add_sense_to_expression(expression_t *expr, int sense){
	expr->sense = sense;
}

void add_rhs_to_expression(expression_t *expr, int64_t rhs){
	expr->rhs = rhs;
}

// maybe no need to implement "multiply_expression"
expression_t *multiply_expressions(expression_t *expr1, expression_t *expr2){
	expression_t *new = init_expression();
	for(int index = 0; index < expr2->expr_size; index++) {
		expression_t *step = init_expression();
		add_expression(step, expr1);

		multiply_constant(step, expr2->literals[expr_index(index, 0)]);
		for (int i = 1; i < len_literal(expr2, index); ++i) {
			multiply_variable(step, expr2->literals[expr_index(index, i)]);
		}
		add_expression(new, step);
		free_expression(step);
	}
	return new;
}