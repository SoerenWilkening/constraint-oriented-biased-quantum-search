#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "SearchLib.h"
#include "definitions.h"

/* ---------- compare() tests ---------- */

/* compare(obj, thr, sense) returns obj*sense < thr*sense.
 * For MINIMIZE (sense=1): returns obj < thr, i.e. obj is strictly better.
 * For MAXIMIZE (sense=-1): returns obj*(-1) < thr*(-1), i.e. obj > thr. */

static void test_compare_minimize_better(void **state) {
    (void)state;
    /* 5 < 10 for minimization -> 5 is better -> returns 1 */
    assert_int_equal(compare(5, 10, MINIMIZE), 1);
}

static void test_compare_minimize_worse(void **state) {
    (void)state;
    /* 10 < 5 for minimization -> false -> returns 0 */
    assert_int_equal(compare(10, 5, MINIMIZE), 0);
}

static void test_compare_maximize_better(void **state) {
    (void)state;
    /* For MAXIMIZE (sense=-1): 10*(-1) < 5*(-1) -> -10 < -5 -> true -> returns 1 */
    assert_int_equal(compare(10, 5, MAXIMIZE), 1);
}

static void test_compare_maximize_worse(void **state) {
    (void)state;
    /* For MAXIMIZE (sense=-1): 5*(-1) < 10*(-1) -> -5 < -10 -> false -> returns 0 */
    assert_int_equal(compare(5, 10, MAXIMIZE), 0);
}

static void test_compare_equal(void **state) {
    (void)state;
    /* 5 == 5, not strictly less -> returns 0 */
    assert_int_equal(compare(5, 5, MINIMIZE), 0);
    assert_int_equal(compare(5, 5, MAXIMIZE), 0);
}

/* ---------- incumbents tests ---------- */

static void test_init_incumbents(void **state) {
    (void)state;

    int arr[4] = {1, 0, 1, 0};
    state_t *initial = init_state(0, arr, 4);

    incumbents_t *inc = init_incumbents(4, initial);
    assert_non_null(inc);
    assert_int_equal(inc->head, 0);
    assert_true(inc->allocated >= 1);

    free_incumbents(inc);
    free_state(initial, 1);
}

static void test_incumbents_initial_state(void **state) {
    (void)state;

    int arr[4] = {1, 0, 1, 0};
    state_t *initial = init_state(0, arr, 4);

    incumbents_t *inc = init_incumbents(4, initial);

    /* The first state in incumbents should match the initial state */
    assert_int_equal(sw_tstbit(inc->states[0].vector, 0), 1);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 1), 0);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 2), 1);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 3), 0);

    free_incumbents(inc);
    free_state(initial, 1);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_compare_minimize_better),
        cmocka_unit_test(test_compare_minimize_worse),
        cmocka_unit_test(test_compare_maximize_better),
        cmocka_unit_test(test_compare_maximize_worse),
        cmocka_unit_test(test_compare_equal),
        cmocka_unit_test(test_init_incumbents),
        cmocka_unit_test(test_incumbents_initial_state),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
