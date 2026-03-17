/**
 * test_features.c - Unit tests for C feature extraction
 *
 * Tests that extract_features() computes the same features as the Python
 * FeatureExtractor, including z-score normalization for per-variable features.
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <string.h>

#include "ml_features.h"
#include "dyn_expr.h"
#include "definitions.h"

#define TOLERANCE 1e-10

/* ============================================================================
 * Helper: build a simple linear term expression
 * ============================================================================ */

/**
 * Build a constraint expression with linear terms.
 * terms: array of (coeff, var_idx) pairs, n_terms entries.
 */
static dyn_expression_t *make_linear_expr(const int64_t *coeffs,
                                           const int64_t *vars,
                                           int n_terms) {
    dyn_expression_t *e = dyn_expr_init();
    for (int i = 0; i < n_terms; i++) {
        dyn_expr_add_term(e, coeffs[i], &vars[i], 1);
    }
    return e;
}

/* ============================================================================
 * test_zero_variables: n_vars=0 returns NULL var_features, zeroed inst features
 * ============================================================================ */

static void test_zero_variables(void **state) {
    (void)state;

    features_result_t r = extract_features(NULL, 0, NULL, 0, 0, NULL, NULL, NULL);
    assert_null(r.var_features);
    assert_int_equal(r.n_vars, 0);
    for (int i = 0; i < NUM_INST_FEATURES; i++) {
        assert_float_equal(r.inst_features[i], 0.0, TOLERANCE);
    }
    features_result_free(&r);
}

/* ============================================================================
 * test_single_variable_no_constraints: 1 var, no obj, no constraints
 * ============================================================================ */

static void test_single_variable_no_constraints(void **state) {
    (void)state;

    double lb[] = {0.0};
    double ub[] = {1.0};
    int vtype[] = {INTEGER};

    features_result_t r = extract_features(NULL, 0, NULL, 0, 1, lb, ub, vtype);
    assert_non_null(r.var_features);
    assert_int_equal(r.n_vars, 1);

    /* With a single variable, z-score normalization sets all features to 0 */
    for (int col = 0; col < NUM_VAR_FEATURES; col++) {
        assert_float_equal(r.var_features[col], 0.0, TOLERANCE);
    }

    /* Instance features */
    assert_float_equal(r.inst_features[0], 1.0, TOLERANCE);  /* n_vars */
    assert_float_equal(r.inst_features[1], 0.0, TOLERANCE);  /* n_con */
    assert_float_equal(r.inst_features[5], 1.0, TOLERANCE);  /* int frac */
    assert_float_equal(r.inst_features[9], 1.0, TOLERANCE);  /* bounds mean */
    assert_float_equal(r.inst_features[10], 0.0, TOLERANCE); /* bounds std */

    features_result_free(&r);
}

/* ============================================================================
 * test_two_vars_one_constraint: verify degree, coefficients, co-occurrence
 * ============================================================================ */

static void test_two_vars_one_constraint(void **state) {
    (void)state;

    /* Constraint: 3*x0 + 5*x1 <= 10 */
    int64_t coeffs[] = {3, 5};
    int64_t vars[] = {0, 1};
    dyn_expression_t *con = make_linear_expr(coeffs, vars, 2);
    dyn_expression_t *con_arr[] = {con};

    double lb[] = {0.0, 0.0};
    double ub[] = {1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER};

    features_result_t r = extract_features(NULL, 0, con_arr, 1, 2, lb, ub, vtype);
    assert_non_null(r.var_features);
    assert_int_equal(r.n_vars, 2);

    /* Before normalization, raw features would be:
     *   x0: degree=1, coeff_mean=3, coeff_max=3, coeff_min=3, obj=0, bw=1, int=1, avg_deg=1, co=1
     *   x1: degree=1, coeff_mean=5, coeff_max=5, coeff_min=5, obj=0, bw=1, int=1, avg_deg=1, co=1
     *
     * After z-score normalization:
     *   - degree: both 1, std=0 -> both 0
     *   - coeff_mean: mean=4, std=1 -> x0: -1, x1: 1
     *   - coeff_max: same as mean
     *   - coeff_min: same as mean
     *   - obj_coeff: both 0, std=0 -> both 0
     *   - bounds_width: both 1, std=0 -> both 0
     *   - is_integer: both 1, std=0 -> both 0
     *   - avg_neighbor_degree: both 1, std=0 -> both 0
     *   - num_co_occurring: both 1, std=0 -> both 0
     */
    double *f = r.var_features;

    /* col 0: degree, both same -> 0 */
    assert_float_equal(f[0 * NUM_VAR_FEATURES + 0], 0.0, TOLERANCE);
    assert_float_equal(f[1 * NUM_VAR_FEATURES + 0], 0.0, TOLERANCE);

    /* col 1: coeff_mean, x0=3, x1=5, mean=4, std=1 -> x0=-1, x1=1 */
    assert_float_equal(f[0 * NUM_VAR_FEATURES + 1], -1.0, TOLERANCE);
    assert_float_equal(f[1 * NUM_VAR_FEATURES + 1], 1.0, TOLERANCE);

    /* col 2: coeff_max, same pattern */
    assert_float_equal(f[0 * NUM_VAR_FEATURES + 2], -1.0, TOLERANCE);
    assert_float_equal(f[1 * NUM_VAR_FEATURES + 2], 1.0, TOLERANCE);

    /* col 3: coeff_min, same pattern */
    assert_float_equal(f[0 * NUM_VAR_FEATURES + 3], -1.0, TOLERANCE);
    assert_float_equal(f[1 * NUM_VAR_FEATURES + 3], 1.0, TOLERANCE);

    /* cols 4-8: all constant across vars -> 0 */
    for (int col = 4; col < NUM_VAR_FEATURES; col++) {
        assert_float_equal(f[0 * NUM_VAR_FEATURES + col], 0.0, TOLERANCE);
        assert_float_equal(f[1 * NUM_VAR_FEATURES + col], 0.0, TOLERANCE);
    }

    /* Instance features */
    assert_float_equal(r.inst_features[0], 2.0, TOLERANCE);  /* n_vars */
    assert_float_equal(r.inst_features[1], 1.0, TOLERANCE);  /* n_con */
    assert_float_equal(r.inst_features[2], 0.5, TOLERANCE);  /* density */
    assert_float_equal(r.inst_features[3], 0.5, TOLERANCE);  /* ratio */
    assert_float_equal(r.inst_features[4], 0.0, TOLERANCE);  /* obj density (no obj) */

    /* Global coeff stats: values are 3 and 5 */
    assert_float_equal(r.inst_features[6], 4.0, TOLERANCE);  /* mean */
    assert_float_equal(r.inst_features[8], 5.0, TOLERANCE);  /* max */
    /* std = sqrt(((3-4)^2 + (5-4)^2)/2) = sqrt(1) = 1 */
    assert_float_equal(r.inst_features[7], 1.0, TOLERANCE);

    dyn_expr_free(con);
    features_result_free(&r);
}

/* ============================================================================
 * test_objective_features: verify objective coefficient extraction
 * ============================================================================ */

static void test_objective_features(void **state) {
    (void)state;

    /* Objective: 10*x0 + 20*x1 (x2 has no obj coeff) */
    int64_t obj_c[] = {10, 20};
    int64_t obj_v[] = {0, 1};
    dyn_expression_t *obj = make_linear_expr(obj_c, obj_v, 2);
    dyn_expression_t *obj_arr[] = {obj};

    double lb[] = {0.0, 0.0, 0.0};
    double ub[] = {1.0, 1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER, INTEGER};

    features_result_t r = extract_features(obj_arr, 1, NULL, 0, 3, lb, ub, vtype);
    assert_non_null(r.var_features);

    /* Instance: objective density = 2/3 */
    assert_float_equal(r.inst_features[4], 2.0 / 3.0, TOLERANCE);

    /* After z-score, obj_coeff raw = [10, 20, 0]
     * mean = 10, std = sqrt((0+100+100)/3) = sqrt(200/3)
     * x0: (10-10)/std = 0
     * x1: (20-10)/std = 10/std
     * x2: (0-10)/std = -10/std
     * x1 and x2 should be opposite
     */
    double *f = r.var_features;
    double v0 = f[0 * NUM_VAR_FEATURES + FEAT_OBJ_COEFF];
    double v1 = f[1 * NUM_VAR_FEATURES + FEAT_OBJ_COEFF];
    double v2 = f[2 * NUM_VAR_FEATURES + FEAT_OBJ_COEFF];
    assert_float_equal(v0, 0.0, TOLERANCE);
    assert_float_equal(v1, -v2, TOLERANCE);
    assert_true(v1 > 0.0);

    dyn_expr_free(obj);
    features_result_free(&r);
}

/* ============================================================================
 * test_co_occurrence: 3 vars, 2 constraints, verify neighbor features
 * ============================================================================ */

static void test_co_occurrence(void **state) {
    (void)state;

    /* Constraint 1: x0 + x1 <= 1 */
    int64_t c1_c[] = {1, 1};
    int64_t c1_v[] = {0, 1};
    dyn_expression_t *con1 = make_linear_expr(c1_c, c1_v, 2);

    /* Constraint 2: x1 + x2 <= 1 */
    int64_t c2_c[] = {1, 1};
    int64_t c2_v[] = {1, 2};
    dyn_expression_t *con2 = make_linear_expr(c2_c, c2_v, 2);

    dyn_expression_t *cons[] = {con1, con2};

    double lb[] = {0.0, 0.0, 0.0};
    double ub[] = {1.0, 1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER, INTEGER};

    features_result_t r = extract_features(NULL, 0, cons, 2, 3, lb, ub, vtype);

    /* Raw (pre-normalization) co-occurrence:
     *   x0: co-occurs with {x1} -> count=1
     *   x1: co-occurs with {x0, x2} -> count=2
     *   x2: co-occurs with {x1} -> count=1
     *
     * Raw degree:
     *   x0: 1, x1: 2, x2: 1
     *
     * Raw avg_neighbor_degree:
     *   x0: degree of {x1} = 2 -> avg = 2
     *   x1: degree of {x0, x2} = (1+1)/2 = 1
     *   x2: degree of {x1} = 2 -> avg = 2
     */

    /* After z-score:
     * degree [1,2,1]: mean=4/3, std=sqrt(2/9) = sqrt(2)/3
     * co [1,2,1]: same distribution -> same normalization
     * avg_deg [2,1,2]: same pattern reversed
     */

    /* Verify instance features */
    assert_float_equal(r.inst_features[0], 3.0, TOLERANCE);  /* n_vars */
    assert_float_equal(r.inst_features[1], 2.0, TOLERANCE);  /* n_con */

    dyn_expr_free(con1);
    dyn_expr_free(con2);
    features_result_free(&r);
}

/* ============================================================================
 * test_mixed_variable_types: integer and fractional variables
 * ============================================================================ */

static void test_mixed_variable_types(void **state) {
    (void)state;

    double lb[] = {0.0, 0.0, 0.0, 0.0};
    double ub[] = {1.0, 10.0, 1.0, 5.0};
    int vtype[] = {INTEGER, FRACTIONAL, INTEGER, FRACTIONAL};

    features_result_t r = extract_features(NULL, 0, NULL, 0, 4, lb, ub, vtype);

    /* Instance: integer_variable_fraction = 2/4 = 0.5 */
    assert_float_equal(r.inst_features[5], 0.5, TOLERANCE);

    /* Instance: bounds_tightness_mean = (1+10+1+5)/4 = 4.25 */
    assert_float_equal(r.inst_features[9], 4.25, TOLERANCE);

    /* bounds_tightness_std = sqrt(((1-4.25)^2+(10-4.25)^2+(1-4.25)^2+(5-4.25)^2)/4) */
    double sum_sq = (1-4.25)*(1-4.25) + (10-4.25)*(10-4.25)
                  + (1-4.25)*(1-4.25) + (5-4.25)*(5-4.25);
    double expected_std = sqrt(sum_sq / 4.0);
    assert_float_equal(r.inst_features[10], expected_std, TOLERANCE);

    features_result_free(&r);
}

/* ============================================================================
 * test_negative_coefficients: absolute values are used
 * ============================================================================ */

static void test_negative_coefficients(void **state) {
    (void)state;

    /* Constraint: -3*x0 + 5*x1 <= 10 */
    int64_t coeffs[] = {-3, 5};
    int64_t vars[] = {0, 1};
    dyn_expression_t *con = make_linear_expr(coeffs, vars, 2);
    dyn_expression_t *con_arr[] = {con};

    /* Objective: -7*x0 */
    int64_t obj_c[] = {-7};
    int64_t obj_v[] = {0};
    dyn_expression_t *obj = make_linear_expr(obj_c, obj_v, 1);
    dyn_expression_t *obj_arr[] = {obj};

    double lb[] = {0.0, 0.0};
    double ub[] = {1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER};

    features_result_t r = extract_features(obj_arr, 1, con_arr, 1, 2, lb, ub, vtype);

    /* Instance coeff mean: (3+5)/2 = 4 (using abs values) */
    assert_float_equal(r.inst_features[6], 4.0, TOLERANCE);
    /* Instance coeff max: 5 */
    assert_float_equal(r.inst_features[8], 5.0, TOLERANCE);

    /* obj density: 1/2 = 0.5 (x0 has obj, x1 doesn't) */
    assert_float_equal(r.inst_features[4], 0.5, TOLERANCE);

    dyn_expr_free(con);
    dyn_expr_free(obj);
    features_result_free(&r);
}

/* ============================================================================
 * test_zscore_uniform: all same values -> all zero after z-score
 * ============================================================================ */

static void test_zscore_uniform(void **state) {
    (void)state;

    /* 3 vars, each in exactly one constraint with same coefficient */
    int64_t c1[] = {2}; int64_t v1[] = {0};
    int64_t c2[] = {2}; int64_t v2[] = {1};
    int64_t c3[] = {2}; int64_t v3[] = {2};
    dyn_expression_t *e1 = make_linear_expr(c1, v1, 1);
    dyn_expression_t *e2 = make_linear_expr(c2, v2, 1);
    dyn_expression_t *e3 = make_linear_expr(c3, v3, 1);
    dyn_expression_t *cons[] = {e1, e2, e3};

    double lb[] = {0.0, 0.0, 0.0};
    double ub[] = {1.0, 1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER, INTEGER};

    features_result_t r = extract_features(NULL, 0, cons, 3, 3, lb, ub, vtype);

    /* All features should be identical across vars, so z-score -> all 0 */
    for (int i = 0; i < 3; i++) {
        for (int col = 0; col < NUM_VAR_FEATURES; col++) {
            assert_float_equal(r.var_features[i * NUM_VAR_FEATURES + col],
                               0.0, TOLERANCE);
        }
    }

    dyn_expr_free(e1);
    dyn_expr_free(e2);
    dyn_expr_free(e3);
    features_result_free(&r);
}

/* ============================================================================
 * test_multiple_constraints_degree: variable appears in multiple constraints
 * ============================================================================ */

static void test_multiple_constraints_degree(void **state) {
    (void)state;

    /* x0 appears in 3 constraints, x1 in 1, x2 in 2 */
    int64_t c1[] = {1, 1}; int64_t v1[] = {0, 1};
    int64_t c2[] = {1};    int64_t v2[] = {0};
    int64_t c3[] = {1, 1}; int64_t v3[] = {0, 2};
    int64_t c4[] = {1};    int64_t v4[] = {2};

    dyn_expression_t *e1 = make_linear_expr(c1, v1, 2);
    dyn_expression_t *e2 = make_linear_expr(c2, v2, 1);
    dyn_expression_t *e3 = make_linear_expr(c3, v3, 2);
    dyn_expression_t *e4 = make_linear_expr(c4, v4, 1);
    dyn_expression_t *cons[] = {e1, e2, e3, e4};

    double lb[] = {0.0, 0.0, 0.0};
    double ub[] = {1.0, 1.0, 1.0};
    int vtype[] = {INTEGER, INTEGER, INTEGER};

    features_result_t r = extract_features(NULL, 0, cons, 4, 3, lb, ub, vtype);

    /* Raw degree: x0=3, x1=1, x2=2. Mean=2, std=sqrt(2/3) */
    /* After z-score: x0 = (3-2)/std, x1 = (1-2)/std, x2 = (2-2)/std = 0 */
    double *f = r.var_features;
    double d0 = f[0 * NUM_VAR_FEATURES + FEAT_DEGREE];
    double d1 = f[1 * NUM_VAR_FEATURES + FEAT_DEGREE];
    double d2 = f[2 * NUM_VAR_FEATURES + FEAT_DEGREE];

    assert_float_equal(d2, 0.0, TOLERANCE);
    assert_true(d0 > 0.0);
    assert_true(d1 < 0.0);
    assert_float_equal(d0, -d1, TOLERANCE);

    /* Instance: n_constraints = 4 */
    assert_float_equal(r.inst_features[1], 4.0, TOLERANCE);

    dyn_expr_free(e1);
    dyn_expr_free(e2);
    dyn_expr_free(e3);
    dyn_expr_free(e4);
    features_result_free(&r);
}

/* ============================================================================
 * test_result_free_null_safe: free on zero-result doesn't crash
 * ============================================================================ */

static void test_result_free_null_safe(void **state) {
    (void)state;

    features_result_t r;
    memset(&r, 0, sizeof(r));
    r.var_features = NULL;
    features_result_free(&r);
    features_result_free(NULL);
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_zero_variables),
        cmocka_unit_test(test_single_variable_no_constraints),
        cmocka_unit_test(test_two_vars_one_constraint),
        cmocka_unit_test(test_objective_features),
        cmocka_unit_test(test_co_occurrence),
        cmocka_unit_test(test_mixed_variable_types),
        cmocka_unit_test(test_negative_coefficients),
        cmocka_unit_test(test_zscore_uniform),
        cmocka_unit_test(test_multiple_constraints_degree),
        cmocka_unit_test(test_result_free_null_safe),
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
