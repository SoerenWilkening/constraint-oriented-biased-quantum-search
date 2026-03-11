#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "Branching.h"
#include "solver_ctx.h"
#include "definitions.h"
#include "prng.h"

/*
 * Helper: build a small model with 3 variables, 1 constraint x0+x1+x2 <= 2,
 * objective -(x0+x1+x2). Returns model and solver context.
 */
static model_t *build_small_model(void) {
    model_t *mod = init_model();

    /* Build constraint: x0 + x1 + x2 <= 2 */
    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    add_variable(con_expr, 1);
    add_variable(con_expr, 2);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 2);
    add_expression_to_constraints(mod->con, con_expr);

    /* Build objective: -(x0 + x1 + x2) */
    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    multiply_constant(obj_expr, -1);
    add_variable(obj_expr, 1);
    multiply_constant(obj_expr, -1);
    add_variable(obj_expr, 2);
    multiply_constant(obj_expr, -1);
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

    preprocessing(3, mod->con);
    preprocessing(3, mod->obj);

    int arr[3] = {0, 0, 0};
    mod->initial_state = init_state(0, arr, 3);
    mod->initial_state->tot_profit = INT64_MAX;
    mod->global_opt = init_state(0, arr, 3);
    mod->global_opt->tot_profit = INT64_MAX;

    mod->n = 3;
    mod->M = 10;
    mod->depth_look_ahead = 0;
    mod->stopping_time = 100;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);

    return mod;
}

/*
 * test_identity_ordering_matches_original:
 * With identity ordering [0,1,2], CSearch_sat should behave the same
 * as with NULL ordering (no variable_order set).
 */
static void test_identity_ordering_matches_original(void **state) {
    (void)state;

    /* Run with NULL ordering */
    model_t *mod1 = build_small_model();
    solver_ctx_t *ctx1 = solver_ctx_create();
    assert_non_null(ctx1);
    solver_ctx_init_prng(ctx1);
    ctx1->seed = 42;
    solver_ctx_init_prng(ctx1);

    int arr1[3] = {1, 1, 0};
    state_t *sol1 = init_state(0, arr1, 3);
    sol1->tot_profit = 0;
    int samples1 = 0;
    prng_state_t prng1;
    prng_seed_from_state(&prng1, 42);

    int result1 = CSearch_sat(ctx1, sol1, 1, mod1->con, mod1->obj, 0, 1, NULL, &samples1);

    /* Run with identity ordering */
    model_t *mod2 = build_small_model();
    solver_ctx_t *ctx2 = solver_ctx_create();
    assert_non_null(ctx2);
    ctx2->seed = 42;
    solver_ctx_init_prng(ctx2);
    solver_ctx_set_default_order(ctx2, 3);

    int arr2[3] = {1, 1, 0};
    state_t *sol2 = init_state(0, arr2, 3);
    sol2->tot_profit = 0;
    int samples2 = 0;

    int result2 = CSearch_sat(ctx2, sol2, 1, mod2->con, mod2->obj, 0, 1, NULL, &samples2);

    /* Both should produce the same result */
    assert_int_equal(result1, result2);
    assert_int_equal(samples1, samples2);

    free_state(sol1, 1);
    free_state(sol2, 1);
    solver_ctx_free(ctx1);
    solver_ctx_free(ctx2);
    free_model(mod1);
    free_model(mod2);
}

/*
 * test_csearch_sat_respects_ordering:
 * With a non-identity ordering, CSearch_sat should process variables
 * in the specified order. We can verify this doesn't crash and runs.
 */
static void test_csearch_sat_respects_ordering(void **state) {
    (void)state;

    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    /* Reverse ordering: [2, 1, 0] */
    double priorities[] = {1.0, 2.0, 3.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);
    /* Descending sort: var2(3.0), var1(2.0), var0(1.0) → [2,1,0] */
    assert_int_equal(ctx->branching_stats.variable_order[0], 2);
    assert_int_equal(ctx->branching_stats.variable_order[1], 1);
    assert_int_equal(ctx->branching_stats.variable_order[2], 0);

    int arr[3] = {1, 1, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = 0;
    int samples = 0;

    /* Should not crash with custom ordering */
    int result CBQS_UNUSED = CSearch_sat(ctx, sol, 1, mod->con, mod->obj, 0, 1, NULL, &samples);

    /* Verify state is valid */
    assert_int_equal(sol->vector.bits, 3);

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/*
 * test_csearch_opt_respects_ordering:
 * CSearch_opt with custom ordering should not crash.
 */
static void test_csearch_opt_respects_ordering(void **state) {
    (void)state;

    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    /* Custom ordering: [1, 2, 0] */
    double priorities[] = {1.0, 3.0, 2.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);

    int arr[3] = {1, 1, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = -2;
    sol->feasible = 1;
    int samples = 0;

    int result CBQS_UNUSED = CSearch_opt(ctx, sol, 1, mod->con, mod->obj, 0, 1, NULL, &samples);

    assert_int_equal(sol->vector.bits, 3);

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/*
 * test_csearch_opt_sat_respects_ordering:
 * CSearch_opt_sat with custom ordering should not crash.
 */
static void test_csearch_opt_sat_respects_ordering(void **state) {
    (void)state;

    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    /* Custom ordering: [2, 0, 1] */
    double priorities[] = {2.0, 1.0, 3.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);

    int arr[3] = {0, 0, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = INT64_MAX;
    sol->feasible = 0;
    int samples = 0;

    int result CBQS_UNUSED = CSearch_opt_sat(ctx, sol, 1, mod->con, mod->obj, 0, 1, NULL, &samples);

    assert_int_equal(sol->vector.bits, 3);

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/*
 * test_null_ordering_works:
 * With no variable_order set (NULL), CSearch should work as before.
 */
static void test_null_ordering_works(void **state) {
    (void)state;

    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    /* No ordering set — variable_order is NULL */
    assert_null(ctx->branching_stats.variable_order);

    int arr[3] = {1, 0, 1};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = 0;
    int samples = 0;

    int result CBQS_UNUSED = CSearch_sat(ctx, sol, 1, mod->con, mod->obj, 0, 1, NULL, &samples);

    assert_int_equal(sol->vector.bits, 3);

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/*
 * test_ordering_with_weights_combined:
 * Custom ordering + branching weights should work together.
 */
static void test_ordering_with_weights_combined(void **state) {
    (void)state;

    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    /* Set custom ordering */
    double priorities[] = {1.0, 3.0, 2.0};
    solver_ctx_set_variable_order(ctx, priorities, 3);

    /* Set branching weights */
    double weights[] = {0.5, 0.3, 0.2};
    solver_ctx_set_branching_weights(ctx, weights, 3);

    int arr[3] = {1, 1, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = 0;
    int samples = 0;

    int result CBQS_UNUSED = CSearch_sat(ctx, sol, 1, mod->con, mod->obj, 0, 1, NULL, &samples);

    assert_int_equal(sol->vector.bits, 3);

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_identity_ordering_matches_original),
        cmocka_unit_test(test_csearch_sat_respects_ordering),
        cmocka_unit_test(test_csearch_opt_respects_ordering),
        cmocka_unit_test(test_csearch_opt_sat_respects_ordering),
        cmocka_unit_test(test_null_ordering_works),
        cmocka_unit_test(test_ordering_with_weights_combined),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
