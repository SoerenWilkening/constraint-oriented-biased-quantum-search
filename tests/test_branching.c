#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>

#include "Branching.h"
#include "definitions.h"

/* Setup fixture: reset BranchingStats global to zero state */
static int branching_setup(void **state) {
    (void)state;
    memset(&BranchingStats, 0, sizeof(BranchingStats));
    BranchingStats.obj_dependent = NULL;
    BranchingStats.constraint_dependent = NULL;
    return 0;
}

/* Teardown: free any allocated arrays */
static int branching_teardown(void **state) {
    (void)state;
    if (BranchingStats.obj_dependent != NULL) {
        free(BranchingStats.obj_dependent);
        BranchingStats.obj_dependent = NULL;
    }
    if (BranchingStats.constraint_dependent != NULL) {
        free(BranchingStats.constraint_dependent);
        BranchingStats.constraint_dependent = NULL;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* test_set_factors: verify set_factors writes to global               */
/* ------------------------------------------------------------------ */
static void test_set_factors(void **state) {
    (void)state;
    set_factors(1.0, 2.0, 3.0, 4.0);
    assert_true(BranchingStats.objective_factor == 1.0);
    assert_true(BranchingStats.constraint_factor == 2.0);
    assert_true(BranchingStats.bias_factor == 3.0);
    assert_true(BranchingStats.look_factor == 4.0);
}

/* ------------------------------------------------------------------ */
/* test_set_bias: verify set_bias writes to global                     */
/* ------------------------------------------------------------------ */
static void test_set_bias(void **state) {
    (void)state;
    set_bias(5.0);
    assert_true(BranchingStats.bias == 5.0);
}

/* ------------------------------------------------------------------ */
/* test_set_obj_dependence: verify array is copied                     */
/* ------------------------------------------------------------------ */
static void test_set_obj_dependence(void **state) {
    (void)state;
    double arr[] = {0.5, 0.5};
    set_obj_dependence(arr, 2);
    assert_non_null(BranchingStats.obj_dependent);
    assert_true(fabs(BranchingStats.obj_dependent[0] - 0.5) < 1e-9);
    assert_true(fabs(BranchingStats.obj_dependent[1] - 0.5) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_set_constraint_dependence: verify array is copied              */
/* ------------------------------------------------------------------ */
static void test_set_constraint_dependence(void **state) {
    (void)state;
    double arr[] = {0.3, 0.7};
    set_constraint_dependence(arr, 2);
    assert_non_null(BranchingStats.constraint_dependent);
    assert_true(fabs(BranchingStats.constraint_dependent[0] - 0.3) < 1e-9);
    assert_true(fabs(BranchingStats.constraint_dependent[1] - 0.7) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_branching_function_equal_bits:                                  */
/* factors=(1,0,0,0), obj_dependent=[0.5, 0.5]                        */
/* bit_S=0, bit_T=0 (both 0): result = 1/1 * 1 * 0.5 = 0.5           */
/* ------------------------------------------------------------------ */
static void test_branching_function_equal_bits(void **state) {
    (void)state;
    set_factors(1.0, 0.0, 0.0, 0.0);
    double arr[] = {0.5, 0.5};
    set_obj_dependence(arr, 2);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &BranchingStats);
    /* Formula: 1/(1+0+0+0) * 1.0 * 0.5 = 0.5 */
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_branching_function_different_bits:                              */
/* bit_S=0, bit_T=1 => subtractive branch                             */
/* ------------------------------------------------------------------ */
static void test_branching_function_different_bits(void **state) {
    (void)state;
    set_factors(1.0, 0.0, 0.0, 0.0);
    double arr[] = {0.5, 0.5};
    set_obj_dependence(arr, 2);

    /* index=0, bit_S=0, bit_T=1 (different bits) */
    /* formula: 1 - 1/(1) * 1.0 * 0.5 = 1 - 0.5 = 0.5 */
    double result = BranchingFunction(0, 0, 1, 0, &BranchingStats);
    assert_true(fabs(result - 0.5) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_branching_function_bias_only:                                   */
/* factors=(0,0,1,0), bias=2.0, both bits 0                            */
/* result = 1/1 * 1 * (2+1)/(2+2) = 3/4 = 0.75                       */
/* ------------------------------------------------------------------ */
static void test_branching_function_bias_only(void **state) {
    (void)state;
    set_factors(0.0, 0.0, 1.0, 0.0);
    set_bias(2.0);

    /* index=0, bit_S=0, bit_T=0, diffcount=0 */
    double result = BranchingFunction(0, 0, 0, 0, &BranchingStats);
    /* formula: 1/(0+0+1+0) * 1.0 * (2+1)/(2+2) = 3/4 = 0.75 */
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_branching_function_bias_different_bits:                         */
/* factors=(0,0,1,0), bias=2.0, bit_S=1, bit_T=0                      */
/* result = 1 - 0.75 = 0.25                                           */
/* ------------------------------------------------------------------ */
static void test_branching_function_bias_different_bits(void **state) {
    (void)state;
    set_factors(0.0, 0.0, 1.0, 0.0);
    set_bias(2.0);

    /* index=0, bit_S=1, bit_T=0 (different bits) */
    double result = BranchingFunction(0, 1, 0, 0, &BranchingStats);
    /* formula: 1 - 1/1 * 1 * (2+1)/(2+2) = 1 - 0.75 = 0.25 */
    assert_true(fabs(result - 0.25) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_branching_function_both_bits_one:                               */
/* factors=(0,0,1,0), bias=2.0, both bits 1                            */
/* Same as both bits 0: result = 0.75                                  */
/* ------------------------------------------------------------------ */
static void test_branching_function_both_bits_one(void **state) {
    (void)state;
    set_factors(0.0, 0.0, 1.0, 0.0);
    set_bias(2.0);

    /* bit_S=1, bit_T=1 (both 1) */
    double result = BranchingFunction(0, 1, 1, 0, &BranchingStats);
    assert_true(fabs(result - 0.75) < 1e-9);
}

/* ------------------------------------------------------------------ */
/* test_state_probability: verify result is valid probability          */
/* ------------------------------------------------------------------ */
static void test_state_probability(void **state) {
    (void)state;
    /* Configure branching with bias only */
    set_factors(0.0, 0.0, 1.0, 0.0);
    set_bias(5.0);

    int arr1[] = {1, 0, 1};
    state_t *s = init_state(0, arr1, 3);
    /* Set branch bits to mark which are "branched" */
    sw_setbit(s->branch, 0);
    sw_setbit(s->branch, 1);
    sw_setbit(s->branch, 2);

    int arr2[] = {1, 0, 0};
    state_t *threshold = init_state(0, arr2, 3);

    double prob = StateProbability(s, threshold);
    assert_true(prob >= 0.0);
    assert_true(prob <= 1.0);

    free_state(s, 1);
    free_state(threshold, 1);
}

/* ------------------------------------------------------------------ */
/* test_state_probability_identical: identical states => high prob      */
/* ------------------------------------------------------------------ */
static void test_state_probability_identical(void **state) {
    (void)state;
    set_factors(0.0, 0.0, 1.0, 0.0);
    set_bias(5.0);

    int arr[] = {1, 0, 1};
    state_t *s = init_state(0, arr, 3);
    sw_setbit(s->branch, 0);
    sw_setbit(s->branch, 1);
    sw_setbit(s->branch, 2);

    state_t *threshold = init_state(0, arr, 3);

    double prob = StateProbability(s, threshold);
    /* When both states are identical, each bit contributes (bias+1)/(bias+2) */
    /* With bias=5: (6/7)^3 ~ 0.6297 */
    double expected = pow(6.0 / 7.0, 3.0);
    assert_true(fabs(prob - expected) < 1e-9);

    free_state(s, 1);
    free_state(threshold, 1);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_set_factors, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_set_bias, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_set_obj_dependence, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_set_constraint_dependence, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_equal_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_only, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_bias_different_bits, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_branching_function_both_bits_one, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_state_probability, branching_setup, branching_teardown),
        cmocka_unit_test_setup_teardown(test_state_probability_identical, branching_setup, branching_teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
