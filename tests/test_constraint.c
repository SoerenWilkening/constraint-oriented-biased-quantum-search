#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "constraint.h"
#include "Expression.h"
#include "definitions.h"

/*
 * Helper: build a knapsack-style constraint from coefficients.
 *
 * Creates: coeffs[0]*x0 + coeffs[1]*x1 + ... + coeffs[n-1]*x(n-1)  sense  rhs
 *
 * Each variable term is built as a separate single-variable expression with
 * multiply_constant applied, then combined via add_expression.  This avoids
 * the multiply_constant-all-clauses pitfall (multiply_constant multiplies
 * ALL existing clauses in an expression).
 */
static expression_t *build_linear_expression(int n, int64_t *coeffs, int sense, int64_t rhs) {
    expression_t *combined = init_expression();
    for (int i = 0; i < n; i++) {
        if (coeffs[i] == 0) continue;
        expression_t *term = init_expression();
        add_variable(term, i);               /* 1*x_i */
        multiply_constant(term, coeffs[i]);  /* coeffs[i]*x_i */
        add_expression(combined, term);
        free_expression(term);
    }
    add_sense_to_expression(combined, sense);
    add_rhs_to_expression(combined, rhs);
    return combined;
}

static new_constraints_t build_knapsack_constraint(int n, int64_t *coeffs, int sense, int64_t rhs) {
    new_constraints_t con = init_new_constraint();
    expression_t *expr = build_linear_expression(n, coeffs, sense, rhs);
    add_expression_to_constraints(&con, expr);
    free_expression(expr);
    return con;
}

/* ------------------------------------------------------------------ */
/* test_init_new_constraint: verify init returns zeroed struct         */
/* ------------------------------------------------------------------ */
static void test_init_new_constraint(void **state) {
    (void)state;
    new_constraints_t con = init_new_constraint();
    assert_int_equal(con.num_constraints, 0);
    assert_non_null(con.factors);
    assert_non_null(con.num_clauses);
    assert_null(con.positive_indices);
    assert_null(con.negative_indices);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_add_single_expression: 2*x0 + 3*x1 <= 5                      */
/* ------------------------------------------------------------------ */
static void test_add_single_expression(void **state) {
    (void)state;
    int64_t coeffs[] = {2, 3};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    assert_int_equal(con.num_constraints, 1);
    assert_int_equal(con.sense[0], LOWER);
    assert_int_equal(con.rhs[0], 5);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_add_multiple_expressions: add 3 constraints                   */
/* ------------------------------------------------------------------ */
static void test_add_multiple_expressions(void **state) {
    (void)state;
    new_constraints_t con = init_new_constraint();

    for (int k = 0; k < 3; k++) {
        int64_t coeffs[] = {1, 1};
        expression_t *expr = build_linear_expression(2, coeffs, LOWER, k + 1);
        add_expression_to_constraints(&con, expr);
        free_expression(expr);
    }

    assert_int_equal(con.num_constraints, 3);
    assert_int_equal(con.rhs[0], 1);
    assert_int_equal(con.rhs[1], 2);
    assert_int_equal(con.rhs[2], 3);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_constraints_satisfied: x0 + x1 <= 2, state (1,0)        */
/* ------------------------------------------------------------------ */
static void test_eval_constraints_satisfied(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 2);

    preprocessing(2, &con);

    /* state: x0=1, x1=0 => sum=1 <= 2  => satisfied */
    int arr[] = {1, 0};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 1);  /* all satisfied */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_constraints_violated: x0 + x1 <= 0, state (1,1)         */
/* ------------------------------------------------------------------ */
static void test_eval_constraints_violated(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &con);

    /* state: x0=1, x1=1 => sum=2 > 0  => violated */
    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 0);  /* violated */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_objective_value: -1*x0 - 2*x1, state (1,1) => -3             */
/* ------------------------------------------------------------------ */
static void test_objective_value(void **state) {
    (void)state;
    int64_t coeffs[] = {-1, -2};
    new_constraints_t obj = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &obj);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    int64_t val = objective_value(&obj, sol);
    assert_int_equal(val, -3);

    free_state(sol, 1);
    free_constraints(&obj);
}

/* ------------------------------------------------------------------ */
/* test_objective_value_partial: 3*x0 + 5*x1, state (1,0) => 3       */
/* ------------------------------------------------------------------ */
static void test_objective_value_partial(void **state) {
    (void)state;
    int64_t coeffs[] = {3, 5};
    new_constraints_t obj = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &obj);

    int arr[] = {1, 0};
    state_t *sol = init_state(0, arr, 2);

    int64_t val = objective_value(&obj, sol);
    assert_int_equal(val, 3);

    free_state(sol, 1);
    free_constraints(&obj);
}

/* ------------------------------------------------------------------ */
/* test_constraint_violation: x0 + x1 <= 1, state (1,1) => violation  */
/* ------------------------------------------------------------------ */
static void test_constraint_violation(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 1);

    preprocessing(2, &con);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    /* constraint_violation returns rhs - sum = 1 - 2 = -1 (negative means violated) */
    int violation = constraint_violation(&con, sol, 0);
    assert_true(violation < 0);  /* negative = violated */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_constraint_violation_satisfied: x0 + x1 <= 3, state (1,1)     */
/* ------------------------------------------------------------------ */
static void test_constraint_violation_satisfied(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 3);

    preprocessing(2, &con);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    /* rhs - sum = 3 - 2 = 1 (positive = satisfied, slack = 1) */
    int violation = constraint_violation(&con, sol, 0);
    assert_true(violation >= 0);

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_preprocessing: verify index arrays are populated              */
/* ------------------------------------------------------------------ */
static void test_preprocessing(void **state) {
    (void)state;
    int64_t coeffs[] = {1, -2};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    assert_null(con.positive_indices);
    assert_null(con.negative_indices);

    preprocessing(2, &con);

    assert_non_null(con.positive_indices);
    assert_non_null(con.negative_indices);
    assert_non_null(con.positive_offsets);
    assert_non_null(con.negative_offsets);
    assert_non_null(con.num_positive_indices);
    assert_non_null(con.num_negative_indices);

    /* With 1*x0 and -2*x1, we should have at least 1 positive and 1 negative index */
    assert_true(con.positive_array_length > 0);
    assert_true(con.negative_array_length > 0);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_all_zero_state: x0 + x1 <= 5, state (0,0) => satisfied  */
/* ------------------------------------------------------------------ */
static void test_eval_all_zero_state(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    preprocessing(2, &con);

    int arr[] = {0, 0};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 1);  /* 0 <= 5 satisfied */

    free_state(sol, 1);
    free_constraints(&con);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_new_constraint),
        cmocka_unit_test(test_add_single_expression),
        cmocka_unit_test(test_add_multiple_expressions),
        cmocka_unit_test(test_eval_constraints_satisfied),
        cmocka_unit_test(test_eval_constraints_violated),
        cmocka_unit_test(test_objective_value),
        cmocka_unit_test(test_objective_value_partial),
        cmocka_unit_test(test_constraint_violation),
        cmocka_unit_test(test_constraint_violation_satisfied),
        cmocka_unit_test(test_preprocessing),
        cmocka_unit_test(test_eval_all_zero_state),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
