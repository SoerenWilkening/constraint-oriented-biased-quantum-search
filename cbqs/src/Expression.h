#ifndef EXPRESSION_H
#define EXPRESSION_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "definitions.h"
#include "dyn_expr.h"

// expression_t is now a typedef to dyn_expression_t
// This provides dynamic memory allocation with small-object optimization
typedef dyn_expression_t expression_t;

int len_literal(expression_t *expr , int clause);
expression_t *init_expression(void);
size_t expr_index(size_t lit, int ind);
void free_expression(expression_t *expr);
void copy_expression_contents(expression_t *dest, expression_t *src);
void print_expression(expression_t *expr);
void sort_expression(expression_t *expr);
void merge_expression(expression_t *expr);

void add_constant(expression_t *expr, int64_t constant);
void add_variable(expression_t *expr, int64_t index);
void add_expression(expression_t *expr1, expression_t *expr2);

void sub_constant(expression_t *expr, int64_t constant);
void sub_variable(expression_t *expr, int64_t index);
void sub_expression(expression_t *expr1, expression_t *expr2);

void multiply_constant(expression_t *expr, int64_t constant);
void multiply_variable(expression_t *expr, int64_t index);

void add_sense_to_expression(expression_t *expr, int sense);
void add_rhs_to_expression(expression_t *expr, int64_t rhs);

expression_t *multiply_expressions(expression_t *expr1, expression_t *expr2);

#endif
