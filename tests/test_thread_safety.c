/**
 * @file test_thread_safety.c
 * @brief Thread safety tests for solver_ctx_t
 *
 * Validates that the solver context architecture enables safe concurrent usage:
 * - Independent contexts don't interfere
 * - Stop flag visibility across threads
 * - Timeout mechanism works correctly
 * - Debug output doesn't crash
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <stdlib.h>
#include <stdint.h>

#include "solver_ctx.h"
#include "Branching.h"
#include "platform.h"
/* bd 47j / bd xjs follow-up: this file now also drives ctg() itself from
 * several threads (test_ctg_concurrent_global_opt), which is the ONLY test
 * anywhere that does so -- and tests/run_sanitizers.sh runs TSan on exactly
 * this target (`-R test_thread_safety`). */
#include "SearchLib.h"
#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "definitions.h"

#if defined(_WIN32)
#  ifndef WIN32_LEAN_AND_MEAN
#    define WIN32_LEAN_AND_MEAN
#  endif
#  include <windows.h>
static void test_sleep_ns(long ns) {
    /* Windows Sleep has 1ms granularity; round up to the nearest millisecond. */
    DWORD ms = (DWORD)((ns + 999999L) / 1000000L);
    if (ms == 0) {
        ms = 1;
    }
    Sleep(ms);
}
/* POSIX setenv/unsetenv are unavailable under mingw-w64's MSVCRT/UCRT.
 * Use _putenv_s, which updates the CRT's getenv cache (SetEnvironmentVariableA
 * only updates the Win32 env block, so getenv() wouldn't see the change under
 * MSVCRT at runtime). Passing an empty value to _putenv_s removes the var. */
#  include <stdlib.h>
#  define test_setenv(k, v) ((void)_putenv_s((k), (v)))
#  define test_unsetenv(k)  ((void)_putenv_s((k), ""))
#else
#  include <time.h>
static void test_sleep_ns(long ns) {
    struct timespec ts = { 0, ns };
    nanosleep(&ts, NULL);
}
#  define test_setenv(k, v) setenv((k), (v), 1)
#  define test_unsetenv(k)  unsetenv((k))
#endif

/* Test that two contexts can be used independently */
static void test_independent_contexts(void **state) {
    (void)state;

    solver_ctx_t *ctx1 = solver_ctx_create();
    solver_ctx_t *ctx2 = solver_ctx_create();

    assert_non_null(ctx1);
    assert_non_null(ctx2);

    /* Set different branching parameters on each */
    solver_ctx_set_branching_factor(ctx1, 1.0);
    solver_ctx_set_bias_factor(ctx1, 0.5);
    solver_ctx_set_bias(ctx1, 3.0);

    solver_ctx_set_branching_factor(ctx2, 0.5);
    solver_ctx_set_bias_factor(ctx2, 1.0);
    solver_ctx_set_bias(ctx2, 7.0);

    /* Verify they're independent */
    assert_true(ctx1->branching_stats.branching_factor == 1.0);
    assert_true(ctx2->branching_stats.branching_factor == 0.5);
    assert_true(ctx1->branching_stats.bias_factor == 0.5);
    assert_true(ctx2->branching_stats.bias_factor == 1.0);
    assert_true(ctx1->branching_stats.bias == 3.0);
    assert_true(ctx2->branching_stats.bias == 7.0);

    solver_ctx_free(ctx1);
    solver_ctx_free(ctx2);
}

/* Thread worker that modifies ctx branching stats */
typedef struct {
    solver_ctx_t *ctx;
    double bias_value;
    int iterations;
} thread_data_t;

static void *worker_thread(void *arg) {
    thread_data_t *data = (thread_data_t *)arg;

    for (int i = 0; i < data->iterations; i++) {
        solver_ctx_set_bias(data->ctx, data->bias_value + i * 0.001);

        /* Simulate some work */
        double dummy = 0;
        for (int j = 0; j < 100; j++) {
            dummy += data->ctx->branching_stats.bias;
        }
        (void)dummy;
    }

    return NULL;
}

/* Test concurrent modification of SEPARATE contexts (should be safe) */
static void test_concurrent_separate_contexts(void **state) {
    (void)state;

    solver_ctx_t *ctx1 = solver_ctx_create();
    solver_ctx_t *ctx2 = solver_ctx_create();

    assert_non_null(ctx1);
    assert_non_null(ctx2);

    thread_data_t data1 = { .ctx = ctx1, .bias_value = 1.0, .iterations = 1000 };
    thread_data_t data2 = { .ctx = ctx2, .bias_value = 2.0, .iterations = 1000 };

    cbqs_thread_t t1, t2;
    assert_int_equal(cbqs_thread_create(&t1, worker_thread, &data1), 0);
    assert_int_equal(cbqs_thread_create(&t2, worker_thread, &data2), 0);

    assert_int_equal(cbqs_thread_join(&t1), 0);
    assert_int_equal(cbqs_thread_join(&t2), 0);

    /* Both should complete without issues
     * Final values will be near their respective targets */
    assert_true(ctx1->branching_stats.bias > 1.0);
    assert_true(ctx2->branching_stats.bias > 2.0);

    solver_ctx_free(ctx1);
    solver_ctx_free(ctx2);
}

/* Test atomic stop flag works across threads
 * This test verifies:
 * 1. The stop flag is visible across threads (atomic works)
 * 2. A stopped context reports should_stop correctly
 * 3. The stop request doesn't cause data races
 */
typedef struct {
    solver_ctx_t *ctx;
    atomic_int started;
    atomic_int observed_stop;
} stop_test_data_t;

static void *stop_watcher_thread(void *arg) {
    stop_test_data_t *data = (stop_test_data_t *)arg;

    /* Signal we've started */
    atomic_store(&data->started, 1);

    /* Spin until we see the stop flag or timeout after many iterations */
    int count = 0;
    while (!solver_ctx_should_stop(data->ctx) && count < 10000000) {
        count++;
        /* Small delay to avoid burning CPU but still be responsive */
        if (count % 1000 == 0) {
            test_sleep_ns(10000);  /* 10 microseconds */
        }
    }

    /* Record whether we saw the stop */
    if (solver_ctx_should_stop(data->ctx)) {
        atomic_store(&data->observed_stop, 1);
    }

    return (void *)(intptr_t)count;
}

static void test_stop_flag_visibility(void **state) {
    (void)state;

    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);

    stop_test_data_t data = {
        .ctx = ctx,
    };
    atomic_init(&data.started, 0);
    atomic_init(&data.observed_stop, 0);

    cbqs_thread_t watcher;
    assert_int_equal(cbqs_thread_create(&watcher, stop_watcher_thread, &data), 0);

    /* Wait for watcher thread to start */
    while (!atomic_load(&data.started)) {
        test_sleep_ns(1000);  /* 1 microsecond */
    }

    /* Now request stop */
    solver_ctx_request_stop(ctx);

    assert_int_equal(cbqs_thread_join(&watcher), 0);

    /* Verify the watcher thread saw the stop */
    assert_true(atomic_load(&data.observed_stop) == 1);
    /* And the ctx still reports stopped */
    assert_true(solver_ctx_should_stop(ctx) == 1);

    solver_ctx_free(ctx);
}

/* Test timeout functionality */
static void test_timeout_triggers_stop(void **state) {
    (void)state;

    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);

    ctx->timeout_ms = 50;  /* 50ms timeout */
    ctx->start_time_ns = cbqs_monotonic_ns();

    /* Wait for timeout */
    test_sleep_ns(100000000L);  /* 100ms */

    /* Should now report stop due to timeout */
    assert_true(solver_ctx_should_stop(ctx) == 1);

    solver_ctx_free(ctx);
}

/* Test debug output produces valid JSON (doesn't crash) */
static void test_debug_output(void **state) {
    (void)state;

    /* Set CBQS_DEBUG to enable debug */
    test_setenv("CBQS_DEBUG", "1");

    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    assert_true(ctx->debug_enabled == 1);

    /* Set some branching stats */
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 3.0);
    solver_ctx_set_look_ahead_factor(ctx, 4.0);
    solver_ctx_set_bias(ctx, 5.0);

    /* Call debug_stats - this writes to stderr
     * We can't easily capture stderr in cmocka, but we can verify it doesn't crash */
    solver_ctx_debug_stats(ctx);

    solver_ctx_free(ctx);

    /* Clean up env */
    test_unsetenv("CBQS_DEBUG");
}


/* ============================================================
 * bd 47j / bd xjs follow-up: ctg()'s cross-worker critical section
 * ============================================================
 *
 * The production topology (Model.solve -> joblib threading): every worker gets
 * its OWN solver_ctx_t, cur_sol and incumbents, and they ALL share ONE model_t*
 * -- including mod->global_opt, which ctg now writes in TWO places under
 * update_lock (the pre-loop feasible-start seed and the in-loop publish).
 *
 * Before this test NOTHING ran ctg from more than one thread: test_searchlib and
 * test_opt_sat_feasibility are single-threaded, and this file (the one target
 * run_sanitizers.sh puts under TSan) did not link SearchLib.c or solver.c at
 * all. So the new critical section had ZERO sanitizer coverage.
 *
 * What it proves:
 *   - no TSan report on the shared mod->global_opt / update_lock / g_active_ctx;
 *   - the shared incumbent is SELF-CONSISTENT after the join (its flag agrees
 *     with eval_constraints on its own vector) -- the bd 47j contract, now
 *     under concurrent writers;
 *   - no worker REGRESSES the incumbent (the feasibility-dominant acceptance
 *     rule never overwrites a feasible global_opt with an infeasible state).
 *
 * `update_lock` itself needs no setup here: cbqs_call_once(&update_lock_once,
 * update_lock_init) is the first statement of ctg.
 */

#define TS_N 8
#define TS_THREADS 4

/* MAXIMIZE sum_i (i+1)*x_i s.t. sum_i x_i >= 3, stored the way the Python layer
 * stores it: `>=` as negated-LOWER (factors -1, rhs n-k) and MAXIMIZE as negated
 * objective factors, so objective_value(0^n) == 0 and improving moves exist (a
 * MINIMIZE fixture from 0^n would never accept and the test would be vacuous).
 * global_opt carries the init_state(0, 0^n) sentinel the Python path hands ctg. */
static model_t *ts_build_max_covering_model(void) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < TS_N; i++) { add_variable(con_expr, i); }
    multiply_constant(con_expr, -1);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, TS_N - 3);      /* <=> sum x >= 3 */
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_all = init_expression();
    for (int i = 0; i < TS_N; i++) {
        expression_t *t = init_expression();
        add_variable(t, i);
        multiply_constant(t, -(i + 1));
        add_expression(obj_all, t);
        free_expression(t);
    }
    add_sense_to_expression(obj_all, LOWER);
    add_rhs_to_expression(obj_all, 0);
    add_expression_to_constraints(mod->obj, obj_all);

    preprocessing(TS_N, mod->con);
    preprocessing(TS_N, mod->obj);

    int arr[TS_N] = {0};
    mod->initial_state = init_state(0, arr, TS_N);
    mod->global_opt    = init_state(0, arr, TS_N);

    mod->n = TS_N;
    mod->depth_look_ahead = 0;
    mod->stopping_time = -1;          /* wall-clock stop OFF (oracle-indexed) */
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;
    mod->M = 200;                     /* small: TSan instrumentation is ~10x */
    mod->opt_switch_oracles = 30;

    free_expression(con_expr);
    free_expression(obj_all);
    return mod;
}

typedef struct {
    model_t *mod;
    uint64_t seed;
    int returned_feasible;
    int final_flag;
} ctg_worker_data_t;

static void *ctg_worker_thread(void *arg) {
    ctg_worker_data_t *d = (ctg_worker_data_t *)arg;

    int zeros[TS_N] = {0};
    state_t *cur_sol = init_state(0, zeros, TS_N);

    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = d->seed;
    solver_ctx_init_prng(ctx);

    incumbents_t *inc = init_incumbents(TS_N, cur_sol);
    d->returned_feasible = ctg(ctx, d->mod, cur_sol, NULL, inc);
    d->final_flag = cur_sol->feasible;

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    return NULL;
}

static void test_ctg_concurrent_global_opt(void **state) {
    (void)state;

    model_t *mod = ts_build_max_covering_model();

    /* Premise: the shared start is INFEASIBLE, so every worker has to publish a
     * first-feasible state -- i.e. the critical section is actually contended. */
    assert_int_equal(mod->global_opt->feasible, 0);
    assert_int_equal(eval_constraints(mod->con, mod->global_opt, TS_N), 0);

    ctg_worker_data_t data[TS_THREADS];
    cbqs_thread_t threads[TS_THREADS];
    for (int i = 0; i < TS_THREADS; i++) {
        data[i].mod = mod;
        data[i].seed = (uint64_t)(i + 1) * 0x9E3779B97F4A7C15ULL;
        data[i].returned_feasible = 0;
        data[i].final_flag = 0;
        assert_int_equal(cbqs_thread_create(&threads[i], ctg_worker_thread, &data[i]), 0);
    }
    for (int i = 0; i < TS_THREADS; i++) {
        assert_int_equal(cbqs_thread_join(&threads[i]), 0);
    }

    /* The contested field is self-consistent: the flag describes the vector. */
    assert_int_equal(mod->global_opt->feasible,
                     eval_constraints(mod->con, mod->global_opt, TS_N));

    /* At least one worker reached feasibility (anti-vacuity: without this the
     * assertion above is satisfied by the untouched infeasible sentinel). */
    int any_feasible = 0;
    for (int i = 0; i < TS_THREADS; i++) {
        if (data[i].returned_feasible) any_feasible = 1;
        /* per-worker state is self-consistent too */
        assert_true(data[i].returned_feasible == 0 || data[i].final_flag == 1);
    }
    assert_true(any_feasible);

    /* ...so the shared incumbent must have been raised and NEVER regressed. */
    assert_int_equal(mod->global_opt->feasible, 1);
    /* MAXIMIZE is stored negated, so a published objective is strictly < 0. */
    assert_true(mod->global_opt->tot_profit < 0);

    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_independent_contexts),
        cmocka_unit_test(test_concurrent_separate_contexts),
        cmocka_unit_test(test_stop_flag_visibility),
        cmocka_unit_test(test_timeout_triggers_stop),
        cmocka_unit_test(test_debug_output),
        cmocka_unit_test(test_ctg_concurrent_global_opt),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
