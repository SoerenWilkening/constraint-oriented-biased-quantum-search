#include "Expression.h"

int min_size = 30000;

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
}

expression_t *init_expression(){
    expression_t *expr = malloc(sizeof(expression_t));
    expr->literals = malloc(MAXCLAUSESIZE * min_size * sizeof(int64_t ));
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
    free_expression(expr2);
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
    free_expression(expr2);
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

// maybe no need to implement "multiply_expression"