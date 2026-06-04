/**
 * @file test_solver_ctx_phases.c
 * @brief Tests for M1: Phase-specific BranchingStats in solver_ctx_t
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <stdlib.h>

/* Undefine compat macro so tests can access all three fields explicitly */
#include "solver_ctx.h"
#include "prng.h"
#undef branching_stats

/* ============================================================
 * Setup/Teardown
 * ============================================================ */

static int setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) {
        return -1;
    }
    *state = ctx;
    return 0;
}

static int teardown(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_free(ctx);
    *state = NULL;
    return 0;
}

/* ============================================================
 * Tests
 * ============================================================ */

/* test_three_stats_initialized_with_defaults:
 * All three BranchingStats_t should have the same default values. */
static void test_three_stats_initialized_with_defaults(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* SAT defaults */
    assert_null(ctx->branching_stats_sat.branching_weights);
    assert_int_equal(ctx->branching_stats_sat.num_weights, 0);
    assert_true(ctx->branching_stats_sat.bias == 5.0);
    assert_true(ctx->branching_stats_sat.branching_factor == 1.0);
    assert_true(ctx->branching_stats_sat.bias_factor == 1.0);
    assert_true(ctx->branching_stats_sat.look_ahead_factor == 0.0);

    /* OPT_SAT defaults */
    assert_null(ctx->branching_stats_opt_sat.branching_weights);
    assert_int_equal(ctx->branching_stats_opt_sat.num_weights, 0);
    assert_true(ctx->branching_stats_opt_sat.bias == 5.0);
    assert_true(ctx->branching_stats_opt_sat.branching_factor == 1.0);
    assert_true(ctx->branching_stats_opt_sat.bias_factor == 1.0);
    assert_true(ctx->branching_stats_opt_sat.look_ahead_factor == 0.0);

    /* OPT defaults */
    assert_null(ctx->branching_stats_opt.branching_weights);
    assert_int_equal(ctx->branching_stats_opt.num_weights, 0);
    assert_true(ctx->branching_stats_opt.bias == 5.0);
    assert_true(ctx->branching_stats_opt.branching_factor == 1.0);
    assert_true(ctx->branching_stats_opt.bias_factor == 1.0);
    assert_true(ctx->branching_stats_opt.look_ahead_factor == 0.0);

    /* active_stats should point to opt_sat */
    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt_sat);
}

/* test_set_sat_bias_independent_of_opt:
 * Setting SAT bias should not affect OPT or OPT_SAT bias. */
static void test_set_sat_bias_independent_of_opt(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 10.0);

    assert_true(ctx->branching_stats_sat.bias == 10.0);
    assert_true(ctx->branching_stats_opt_sat.bias == 5.0);
    assert_true(ctx->branching_stats_opt.bias == 5.0);
}

/* test_set_opt_sat_weights_independent_of_sat:
 * Setting OPT_SAT weights should not affect SAT or OPT weights. */
static void test_set_opt_sat_weights_independent_of_sat(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double weights[] = {1.0, 2.0, 3.0};
    solver_ctx_set_opt_sat_branching_weights(ctx, weights, 3);

    /* OPT_SAT should have weights set */
    assert_non_null(ctx->branching_stats_opt_sat.branching_weights);
    assert_int_equal(ctx->branching_stats_opt_sat.num_weights, 3);

    /* SAT and OPT should remain NULL */
    assert_null(ctx->branching_stats_sat.branching_weights);
    assert_int_equal(ctx->branching_stats_sat.num_weights, 0);
    assert_null(ctx->branching_stats_opt.branching_weights);
    assert_int_equal(ctx->branching_stats_opt.num_weights, 0);
}

/* test_set_opt_bias_independent_of_opt_sat:
 * Setting OPT bias should not affect OPT_SAT or SAT bias. */
static void test_set_opt_bias_independent_of_opt_sat(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_opt_bias(ctx, 20.0);

    assert_true(ctx->branching_stats_opt.bias == 20.0);
    assert_true(ctx->branching_stats_opt_sat.bias == 5.0);
    assert_true(ctx->branching_stats_sat.bias == 5.0);
}

/* test_free_releases_all_three_stats:
 * Setting weights on all three phases, then freeing should not leak. */
static void test_free_releases_all_three_stats(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    double w1[] = {1.0, 1.0};
    double w2[] = {2.0, 2.0};
    double w3[] = {3.0, 3.0};

    solver_ctx_set_sat_branching_weights(ctx, w1, 2);
    solver_ctx_set_opt_sat_branching_weights(ctx, w2, 2);
    solver_ctx_set_opt_branching_weights(ctx, w3, 2);

    assert_non_null(ctx->branching_stats_sat.branching_weights);
    assert_non_null(ctx->branching_stats_opt_sat.branching_weights);
    assert_non_null(ctx->branching_stats_opt.branching_weights);

    /* Free is handled by teardown; if ASan is on, any leak would fail */
}

/* test_default_values_match_current_defaults:
 * The backwards-compat setter (unprefixed) should set ALL three stats. */
static void test_default_values_match_current_defaults(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Use the backwards-compat unprefixed setter */
    solver_ctx_set_bias(ctx, 7.0);

    /* All three should be updated */
    assert_true(ctx->branching_stats_sat.bias == 7.0);
    assert_true(ctx->branching_stats_opt_sat.bias == 7.0);
    assert_true(ctx->branching_stats_opt.bias == 7.0);

    /* Also test unprefixed branching_factor setter */
    solver_ctx_set_branching_factor(ctx, 2.5);
    assert_true(ctx->branching_stats_sat.branching_factor == 2.5);
    assert_true(ctx->branching_stats_opt_sat.branching_factor == 2.5);
    assert_true(ctx->branching_stats_opt.branching_factor == 2.5);

    /* Also test unprefixed bias_factor setter */
    solver_ctx_set_bias_factor(ctx, 3.0);
    assert_true(ctx->branching_stats_sat.bias_factor == 3.0);
    assert_true(ctx->branching_stats_opt_sat.bias_factor == 3.0);
    assert_true(ctx->branching_stats_opt.bias_factor == 3.0);

    /* Also test unprefixed look_ahead_factor setter */
    solver_ctx_set_look_ahead_factor(ctx, 0.5);
    assert_true(ctx->branching_stats_sat.look_ahead_factor == 0.5);
    assert_true(ctx->branching_stats_opt_sat.look_ahead_factor == 0.5);
    assert_true(ctx->branching_stats_opt.look_ahead_factor == 0.5);
}

/* ============================================================
 * M0c (bd 8an.1.3): per-worker PRNG stream decorrelation
 * ============================================================ */

/**
 * solver_ctx_init_prng() must seed the worker's thread-local stream from the
 * master jumped ctx->worker_id times. Verifies: the default worker_id is 0; the
 * setter stores the value; under a fixed seed, worker_id == 0 is reproducible
 * across contexts (so single-worker determinism, CLAUDE.md §8, is preserved),
 * and worker_id == 1 yields a decorrelated (distinct) stream.
 */
static void test_init_prng_decorrelates_by_worker_id(void **unused) {
    (void)unused;
    const uint64_t SEED = 0x5EEDULL;   /* non-zero: used verbatim, no entropy */
    enum { NV = 6 };

    /* Default worker_id is 0, and the setter stores what it is given. */
    solver_ctx_t *probe = solver_ctx_create();
    assert_int_equal(probe->worker_id, 0);
    solver_ctx_set_worker_id(probe, 3);
    assert_int_equal(probe->worker_id, 3);
    solver_ctx_set_worker_id(NULL, 7);   /* NULL-safe, no crash */
    solver_ctx_free(probe);

    double w0[NV], w0_again[NV], w1[NV];

    solver_ctx_t *a = solver_ctx_create();
    a->seed = SEED;
    solver_ctx_set_worker_id(a, 0);
    solver_ctx_init_prng(a);
    for (int i = 0; i < NV; i++) w0[i] = prng_next_double();
    solver_ctx_free(a);

    solver_ctx_t *b = solver_ctx_create();   /* worker 0 again, same seed */
    b->seed = SEED;
    solver_ctx_set_worker_id(b, 0);
    solver_ctx_init_prng(b);
    for (int i = 0; i < NV; i++) w0_again[i] = prng_next_double();
    solver_ctx_free(b);

    solver_ctx_t *d = solver_ctx_create();   /* worker 1, same seed */
    d->seed = SEED;
    solver_ctx_set_worker_id(d, 1);
    solver_ctx_init_prng(d);
    for (int i = 0; i < NV; i++) w1[i] = prng_next_double();
    solver_ctx_free(d);

    int reproducible = 1, distinct = 0;
    for (int i = 0; i < NV; i++) {
        if (w0[i] != w0_again[i]) reproducible = 0;
        if (w0[i] != w1[i]) distinct = 1;
    }
    assert_true(reproducible);   /* worker_id 0 stable -> legacy stream preserved */
    assert_true(distinct);       /* worker_id 1 jumped -> decorrelated */
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_three_stats_initialized_with_defaults, setup, teardown),
        cmocka_unit_test_setup_teardown(test_set_sat_bias_independent_of_opt, setup, teardown),
        cmocka_unit_test_setup_teardown(test_set_opt_sat_weights_independent_of_sat, setup, teardown),
        cmocka_unit_test_setup_teardown(test_set_opt_bias_independent_of_opt_sat, setup, teardown),
        cmocka_unit_test_setup_teardown(test_free_releases_all_three_stats, setup, teardown),
        cmocka_unit_test_setup_teardown(test_default_values_match_current_defaults, setup, teardown),
        cmocka_unit_test(test_init_prng_decorrelates_by_worker_id),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
