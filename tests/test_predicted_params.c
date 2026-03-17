/**
 * @file test_predicted_params.c
 * @brief Tests for solver_ctx_set_predicted_params() consolidated setter
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <stdlib.h>

/* Undefine compat macro so tests can access all three fields explicitly */
#include "solver_ctx.h"
#undef branching_stats

/* ============================================================
 * Setup/Teardown
 * ============================================================ */

static int setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) {
        return -1;
    }
    *state = ctx;
    return 0;
}

static int teardown(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_free(ctx);
    *state = NULL;
    return 0;
}

/* ============================================================
 * Tests
 * ============================================================ */

/* test_sets_bias_on_all_three_phases:
 * bias should be written to sat, opt_sat, and opt. */
static void test_sets_bias_on_all_three_phases(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0, 3.0};
    double priorities[] = {0.5, 1.5, 0.8};
    solver_ctx_set_predicted_params(ctx, 42.0, 2.5, 3.0, weights, priorities, 3);

    assert_true(ctx->branching_stats_sat.bias == 42.0);
    assert_true(ctx->branching_stats_opt_sat.bias == 42.0);
    assert_true(ctx->branching_stats_opt.bias == 42.0);
}

/* test_sets_branching_factor_on_all_three_phases:
 * branching_factor should be written to sat, opt_sat, and opt. */
static void test_sets_branching_factor_on_all_three_phases(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0};
    double priorities[] = {0.5, 1.5};
    solver_ctx_set_predicted_params(ctx, 10.0, 2.5, 3.0, weights, priorities, 2);

    assert_true(ctx->branching_stats_sat.branching_factor == 2.5);
    assert_true(ctx->branching_stats_opt_sat.branching_factor == 2.5);
    assert_true(ctx->branching_stats_opt.branching_factor == 2.5);
}

/* test_sets_bias_factor_on_all_three_phases:
 * bias_factor should be written to sat, opt_sat, and opt. */
static void test_sets_bias_factor_on_all_three_phases(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0};
    double priorities[] = {0.5, 1.5};
    solver_ctx_set_predicted_params(ctx, 10.0, 2.5, 3.0, weights, priorities, 2);

    assert_true(ctx->branching_stats_sat.bias_factor == 3.0);
    assert_true(ctx->branching_stats_opt_sat.bias_factor == 3.0);
    assert_true(ctx->branching_stats_opt.bias_factor == 3.0);
}

/* test_sets_weights_on_all_three_phases:
 * branching_weights should be set (L1-normalized) on all three phases. */
static void test_sets_weights_on_all_three_phases(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 3.0};
    double priorities[] = {0.5, 1.5};
    solver_ctx_set_predicted_params(ctx, 10.0, 1.0, 1.0, weights, priorities, 2);

    /* Weights are L1-normalized: [1/4, 3/4] */
    assert_non_null(ctx->branching_stats_sat.branching_weights);
    assert_non_null(ctx->branching_stats_opt_sat.branching_weights);
    assert_non_null(ctx->branching_stats_opt.branching_weights);

    assert_int_equal(ctx->branching_stats_sat.num_weights, 2);
    assert_int_equal(ctx->branching_stats_opt_sat.num_weights, 2);
    assert_int_equal(ctx->branching_stats_opt.num_weights, 2);

    assert_true(fabs(ctx->branching_stats_sat.branching_weights[0] - 0.25) < 1e-10);
    assert_true(fabs(ctx->branching_stats_sat.branching_weights[1] - 0.75) < 1e-10);
    assert_true(fabs(ctx->branching_stats_opt.branching_weights[0] - 0.25) < 1e-10);
    assert_true(fabs(ctx->branching_stats_opt.branching_weights[1] - 0.75) < 1e-10);
}

/* test_sets_variable_order_on_all_three_phases:
 * variable_order should be set from priorities on all three phases. */
static void test_sets_variable_order_on_all_three_phases(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0, 3.0};
    /* priorities: index 1 (1.5) > index 2 (0.8) > index 0 (0.5) */
    double priorities[] = {0.5, 1.5, 0.8};
    solver_ctx_set_predicted_params(ctx, 10.0, 1.0, 1.0, weights, priorities, 3);

    /* Check all three phases have variable_order set */
    assert_non_null(ctx->branching_stats_sat.variable_order);
    assert_non_null(ctx->branching_stats_opt_sat.variable_order);
    assert_non_null(ctx->branching_stats_opt.variable_order);

    assert_int_equal(ctx->branching_stats_sat.num_vars, 3);
    assert_int_equal(ctx->branching_stats_opt_sat.num_vars, 3);
    assert_int_equal(ctx->branching_stats_opt.num_vars, 3);

    /* Order should be [1, 2, 0] (descending priority) */
    assert_int_equal(ctx->branching_stats_sat.variable_order[0], 1);
    assert_int_equal(ctx->branching_stats_sat.variable_order[1], 2);
    assert_int_equal(ctx->branching_stats_sat.variable_order[2], 0);

    assert_int_equal(ctx->branching_stats_opt.variable_order[0], 1);
    assert_int_equal(ctx->branching_stats_opt.variable_order[1], 2);
    assert_int_equal(ctx->branching_stats_opt.variable_order[2], 0);
}

/* test_null_weights_clears_weights:
 * Passing NULL weights should clear weights on all phases. */
static void test_null_weights_clears_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* First set weights */
    double weights[] = {1.0, 2.0};
    double priorities[] = {0.5, 1.5};
    solver_ctx_set_predicted_params(ctx, 10.0, 1.0, 1.0, weights, priorities, 2);
    assert_non_null(ctx->branching_stats_sat.branching_weights);

    /* Now call with NULL weights */
    solver_ctx_set_predicted_params(ctx, 10.0, 1.0, 1.0, NULL, priorities, 2);
    assert_null(ctx->branching_stats_sat.branching_weights);
    assert_null(ctx->branching_stats_opt_sat.branching_weights);
    assert_null(ctx->branching_stats_opt.branching_weights);
}

/* test_null_priorities_sets_default_order:
 * Passing NULL priorities should set default identity order. */
static void test_null_priorities_sets_default_order(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0, 3.0};
    solver_ctx_set_predicted_params(ctx, 10.0, 1.0, 1.0, weights, NULL, 3);

    /* Default order should be [0, 1, 2] */
    assert_non_null(ctx->branching_stats_sat.variable_order);
    assert_int_equal(ctx->branching_stats_sat.variable_order[0], 0);
    assert_int_equal(ctx->branching_stats_sat.variable_order[1], 1);
    assert_int_equal(ctx->branching_stats_sat.variable_order[2], 2);
}

/* test_null_ctx_does_not_crash:
 * Passing NULL ctx should be a no-op. */
static void test_null_ctx_does_not_crash(void **state) {
    (void)state;
    double weights[] = {1.0};
    double priorities[] = {1.0};
    solver_ctx_set_predicted_params(NULL, 10.0, 1.0, 1.0, weights, priorities, 1);
    /* If we get here without crashing, the test passes */
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_sets_bias_on_all_three_phases, setup, teardown),
        cmocka_unit_test_setup_teardown(test_sets_branching_factor_on_all_three_phases, setup, teardown),
        cmocka_unit_test_setup_teardown(test_sets_bias_factor_on_all_three_phases, setup, teardown),
        cmocka_unit_test_setup_teardown(test_sets_weights_on_all_three_phases, setup, teardown),
        cmocka_unit_test_setup_teardown(test_sets_variable_order_on_all_three_phases, setup, teardown),
        cmocka_unit_test_setup_teardown(test_null_weights_clears_weights, setup, teardown),
        cmocka_unit_test_setup_teardown(test_null_priorities_sets_default_order, setup, teardown),
        cmocka_unit_test_setup_teardown(test_null_ctx_does_not_crash, setup, teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
