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

/* test_ctx_set_factors: verify individual factor setters write to ctx */
static void test_ctx_set_factors(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 3.0);
    solver_ctx_set_look_ahead_factor(ctx, 4.0);
    assert_true(ctx->branching_stats.branching_factor == 1.0);
    assert_true(ctx->branching_stats.bias_factor == 3.0);
    assert_true(ctx->branching_stats.look_ahead_factor == 4.0);
}

/* test_ctx_set_bias: verify solver_ctx_set_bias writes to ctx */
static void test_ctx_set_bias(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, 5.0);
    assert_true(ctx->branching_stats.bias == 5.0);
}

/* test_ctx_set_branching_weights: verify array is copied and L1-normalized */
static void test_ctx_set_branching_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {0.5, 0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    /* L1 norm of [0.5, 0.5] = 1.0, so normalized = [0.5, 0.5] */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 0.5) < 1e-9);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 0.5) < 1e-9);
}

/* ============================================================
 * Tests for BranchingFunction using ctx->branching_stats
 * ============================================================ */

/* test_branching_function_equal_bits:
 * branching_factor=1.0, bias_factor=0.0, look_factor=0.0
 * branching_weights=[0.5, 0.5]
 * bit_S=0, bit_T=0: value = 1/(1) * 1.0 * 0.5 = 0.5 */
static void test_branching_function_equal_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    /* Formula: 1/(1+0+0) * 1.0 * 0.5 = 0.5 */
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* test_branching_function_different_bits:
 * bit_S=0, bit_T=1 => subtractive branch */
static void test_branching_function_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);

    /* index=0, bit_S=0, bit_T=1 (different bits) */
    /* formula: 1 - 1/(1) * 1.0 * 0.5 = 1 - 0.5 = 0.5 */
    double result = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* test_branching_function_bias_only:
 * bias_factor=1.0, bias=2.0, no weights
 * result = 1/1 * 1 * (2+1)/(2+2) = 3/4 = 0.75 */
static void test_branching_function_bias_only(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    /* formula: 1/(0+1+0) * 1.0 * (2+1)/(2+2) = 3/4 = 0.75 */
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* test_branching_function_bias_different_bits:
 * bias_factor=1.0, bias=2.0, bit_S=1, bit_T=0
 * result = 1 - 0.75 = 0.25 */
static void test_branching_function_bias_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* index=0, bit_S=1, bit_T=0 (different bits) */
    double result = BranchingFunction(0, 1, 0, 0, &ctx->branching_stats);
    /* formula: 1 - 1/1 * 1 * (2+1)/(2+2) = 1 - 0.75 = 0.25 */
    assert_true(fabs(result - 0.25) < 1e-9);
}

/* test_branching_function_both_bits_one:
 * bias_factor=1.0, bias=2.0, both bits 1
 * Same as both bits 0: result = 0.75 */
static void test_branching_function_both_bits_one(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    /* bit_S=1, bit_T=1 (both 1) */
    double result = BranchingFunction(0, 1, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* test_branching_function_null_weights:
 * No weights set, verify 2-term formula (bias only when look_factor=0) */
static void test_branching_function_null_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    /* Default: branching_weights = NULL, bias_factor=1, bias=5, look_factor=0 */
    /* 2-term formula: normalizer = 1/(1+0) = 1, value = 1 * (5+1)/(5+2) = 6/7 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    double expected = 6.0 / 7.0;
    assert_true(fabs(result - expected) < 1e-9);
}

/* test_branching_function_3term:
 * All three terms active: branching_factor=1, bias_factor=1, look_factor=1
 * weights=[0.8, 0.2], bias=2.0, diffcount=1 (non-zero so look_factor stays)
 *
 * factor_sum = 1 + 1 + 1 = 3, normalizer = 1/3
 * branching term: 1/3 * 1 * 0.8 = 0.2667
 * bias term: 1/3 * 1 * (3/4) = 0.25
 * look term: 1/3 * 1 * 1.0 = 0.3333 (diffcount=1 >= 0, lookahead=1.0)
 * value = 0.2667 + 0.25 + 0.3333 = 0.85 */
static void test_branching_function_3term(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 1.0);
    solver_ctx_set_bias(ctx, 2.0);
    double arr[] = {0.8, 0.2};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    /* After L1 normalization: [0.8, 0.2] */

    /* index=0, bit_S=0, bit_T=0, diffcount=1 */
    double result = BranchingFunction(0, 0, 0, 1, &ctx->branching_stats);
    /* normalizer = 1/3
     * branching: 1/3 * 1.0 * 0.8 = 0.26667
     * bias: 1/3 * 1.0 * 3/4 = 0.25
     * look: 1/3 * 1.0 * 1.0 = 0.33333
     * value = 0.85 */
    double expected = (1.0/3.0) * 0.8 + (1.0/3.0) * 0.75 + (1.0/3.0) * 1.0;
    assert_true(fabs(result - expected) < 1e-9);
}

/* test_branching_weights_normalization:
 * Set weights [2.0, 8.0], verify stored as [0.2, 0.8] after L1 normalization */
static void test_branching_weights_normalization(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {2.0, 8.0};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 0.2) < 1e-9);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 0.8) < 1e-9);
}

/* test_branching_weights_overwrite:
 * Call set_branching_weights twice, verify first array freed (no ASan leak) */
static void test_branching_weights_overwrite(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr1[] = {1.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr1, 2);
    assert_non_null(ctx->branching_stats.branching_weights);

    double arr2[] = {3.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr2, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    /* L1 norm of [3.0, 1.0] = 4.0, so normalized = [0.75, 0.25] */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 0.75) < 1e-9);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 0.25) < 1e-9);
}

/* test_branching_weights_clear:
 * Call set_branching_weights then set with NULL, verify pointer is NULL */
static void test_branching_weights_clear(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {1.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);

    /* Clear by passing NULL */
    solver_ctx_set_branching_weights(ctx, NULL, 0);
    assert_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 0);
}

/* ============================================================
 * Tests for StateProbability using ctx
 * ============================================================ */

/* test_state_probability: verify result is valid probability */
static void test_state_probability(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Configure branching with bias only */
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
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
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
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

/* test_branching_function_all_factors_zero:
 * Set branching_factor=0, bias_factor=0, look_factor=0.
 * All factors zero means factor_sum=0, should trigger division-by-zero guard.
 * Expected result: 0.5 */
static void test_branching_function_all_factors_zero(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);

    /* No weights set, so factor_sum = bias_factor + look_factor = 0 + 0 = 0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.5) < 1e-9);

    /* Also test with different bits -- guard returns 0.5 regardless */
    double result_diff = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result_diff - 0.5) < 1e-9);
}

/* test_branching_weights_realloc_different_sizes:
 * Set weights of size 2, then overwrite with size 5, then clear with NULL.
 * Verify num_weights and stored values after each operation.
 * Tests memory reallocation with different sizes. */
static void test_branching_weights_realloc_different_sizes(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Step 1: Set weights of size 2 */
    double arr1[] = {1.0, 3.0};
    solver_ctx_set_branching_weights(ctx, arr1, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    /* L1 norm of [1.0, 3.0] = 4.0, normalized = [0.25, 0.75] */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 0.25) < 1e-9);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 0.75) < 1e-9);

    /* Step 2: Overwrite with size 5 (different size!) */
    double arr2[] = {1.0, 2.0, 3.0, 4.0, 5.0};
    solver_ctx_set_branching_weights(ctx, arr2, 5);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 5);
    /* L1 norm of [1,2,3,4,5] = 15.0, first weight = 1/15 */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0 / 15.0) < 1e-9);
    assert_true(fabs(ctx->branching_stats.branching_weights[4] - 5.0 / 15.0) < 1e-9);

    /* Step 3: Clear with NULL */
    solver_ctx_set_branching_weights(ctx, NULL, 0);
    assert_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 0);
}

/* test_branching_weights_single_element:
 * Set weights=[1.0] (single element). L1 norm of [1.0] = 1.0, stored = [1.0].
 * Call BranchingFunction with branching_factor=1.0, bias_factor=0, look_factor=0.
 * factor_sum = 0 + 0 + 1.0 = 1.0, normalizer = 1.0
 * value = 1.0 * 1.0 * 1.0 = 1.0
 * With bit_S=0, bit_T=0: total_bias = value = 1.0 */
static void test_branching_weights_single_element(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double arr[] = {1.0};
    solver_ctx_set_branching_weights(ctx, arr, 1);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 1);
    /* L1 norm of [1.0] = 1.0, stored value = 1.0 */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0) < 1e-9);

    /* BranchingFunction with only branching term active */
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    /* factor_sum = 0 + 0 + 1.0 = 1.0, normalizer = 1.0 */
    /* value = 1.0 * 1.0 * 1.0 = 1.0 */
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 1.0) < 1e-9);

    /* With different bits: total_bias = 1 - 1.0 = 0.0 */
    double result_diff = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result_diff - 0.0) < 1e-9);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        /* New ctx-based setter tests */
        cmocka_unit_test_setup_teardown(test_ctx_set_factors, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_ctx_set_bias, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_ctx_set_branching_weights, branching_setup, branching_teardown),
        /* BranchingFunction tests using ctx->branching_stats */
        cmocka_unit_test_setup_teardown(test_branching_function_equal_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_only, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_both_bits_one, branching_setup, branching_teardown),
        /* New tests for unified branching model */
        cmocka_unit_test_setup_teardown(test_branching_function_null_weights, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_3term, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_normalization, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_overwrite, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_clear, branching_setup, branching_teardown),
        /* StateProbability tests using ctx */
        cmocka_unit_test_setup_teardown(test_state_probability, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_state_probability_identical, branching_setup, branching_teardown),
        /* New coverage tests for edge cases */
        cmocka_unit_test_setup_teardown(test_branching_function_all_factors_zero, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_realloc_different_sizes, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_single_element, branching_setup, branching_teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
