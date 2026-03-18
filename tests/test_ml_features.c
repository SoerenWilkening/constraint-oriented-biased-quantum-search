/**
 * test_ml_features.c - Tests for log_linear_dot() and sub-linear instance prediction
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <string.h>

#include "ml_features.h"

/* Include the .c file to access static functions */
#include "ml_features.c"

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_zero_weights: all-zero weights produce zero    */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_zero_weights(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES] = {100.0, 50.0, 0.5, 0.5, 0.8, 1.0, 3.0, 1.5, 10.0, 0.7, 0.2};
    double w[ML_INST_TERMS_SUBLINEAR];
    memset(w, 0, sizeof(w));

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    assert_true(fabs(result) < 1e-12);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_intercept_only: only intercept weight is set   */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_intercept_only(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES] = {100.0, 50.0, 0.5, 0.5, 0.8, 1.0, 3.0, 1.5, 10.0, 0.7, 0.2};
    double w[ML_INST_TERMS_SUBLINEAR];
    memset(w, 0, sizeof(w));
    w[0] = 7.5;

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    assert_true(fabs(result - 7.5) < 1e-12);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_bounded_feature: bounded feature used as-is    */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_bounded_feature(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES];
    memset(x, 0, sizeof(x));
    x[2] = 0.75;  /* constraint_density - bounded */

    double w[ML_INST_TERMS_SUBLINEAR];
    memset(w, 0, sizeof(w));
    w[1 + 2] = 2.0;

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    assert_true(fabs(result - 1.5) < 1e-12);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_unbounded_feature: unbounded gets log(1+|f|)   */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_unbounded_feature(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES];
    memset(x, 0, sizeof(x));
    x[0] = 100.0;  /* n_variables - unbounded */

    double w[ML_INST_TERMS_SUBLINEAR];
    memset(w, 0, sizeof(w));
    w[1 + 0] = 1.0;

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    double expected = log(1.0 + 100.0);
    assert_true(fabs(result - expected) < 1e-10);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_negative_unbounded: log(1+|f|) handles neg     */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_negative_unbounded(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES];
    memset(x, 0, sizeof(x));
    x[6] = -5.0;  /* coeff_mean - unbounded */

    double w[ML_INST_TERMS_SUBLINEAR];
    memset(w, 0, sizeof(w));
    w[1 + 6] = 1.0;

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    double expected = log(1.0 + 5.0);
    assert_true(fabs(result - expected) < 1e-10);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_all_features: verify full sum with all features*/
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_all_features(void **state) {
    (void)state;
    double x[ML_NUM_INST_FEATURES] = {
        100.0, 50.0, 0.5, 0.5, 0.8, 1.0, 3.0, 1.5, 10.0, 0.7, 0.2
    };

    double w[ML_INST_TERMS_SUBLINEAR];
    for (int i = 0; i < ML_INST_TERMS_SUBLINEAR; i++)
        w[i] = 1.0;

    double expected = 1.0;
    expected += log(1.0 + 100.0);
    expected += log(1.0 + 50.0);
    expected += log(1.0 + 3.0);
    expected += log(1.0 + 1.5);
    expected += log(1.0 + 10.0);
    expected += 0.5 + 0.5 + 0.8 + 1.0 + 0.7 + 0.2;

    double result = log_linear_dot(x, w, ML_NUM_INST_FEATURES);
    assert_true(fabs(result - expected) < 1e-10);
}

/* ------------------------------------------------------------------ */
/* test_log_linear_dot_term_count                                     */
/* ------------------------------------------------------------------ */
static void test_log_linear_dot_term_count(void **state) {
    (void)state;
    assert_int_equal(ML_INST_TERMS_SUBLINEAR, 12);
}

/* ------------------------------------------------------------------ */
/* test_predict_params_sublinear_scaling                               */
/* ------------------------------------------------------------------ */
static void test_predict_params_sublinear_scaling(void **state) {
    (void)state;

    double x_small[ML_NUM_INST_FEATURES] = {0};
    double x_large[ML_NUM_INST_FEATURES] = {0};
    x_small[0] = 100.0;
    x_large[0] = 10000.0;

    double w[ML_INST_TERMS_SUBLINEAR] = {0};
    w[1] = 1.0;

    double r_small = log_linear_dot(x_small, w, ML_NUM_INST_FEATURES);
    double r_large = log_linear_dot(x_large, w, ML_NUM_INST_FEATURES);

    double ratio = r_large / r_small;
    assert_true(ratio < 3.0);
    assert_true(ratio > 1.0);
}

/* ------------------------------------------------------------------ */
/* test_log_features_mask: verify the bitmask is correct              */
/* ------------------------------------------------------------------ */
static void test_log_features_mask(void **state) {
    (void)state;
    assert_true(ML_INST_LOG_FEATURES & (1u << 0));
    assert_true(ML_INST_LOG_FEATURES & (1u << 1));
    assert_true(ML_INST_LOG_FEATURES & (1u << 6));
    assert_true(ML_INST_LOG_FEATURES & (1u << 7));
    assert_true(ML_INST_LOG_FEATURES & (1u << 8));

    assert_false(ML_INST_LOG_FEATURES & (1u << 2));
    assert_false(ML_INST_LOG_FEATURES & (1u << 3));
    assert_false(ML_INST_LOG_FEATURES & (1u << 4));
    assert_false(ML_INST_LOG_FEATURES & (1u << 5));
    assert_false(ML_INST_LOG_FEATURES & (1u << 9));
    assert_false(ML_INST_LOG_FEATURES & (1u << 10));
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_log_linear_dot_zero_weights),
        cmocka_unit_test(test_log_linear_dot_intercept_only),
        cmocka_unit_test(test_log_linear_dot_bounded_feature),
        cmocka_unit_test(test_log_linear_dot_unbounded_feature),
        cmocka_unit_test(test_log_linear_dot_negative_unbounded),
        cmocka_unit_test(test_log_linear_dot_all_features),
        cmocka_unit_test(test_log_linear_dot_term_count),
        cmocka_unit_test(test_predict_params_sublinear_scaling),
        cmocka_unit_test(test_log_features_mask),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
