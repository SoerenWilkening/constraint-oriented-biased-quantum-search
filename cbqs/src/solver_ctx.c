/**
 * @file solver_ctx.c
 * @brief Solver context lifecycle implementation
 */

/* Feature test macro for GNU/POSIX extensions.
 * Enables clock_gettime, CLOCK_MONOTONIC, and _SC_NPROCESSORS_ONLN.
 * Must be defined before any includes to take effect.
 */
#define _GNU_SOURCE

#include "solver_ctx.h"
#include "prng.h"
#include "arena.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <unistd.h>  /* for sysconf */

/* ============================================================
 * Lifecycle Functions
 * ============================================================ */

solver_ctx_t *solver_ctx_create(void) {
    solver_ctx_t *ctx = malloc(sizeof(solver_ctx_t));
    if (ctx == NULL) {
        return NULL;
    }

    /* Initialize branching_stats with default values */
    ctx->branching_stats.branching_weights = NULL;
    ctx->branching_stats.num_weights = 0;
    ctx->branching_stats.branching_factor = 1.0;
    ctx->branching_stats.bias_factor = 1;
    ctx->branching_stats.bias = 5;
    ctx->branching_stats.look_factor = 0.0;

    /* Initialize atomic stop flag */
    atomic_init(&ctx->stop, false);

    /* No timeout by default */
    ctx->timeout_ms = 0;

    /* Check CBQS_DEBUG environment variable */
    ctx->debug_enabled = (getenv("CBQS_DEBUG") != NULL);

    /* Initialize PRNG-related fields */
    ctx->seed = 0;
    ctx->seed_used = 0;
    ctx->num_threads = 0;
    ctx->num_threads_used = 0;
    memset(&ctx->master_prng, 0, sizeof(prng_state_t));

    /* Record start time */
    clock_gettime(CLOCK_MONOTONIC, &ctx->start_time);

    /* Create arena for hot-path allocations */
    ctx->arena = arena_create(ARENA_DEFAULT_SIZE);
    if (ctx->arena == NULL) {
        free(ctx);
        return NULL;
    }

    return ctx;
}

void solver_ctx_free(solver_ctx_t *ctx) {
    if (ctx == NULL) {
        return;
    }

    /* Free branching_weights array if allocated */
    if (ctx->branching_stats.branching_weights != NULL) {
        free(ctx->branching_stats.branching_weights);
        ctx->branching_stats.branching_weights = NULL;
    }

    /* Free arena if allocated */
    if (ctx->arena != NULL) {
        arena_free(ctx->arena);
        ctx->arena = NULL;
    }

    free(ctx);
}

/* ============================================================
 * Stop Signal API
 * ============================================================ */

void solver_ctx_request_stop(solver_ctx_t *ctx) {
    if (ctx == NULL) {
        return;
    }
    atomic_store(&ctx->stop, true);
}

int solver_ctx_should_stop(solver_ctx_t *ctx) {
    if (ctx == NULL) {
        return 0;
    }

    /* Check atomic stop flag first */
    if (atomic_load(&ctx->stop)) {
        return 1;
    }

    /* Check timeout if configured */
    if (ctx->timeout_ms > 0) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);

        /* Calculate elapsed time in milliseconds */
        uint64_t elapsed_ms = (uint64_t)(now.tv_sec - ctx->start_time.tv_sec) * 1000;
        elapsed_ms += (uint64_t)(now.tv_nsec - ctx->start_time.tv_nsec) / 1000000;

        if (elapsed_ms >= ctx->timeout_ms) {
            /* Set stop flag for subsequent checks */
            atomic_store(&ctx->stop, true);
            return 1;
        }
    }

    return 0;
}

/* ============================================================
 * Context-aware Setters
 * ============================================================ */

void solver_ctx_set_bias(solver_ctx_t *ctx, double bias) {
    if (ctx == NULL) {
        return;
    }
    ctx->branching_stats.bias = bias;
}

void solver_ctx_set_branching_weights(solver_ctx_t *ctx, const double *weights, int n) {
    if (ctx == NULL) {
        return;
    }

    /* Free existing weights if present */
    if (ctx->branching_stats.branching_weights != NULL) {
        free(ctx->branching_stats.branching_weights);
        ctx->branching_stats.branching_weights = NULL;
        ctx->branching_stats.num_weights = 0;
    }

    /* NULL/empty means clear weights */
    if (weights == NULL || n <= 0) {
        return;
    }

    /* Allocate and copy */
    ctx->branching_stats.branching_weights = calloc((size_t)n, sizeof(double));
    if (ctx->branching_stats.branching_weights == NULL) {
        return;
    }
    memcpy(ctx->branching_stats.branching_weights, weights, (size_t)n * sizeof(double));
    ctx->branching_stats.num_weights = n;

    /* L1 normalize: sum all values (all non-negative, validated upstream) */
    double sum = 0.0;
    for (int i = 0; i < n; i++) {
        sum += fabs(ctx->branching_stats.branching_weights[i]);
    }
    if (sum > 0.0) {
        for (int i = 0; i < n; i++) {
            ctx->branching_stats.branching_weights[i] /= sum;
        }
    }
}

void solver_ctx_set_branching_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) {
        return;
    }
    ctx->branching_stats.branching_factor = factor;
}

void solver_ctx_set_bias_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) {
        return;
    }
    ctx->branching_stats.bias_factor = factor;
}

void solver_ctx_set_look_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) {
        return;
    }
    ctx->branching_stats.look_factor = factor;
}

/* ============================================================
 * Debug Output
 * ============================================================ */

void solver_ctx_debug_stats(solver_ctx_t *ctx) {
    if (ctx == NULL || !ctx->debug_enabled) {
        return;
    }

    /* Calculate elapsed time */
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    double elapsed_sec = (double)(now.tv_sec - ctx->start_time.tv_sec);
    elapsed_sec += (double)(now.tv_nsec - ctx->start_time.tv_nsec) / 1e9;

    /* Output JSON to stderr */
    fprintf(stderr,
            "{\"type\":\"solve_stats\","
            "\"elapsed_sec\":%.3f,"
            "\"bias\":%.2f,"
            "\"bias_factor\":%.2f,"
            "\"branching_factor\":%.2f,"
            "\"look_factor\":%.2f,"
            "\"has_branching_weights\":%s,"
            "\"timeout_ms\":%llu,"
            "\"stopped\":%s}\n",
            elapsed_sec,
            ctx->branching_stats.bias,
            ctx->branching_stats.bias_factor,
            ctx->branching_stats.branching_factor,
            ctx->branching_stats.look_factor,
            (ctx->branching_stats.branching_weights != NULL) ? "true" : "false",
            (unsigned long long)ctx->timeout_ms,
            atomic_load(&ctx->stop) ? "true" : "false");
}

/* ============================================================
 * PRNG and Thread Configuration
 * ============================================================ */

int solver_ctx_get_default_threads(void) {
    /* Check CBQS_THREADS env var first */
    const char *env_threads = getenv("CBQS_THREADS");
    if (env_threads != NULL) {
        int threads = atoi(env_threads);
        if (threads > 0) {
            return threads;
        }
    }

    /* Try to detect CPU count */
    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    if (nprocs > 0) {
        return (int)nprocs;
    }

    /* Fallback to 4 threads */
    return 4;
}

void solver_ctx_init_prng(solver_ctx_t *ctx) {
    if (ctx == NULL) {
        return;
    }

    /* Resolve seed */
    if (ctx->seed == 0) {
        ctx->seed_used = prng_get_entropy_seed();
    } else {
        ctx->seed_used = ctx->seed;
    }

    /* Initialize master PRNG */
    prng_seed_from_state(&ctx->master_prng, ctx->seed_used);

    /* Resolve thread count */
    if (ctx->num_threads <= 0) {
        ctx->num_threads_used = solver_ctx_get_default_threads();
    } else {
        ctx->num_threads_used = ctx->num_threads;
    }

    /* Initialize thread-local PRNG for main thread (thread 0) */
    prng_seed_thread(&ctx->master_prng, 0);
}

/* ============================================================
 * Arena Management
 * ============================================================ */

void solver_ctx_arena_reset(solver_ctx_t *ctx) {
    if (ctx != NULL && ctx->arena != NULL) {
        arena_reset(ctx->arena);
    }
}
