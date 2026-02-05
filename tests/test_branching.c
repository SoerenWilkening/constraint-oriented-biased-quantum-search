#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>

#include "Branching.h"
#include "solver_ctx.h"
#include "definitions.h"

/* ============================================================
 * Setup/Teardown using solver_ctx_t
 * ============================================================ */

/* Setup fixture: create solver context */
static int branching_setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) {
        return -1;  /* Allocation failure */
    }
    *state = ctx;  /* Store ctx for use in tests */
    return 0;
}

/* Teardown: free solver context */
static int branching_teardown(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_free(ctx);
    *state = NULL;
    return 0;
}

/* ============================================================
 * Tests for solver_ctx_t setters (new API)
 * ============================================================ */

/* test_ctx_set_factors: verify solver_ctx_set_factors writes to ctx */
static void test_ctx_set_factors(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 1.0, 2.0, 3.0, 4.0);
    assert_true(ctx->branching_stats.objective_factor == 1.0);
    assert_true(ctx->branching_stats.constraint_factor == 2.0);
    assert_true(ctx->branching_stats.bias_factor == 3.0);
    assert_true(ctx->branching_stats.look_factor == 4.0);
}

/* test_ctx_set_bias: verify solver_ctx_set_bias writes to ctx */
static void test_ctx_set_bias(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, 5.0);
    assert_true(ctx->branching_stats.bias == 5.0);
}

/* test_ctx_set_obj_dependence: verify array is copied to ctx */
static void test_ctx_set_obj_dependence(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {0.5, 0.5};
    solver_ctx_set_obj_dependence(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.obj_dependent);
    assert_true(fabs(ctx->branching_stats.obj_dependent[0] - 0.5) < 1e-9);
    assert_true(fabs(ctx->branching_stats.obj_dependent[1] - 0.5) < 1e-9);
}

/* test_ctx_set_constraint_dependence: verify array is copied to ctx */
static void test_ctx_set_constraint_dependence(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {0.3, 0.7};
    solver_ctx_set_constraint_dependence(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.constraint_dependent);
    assert_true(fabs(ctx->branching_stats.constraint_dependent[0] - 0.3) < 1e-9);
    assert_true(fabs(ctx->branching_stats.constraint_dependent[1] - 0.7) < 1e-9);
}

/* ============================================================
 * Tests for BranchingFunction using ctx->branching_stats
 * ============================================================ */

/* test_branching_function_equal_bits:
 * factors=(1,0,0,0), obj_dependent=[0.5, 0.5]
 * bit_S=0, bit_T=0 (both 0): result = 1/1 * 1 * 0.5 = 0.5 */
static void test_branching_function_equal_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 1.0, 0.0, 0.0, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_obj_dependence(ctx, arr, 2);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    /* Formula: 1/(1+0+0+0) * 1.0 * 0.5 = 0.5 */
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* test_branching_function_different_bits:
 * bit_S=0, bit_T=1 => subtractive branch */
static void test_branching_function_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 1.0, 0.0, 0.0, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_obj_dependence(ctx, arr, 2);

    /* index=0, bit_S=0, bit_T=1 (different bits) */
    /* formula: 1 - 1/(1) * 1.0 * 0.5 = 1 - 0.5 = 0.5 */
    double result = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* test_branching_function_bias_only:
 * factors=(0,0,1,0), bias=2.0, both bits 0
 * result = 1/1 * 1 * (2+1)/(2+2) = 3/4 = 0.75 */
static void test_branching_function_bias_only(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 0.0, 0.0, 1.0, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    /* formula: 1/(0+0+1+0) * 1.0 * (2+1)/(2+2) = 3/4 = 0.75 */
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* test_branching_function_bias_different_bits:
 * factors=(0,0,1,0), bias=2.0, bit_S=1, bit_T=0
 * result = 1 - 0.75 = 0.25 */
static void test_branching_function_bias_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 0.0, 0.0, 1.0, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* index=0, bit_S=1, bit_T=0 (different bits) */
    double result = BranchingFunction(0, 1, 0, 0, &ctx->branching_stats);
    /* formula: 1 - 1/1 * 1 * (2+1)/(2+2) = 1 - 0.75 = 0.25 */
    assert_true(fabs(result - 0.25) < 1e-9);
}

/* test_branching_function_both_bits_one:
 * factors=(0,0,1,0), bias=2.0, both bits 1
 * Same as both bits 0: result = 0.75 */
static void test_branching_function_both_bits_one(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_factors(ctx, 0.0, 0.0, 1.0, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* bit_S=1, bit_T=1 (both 1) */
    double result = BranchingFunction(0, 1, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* ============================================================
 * Tests for StateProbability using ctx
 * ============================================================ */

/* test_state_probability: verify result is valid probability */
static void test_state_probability(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Configure branching with bias only */
    solver_ctx_set_factors(ctx, 0.0, 0.0, 1.0, 0.0);
    solver_ctx_set_bias(ctx, 5.0);

    int arr1[] = {1, 0, 1};
    state_t *s = init_state(0, arr1, 3);
    /* Set branch bits to mark which are "branched" */
    sw_setbit(s->branch, 0);
    sw_setbit(s->branch, 1);
    sw_setbit(s->branch, 2);

    int arr2[] = {1, 0, 0};
    state_t *threshold = init_state(0, arr2, 3);

    double prob = StateProbability(ctx, s, threshold);
    assert_true(prob >= 0.0);
    assert_true(prob <= 1.0);

    free_state(s, 1);
    free_state(threshold, 1);
}

/* test_state_probability_identical: identical states => high prob */
static void test_state_probability_identical(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Configure branching */
    solver_ctx_set_factors(ctx, 0.0, 0.0, 1.0, 0.0);
    solver_ctx_set_bias(ctx, 5.0);

    int arr[] = {1, 0, 1};
    state_t *s = init_state(0, arr, 3);
    sw_setbit(s->branch, 0);
    sw_setbit(s->branch, 1);
    sw_setbit(s->branch, 2);

    state_t *threshold = init_state(0, arr, 3);

    double prob = StateProbability(ctx, s, threshold);
    /* When both states are identical, each bit contributes (bias+1)/(bias+2) */
    /* With bias=5: (6/7)^3 ~ 0.6297 */
    double expected = pow(6.0 / 7.0, 3.0);
    assert_true(fabs(prob - expected) < 1e-9);

    free_state(s, 1);
    free_state(threshold, 1);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        /* New ctx-based setter tests */
        cmocka_unit_test_setup_teardown(test_ctx_set_factors, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_ctx_set_bias, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_ctx_set_obj_dependence, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_ctx_set_constraint_dependence, branching_setup, branching_teardown),
        /* BranchingFunction tests using ctx->branching_stats */
        cmocka_unit_test_setup_teardown(test_branching_function_equal_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_only, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_both_bits_one, branching_setup, branching_teardown),
        /* StateProbability tests using ctx */
        cmocka_unit_test_setup_teardown(test_state_probability, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_state_probability_identical, branching_setup, branching_teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
