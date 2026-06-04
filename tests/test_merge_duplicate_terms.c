#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "Expression.h"

/* test_no_duplicates: expression with no duplicate terms stays the same */
static void test_no_duplicates(void **state) {
	(void)state;

	/* Build 3*x0 + 2*x1 + 5 */
	expression_t *expr = init_expression();
	add_variable(expr, 0);
	multiply_constant(expr, 3);
	add_variable(expr, 1);

	int64_t *lits = dyn_expr_literals(expr);
	/* Make second term coefficient 2 */
	lits[expr_index(1, 0)] = 2;

	add_constant(expr, 5);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 0);

	/* All three terms should still exist */
	lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	/* Count non-zero terms */
	int count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] > 0) count++;
	}
	assert_int_equal(count, 3);

	free_expression(expr);
}

/* test_merge_linear_duplicates: 3*x0 + 5*x0 -> 8*x0 */
static void test_merge_linear_duplicates(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	/* Add 3*x0 */
	add_variable(expr, 0);
	multiply_constant(expr, 3);
	/* Add 5*x0 as a separate term */
	int64_t vars[] = {0};
	dyn_expr_add_term(expr, 5, vars, 1);

	assert_int_equal(expr->expr_size, 2);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 1);

	/* Should have merged: find the surviving term */
	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	int64_t merged_coeff = 0;
	int live_count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] >= 2) {
			merged_coeff = lits[expr_index(i, 0)];
			/* Variable index should be 0 */
			assert_int_equal(lits[expr_index(i, 1)], 0);
			live_count++;
		}
	}
	assert_int_equal(live_count, 1);
	assert_int_equal(merged_coeff, 8);

	free_expression(expr);
}

/* test_merge_quadratic_duplicates: 2*x0*x1 + 3*x0*x1 -> 5*x0*x1 */
static void test_merge_quadratic_duplicates(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	/* Add 2*x0*x1 */
	int64_t vars1[] = {0, 1};
	dyn_expr_add_term(expr, 2, vars1, 2);
	/* Add 3*x0*x1 */
	dyn_expr_add_term(expr, 3, vars1, 2);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 1);

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	int64_t merged_coeff = 0;
	int live_count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] >= 2) {
			merged_coeff = lits[expr_index(i, 0)];
			live_count++;
		}
	}
	assert_int_equal(live_count, 1);
	assert_int_equal(merged_coeff, 5);

	free_expression(expr);
}

/* test_merge_unsorted_vars: 2*x1*x0 + 3*x0*x1 should merge (same vars, different order) */
static void test_merge_unsorted_vars(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	/* Add 2*x1*x0 (variables in reverse order) */
	int64_t vars1[] = {1, 0};
	dyn_expr_add_term(expr, 2, vars1, 2);
	/* Add 3*x0*x1 (variables in order) */
	int64_t vars2[] = {0, 1};
	dyn_expr_add_term(expr, 3, vars2, 2);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 1);

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	int64_t merged_coeff = 0;
	int live_count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] >= 2) {
			merged_coeff = lits[expr_index(i, 0)];
			live_count++;
		}
	}
	assert_int_equal(live_count, 1);
	assert_int_equal(merged_coeff, 5);

	free_expression(expr);
}

/* test_merge_constants_untouched: constants are not merged by this function */
static void test_merge_constants_untouched(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	add_constant(expr, 5);
	add_constant(expr, 3);
	add_variable(expr, 0);

	int found = merge_duplicate_variable_terms(expr);
	/* No duplicate variable terms -- constants don't count */
	assert_int_equal(found, 0);

	free_expression(expr);
}

/* test_merge_mixed: 3*x0 + 2*x1 + 5*x0 + 7 -> 8*x0 + 2*x1 + 7 */
static void test_merge_mixed(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	int64_t v0[] = {0};
	dyn_expr_add_term(expr, 3, v0, 1);
	int64_t v1[] = {1};
	dyn_expr_add_term(expr, 2, v1, 1);
	dyn_expr_add_term(expr, 5, v0, 1);
	dyn_expr_add_constant(expr, 7);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 1);

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	/* Check: should have x0 with coeff 8, x1 with coeff 2, constant 7 */
	int64_t coeff_x0 = 0, coeff_x1 = 0, coeff_const = 0;
	int var_count = 0, const_count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] == 0) continue;
		if (lens[i] == 1) {
			coeff_const += lits[expr_index(i, 0)];
			const_count++;
		} else if (lens[i] == 2) {
			int64_t var_idx = lits[expr_index(i, 1)];
			if (var_idx == 0) coeff_x0 = lits[expr_index(i, 0)];
			else if (var_idx == 1) coeff_x1 = lits[expr_index(i, 0)];
			var_count++;
		}
	}
	assert_int_equal(var_count, 2);
	assert_int_equal(const_count, 1);
	assert_int_equal(coeff_x0, 8);
	assert_int_equal(coeff_x1, 2);
	assert_int_equal(coeff_const, 7);

	free_expression(expr);
}

/* test_merge_quadratic_with_linear: 2*x0*x1 + 3*x0 + 5*x0*x1 -> 7*x0*x1 + 3*x0 */
static void test_merge_quadratic_with_linear(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	/* Add 2*x0*x1 */
	int64_t vars_q[] = {0, 1};
	dyn_expr_add_term(expr, 2, vars_q, 2);
	/* Add 3*x0 */
	int64_t vars_l[] = {0};
	dyn_expr_add_term(expr, 3, vars_l, 1);
	/* Add 5*x0*x1 */
	dyn_expr_add_term(expr, 5, vars_q, 2);

	assert_int_equal(expr->expr_size, 3);

	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 1);

	int64_t *lits = dyn_expr_literals(expr);
	int *lens = dyn_expr_len_literal(expr);

	int64_t coeff_x0x1 = 0, coeff_x0 = 0;
	int quad_count = 0, lin_count = 0;
	for (size_t i = 0; i < expr->expr_size; i++) {
		if (lens[i] == 3) {
			/* quadratic term: coefficient + 2 vars */
			coeff_x0x1 = lits[expr_index(i, 0)];
			assert_int_equal(lits[expr_index(i, 1)], 0);
			assert_int_equal(lits[expr_index(i, 2)], 1);
			quad_count++;
		} else if (lens[i] == 2) {
			/* linear term */
			coeff_x0 = lits[expr_index(i, 0)];
			assert_int_equal(lits[expr_index(i, 1)], 0);
			lin_count++;
		}
	}
	assert_int_equal(quad_count, 1);
	assert_int_equal(lin_count, 1);
	assert_int_equal(coeff_x0x1, 7);
	assert_int_equal(coeff_x0, 3);

	free_expression(expr);
}

/* test_empty_expression: no crash on empty expression */
static void test_empty_expression(void **state) {
	(void)state;

	expression_t *expr = init_expression();
	int found = merge_duplicate_variable_terms(expr);
	assert_int_equal(found, 0);
	free_expression(expr);
}

int main(void) {
	const struct CMUnitTest tests[] = {
		cmocka_unit_test(test_no_duplicates),
		cmocka_unit_test(test_merge_linear_duplicates),
		cmocka_unit_test(test_merge_quadratic_duplicates),
		cmocka_unit_test(test_merge_unsorted_vars),
		cmocka_unit_test(test_merge_constants_untouched),
		cmocka_unit_test(test_merge_mixed),
		cmocka_unit_test(test_merge_quadratic_with_linear),
		cmocka_unit_test(test_empty_expression),
	};
	return cmocka_run_group_tests(tests, NULL, NULL);
}
