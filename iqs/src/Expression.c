#include "Expression.h"

expression_t *init_expression(){
    expression_t *expr = malloc(sizeof(expression_t));
//    memset(expr->len_literal, 0, 5000 * sizeof(int));
//    memset(expr->literals, 0, 3 * 50000 * sizeof(int));
    expr->expr_size = 0;
    return expr;
}

int expr_index(int lit, int ind){
    return 3 * lit + ind;
}

void add_constant(expression_t *expr, int64_t constant){
//    expr->literals[expr->expr_size][0] = constant;
    expr->literals[expr_index(expr->expr_size, 0)] = constant;
    expr->len_literal[expr->expr_size] = 1;
    expr->expr_size++;
}

void add_variable(expression_t *expr, int64_t index){
    expr->literals[expr_index(expr->expr_size, 0)] = 1;
    expr->literals[expr_index(expr->expr_size, 1)] = index;
    expr->len_literal[expr->expr_size] = 2;
    expr->expr_size++;
}

void add_expression(expression_t *expr1, expression_t *expr2){
    for (int i = 0; i < expr2->expr_size; i++){
        for (int j = 0; j < expr2->len_literal[i]; j++){
            expr1->literals[expr_index(expr1->expr_size, j)] = expr2->literals[expr_index(i, j)];
        }
        expr1->len_literal[expr1->expr_size] = expr2->len_literal[i];
       expr1->expr_size++;
    }
    free(expr2);
}

void sub_constant(expression_t *expr, int64_t constant){
    expr->literals[expr_index(expr->expr_size, 0)] = -constant;
    expr->len_literal[expr->expr_size] = 1;
    expr->expr_size++;
}

void sub_variable(expression_t *expr, int64_t index){
    expr->literals[expr_index(expr->expr_size, 0)] = -1;
    expr->literals[expr_index(expr->expr_size, 1)] = index;
    expr->len_literal[expr->expr_size] = 2;
    expr->expr_size++;
}

void sub_expression(expression_t *expr1, expression_t *expr2){
    for (int i = 0; i < expr2->expr_size; i++){
        expr1->literals[expr_index(expr1->expr_size, 0)] = -1 * expr2->literals[expr_index(i, 0)];
        for (int j = 1; j < expr2->len_literal[i]; j++){
//            expr1->literals[expr1->expr_size][j] = expr2->literals[i][j];
            expr1->literals[expr_index(expr1->expr_size, j)] = expr2->literals[expr_index(i, j)];
        }
        expr1->len_literal[expr1->expr_size] = expr2->len_literal[i];
        expr1->expr_size++;
    }
//    free(expr2);
}

void multiply_constant(expression_t *expr, int64_t constant){
    for (int i = 0; i < expr->expr_size; i++){
        expr->literals[expr_index(i, 0)] *= constant;
    }
}

void multiply_variable(expression_t *expr, int64_t index){
    for (int i = 0; i < expr->expr_size; i++){
//        expr->literals[i][expr->len_literal[i]++] = expr_index;
        expr->literals[expr_index(i, expr->len_literal[i])] = index;
        expr->len_literal[i]++;
    }
}

// maybe no need to implement "multiply_expression"