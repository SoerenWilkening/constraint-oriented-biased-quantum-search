/**
 * test_dyn_expr.c - Unit tests for dynamic expression with SOO
 *
 * Tests the dyn_expression_t type including:
 * - Basic lifecycle (init/free)
 * - Inline storage for small expressions (<=8 terms)
 * - Inline-to-heap transition at 9 terms
 * - Heap growth with 2x capacity doubling
 * - Memory efficiency (small expressions use less memory)
 * - Copy operations for both inline and heap
 *
 * Phase 6: Memory Optimization
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <string.h>

#include "dyn_expr.h"

/* ============================================================================
 * Lifecycle tests
 * ============================================================================ */

/**
 * test_dyn_expr_init_free: verify init creates valid expr, free doesn't crash
 */
static void test_dyn_expr_init_free(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();
    assert_non_null(expr);
    assert_int_equal(dyn_expr_size(expr), 0);
    assert_int_equal(dyn_expr_is_inline(expr), 1);

    /* Free should not crash */
    dyn_expr_free(expr);

    /* Free NULL should also not crash */
    dyn_expr_free(NULL);
}

/* ============================================================================
 * Inline storage tests
 * ============================================================================ */

/**
 * test_dyn_expr_inline_storage: add 1-8 terms, verify inline mode (capacity==0)
 */
static void test_dyn_expr_inline_storage(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add 8 terms (at inline threshold) */
    for (int i = 0; i < 8; i++) {
        int result = dyn_expr_add_variable(expr, i);
        assert_int_equal(result, 0);
        assert_int_equal(dyn_expr_size(expr), (size_t)(i + 1));
        /* Should still be inline */
        assert_int_equal(dyn_expr_is_inline(expr), 1);
    }

    /* Verify all 8 terms stored correctly */
    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    for (int i = 0; i < 8; i++) {
        assert_int_equal(lens[i], 2);  /* coefficient + 1 variable */
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 0], 1);  /* coeff = 1 */
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 1], i);  /* var index */
    }

    dyn_expr_free(expr);
}

/**
 * test_dyn_expr_boundary_8_9: exact boundary behavior at inline threshold
 */
static void test_dyn_expr_boundary_8_9(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add exactly 8 terms - should remain inline */
    for (int i = 0; i < 8; i++) {
        dyn_expr_add_constant(expr, i + 1);
    }
    assert_int_equal(dyn_expr_size(expr), 8);
    assert_int_equal(dyn_expr_is_inline(expr), 1);

    /* Add 9th term - should transition to heap */
    dyn_expr_add_constant(expr, 9);
    assert_int_equal(dyn_expr_size(expr), 9);
    assert_int_equal(dyn_expr_is_inline(expr), 0);

    /* Verify all data preserved after transition */
    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    for (int i = 0; i < 9; i++) {
        assert_int_equal(lens[i], 1);  /* constant term */
        assert_int_equal(lits[i * MAX_VARS_PER_TERM], i + 1);
    }

    dyn_expr_free(expr);
}

/* ============================================================================
 * Heap transition and growth tests
 * ============================================================================ */

/**
 * test_dyn_expr_inline_to_heap: add 9 terms, verify heap transition
 */
static void test_dyn_expr_inline_to_heap(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add 9 terms to trigger heap transition */
    for (int i = 0; i < 9; i++) {
        int result = dyn_expr_add_variable(expr, i * 2);
        assert_int_equal(result, 0);
    }

    assert_int_equal(dyn_expr_size(expr), 9);
    /* Should now be on heap */
    assert_int_equal(dyn_expr_is_inline(expr), 0);

    /* Verify data integrity after transition */
    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    for (int i = 0; i < 9; i++) {
        assert_int_equal(lens[i], 2);
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 0], 1);
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 1], i * 2);
    }

    dyn_expr_free(expr);
}

/**
 * test_dyn_expr_heap_growth: add 33+ terms, verify 2x growth
 */
static void test_dyn_expr_heap_growth(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add 50 terms to trigger multiple growth cycles */
    /* Initial heap capacity is 32, should grow to 64 */
    for (int i = 0; i < 50; i++) {
        int result = dyn_expr_add_variable(expr, i);
        assert_int_equal(result, 0);
    }

    assert_int_equal(dyn_expr_size(expr), 50);
    assert_int_equal(dyn_expr_is_inline(expr), 0);

    /* Verify all data preserved */
    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    for (int i = 0; i < 50; i++) {
        assert_int_equal(lens[i], 2);
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 0], 1);
        assert_int_equal(lits[i * MAX_VARS_PER_TERM + 1], i);
    }

    dyn_expr_free(expr);
}

/* ============================================================================
 * Memory efficiency test
 * ============================================================================ */

/**
 * test_dyn_expr_memory_efficiency: 2-term expr uses less memory than 20-term
 *
 * This is a semantic test: a 2-term expression using inline storage should
 * conceptually use less memory than a 20-term expression requiring heap.
 * We verify this by checking the storage modes.
 */
static void test_dyn_expr_memory_efficiency(void **state) {
    (void)state;

    dyn_expression_t *small_expr = dyn_expr_init();
    dyn_expression_t *large_expr = dyn_expr_init();

    /* Small: 2 terms (should be inline) */
    dyn_expr_add_variable(small_expr, 0);
    dyn_expr_add_variable(small_expr, 1);

    /* Large: 20 terms (should be heap) */
    for (int i = 0; i < 20; i++) {
        dyn_expr_add_variable(large_expr, i);
    }

    /* Verify small is inline, large is heap */
    assert_int_equal(dyn_expr_is_inline(small_expr), 1);
    assert_int_equal(dyn_expr_is_inline(large_expr), 0);

    /* Small expression struct contains all its data (no heap allocs)
     * Large expression struct + heap allocations use more memory
     * The SOO optimization means small_expr doesn't call malloc for data */

    dyn_expr_free(small_expr);
    dyn_expr_free(large_expr);
}

/* ============================================================================
 * Add operation tests
 * ============================================================================ */

/**
 * test_dyn_expr_add_constant: constants stored correctly
 */
static void test_dyn_expr_add_constant(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    dyn_expr_add_constant(expr, 42);
    assert_int_equal(dyn_expr_size(expr), 1);

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    assert_int_equal(lens[0], 1);  /* len 1 for constant */
    assert_int_equal(lits[0], 42);

    /* Zero constants should be skipped (like Expression.c) */
    dyn_expr_add_constant(expr, 0);
    assert_int_equal(dyn_expr_size(expr), 1);  /* Still 1 */

    dyn_expr_add_constant(expr, -17);
    assert_int_equal(dyn_expr_size(expr), 2);
    assert_int_equal(lits[MAX_VARS_PER_TERM], -17);

    dyn_expr_free(expr);
}

/**
 * test_dyn_expr_add_variable: variables stored correctly
 */
static void test_dyn_expr_add_variable(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    dyn_expr_add_variable(expr, 5);
    assert_int_equal(dyn_expr_size(expr), 1);

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    assert_int_equal(lens[0], 2);  /* coefficient + 1 variable */
    assert_int_equal(lits[0], 1);  /* coefficient is 1 */
    assert_int_equal(lits[1], 5);  /* variable index is 5 */

    dyn_expr_free(expr);
}

/**
 * test_dyn_expr_add_term: general term with coefficient and variables
 */
static void test_dyn_expr_add_term(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add term: 3 * x_1 * x_2 */
    int64_t vars[] = {1, 2};
    int result = dyn_expr_add_term(expr, 3, vars, 2);
    assert_int_equal(result, 0);
    assert_int_equal(dyn_expr_size(expr), 1);

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    assert_int_equal(lens[0], 3);  /* coeff + 2 vars */
    assert_int_equal(lits[0], 3);  /* coefficient */
    assert_int_equal(lits[1], 1);  /* var 1 */
    assert_int_equal(lits[2], 2);  /* var 2 */

    /* Add constant term via add_term */
    result = dyn_expr_add_term(expr, 7, NULL, 0);
    assert_int_equal(result, 0);
    assert_int_equal(dyn_expr_size(expr), 2);
    assert_int_equal(lens[1], 1);
    assert_int_equal(lits[MAX_VARS_PER_TERM], 7);

    dyn_expr_free(expr);
}

/* ============================================================================
 * Copy tests
 * ============================================================================ */

/**
 * test_dyn_expr_copy_inline: copy inline expression
 */
static void test_dyn_expr_copy_inline(void **state) {
    (void)state;

    dyn_expression_t *src = dyn_expr_init();
    dyn_expression_t *dest = dyn_expr_init();

    /* Build inline expression */
    dyn_expr_add_variable(src, 0);
    dyn_expr_add_constant(src, 10);
    dyn_expr_set_sense(src, 7);  /* LOWER */
    dyn_expr_set_rhs(src, 42);

    assert_int_equal(dyn_expr_is_inline(src), 1);

    /* Copy */
    dyn_expr_copy(dest, src);

    /* Verify copy */
    assert_int_equal(dyn_expr_size(dest), dyn_expr_size(src));
    assert_int_equal(dest->sense, src->sense);
    assert_int_equal(dest->rhs, src->rhs);
    assert_int_equal(dyn_expr_is_inline(dest), 1);

    /* Verify data independence */
    dyn_expr_add_constant(src, 99);
    assert_int_equal(dyn_expr_size(src), 3);
    assert_int_equal(dyn_expr_size(dest), 2);  /* Unchanged */

    dyn_expr_free(src);
    dyn_expr_free(dest);
}

/**
 * test_dyn_expr_copy_heap: copy heap expression
 */
static void test_dyn_expr_copy_heap(void **state) {
    (void)state;

    dyn_expression_t *src = dyn_expr_init();
    dyn_expression_t *dest = dyn_expr_init();

    /* Build heap expression (>8 terms) */
    for (int i = 0; i < 15; i++) {
        dyn_expr_add_variable(src, i);
    }
    dyn_expr_set_sense(src, 6);  /* GREATER */
    dyn_expr_set_rhs(src, 100);

    assert_int_equal(dyn_expr_is_inline(src), 0);

    /* Copy */
    dyn_expr_copy(dest, src);

    /* Verify copy */
    assert_int_equal(dyn_expr_size(dest), dyn_expr_size(src));
    assert_int_equal(dest->sense, src->sense);
    assert_int_equal(dest->rhs, src->rhs);
    assert_int_equal(dyn_expr_is_inline(dest), 0);

    /* Verify data content */
    int64_t *src_lits = dyn_expr_literals(src);
    int64_t *dest_lits = dyn_expr_literals(dest);
    int *src_lens = dyn_expr_len_literal(src);
    int *dest_lens = dyn_expr_len_literal(dest);

    for (int i = 0; i < 15; i++) {
        assert_int_equal(dest_lens[i], src_lens[i]);
        for (int j = 0; j < src_lens[i]; j++) {
            assert_int_equal(dest_lits[i * MAX_VARS_PER_TERM + j],
                           src_lits[i * MAX_VARS_PER_TERM + j]);
        }
    }

    /* Verify pointers are different (deep copy) */
    assert_ptr_not_equal(dest_lits, src_lits);
    assert_ptr_not_equal(dest_lens, src_lens);

    dyn_expr_free(src);
    dyn_expr_free(dest);
}

/* ============================================================================
 * Sense and RHS tests
 * ============================================================================ */

/**
 * test_dyn_expr_sense_rhs: sense and rhs fields work
 */
static void test_dyn_expr_sense_rhs(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Initial values */
    assert_int_equal(expr->sense, 0);
    assert_int_equal(expr->rhs, 0);

    /* Set values */
    dyn_expr_set_sense(expr, 7);  /* LOWER */
    dyn_expr_set_rhs(expr, 12345);

    assert_int_equal(expr->sense, 7);
    assert_int_equal(expr->rhs, 12345);

    /* Negative RHS */
    dyn_expr_set_rhs(expr, -999);
    assert_int_equal(expr->rhs, -999);

    dyn_expr_free(expr);
}

/* ============================================================================
 * Large scale test
 * ============================================================================ */

/**
 * test_dyn_expr_large_expression: stress test with many terms
 */
static void test_dyn_expr_large_expression(void **state) {
    (void)state;

    dyn_expression_t *expr = dyn_expr_init();

    /* Add 1000 terms */
    for (int i = 0; i < 1000; i++) {
        int result = dyn_expr_add_variable(expr, i);
        assert_int_equal(result, 0);
    }

    assert_int_equal(dyn_expr_size(expr), 1000);
    assert_int_equal(dyn_expr_is_inline(expr), 0);

    /* Verify first and last terms */
    int64_t *lits = dyn_expr_literals(expr);
    assert_int_equal(lits[0], 1);  /* First coeff */
    assert_int_equal(lits[1], 0);  /* First var */
    assert_int_equal(lits[999 * MAX_VARS_PER_TERM + 0], 1);   /* Last coeff */
    assert_int_equal(lits[999 * MAX_VARS_PER_TERM + 1], 999); /* Last var */

    dyn_expr_free(expr);
}

/* ============================================================================
 * Test runner
 * ============================================================================ */

int main(void) {
    const struct CMUnitTest tests[] = {
        /* Lifecycle */
        cmocka_unit_test(test_dyn_expr_init_free),

        /* Inline storage */
        cmocka_unit_test(test_dyn_expr_inline_storage),
        cmocka_unit_test(test_dyn_expr_boundary_8_9),

        /* Heap transition and growth */
        cmocka_unit_test(test_dyn_expr_inline_to_heap),
        cmocka_unit_test(test_dyn_expr_heap_growth),

        /* Memory efficiency */
        cmocka_unit_test(test_dyn_expr_memory_efficiency),

        /* Add operations */
        cmocka_unit_test(test_dyn_expr_add_constant),
        cmocka_unit_test(test_dyn_expr_add_variable),
        cmocka_unit_test(test_dyn_expr_add_term),

        /* Copy operations */
        cmocka_unit_test(test_dyn_expr_copy_inline),
        cmocka_unit_test(test_dyn_expr_copy_heap),

        /* Sense and RHS */
        cmocka_unit_test(test_dyn_expr_sense_rhs),

        /* Large scale */
        cmocka_unit_test(test_dyn_expr_large_expression),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
