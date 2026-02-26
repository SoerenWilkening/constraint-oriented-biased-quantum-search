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
#include <pthread.h>
#include <stdlib.h>
#include <stdint.h>

#include "solver_ctx.h"
#include "Branching.h"

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

    pthread_t t1, t2;
    pthread_create(&t1, NULL, worker_thread, &data1);
    pthread_create(&t2, NULL, worker_thread, &data2);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);

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
            struct timespec ts = { 0, 10000 };  /* 10 microseconds */
            nanosleep(&ts, NULL);
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

    pthread_t watcher;
    pthread_create(&watcher, NULL, stop_watcher_thread, &data);

    /* Wait for watcher thread to start */
    while (!atomic_load(&data.started)) {
        struct timespec ts = { 0, 1000 };  /* 1 microsecond */
        nanosleep(&ts, NULL);
    }

    /* Now request stop */
    solver_ctx_request_stop(ctx);

    void *result;
    pthread_join(watcher, &result);

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
    clock_gettime(CLOCK_MONOTONIC, &ctx->start_time);

    /* Wait for timeout */
    struct timespec delay = { .tv_sec = 0, .tv_nsec = 100000000 };  /* 100ms */
    nanosleep(&delay, NULL);

    /* Should now report stop due to timeout */
    assert_true(solver_ctx_should_stop(ctx) == 1);

    solver_ctx_free(ctx);
}

/* Test debug output produces valid JSON (doesn't crash) */
static void test_debug_output(void **state) {
    (void)state;

    /* Set CBQS_DEBUG to enable debug */
    setenv("CBQS_DEBUG", "1", 1);

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
    unsetenv("CBQS_DEBUG");
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_independent_contexts),
        cmocka_unit_test(test_concurrent_separate_contexts),
        cmocka_unit_test(test_stop_flag_visibility),
        cmocka_unit_test(test_timeout_triggers_stop),
        cmocka_unit_test(test_debug_output),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
