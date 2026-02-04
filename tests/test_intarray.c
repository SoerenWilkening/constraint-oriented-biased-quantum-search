#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "intarray.h"

/* test_sw_init: verify bit array initialization */
static void test_sw_init(void **state) {
    (void)state;

    array_t A = sw_init(64);
    assert_int_equal(A.bits, 64);
    /* 64 >> 6 = 1, +1 = 2 parts */
    assert_int_equal(A.n, 2);
    assert_non_null(A.part);
    sw_clear(A);

    array_t B = sw_init(128);
    assert_int_equal(B.bits, 128);
    /* 128 >> 6 = 2, +1 = 3 parts */
    assert_int_equal(B.n, 3);
    assert_non_null(B.part);
    sw_clear(B);

    /* Edge case: small array */
    array_t C = sw_init(1);
    assert_int_equal(C.bits, 1);
    assert_int_equal(C.n, 1);
    assert_non_null(C.part);
    sw_clear(C);
}

/* test_sw_setbit_tstbit: set bits and verify they read back correctly */
static void test_sw_setbit_tstbit(void **state) {
    (void)state;

    array_t A = sw_init(128);

    /* All bits should start as 0 */
    assert_int_equal(sw_tstbit(A, 0), 0);
    assert_int_equal(sw_tstbit(A, 63), 0);
    assert_int_equal(sw_tstbit(A, 64), 0);
    assert_int_equal(sw_tstbit(A, 127), 0);

    /* Set specific bits */
    sw_setbit(A, 0);
    sw_setbit(A, 63);
    sw_setbit(A, 64);
    sw_setbit(A, 127);

    /* Verify set bits */
    assert_int_equal(sw_tstbit(A, 0), 1);
    assert_int_equal(sw_tstbit(A, 63), 1);
    assert_int_equal(sw_tstbit(A, 64), 1);
    assert_int_equal(sw_tstbit(A, 127), 1);

    /* Verify unset bits remain 0 */
    assert_int_equal(sw_tstbit(A, 1), 0);
    assert_int_equal(sw_tstbit(A, 62), 0);
    assert_int_equal(sw_tstbit(A, 65), 0);
    assert_int_equal(sw_tstbit(A, 126), 0);

    sw_clear(A);
}

/* test_sw_clrbit: set then clear a bit */
static void test_sw_clrbit(void **state) {
    (void)state;

    array_t A = sw_init(64);
    sw_setbit(A, 10);
    assert_int_equal(sw_tstbit(A, 10), 1);

    sw_clrbit(A, 10);
    assert_int_equal(sw_tstbit(A, 10), 0);

    sw_clear(A);
}

/* test_sw_flpbit: flip bit toggles 0->1->0 */
static void test_sw_flpbit(void **state) {
    (void)state;

    array_t A = sw_init(64);

    assert_int_equal(sw_tstbit(A, 5), 0);
    sw_flpbit(A, 5);
    assert_int_equal(sw_tstbit(A, 5), 1);
    sw_flpbit(A, 5);
    assert_int_equal(sw_tstbit(A, 5), 0);

    sw_clear(A);
}

/* test_sw_set_ui_0: zero out all bits */
static void test_sw_set_ui_0(void **state) {
    (void)state;

    array_t A = sw_init(128);
    sw_setbit(A, 0);
    sw_setbit(A, 42);
    sw_setbit(A, 64);
    sw_setbit(A, 100);

    sw_set_ui_0(A);

    assert_int_equal(sw_tstbit(A, 0), 0);
    assert_int_equal(sw_tstbit(A, 42), 0);
    assert_int_equal(sw_tstbit(A, 64), 0);
    assert_int_equal(sw_tstbit(A, 100), 0);

    sw_clear(A);
}

/* test_sw_set_copy: copy array and verify independence */
static void test_sw_set_copy(void **state) {
    (void)state;

    array_t A = sw_init(128);
    sw_setbit(A, 10);
    sw_setbit(A, 70);

    array_t B = sw_set(A);

    /* B should be equal to A */
    assert_int_equal(sw_cmp(A, B), 1);

    /* Modify A, B should remain unchanged */
    sw_setbit(A, 20);
    assert_int_equal(sw_cmp(A, B), 0);
    assert_int_equal(sw_tstbit(B, 20), 0);

    sw_clear(A);
    sw_clear(B);
}

/* test_sw_cmp: compare identical and different arrays */
static void test_sw_cmp(void **state) {
    (void)state;

    array_t A = sw_init(64);
    array_t B = sw_init(64);

    /* Both zeroed: should be equal */
    assert_int_equal(sw_cmp(A, B), 1);

    /* Set same bit in both */
    sw_setbit(A, 5);
    sw_setbit(B, 5);
    assert_int_equal(sw_cmp(A, B), 1);

    /* Make them differ */
    sw_setbit(A, 10);
    assert_int_equal(sw_cmp(A, B), 0);

    sw_clear(A);
    sw_clear(B);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_sw_init),
        cmocka_unit_test(test_sw_setbit_tstbit),
        cmocka_unit_test(test_sw_clrbit),
        cmocka_unit_test(test_sw_flpbit),
        cmocka_unit_test(test_sw_set_ui_0),
        cmocka_unit_test(test_sw_set_copy),
        cmocka_unit_test(test_sw_cmp),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
