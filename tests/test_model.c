#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>
#include <cmocka.h>

#include "model.h"
#include "definitions.h"

/* ------------------------------------------------------------------ */
/* test_init_model: verify init_model returns non-NULL                 */
/* ------------------------------------------------------------------ */
static void test_init_model(void **state) {
    (void)state;
    model_t *mod = init_model();
    assert_non_null(mod);
    free_model(mod);
}

/* ------------------------------------------------------------------ */
/* test_free_model: init and free without crash                        */
/* ------------------------------------------------------------------ */
static void test_free_model(void **state) {
    (void)state;
    model_t *mod = init_model();
    assert_non_null(mod);
    free_model(mod);
    /* If we reach here, no crash -- test passes. ASan catches leaks. */
}

/* ------------------------------------------------------------------ */
/* test_model_defaults: verify sensible defaults after init            */
/* ------------------------------------------------------------------ */
static void test_model_defaults(void **state) {
    (void)state;
    model_t *mod = init_model();

    assert_int_equal(mod->n, 0);
    assert_null(mod->initial_state);
    assert_null(mod->global_opt);
    assert_non_null(mod->obj);
    assert_non_null(mod->con);
    assert_int_equal(mod->depth_look_ahead, 0);
    assert_int_equal(mod->solver, SATISFY);
    assert_int_equal(mod->stopping_condition, STOPATFIRST);
    assert_int_equal(mod->max_delta, 7);
    assert_int_equal(mod->reset_delta, 1);
    assert_int_equal(mod->num_workers, 12);
    assert_int_equal(mod->stopping_time, 1000000);
    assert_int_equal(mod->max_worse_acceptances, 10);
    assert_int_equal(mod->distance, 2);
    assert_true(mod->runtime == 0.0);

    free_model(mod);
}

/* ------------------------------------------------------------------ */
/* test_model_obj_con_initialized: obj/con have zero constraints       */
/* ------------------------------------------------------------------ */
static void test_model_obj_con_initialized(void **state) {
    (void)state;
    model_t *mod = init_model();

    assert_int_equal(mod->obj->num_constraints, 0);
    assert_int_equal(mod->con->num_constraints, 0);

    free_model(mod);
}

/* ------------------------------------------------------------------ */
/* test_model_qtg_applications_int64 (bd 9fi): qtg_applications is the  */
/* post-parallel aggregation slot — Model.solve() writes                */
/*   mod->qtg_applications = max(per-worker size_t oracle_count)         */
/* (Model.pyx), then the oracle_calls property/result read it. The      */
/* per-worker counter is size_t (64-bit), so a raw-API caller with a    */
/* huge mod->M can produce an aggregate > INT32_MAX. The field (and its */
/* Cython mirror in Model.pxd) must be int64 so the value neither       */
/* truncates in C nor raises OverflowError at the Cython assignment.    */
/* This fails on the pre-9fi `int` field (the value truncates) and      */
/* passes once it is `int64_t`.                                         */
/* ------------------------------------------------------------------ */
static void test_model_qtg_applications_int64(void **state) {
    (void)state;
    model_t *mod = init_model();

    /* default is zero (init_model) */
    assert_true(mod->qtg_applications == 0);

    /* the field must be wide enough to hold the 64-bit aggregate */
    assert_true(sizeof(mod->qtg_applications) == sizeof(int64_t));

    /* round-trip a value beyond the int32 range without truncation */
    int64_t big = (int64_t)INT32_MAX + 1000000LL;  /* 2147483647 + 1e6 */
    mod->qtg_applications = big;
    assert_true((int64_t)mod->qtg_applications == big);
    assert_true((int64_t)mod->qtg_applications > (int64_t)INT32_MAX);

    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_model),
        cmocka_unit_test(test_free_model),
        cmocka_unit_test(test_model_defaults),
        cmocka_unit_test(test_model_obj_con_initialized),
        cmocka_unit_test(test_model_qtg_applications_int64),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
