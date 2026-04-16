#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <string.h>

#include "variable_vector.h"

/* test_vv_init_free: init with n=0, verify fields, free without crash */
static void test_vv_init_free(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(0);
	assert_int_equal(vv.n, 0);
	assert_null(vv.indices);
	assert_null(vv.lb);
	assert_null(vv.ub);
	assert_null(vv.vtype);
	c_variable_vector_free(&vv);
}

/* test_vv_init_positive_n: init with n>0, verify non-NULL arrays and size */
static void test_vv_init_positive_n(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(5);
	assert_int_equal(vv.n, 5);
	assert_non_null(vv.indices);
	assert_non_null(vv.lb);
	assert_non_null(vv.ub);
	assert_non_null(vv.vtype);
	c_variable_vector_free(&vv);
}

/* test_vv_zero_initialized: arrays are zero-initialized after init */
static void test_vv_zero_initialized(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(4);
	for (int i = 0; i < 4; i++) {
		assert_int_equal(vv.indices[i], 0);
		assert_int_equal(vv.lb[i], 0);
		assert_int_equal(vv.ub[i], 0);
		assert_int_equal(vv.vtype[i], 0);
	}
	c_variable_vector_free(&vv);
}

/* test_vv_write_read: write values then read them back */
static void test_vv_write_read(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(3);

	vv.indices[0] = 10; vv.indices[1] = 20; vv.indices[2] = 30;
	vv.lb[0] = 0;  vv.lb[1] = -5; vv.lb[2] = 1;
	vv.ub[0] = 1;  vv.ub[1] = 10; vv.ub[2] = 100;
	vv.vtype[0] = INTEGER; vv.vtype[1] = FRACTIONAL; vv.vtype[2] = INTEGER;

	assert_int_equal(vv.indices[0], 10);
	assert_int_equal(vv.indices[2], 30);
	assert_int_equal(vv.lb[1], -5);
	assert_int_equal(vv.ub[2], 100);
	assert_int_equal(vv.vtype[0], INTEGER);
	assert_int_equal(vv.vtype[1], FRACTIONAL);

	c_variable_vector_free(&vv);
}

/* test_vv_large: init with large n, verify memory is accessible */
static void test_vv_large(void **state) {
	(void)state;

	int n = 10000;
	c_variable_vector_t vv = c_variable_vector_init(n);
	assert_int_equal(vv.n, n);
	assert_non_null(vv.indices);

	/* Write to first and last elements */
	vv.indices[0] = 42;
	vv.indices[n - 1] = 99;
	vv.lb[n - 1] = -1;
	vv.ub[n - 1] = 1;

	assert_int_equal(vv.indices[0], 42);
	assert_int_equal(vv.indices[n - 1], 99);
	assert_int_equal(vv.lb[n - 1], -1);
	assert_int_equal(vv.ub[n - 1], 1);

	c_variable_vector_free(&vv);
}

/* test_vv_free_nulls_pointers: after free, pointers are NULL and n is 0 */
static void test_vv_free_nulls_pointers(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(5);
	c_variable_vector_free(&vv);

	assert_int_equal(vv.n, 0);
	assert_null(vv.indices);
	assert_null(vv.lb);
	assert_null(vv.ub);
	assert_null(vv.vtype);
}

/* test_vv_init_negative_n: init with negative n clamps to 0 */
static void test_vv_init_negative_n(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(-5);
	assert_int_equal(vv.n, 0);
	assert_null(vv.indices);
	assert_null(vv.lb);
	assert_null(vv.ub);
	assert_null(vv.vtype);
	c_variable_vector_free(&vv);
}

/* test_vv_double_free_safe: calling free twice does not crash */
static void test_vv_double_free_safe(void **state) {
	(void)state;

	c_variable_vector_t vv = c_variable_vector_init(3);
	c_variable_vector_free(&vv);
	c_variable_vector_free(&vv);  /* Should be safe (all NULL) */
	assert_int_equal(vv.n, 0);
}

int main(void) {
	const struct CMUnitTest tests[] = {
		cmocka_unit_test(test_vv_init_free),
		cmocka_unit_test(test_vv_init_positive_n),
		cmocka_unit_test(test_vv_zero_initialized),
		cmocka_unit_test(test_vv_write_read),
		cmocka_unit_test(test_vv_large),
		cmocka_unit_test(test_vv_free_nulls_pointers),
		cmocka_unit_test(test_vv_init_negative_n),
		cmocka_unit_test(test_vv_double_free_safe),
	};
	return cmocka_run_group_tests(tests, NULL, NULL);
}
