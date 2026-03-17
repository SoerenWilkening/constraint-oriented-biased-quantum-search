/**
 * @file solver_ctx.h
 * @brief Solver context struct and lifecycle functions
 *
 * This module provides the solver_ctx_t type which encapsulates all per-solve
 * mutable state, encapsulating all per-solve mutable state (replaces former global variables).
 * The context enables thread-safe parallel solves and clean resource management.
 */

#ifndef SOLVER_CTX_H
#define SOLVER_CTX_H

#include <stdatomic.h>
#include <stdint.h>
#include <time.h>
#include "Branching.h"
#include "prng.h"
#include "arena.h"

/**
 * @brief Solver context carrying all per-solve mutable state
 *
 * This struct replaces global variables, enabling:
 * - Thread-safe parallel solves (each solve gets its own context)
 * - Clean resource management (create/free lifecycle)
 * - Timeout support via start_time + timeout_ms
 * - Debug output control via CBQS_DEBUG environment variable
 *
 * Note: Using named struct 'solver_ctx' to match forward declaration in Branching.h
 */
struct solver_ctx {
    /** Phase-specific branching statistics */
    BranchingStats_t branching_stats_sat;
    BranchingStats_t branching_stats_opt_sat;
    BranchingStats_t branching_stats_opt;

    /** Pointer to currently active phase stats */
    BranchingStats_t *active_stats;

    /** Thread-safe stop signal (atomic for cross-thread safety) */
    atomic_bool stop;

    /** Timeout in milliseconds (0 = no timeout) */
    uint64_t timeout_ms;

    /** Solve start time (for timeout calculation) */
    struct timespec start_time;

    /** Debug output enabled (checked from CBQS_DEBUG env var at init) */
    int debug_enabled;

    /** Master seed for PRNG (0 = auto-generate from entropy) */
    uint64_t seed;

    /** Actual seed used (stored after resolution, for reproducibility) */
    uint64_t seed_used;

    /** Number of threads for parallel operations (0 = auto-detect) */
    int num_threads;

    /** Actual thread count used (stored after resolution) */
    int num_threads_used;

    /** Master PRNG state for deriving thread-specific states */
    prng_state_t master_prng;

    /** Arena for hot-path allocations (per-solve lifetime) */
    arena_t *arena;
};
typedef struct solver_ctx solver_ctx_t;

/* Backwards-compatibility macro: ctx->branching_stats resolves to ctx->branching_stats_opt.
 * Code that needs explicit access to all three should #undef branching_stats after including. */
#define branching_stats branching_stats_opt

/* ============================================================
 * Lifecycle Functions
 * ============================================================ */

/**
 * @brief Create and initialize a new solver context
 *
 * Allocates a solver_ctx_t and initializes all fields:
 * - branching_stats with default values
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
 * - branching_stats.branching_weights array (if not NULL)
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
 * Context-aware Setters
 * ============================================================ */

/**
 * @brief Set the bias value
 *
 * @param ctx Solver context
 * @param bias Bias value (default: 5)
 */
void solver_ctx_set_bias(solver_ctx_t *ctx, double bias);

/**
 * @brief Set per-variable branching weights
 *
 * Copies the provided array into the context, L1-normalizes it, and stores it.
 * Frees any existing weights array first. Pass NULL/0 to clear weights.
 *
 * @param ctx Solver context
 * @param weights Weight values to copy (NULL to clear)
 * @param n Number of elements
 */
void solver_ctx_set_branching_weights(solver_ctx_t *ctx, const double *weights, int n);

/**
 * @brief Set the branching factor (weight for branching_weights term)
 *
 * @param ctx Solver context
 * @param factor Factor value (default: 1.0)
 */
void solver_ctx_set_branching_factor(solver_ctx_t *ctx, double factor);

/**
 * @brief Set the bias factor (weight for assignment_bias term)
 *
 * @param ctx Solver context
 * @param factor Factor value (default: 1.0)
 */
void solver_ctx_set_bias_factor(solver_ctx_t *ctx, double factor);

/**
 * @brief Set the look-ahead factor (weight for look-ahead term)
 *
 * @param ctx Solver context
 * @param factor Factor value (default: 0.0)
 */
void solver_ctx_set_look_ahead_factor(solver_ctx_t *ctx, double factor);

/* ============================================================
 * Variable Ordering API
 * ============================================================ */

/**
 * @brief Set variable iteration order from priority values
 *
 * Sorts variables by priority (descending) to produce an iteration order.
 * Higher priority values are visited first. Ties are broken by index (stable).
 *
 * @param ctx Solver context
 * @param priorities Priority values per variable (higher = visited first)
 * @param n Number of variables
 */
void solver_ctx_set_variable_order(solver_ctx_t *ctx, const double *priorities, int n);

/**
 * @brief Set identity (default) variable ordering [0, 1, ..., n-1]
 *
 * @param ctx Solver context
 * @param n Number of variables
 */
void solver_ctx_set_default_order(solver_ctx_t *ctx, int n);

/**
 * @brief Set variable ordering by constraint degree (most-constrained first)
 *
 * Sorts variables by degree (descending). Higher degree = visited first.
 *
 * @param ctx Solver context
 * @param degrees Per-variable constraint degree counts
 * @param n Number of variables
 */
void solver_ctx_set_degree_order(solver_ctx_t *ctx, const int *degrees, int n);

/* ============================================================
 * Phase-Specific Setters
 * ============================================================ */

void solver_ctx_set_sat_bias(solver_ctx_t *ctx, double bias);
void solver_ctx_set_opt_sat_bias(solver_ctx_t *ctx, double bias);
void solver_ctx_set_opt_bias(solver_ctx_t *ctx, double bias);

void solver_ctx_set_sat_branching_weights(solver_ctx_t *ctx, const double *weights, int n);
void solver_ctx_set_opt_sat_branching_weights(solver_ctx_t *ctx, const double *weights, int n);
void solver_ctx_set_opt_branching_weights(solver_ctx_t *ctx, const double *weights, int n);

void solver_ctx_set_sat_branching_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_sat_branching_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_branching_factor(solver_ctx_t *ctx, double factor);

void solver_ctx_set_sat_bias_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_sat_bias_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_bias_factor(solver_ctx_t *ctx, double factor);

void solver_ctx_set_sat_look_ahead_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_sat_look_ahead_factor(solver_ctx_t *ctx, double factor);
void solver_ctx_set_opt_look_ahead_factor(solver_ctx_t *ctx, double factor);

/* ============================================================
 * Consolidated Parameter Setter
 * ============================================================ */

/**
 * @brief Set all predicted parameters on all three phases in one call
 *
 * Writes bias, branching_factor, bias_factor, weights, and variable_order
 * to sat, opt_sat, and opt BranchingStats simultaneously. Replaces the
 * pattern of ~12 individual setter calls from the Python prediction path.
 *
 * @param ctx Solver context
 * @param bias Bias value for all phases
 * @param branching_factor Branching factor for all phases
 * @param bias_factor Bias factor for all phases
 * @param weights Per-variable branching weights (NULL to clear)
 * @param variable_order Per-variable priority values for ordering (NULL for default)
 * @param n Number of variables (length of weights and variable_order arrays)
 */
void solver_ctx_set_predicted_params(solver_ctx_t *ctx, double bias,
                                     double branching_factor, double bias_factor,
                                     const double *weights,
                                     const double *variable_order, int n);

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

/* ============================================================
 * PRNG and Thread Configuration
 * ============================================================ */

/**
 * @brief Initialize PRNG and resolve thread count
 *
 * Must be called after setting ctx->seed and ctx->num_threads.
 * - If seed == 0, generates from entropy
 * - If num_threads == 0, auto-detects CPU count
 * - Initializes master_prng from resolved seed
 *
 * @param ctx Solver context
 */
void solver_ctx_init_prng(solver_ctx_t *ctx);

/**
 * @brief Get default thread count from env or CPU detection
 * @return Thread count (minimum 1)
 */
int solver_ctx_get_default_threads(void);

/**
 * @brief Reset arena for reuse between solver iterations
 *
 * Resets the arena allocator to reclaim memory without freeing chunks.
 * Call this between solver iterations to reuse memory efficiently.
 *
 * @param ctx Solver context (no-op if NULL or arena is NULL)
 */
void solver_ctx_arena_reset(solver_ctx_t *ctx);

#endif /* SOLVER_CTX_H */
