#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "SearchLib.h"
#include "definitions.h"

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
        cmocka_unit_test(test_init_incumbents),
        cmocka_unit_test(test_incumbents_initial_state),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
