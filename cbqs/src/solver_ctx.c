/**
 * @file solver_ctx.c
 * @brief Solver context lifecycle implementation
 */

#include "solver_ctx.h"
#undef branching_stats  /* Use explicit field names in this file */
#include "platform.h"
#include "prng.h"
#include "arena.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ============================================================
 * Internal Helpers
 * ============================================================ */

static void branching_stats_init_defaults(BranchingStats_t *stats) {
    stats->branching_weights = NULL;
    stats->num_weights = 0;
    stats->branching_factor = 1.0;
    stats->bias_factor = 1.0;
    stats->bias = 5.0;
    stats->look_ahead_factor = 0.0;
    stats->variable_order = NULL;
    stats->num_vars = 0;
}

static void branching_stats_free_weights(BranchingStats_t *stats) {
    if (stats->branching_weights != NULL) {
        free(stats->branching_weights);
        stats->branching_weights = NULL;
        stats->num_weights = 0;
    }
    if (stats->variable_order != NULL) {
        free(stats->variable_order);
        stats->variable_order = NULL;
        stats->num_vars = 0;
    }
}

static void branching_stats_set_weights(BranchingStats_t *stats, const double *weights, int n) {
    branching_stats_free_weights(stats);

    if (weights == NULL || n <= 0) {
        return;
    }

    stats->branching_weights = calloc((size_t)n, sizeof(double));
    if (stats->branching_weights == NULL) {
        return;
    }
    memcpy(stats->branching_weights, weights, (size_t)n * sizeof(double));
    stats->num_weights = n;

    /* Stored AS-IS: branching_weights are SIGNED per-variable logit offsets
     * (theta_i) consumed additively by BranchingFunction (M0f, NORTHSTAR §4).
     * The old L1 normalization was removed -- normalizing would couple the
     * per-variable channel back to a shared denominator and rescale the radius
     * (NORTHSTAR §1.5); the sign and magnitude are now both meaningful. */
}

/* ============================================================
 * Lifecycle Functions
 * ============================================================ */

solver_ctx_t *solver_ctx_create(void) {
    solver_ctx_t *ctx = malloc(sizeof(solver_ctx_t));
    if (ctx == NULL) {
        return NULL;
    }

    /* Initialize all three phase-specific branching stats with defaults */
    branching_stats_init_defaults(&ctx->branching_stats_sat);
    branching_stats_init_defaults(&ctx->branching_stats_opt_sat);
    branching_stats_init_defaults(&ctx->branching_stats_opt);
    ctx->active_stats = &ctx->branching_stats_opt_sat;

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
    ctx->worker_id = 0;
    ctx->oracle_count = 0;
    /* Opt-phase branching diagnostics (M0g / bd 8an.1.7) — pure per-worker
     * observation counters, accumulated over the solve (see solver_ctx.h). */
    ctx->opt_candidates = 0;
    ctx->opt_flip_sum = 0;
    ctx->opt_flip_sumsq = 0;
    ctx->opt_free_sum = 0;
    ctx->opt_sample_cap = 0;  /* bd 0o8: 0 == unbounded (exact rejection sim) */
    memset(&ctx->master_prng, 0, sizeof(prng_state_t));

    /* Record start time */
    ctx->start_time_ns = cbqs_monotonic_ns();

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

    /* Free branching_weights and variable_order arrays for all three phases */
    branching_stats_free_weights(&ctx->branching_stats_sat);
    branching_stats_free_weights(&ctx->branching_stats_opt_sat);
    branching_stats_free_weights(&ctx->branching_stats_opt);

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
        uint64_t now_ns = cbqs_monotonic_ns();

        /* Calculate elapsed time in milliseconds */
        uint64_t elapsed_ms = (now_ns - ctx->start_time_ns) / 1000000ULL;

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

/* Backwards-compatible setters: set ALL three phase stats */

void solver_ctx_set_bias(solver_ctx_t *ctx, double bias) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.bias = bias;
    ctx->branching_stats_opt_sat.bias = bias;
    ctx->branching_stats_opt.bias = bias;
}

void solver_ctx_set_branching_weights(solver_ctx_t *ctx, const double *weights, int n) {
    if (ctx == NULL) { return; }
    branching_stats_set_weights(&ctx->branching_stats_sat, weights, n);
    branching_stats_set_weights(&ctx->branching_stats_opt_sat, weights, n);
    branching_stats_set_weights(&ctx->branching_stats_opt, weights, n);
}

void solver_ctx_set_branching_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.branching_factor = factor;
    ctx->branching_stats_opt_sat.branching_factor = factor;
    ctx->branching_stats_opt.branching_factor = factor;
}

void solver_ctx_set_bias_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.bias_factor = factor;
    ctx->branching_stats_opt_sat.bias_factor = factor;
    ctx->branching_stats_opt.bias_factor = factor;
}

void solver_ctx_set_look_ahead_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.look_ahead_factor = factor;
    ctx->branching_stats_opt_sat.look_ahead_factor = factor;
    ctx->branching_stats_opt.look_ahead_factor = factor;
}

/* ============================================================
 * Phase-Specific Setters
 * ============================================================ */

void solver_ctx_set_sat_bias(solver_ctx_t *ctx, double bias) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.bias = bias;
}

void solver_ctx_set_opt_sat_bias(solver_ctx_t *ctx, double bias) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt_sat.bias = bias;
}

void solver_ctx_set_opt_bias(solver_ctx_t *ctx, double bias) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt.bias = bias;
}

void solver_ctx_set_sat_branching_weights(solver_ctx_t *ctx, const double *weights, int n) {
    if (ctx == NULL) { return; }
    branching_stats_set_weights(&ctx->branching_stats_sat, weights, n);
}

void solver_ctx_set_opt_sat_branching_weights(solver_ctx_t *ctx, const double *weights, int n) {
    if (ctx == NULL) { return; }
    branching_stats_set_weights(&ctx->branching_stats_opt_sat, weights, n);
}

void solver_ctx_set_opt_branching_weights(solver_ctx_t *ctx, const double *weights, int n) {
    if (ctx == NULL) { return; }
    branching_stats_set_weights(&ctx->branching_stats_opt, weights, n);
}

void solver_ctx_set_sat_branching_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.branching_factor = factor;
}

void solver_ctx_set_opt_sat_branching_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt_sat.branching_factor = factor;
}

void solver_ctx_set_opt_branching_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt.branching_factor = factor;
}

void solver_ctx_set_sat_bias_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.bias_factor = factor;
}

void solver_ctx_set_opt_sat_bias_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt_sat.bias_factor = factor;
}

void solver_ctx_set_opt_bias_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt.bias_factor = factor;
}

void solver_ctx_set_sat_look_ahead_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_sat.look_ahead_factor = factor;
}

void solver_ctx_set_opt_sat_look_ahead_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt_sat.look_ahead_factor = factor;
}

void solver_ctx_set_opt_look_ahead_factor(solver_ctx_t *ctx, double factor) {
    if (ctx == NULL) { return; }
    ctx->branching_stats_opt.look_ahead_factor = factor;
}

/* ============================================================
 * Consolidated Parameter Setter
 * ============================================================ */

void solver_ctx_set_predicted_params(solver_ctx_t *ctx, double bias,
                                     double branching_factor, double bias_factor,
                                     const double *weights,
                                     const double *variable_order, int n) {
    if (ctx == NULL) { return; }

    /* Set scalar parameters on all three phases */
    ctx->branching_stats_sat.bias = bias;
    ctx->branching_stats_opt_sat.bias = bias;
    ctx->branching_stats_opt.bias = bias;

    ctx->branching_stats_sat.branching_factor = branching_factor;
    ctx->branching_stats_opt_sat.branching_factor = branching_factor;
    ctx->branching_stats_opt.branching_factor = branching_factor;

    ctx->branching_stats_sat.bias_factor = bias_factor;
    ctx->branching_stats_opt_sat.bias_factor = bias_factor;
    ctx->branching_stats_opt.bias_factor = bias_factor;

    /* Set weights on all three phases (handles NULL/clear case) */
    branching_stats_set_weights(&ctx->branching_stats_sat, weights, n);
    branching_stats_set_weights(&ctx->branching_stats_opt_sat, weights, n);
    branching_stats_set_weights(&ctx->branching_stats_opt, weights, n);

    /* Set variable ordering from priorities, or default if NULL */
    if (variable_order != NULL && n > 0) {
        solver_ctx_set_variable_order(ctx, variable_order, n);
    } else {
        solver_ctx_set_default_order(ctx, n);
    }
}

/* ============================================================
 * Variable Ordering
 * ============================================================ */

/* Helper struct for argsort */
typedef struct {
    double value;
    int index;
} indexed_value_t;

/* Compare for descending sort (higher values first), stable by index */
static int cmp_indexed_desc(const void *a, const void *b) {
    const indexed_value_t *ia = (const indexed_value_t *)a;
    const indexed_value_t *ib = (const indexed_value_t *)b;
    if (ia->value > ib->value) return -1;
    if (ia->value < ib->value) return 1;
    /* Tie-break by index (ascending) for stability */
    return (ia->index > ib->index) - (ia->index < ib->index);
}

static void free_variable_order(BranchingStats_t *stats) {
    if (stats->variable_order != NULL) {
        free(stats->variable_order);
        stats->variable_order = NULL;
        stats->num_vars = 0;
    }
}

/* Set variable_order on a single BranchingStats_t from a sorted index array */
static void set_variable_order_on_stats(BranchingStats_t *stats, const int *order, int n) {
    free_variable_order(stats);
    if (order == NULL || n <= 0) { return; }
    stats->variable_order = malloc((size_t)n * sizeof(int));
    if (stats->variable_order == NULL) { return; }
    for (int i = 0; i < n; i++) {
        stats->variable_order[i] = order[i];
    }
    stats->num_vars = n;
}

void solver_ctx_set_variable_order(solver_ctx_t *ctx, const double *priorities, int n) {
    if (ctx == NULL) { return; }

    if (priorities == NULL || n <= 0) {
        /* Clear all three phases */
        free_variable_order(&ctx->branching_stats_sat);
        free_variable_order(&ctx->branching_stats_opt_sat);
        free_variable_order(&ctx->branching_stats_opt);
        return;
    }

    /* Argsort priorities descending */
    indexed_value_t *indexed = malloc((size_t)n * sizeof(indexed_value_t));
    if (indexed == NULL) { return; }

    for (int i = 0; i < n; i++) {
        indexed[i].value = priorities[i];
        indexed[i].index = i;
    }

    qsort(indexed, (size_t)n, sizeof(indexed_value_t), cmp_indexed_desc);

    int *order = malloc((size_t)n * sizeof(int));
    if (order == NULL) {
        free(indexed);
        return;
    }
    for (int i = 0; i < n; i++) {
        order[i] = indexed[i].index;
    }
    free(indexed);

    /* Set all three phases (backwards compat) */
    set_variable_order_on_stats(&ctx->branching_stats_sat, order, n);
    set_variable_order_on_stats(&ctx->branching_stats_opt_sat, order, n);
    set_variable_order_on_stats(&ctx->branching_stats_opt, order, n);

    free(order);
}

void solver_ctx_set_default_order(solver_ctx_t *ctx, int n) {
    if (ctx == NULL) { return; }

    if (n <= 0) {
        free_variable_order(&ctx->branching_stats_sat);
        free_variable_order(&ctx->branching_stats_opt_sat);
        free_variable_order(&ctx->branching_stats_opt);
        return;
    }

    int *order = malloc((size_t)n * sizeof(int));
    if (order == NULL) { return; }
    for (int i = 0; i < n; i++) {
        order[i] = i;
    }

    /* Set all three phases (backwards compat) */
    set_variable_order_on_stats(&ctx->branching_stats_sat, order, n);
    set_variable_order_on_stats(&ctx->branching_stats_opt_sat, order, n);
    set_variable_order_on_stats(&ctx->branching_stats_opt, order, n);

    free(order);
}

void solver_ctx_set_degree_order(solver_ctx_t *ctx, const int *degrees, int n) {
    if (ctx == NULL) { return; }

    if (degrees == NULL || n <= 0) {
        free_variable_order(&ctx->branching_stats_sat);
        free_variable_order(&ctx->branching_stats_opt_sat);
        free_variable_order(&ctx->branching_stats_opt);
        return;
    }

    /* Convert int degrees to double priorities and reuse set_variable_order */
    double *priorities = malloc((size_t)n * sizeof(double));
    if (priorities == NULL) { return; }

    for (int i = 0; i < n; i++) {
        priorities[i] = (double)degrees[i];
    }

    solver_ctx_set_variable_order(ctx, priorities, n);
    free(priorities);
}

/* ============================================================
 * Debug Output
 * ============================================================ */

void solver_ctx_debug_stats(solver_ctx_t *ctx) {
    if (ctx == NULL || !ctx->debug_enabled) {
        return;
    }

    /* Calculate elapsed time */
    uint64_t now_ns = cbqs_monotonic_ns();
    double elapsed_sec = (double)(now_ns - ctx->start_time_ns) / 1e9;

    /* Output JSON to stderr */
    fprintf(stderr,
            "{\"type\":\"solve_stats\","
            "\"elapsed_sec\":%.3f,"
            "\"bias\":%.2f,"
            "\"bias_factor\":%.2f,"
            "\"branching_factor\":%.2f,"
            "\"look_ahead_factor\":%.2f,"
            "\"has_branching_weights\":%s,"
            "\"timeout_ms\":%llu,"
            "\"stopped\":%s}\n",
            elapsed_sec,
            ctx->active_stats->bias,
            ctx->active_stats->bias_factor,
            ctx->active_stats->branching_factor,
            ctx->active_stats->look_ahead_factor,
            (ctx->active_stats->branching_weights != NULL) ? "true" : "false",
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
    int nprocs = cbqs_num_processors();
    if (nprocs > 0) {
        return nprocs;
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

    /* Initialize thread-local PRNG for this portfolio worker. Jumping the
     * master stream worker_id times gives each worker a non-overlapping
     * sequence; worker_id == 0 reproduces the legacy single-stream behavior. */
    prng_seed_thread(&ctx->master_prng, ctx->worker_id);
}

void solver_ctx_set_worker_id(solver_ctx_t *ctx, int worker_id) {
    if (ctx == NULL) {
        return;
    }
    ctx->worker_id = worker_id;
}

/* ============================================================
 * Arena Management
 * ============================================================ */

void solver_ctx_arena_reset(solver_ctx_t *ctx) {
    if (ctx != NULL && ctx->arena != NULL) {
        arena_reset(ctx->arena);
    }
}
