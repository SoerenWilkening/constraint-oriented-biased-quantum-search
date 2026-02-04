#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "Expression.h"

/* test_init_expression: verify fresh expression is empty */
static void test_init_expression(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    assert_non_null(expr);
    assert_int_equal(expr->expr_size, 0);
    free_expression(expr);
}

/* test_add_constant: add a constant term */
static void test_add_constant(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_constant(expr, 5);
    assert_int_equal(expr->expr_size, 1);

    /* Coefficient (slot 0) is 5 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 5);
    /* len_literal is 1 for constants (coefficient only, no variables) */
    assert_int_equal(expr->len_literal[0], 1);

    free_expression(expr);
}

/* test_add_variable: add a single variable x_3 (coefficient 1) */
static void test_add_variable(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_variable(expr, 3);
    assert_int_equal(expr->expr_size, 1);

    /* len_literal is 2: coefficient + 1 variable index */
    assert_int_equal(expr->len_literal[0], 2);
    /* coefficient is 1 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 1);
    /* variable index is 3 */
    assert_int_equal(expr->literals[expr_index(0, 1)], 3);

    free_expression(expr);
}

/* test_add_two_variables: add x_0 + x_1 */
static void test_add_two_variables(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_variable(expr, 0);
    add_variable(expr, 1);
    assert_int_equal(expr->expr_size, 2);

    /* First clause: 1*x_0 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 1);
    assert_int_equal(expr->literals[expr_index(0, 1)], 0);

    /* Second clause: 1*x_1 */
    assert_int_equal(expr->literals[expr_index(1, 0)], 1);
    assert_int_equal(expr->literals[expr_index(1, 1)], 1);

    free_expression(expr);
}

/* test_multiply_constant: 3*x_0 */
static void test_multiply_constant(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_variable(expr, 0);
    multiply_constant(expr, 3);

    assert_int_equal(expr->expr_size, 1);
    /* Coefficient should now be 3 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 3);
    /* Variable index unchanged */
    assert_int_equal(expr->literals[expr_index(0, 1)], 0);

    free_expression(expr);
}

/* test_add_expression: combine two expressions */
static void test_add_expression(void **state) {
    (void)state;

    /* Build 3*x_0 */
    expression_t *expr1 = init_expression();
    add_variable(expr1, 0);
    multiply_constant(expr1, 3);

    /* Build 2*x_1 */
    expression_t *expr2 = init_expression();
    add_variable(expr2, 1);
    multiply_constant(expr2, 2);

    /* Combine: 3*x_0 + 2*x_1 */
    add_expression(expr1, expr2);
    assert_int_equal(expr1->expr_size, 2);

    /* First clause: 3*x_0 */
    assert_int_equal(expr1->literals[expr_index(0, 0)], 3);
    assert_int_equal(expr1->literals[expr_index(0, 1)], 0);

    /* Second clause: 2*x_1 */
    assert_int_equal(expr1->literals[expr_index(1, 0)], 2);
    assert_int_equal(expr1->literals[expr_index(1, 1)], 1);

    free_expression(expr1);
    free_expression(expr2);
}

/* test_multiply_variable: x_0 * x_1 product term */
static void test_multiply_variable(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_variable(expr, 0);
    multiply_variable(expr, 1);

    assert_int_equal(expr->expr_size, 1);
    /* len_literal should be 3: coefficient + 2 variable indices */
    assert_int_equal(expr->len_literal[0], 3);
    /* coefficient is 1 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 1);
    /* variable indices: 0 and 1 */
    assert_int_equal(expr->literals[expr_index(0, 1)], 0);
    assert_int_equal(expr->literals[expr_index(0, 2)], 1);

    free_expression(expr);
}

/* test_sub_constant: 10 - 3 = 7 */
static void test_sub_constant(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_constant(expr, 10);
    sub_constant(expr, 3);

    /* expr_size is 2 (two constant clauses: +10 and -3) */
    assert_int_equal(expr->expr_size, 2);
    /* First clause: 10 */
    assert_int_equal(expr->literals[expr_index(0, 0)], 10);
    /* Second clause: -3 */
    assert_int_equal(expr->literals[expr_index(1, 0)], -3);

    free_expression(expr);
}

/* test_sense_and_rhs: set constraint sense and RHS */
static void test_sense_and_rhs(void **state) {
    (void)state;

    expression_t *expr = init_expression();
    add_sense_to_expression(expr, LOWER);
    add_rhs_to_expression(expr, 42);

    assert_int_equal(expr->sense, LOWER);
    assert_int_equal(expr->rhs, 42);

    free_expression(expr);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_expression),
        cmocka_unit_test(test_add_constant),
        cmocka_unit_test(test_add_variable),
        cmocka_unit_test(test_add_two_variables),
        cmocka_unit_test(test_multiply_constant),
        cmocka_unit_test(test_add_expression),
        cmocka_unit_test(test_multiply_variable),
        cmocka_unit_test(test_sub_constant),
        cmocka_unit_test(test_sense_and_rhs),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
