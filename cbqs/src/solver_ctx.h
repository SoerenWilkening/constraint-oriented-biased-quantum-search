/**
 * @file solver_ctx.h
 * @brief Solver context struct and lifecycle functions
 *
 * This module provides the solver_ctx_t type which encapsulates all per-solve
 * mutable state, replacing global variables like BranchingStats and stop_flag.
 * The context enables thread-safe parallel solves and clean resource management.
 */

#ifndef SOLVER_CTX_H
#define SOLVER_CTX_H

#include <stdatomic.h>
#include <stdint.h>
#include <time.h>
#include "Branching.h"

/**
 * @brief Solver context carrying all per-solve mutable state
 *
 * This struct replaces global variables, enabling:
 * - Thread-safe parallel solves (each solve gets its own context)
 * - Clean resource management (create/free lifecycle)
 * - Timeout support via start_time + timeout_ms
 * - Debug output control via CBQS_DEBUG environment variable
 */
typedef struct {
    /** Branching statistics (embedded, not pointer) */
    BranchingStats_t branching_stats;

    /** Thread-safe stop signal (atomic for cross-thread safety) */
    atomic_bool stop;

    /** Timeout in milliseconds (0 = no timeout) */
    uint64_t timeout_ms;

    /** Solve start time (for timeout calculation) */
    struct timespec start_time;

    /** Debug output enabled (checked from CBQS_DEBUG env var at init) */
    int debug_enabled;
} solver_ctx_t;

/* ============================================================
 * Lifecycle Functions
 * ============================================================ */

/**
 * @brief Create and initialize a new solver context
 *
 * Allocates a solver_ctx_t and initializes all fields:
 * - branching_stats with default values (matching global BranchingStats)
 * - stop = false
 * - timeout_ms = 0 (no timeout)
 * - start_time = current time
 * - debug_enabled = true if CBQS_DEBUG env var is set
 *
 * @return Newly allocated context, or NULL on allocation failure
 */
solver_ctx_t *solver_ctx_create(void);

/**
 * @brief Free a solver context and all owned resources
 *
 * Frees:
 * - branching_stats.obj_dependent array (if not NULL)
 * - branching_stats.constraint_dependent array (if not NULL)
 * - The context struct itself
 *
 * @param ctx Context to free (safe to pass NULL)
 */
void solver_ctx_free(solver_ctx_t *ctx);

/* ============================================================
 * Stop Signal API
 * ============================================================ */

/**
 * @brief Request the solver to stop
 *
 * Thread-safe. Can be called from any thread (e.g., signal handler,
 * timeout thread, or main thread) to request graceful termination.
 *
 * @param ctx Solver context
 */
void solver_ctx_request_stop(solver_ctx_t *ctx);

/**
 * @brief Check if solver should stop
 *
 * Thread-safe. Checks:
 * 1. The atomic stop flag
 * 2. If timeout_ms > 0, whether elapsed time exceeds timeout
 *
 * If timeout is exceeded, sets the stop flag for subsequent checks.
 *
 * @param ctx Solver context
 * @return 1 if should stop, 0 otherwise
 */
int solver_ctx_should_stop(solver_ctx_t *ctx);

/* ============================================================
 * Context-aware Setters (parallel to existing global setters)
 * ============================================================ */

/**
 * @brief Set all branching factor weights
 *
 * @param ctx Solver context
 * @param obj Objective factor weight
 * @param con Constraint factor weight
 * @param bias Bias factor weight
 * @param look Look-ahead factor weight
 */
void solver_ctx_set_factors(solver_ctx_t *ctx, double obj, double con, double bias, double look);

/**
 * @brief Set the bias value
 *
 * @param ctx Solver context
 * @param bias Bias value (default: 5)
 */
void solver_ctx_set_bias(solver_ctx_t *ctx, double bias);

/**
 * @brief Set objective dependence array
 *
 * Copies the provided array into the context. Frees any existing array first.
 *
 * @param ctx Solver context
 * @param dep Dependence values to copy
 * @param n Number of elements
 */
void solver_ctx_set_obj_dependence(solver_ctx_t *ctx, double *dep, int n);

/**
 * @brief Set constraint dependence array
 *
 * Copies the provided array into the context. Frees any existing array first.
 *
 * @param ctx Solver context
 * @param dep Dependence values to copy
 * @param n Number of elements
 */
void solver_ctx_set_constraint_dependence(solver_ctx_t *ctx, double *dep, int n);

/* ============================================================
 * Debug Output
 * ============================================================ */

/**
 * @brief Output debug statistics in JSON format to stderr
 *
 * Only outputs if ctx->debug_enabled is true (CBQS_DEBUG was set at init).
 * Outputs JSON like: {"type":"solve_stats","elapsed_sec":1.234,...}
 *
 * @param ctx Solver context
 */
void solver_ctx_debug_stats(solver_ctx_t *ctx);

#endif /* SOLVER_CTX_H */
