#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "solver_ctx.h"
#include "Branching.h"

/* Setup fixture: create solver context */
static int setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) return -1;
    *state = ctx;
    return 0;
}

/* Teardown: free solver context */
static int teardown(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_free(ctx);
    *state = NULL;
    return 0;
}

/* test_default_ordering_is_identity: identity [0,1,2,...,n-1] */
static void test_default_ordering_is_identity(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_default_order(ctx, 5);

    assert_non_null(ctx->branching_stats.variable_order);
    assert_int_equal(ctx->branching_stats.num_vars, 5);
    for (int i = 0; i < 5; i++) {
        assert_int_equal(ctx->branching_stats.variable_order[i], i);
    }
}

/* test_set_priorities_produces_sorted_order: priorities [3,1,2] → order [0,2,1] */
static void test_set_priorities_produces_sorted_order(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double priorities[] = {3.0, 1.0, 2.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);

    assert_non_null(ctx->branching_stats.variable_order);
    assert_int_equal(ctx->branching_stats.num_vars, 3);
    /* Highest priority (3.0) is var 0, then (2.0) var 2, then (1.0) var 1 */
    assert_int_equal(ctx->branching_stats.variable_order[0], 0);
    assert_int_equal(ctx->branching_stats.variable_order[1], 2);
    assert_int_equal(ctx->branching_stats.variable_order[2], 1);
}

/* test_equal_priorities_stable_order: ties broken by index */
static void test_equal_priorities_stable_order(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double priorities[] = {1.0, 1.0, 1.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);

    assert_non_null(ctx->branching_stats.variable_order);
    /* Equal priorities → identity order (stable sort, ascending index) */
    assert_int_equal(ctx->branching_stats.variable_order[0], 0);
    assert_int_equal(ctx->branching_stats.variable_order[1], 1);
    assert_int_equal(ctx->branching_stats.variable_order[2], 2);
}

/* test_null_priorities_uses_default: NULL priorities clears ordering */
static void test_null_priorities_clears(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* First set an order */
    solver_ctx_set_default_order(ctx, 3);
    assert_non_null(ctx->branching_stats.variable_order);

    /* Clear with NULL */
    solver_ctx_set_variable_order(ctx, NULL, 0);
    assert_null(ctx->branching_stats.variable_order);
    assert_int_equal(ctx->branching_stats.num_vars, 0);
}

/* test_set_variable_order_from_degrees: degree-based ordering */
static void test_set_variable_order_from_degrees(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    /* degrees: var0=2, var1=5, var2=1, var3=5 */
    int degrees[] = {2, 5, 1, 5};
    solver_ctx_set_degree_order(ctx, degrees, 4);

    assert_non_null(ctx->branching_stats.variable_order);
    assert_int_equal(ctx->branching_stats.num_vars, 4);
    /* Highest degree first: var1(5), var3(5), var0(2), var2(1) */
    /* Ties broken by index: var1 before var3 */
    assert_int_equal(ctx->branching_stats.variable_order[0], 1);
    assert_int_equal(ctx->branching_stats.variable_order[1], 3);
    assert_int_equal(ctx->branching_stats.variable_order[2], 0);
    assert_int_equal(ctx->branching_stats.variable_order[3], 2);
}

/* test_free_releases_ordering_arrays: no leak when freeing ctx with ordering */
static void test_free_releases_ordering_arrays(void **state) {
    (void)state;
    /* Create and destroy ctx with ordering set - ASan will catch leaks */
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    solver_ctx_set_default_order(ctx, 100);
    assert_non_null(ctx->branching_stats.variable_order);
    solver_ctx_free(ctx);
}

/* test_overwrite_ordering: setting new order frees old one */
static void test_overwrite_ordering(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_default_order(ctx, 3);
    assert_int_equal(ctx->branching_stats.num_vars, 3);

    double priorities[] = {10.0, 1.0, 5.0, 3.0, 7.0};
    solver_ctx_set_variable_order(ctx, priorities, 5);
    assert_int_equal(ctx->branching_stats.num_vars, 5);
    /* Order: var0(10), var4(7), var2(5), var3(3), var1(1) */
    assert_int_equal(ctx->branching_stats.variable_order[0], 0);
    assert_int_equal(ctx->branching_stats.variable_order[1], 4);
    assert_int_equal(ctx->branching_stats.variable_order[2], 2);
    assert_int_equal(ctx->branching_stats.variable_order[3], 3);
    assert_int_equal(ctx->branching_stats.variable_order[4], 1);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_default_ordering_is_identity, setup, teardown),
        cmocka_unit_test_setup_teardown(test_set_priorities_produces_sorted_order, setup, teardown),
        cmocka_unit_test_setup_teardown(test_equal_priorities_stable_order, setup, teardown),
        cmocka_unit_test_setup_teardown(test_null_priorities_clears, setup, teardown),
        cmocka_unit_test_setup_teardown(test_set_variable_order_from_degrees, setup, teardown),
        cmocka_unit_test(test_free_releases_ordering_arrays),
        cmocka_unit_test_setup_teardown(test_overwrite_ordering, setup, teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
