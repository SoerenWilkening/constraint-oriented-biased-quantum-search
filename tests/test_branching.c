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

/* test_ctx_set_branching_weights: weights are copied and stored AS-IS
 * (M0f: NO L1 normalization, signed values preserved). */
static void test_ctx_set_branching_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {0.5, -0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    /* Stored verbatim -- including the negative entry (no normalization). */
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 0.5) < 1e-12);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - (-0.5)) < 1e-12);
}

/* ============================================================
 * Tests for BranchingFunction using ctx->branching_stats
 *
 * M0f form: base = (bias_factor*assignment_bias + look_ahead_factor*lookahead)
 *                  / (bias_factor + look_ahead_factor)   [0.5 if that sum <= 0]
 *           value = sigma(logit(base) + branching_factor*theta_i)  if offset!=0
 *                 = base                                            if offset==0
 * ============================================================ */

/* test_branching_function_equal_bits:
 * branching_factor=1.0, bias_factor=0.0, look_ahead_factor=0.0, weights=[0.5,0.5].
 * base: factor_sum=0 -> 0.5; offset = 1.0*0.5 = 0.5;
 * value = sigma(logit(0.5)+0.5) = sigma(0.5).  bit_S=0,bit_T=0 -> value. */
static void test_branching_function_equal_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);

    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    double expected = 1.0 / (1.0 + exp(-0.5));  /* sigma(0.5) ~ 0.62246 */
    assert_true(fabs(result - expected) < 1e-9);
}

/* test_branching_function_different_bits:
 * same as above but bit_S=0, bit_T=1 => subtractive branch => 1 - sigma(0.5) */
static void test_branching_function_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    double arr[] = {0.5, 0.5};
    solver_ctx_set_branching_weights(ctx, arr, 2);

    double result = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    double expected = 1.0 - 1.0 / (1.0 + exp(-0.5));
    assert_true(fabs(result - expected) < 1e-9);
}

/* test_branching_function_bias_only:
 * bias_factor=1.0, bias=2.0, no weights => value = base = (2+1)/(2+2) = 0.75.
 * (Baseline: unchanged by M0f -- the no-weights path returns base directly.) */
static void test_branching_function_bias_only(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* test_branching_function_bias_different_bits:
 * bias_factor=1.0, bias=2.0, bit_S=1, bit_T=0 => 1 - 0.75 = 0.25 */
static void test_branching_function_bias_different_bits(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    double result = BranchingFunction(0, 1, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.25) < 1e-9);
}

/* test_branching_function_both_bits_one:
 * bias_factor=1.0, bias=2.0, both bits 1 => same as both bits 0 => 0.75 */
static void test_branching_function_both_bits_one(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 2.0);

    double result = BranchingFunction(0, 1, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* test_branching_function_null_weights: THE branching golden value (NORTHSTAR §8).
 * Default: branching_weights = NULL, bias_factor=1, bias=5, look_ahead_factor=0.
 * No weights => value = base = (5+1)/(5+2) = 6/7. Must survive M0f bit-for-bit. */
static void test_branching_function_null_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    double expected = 6.0 / 7.0;
    assert_true(result == expected);  /* exact: no sigmoid round-trip on the no-weights path */
}

/* test_branching_function_3term:
 * branching_factor=1, bias_factor=1, look_ahead_factor=1, weights=[0.8,0.2],
 * bias=2.0, diffcount=1 (look_ahead live).
 * base = (1*0.75 + 1*1.0) / (1+1) = 0.875; offset = 1*0.8 = 0.8;
 * value = sigma(logit(0.875) + 0.8). */
static void test_branching_function_3term(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 1.0);
    solver_ctx_set_bias(ctx, 2.0);
    double arr[] = {0.8, 0.2};
    solver_ctx_set_branching_weights(ctx, arr, 2);

    double result = BranchingFunction(0, 0, 0, 1, &ctx->branching_stats);
    double base = 0.875;
    double expected = 1.0 / (1.0 + exp(-(log(base / (1.0 - base)) + 0.8)));
    assert_true(fabs(result - expected) < 1e-9);
}

/* test_branching_weights_no_normalization:
 * M0f: weights [2.0, 8.0] are stored verbatim (NOT L1-normalized to [0.2,0.8]). */
static void test_branching_weights_no_normalization(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {2.0, 8.0};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 2.0) < 1e-12);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 8.0) < 1e-12);
}

/* test_branching_weights_overwrite:
 * Call set_branching_weights twice; first array freed (no ASan leak), second
 * stored verbatim (no normalization). */
static void test_branching_weights_overwrite(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr1[] = {1.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr1, 2);
    assert_non_null(ctx->branching_stats.branching_weights);

    double arr2[] = {3.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr2, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 3.0) < 1e-12);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 1.0) < 1e-12);
}

/* test_branching_weights_clear:
 * Call set_branching_weights then set with NULL, verify pointer is NULL */
static void test_branching_weights_clear(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double arr[] = {1.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    assert_non_null(ctx->branching_stats.branching_weights);

    solver_ctx_set_branching_weights(ctx, NULL, 0);
    assert_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 0);
}

/* ============================================================
 * M0f: sigmoid+clamp reparameterization invariants
 * ============================================================ */

/* test_branching_theta_zero_identity:
 * theta == 0 (or branching_factor == 0) reproduces the no-weights baseline
 * BIT-FOR-BIT (no sigmoid round-trip): the effective offset is exactly 0, so
 * value = base. Pins NORTHSTAR §4(c) + the §8 golden through the weights path. */
static void test_branching_theta_zero_identity(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 5.0);

    /* Baseline with NO weights. */
    double baseline = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(baseline == 6.0 / 7.0);

    /* All-zero weights: offset == 0 -> identical bit-for-bit. */
    double zeros[] = {0.0, 0.0};
    solver_ctx_set_branching_weights(ctx, zeros, 2);
    double with_zero_weights = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(with_zero_weights == baseline);

    /* Non-zero weights but branching_factor == 0 -> channel disabled, offset==0. */
    double nz[] = {5.0, -3.0};
    solver_ctx_set_branching_weights(ctx, nz, 2);
    solver_ctx_set_branching_factor(ctx, 0.0);
    double with_zero_factor = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(with_zero_factor == baseline);
}

/* test_branching_value_clamped:
 * §1.7 bounded decisions: extreme theta can never pin value to exactly 0 or 1;
 * it saturates at the (BRANCH_EPS, 1-BRANCH_EPS) clamp boundary. */
static void test_branching_value_clamped(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 5.0);

    double pos[] = {1e6};
    solver_ctx_set_branching_weights(ctx, pos, 1);
    double rp = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(rp < 1.0);                 /* never pinned to 1 */
    assert_true(fabs(rp - (1.0 - 1e-9)) < 1e-15);

    double neg[] = {-1e6};
    solver_ctx_set_branching_weights(ctx, neg, 1);
    double rn = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(rn > 0.0);                 /* never pinned to 0 */
    assert_true(fabs(rn - 1e-9) < 1e-15);
}

/* test_branching_signed_direction:
 * a positive theta pushes value above the base; a negative theta pushes it
 * below -- proves the L1-drop kept the sign and magnitude meaningful. */
static void test_branching_signed_direction(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 5.0);
    double base = 6.0 / 7.0;

    double pos[] = {2.0};
    solver_ctx_set_branching_weights(ctx, pos, 1);
    double rp = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(rp > base);

    double neg[] = {-2.0};
    solver_ctx_set_branching_weights(ctx, neg, 1);
    double rn = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(rn < base);
}

/* ============================================================
 * Tests for StateProbability using ctx
 * ============================================================ */

/* test_state_probability: verify result is valid probability */
static void test_state_probability(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);
    solver_ctx_set_bias(ctx, 5.0);

    int arr1[] = {1, 0, 1};
    state_t *s = init_state(0, arr1, 3);
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
    /* Each bit contributes base = (bias+1)/(bias+2); with bias=5: (6/7)^3 */
    double expected = pow(6.0 / 7.0, 3.0);
    assert_true(fabs(prob - expected) < 1e-9);

    free_state(s, 1);
    free_state(threshold, 1);
}

/* test_branching_function_all_factors_zero:
 * branching_factor=0, bias_factor=0, look_ahead_factor=0, no weights.
 * factor_sum = 0 -> base = 0.5; offset = 0 -> value = 0.5. */
static void test_branching_function_all_factors_zero(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);

    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.5) < 1e-9);

    double result_diff = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result_diff - 0.5) < 1e-9);
}

/* test_branching_weights_realloc_different_sizes:
 * Set size 2, overwrite with size 5, clear. Verify num_weights + verbatim
 * (un-normalized) storage after each step. */
static void test_branching_weights_realloc_different_sizes(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double arr1[] = {1.0, 3.0};
    solver_ctx_set_branching_weights(ctx, arr1, 2);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 2);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0) < 1e-12);
    assert_true(fabs(ctx->branching_stats.branching_weights[1] - 3.0) < 1e-12);

    double arr2[] = {1.0, 2.0, 3.0, 4.0, 5.0};
    solver_ctx_set_branching_weights(ctx, arr2, 5);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 5);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0) < 1e-12);
    assert_true(fabs(ctx->branching_stats.branching_weights[4] - 5.0) < 1e-12);

    solver_ctx_set_branching_weights(ctx, NULL, 0);
    assert_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 0);
}

/* test_branching_weights_single_element:
 * weights=[1.0] stored verbatim. branching_factor=1, bias_factor=0,
 * look_ahead_factor=0: base = 0.5 (factor_sum=0); offset = 1*1 = 1;
 * value = sigma(logit(0.5)+1) = sigma(1). */
static void test_branching_weights_single_element(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double arr[] = {1.0};
    solver_ctx_set_branching_weights(ctx, arr, 1);
    assert_non_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 1);
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0) < 1e-12);

    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_ahead_factor(ctx, 0.0);

    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    double expected = 1.0 / (1.0 + exp(-1.0));  /* sigma(1) ~ 0.73106 */
    assert_true(fabs(result - expected) < 1e-9);

    double result_diff = BranchingFunction(0, 0, 1, 0, &ctx->branching_stats);
    assert_true(fabs(result_diff - (1.0 - expected)) < 1e-9);
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
        cmocka_unit_test_setup_teardown(test_branching_function_null_weights, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_3term, branching_setup, branching_teardown),
        /* M0f weight-storage (no normalization) */
        cmocka_unit_test_setup_teardown(test_branching_weights_no_normalization, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_overwrite, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_clear, branching_setup, branching_teardown),
        /* M0f sigmoid+clamp invariants */
        cmocka_unit_test_setup_teardown(test_branching_theta_zero_identity, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_value_clamped, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_signed_direction, branching_setup, branching_teardown),
        /* StateProbability tests using ctx */
        cmocka_unit_test_setup_teardown(test_state_probability, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_state_probability_identical, branching_setup, branching_teardown),
        /* Edge cases */
        cmocka_unit_test_setup_teardown(test_branching_function_all_factors_zero, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_realloc_different_sizes, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_weights_single_element, branching_setup, branching_teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
