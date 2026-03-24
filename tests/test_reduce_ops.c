#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <stdint.h>

#include "variable_vector.h"
#include "Expression.h"
#include "dyn_expr.h"

/* =========================================================================
 * bilinear_reduce tests
 * ========================================================================= */

/* Basic 2x3 sparse matrix with some zeros */
static void test_bilinear_basic(void **state) {
	(void)state;
	int y_idx[] = {10, 20};
	int x_idx[] = {0, 1, 2};
	/* Row-major 2x3: [[5, 0, 3], [0, 7, 0]] */
	int64_t mat[] = {5, 0, 3, 0, 7, 0};

	expression_t *expr = bilinear_reduce(y_idx, 2, mat, x_idx, 3);
	assert_non_null(expr);
	/* Should have 3 nonzero terms: (5,y10,x0), (3,y10,x2), (7,y20,x1) */
	assert_int_equal(dyn_expr_size(expr), 3);

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	/* Term 0: coeff=5, y=10, x=0 */
	assert_int_equal(lits[0 * MAX_VARS_PER_TERM + 0], 5);
	assert_int_equal(lits[0 * MAX_VARS_PER_TERM + 1], 10);
	assert_int_equal(lits[0 * MAX_VARS_PER_TERM + 2], 0);
	assert_int_equal(lens[0], 3);

	/* Term 1: coeff=3, y=10, x=2 */
	assert_int_equal(lits[1 * MAX_VARS_PER_TERM + 0], 3);
	assert_int_equal(lits[1 * MAX_VARS_PER_TERM + 1], 10);
	assert_int_equal(lits[1 * MAX_VARS_PER_TERM + 2], 2);
	assert_int_equal(lens[1], 3);

	/* Term 2: coeff=7, y=20, x=1 */
	assert_int_equal(lits[2 * MAX_VARS_PER_TERM + 0], 7);
	assert_int_equal(lits[2 * MAX_VARS_PER_TERM + 1], 20);
	assert_int_equal(lits[2 * MAX_VARS_PER_TERM + 2], 1);
	assert_int_equal(lens[2], 3);

	free_expression(expr);
}

/* All-zero matrix produces empty expression */
static void test_bilinear_all_zeros(void **state) {
	(void)state;
	int y_idx[] = {0, 1};
	int x_idx[] = {2, 3};
	int64_t mat[] = {0, 0, 0, 0};

	expression_t *expr = bilinear_reduce(y_idx, 2, mat, x_idx, 2);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 0);
	free_expression(expr);
}

/* m=0 or n=0 produces empty expression */
static void test_bilinear_empty(void **state) {
	(void)state;
	int idx[] = {0};
	int64_t mat[] = {1};

	expression_t *e1 = bilinear_reduce(idx, 0, mat, idx, 1);
	assert_non_null(e1);
	assert_int_equal(dyn_expr_size(e1), 0);
	free_expression(e1);

	expression_t *e2 = bilinear_reduce(idx, 1, mat, idx, 0);
	assert_non_null(e2);
	assert_int_equal(dyn_expr_size(e2), 0);
	free_expression(e2);
}

/* Negative coefficients work correctly */
static void test_bilinear_negative(void **state) {
	(void)state;
	int y_idx[] = {0};
	int x_idx[] = {1};
	int64_t mat[] = {-42};

	expression_t *expr = bilinear_reduce(y_idx, 1, mat, x_idx, 1);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 1);
	int64_t *lits = dyn_expr_literals(expr);
	assert_int_equal(lits[0], -42);
	free_expression(expr);
}

/* NULL inputs return NULL */
static void test_bilinear_null(void **state) {
	(void)state;
	int idx[] = {0};
	int64_t mat[] = {1};

	assert_null(bilinear_reduce(NULL, 1, mat, idx, 1));
	assert_null(bilinear_reduce(idx, 1, NULL, idx, 1));
	assert_null(bilinear_reduce(idx, 1, mat, NULL, 1));
}

/* Large dense matrix triggers heap transition */
static void test_bilinear_large(void **state) {
	(void)state;
	int y_idx[10], x_idx[10];
	int64_t mat[100];
	for (int i = 0; i < 10; i++) {
		y_idx[i] = i;
		x_idx[i] = i + 10;
	}
	for (int i = 0; i < 100; i++) mat[i] = i + 1;

	expression_t *expr = bilinear_reduce(y_idx, 10, mat, x_idx, 10);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 100);
	free_expression(expr);
}

/* =========================================================================
 * linear_reduce tests
 * ========================================================================= */

/* Basic with some zero coefficients */
static void test_linear_basic(void **state) {
	(void)state;
	int64_t coeffs[] = {3, 0, -5, 7};
	int x_idx[] = {10, 20, 30, 40};

	expression_t *expr = linear_reduce(coeffs, x_idx, 4);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 3); /* skip the zero */

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	/* Term 0: coeff=3, x=10 */
	assert_int_equal(lits[0 * MAX_VARS_PER_TERM + 0], 3);
	assert_int_equal(lits[0 * MAX_VARS_PER_TERM + 1], 10);
	assert_int_equal(lens[0], 2);

	/* Term 1: coeff=-5, x=30 */
	assert_int_equal(lits[1 * MAX_VARS_PER_TERM + 0], -5);
	assert_int_equal(lits[1 * MAX_VARS_PER_TERM + 1], 30);
	assert_int_equal(lens[1], 2);

	/* Term 2: coeff=7, x=40 */
	assert_int_equal(lits[2 * MAX_VARS_PER_TERM + 0], 7);
	assert_int_equal(lits[2 * MAX_VARS_PER_TERM + 1], 40);
	assert_int_equal(lens[2], 2);

	free_expression(expr);
}

/* All-zero coefficients produce empty expression */
static void test_linear_all_zeros(void **state) {
	(void)state;
	int64_t coeffs[] = {0, 0, 0};
	int x_idx[] = {0, 1, 2};

	expression_t *expr = linear_reduce(coeffs, x_idx, 3);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 0);
	free_expression(expr);
}

/* n=0 produces empty expression */
static void test_linear_empty(void **state) {
	(void)state;
	int64_t coeffs[] = {1};
	int x_idx[] = {0};

	expression_t *expr = linear_reduce(coeffs, x_idx, 0);
	assert_non_null(expr);
	assert_int_equal(dyn_expr_size(expr), 0);
	free_expression(expr);
}

/* NULL inputs return NULL */
static void test_linear_null(void **state) {
	(void)state;
	int64_t coeffs[] = {1};
	int x_idx[] = {0};

	assert_null(linear_reduce(NULL, x_idx, 1));
	assert_null(linear_reduce(coeffs, NULL, 1));
}

int main(void) {
	const struct CMUnitTest tests[] = {
		cmocka_unit_test(test_bilinear_basic),
		cmocka_unit_test(test_bilinear_all_zeros),
		cmocka_unit_test(test_bilinear_empty),
		cmocka_unit_test(test_bilinear_negative),
		cmocka_unit_test(test_bilinear_null),
		cmocka_unit_test(test_bilinear_large),
		cmocka_unit_test(test_linear_basic),
		cmocka_unit_test(test_linear_all_zeros),
		cmocka_unit_test(test_linear_empty),
		cmocka_unit_test(test_linear_null),
	};
	return cmocka_run_group_tests(tests, NULL, NULL);
}
