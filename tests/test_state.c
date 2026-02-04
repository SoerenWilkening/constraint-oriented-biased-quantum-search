#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "state.h"

/* test_init_state: create state from array and verify fields */
static void test_init_state(void **state) {
    (void)state;

    int arr[4] = {1, 0, 1, 0};
    state_t *s = init_state(0, arr, 4);

    assert_non_null(s);
    assert_int_equal(s->tot_profit, 0);
    assert_int_equal(sw_tstbit(s->vector, 0), 1);
    assert_int_equal(sw_tstbit(s->vector, 1), 0);
    assert_int_equal(sw_tstbit(s->vector, 2), 1);
    assert_int_equal(sw_tstbit(s->vector, 3), 0);

    free_state(s, 1);
}

/* test_copy_state: copy is independent from original */
static void test_copy_state(void **state) {
    (void)state;

    int arr[4] = {1, 1, 0, 0};
    state_t *s = init_state(42, arr, 4);
    state_t *c = copy_state(s);

    /* Vectors should match */
    assert_int_equal(sw_cmp(s->vector, c->vector), 1);
    assert_int_equal(c->tot_profit, s->tot_profit);
    assert_int_equal(c->tot_profit, 42);

    /* Modify original, copy should be unchanged */
    sw_setbit(s->vector, 2);
    assert_int_equal(sw_cmp(s->vector, c->vector), 0);
    assert_int_equal(sw_tstbit(c->vector, 2), 0);

    free_state(s, 1);
    free_state(c, 1);
}

/* test_copy_state_inplace: copy data into pre-allocated destination */
static void test_copy_state_inplace(void **state) {
    (void)state;

    int arr_src[4] = {1, 0, 1, 1};
    state_t *src = init_state(99, arr_src, 4);

    int arr_dst[4] = {0, 0, 0, 0};
    state_t *dest = init_state(0, arr_dst, 4);

    copy_state_inplace(dest, src);

    assert_int_equal(sw_cmp(dest->vector, src->vector), 1);
    assert_int_equal(dest->tot_profit, 99);

    free_state(src, 1);
    free_state(dest, 1);
}

/* test_free_state: init and free without crash (ASan validates no leaks) */
static void test_free_state(void **state) {
    (void)state;

    int arr[4] = {0, 1, 0, 1};
    state_t *s = init_state(0, arr, 4);
    assert_non_null(s);
    free_state(s, 1);
    /* If we get here without crash or ASan error, test passes */
}

/* test_init_large_state: allocate array of states */
static void test_init_large_state(void **state) {
    (void)state;

    state_t *states = init_large_state(10, 5);
    assert_non_null(states);

    /* Verify each state is initialized */
    for (int i = 0; i < 5; i++) {
        assert_int_equal(states[i].tot_profit, 0);
        assert_int_equal(states[i].vector.bits, 10);
        assert_non_null(states[i].vector.part);
    }

    free_state(states, 5);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_state),
        cmocka_unit_test(test_copy_state),
        cmocka_unit_test(test_copy_state_inplace),
        cmocka_unit_test(test_free_state),
        cmocka_unit_test(test_init_large_state),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
