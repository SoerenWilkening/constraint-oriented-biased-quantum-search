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
#include "Branching.h"
#include "prng.h"

/** bd 0o8.3: candidates drawn between two wall-clock deadline checks inside a
 *  CSearch_* sample loop. Power of two so the check is a cheap bitmask; large
 *  enough that clock-read overhead is O(Leff/CHUNK) and the overshoot past the
 *  deadline is bounded to <= CHUNK candidates (sub-ms at n=3000). */
#define CBQS_DEADLINE_CHUNK 1024u
#include "arena.h"

/** bd 4uf: sentinel for solver_ctx_t.callback_value — "no per-worker incumbent
 *  value was set for this callback invocation" (non-ctg callback sites). */
#define SOLVER_CTX_CALLBACK_VALUE_UNSET INT64_MIN

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

/** bd w29 (M5 / 71e): continuous oracle-indexed opt-radius DECAY schedule spec.
 *  A FAITHFUL between-round schedule of the opt-phase state-prep angle: the
 *  opt-phase scalar-bias radius is recomputed BETWEEN Grover rounds (a classical
 *  write of stats->bias via ctg) from a non-quantum-internal, T(n)-normalized key
 *  (total_oracles / mod->M in [0,1]) and held CONSTANT through every round's
 *  Grover iterations. The inner sampler (Branching.h / quantum_search.c /
 *  approximate_state_sampler.c) is BYTE-UNCHANGED — BranchingFunction still only
 *  READS stats->bias. Mirrors opt_switch_oracles (round(alpha*T(n))). The schedule
 *  shape is r(t) = r_end + (r_start - r_end) * (1 - t)^gamma for t in [0,1]:
 *    t=0 -> r_start (broad, opt-phase start);  t=1 -> r_end (tight, near T(n)).
 *    gamma == 1 linear; gamma > 1 tightens EARLY (steep early, gentle near t=1);
 *    gamma < 1 stays broad longer then drops (gentle early, steep near t=1).
 *    r_start == r_end degenerates to
 *    the CONSTANT static lever bit-for-bit (opt_radius_schedule_eval early-returns
 *    r_start, so the bias matches radius_to_bias(n, r_start) exactly). enabled == 0
 *    is the strict no-op default (the existing static opt_branching_radius path). */
typedef struct {
    int    enabled;   /* 0 == OFF (static lever path; the default). */
    double r_start;   /* target radius at t=0 (broad). > 0 when enabled. */
    double r_end;     /* target radius at t=1 (tight). > 0 when enabled. */
    double gamma;     /* decay-shape exponent. > 0 when enabled (1.0 == linear). */
} opt_radius_schedule_t;

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

    /** Solve start time in monotonic nanoseconds (for timeout calculation) */
    uint64_t start_time_ns;

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

    /** Portfolio worker index (0-based). Decorrelates this worker's PRNG
     *  stream from the shared master via prng_seed_thread(master, worker_id).
     *  worker_id == 0 reproduces the legacy single-stream behavior. */
    int worker_id;

    /** Per-worker cumulative oracle charge (Σ 2j+1 over ctg rounds).
     *  NEVER reset for the lifetime of the worker's context — this is the
     *  faithful, race-free quantum-cost metric that replaces the racy shared
     *  mod->qtg_applications (NORTHSTAR §11, CLAUDE.md §1.2). */
    size_t oracle_count;

    /** Per-worker wall-clock telemetry: seconds elapsed in this worker's ctg
     *  call (monotonic clock). Replaces the racy shared mod->runtime, which ctg
     *  wrote unlocked every loop iteration so all threading workers raced on it
     *  (last-writer-wins; CLAUDE.md §5, same class as the oracle_count race fixed
     *  in 8an.1.4). Pure telemetry — it never gates termination. solve() reduces
     *  it max-over-workers post-fan-out into mod->runtime (bd lif). */
    double runtime;

    /** bd 4uf (NORTHSTAR §11 M0e): the internal tot_profit of THIS worker's
     *  newest feasible incumbent, written by ctg immediately before invoking
     *  the history callback so the Cython wrapper can record the PER-WORKER
     *  incumbent value without dereferencing the shared mod->global_opt (an
     *  unlocked cross-thread read once the callback fires outside update_lock).
     *  Race-free like oracle_count (one ctx per worker; same-thread write→read).
     *  Callback sites that do not log per-worker incumbents (local_search's
     *  fresh ctx, quantum_local_search's NULL ctx) leave it at the UNSET
     *  sentinel; the Python side falls back to its legacy single-trajectory
     *  value source for those. */
    int64_t callback_value;

    /** Opt-phase branching diagnostics (M0g / bd 8an.1.7, NORTHSTAR §9).
     *  Per-worker observation counters accumulated over EVERY candidate the
     *  exploratory `opt` phase (CSearch_opt) generates — the phase where the
     *  scalar-bias radius lever lives and the bias is consulted ONLY on
     *  both-feasible "free" decisions. PURE INSTRUMENTATION: they are written
     *  but never read inside any decision; they do not touch the PRNG stream,
     *  the oracle accounting, or any branching outcome (faithfulness, §1.1/§1.2).
     *  Like oracle_count they are per-worker (one ctx per thread) so the writes
     *  are race-free without locking. Used by the §9 scale-invariance test to
     *  check the realized Hamming-radius distribution (mean+var via
     *  Σ NumChanges and Σ NumChanges²) and the free-decision fraction f(n)
     *  (Σ free decisions / (candidates · n)) are invariant across n. */
    uint64_t opt_candidates;   /* # candidates generated by CSearch_opt        */
    uint64_t opt_flip_sum;     /* Σ NumChanges (realized Hamming radius)        */
    uint64_t opt_flip_sumsq;   /* Σ NumChanges² (for the radius variance)       */
    uint64_t opt_free_sum;     /* Σ both-feasible "free" decisions per candidate*/

    /** M2a (bd 8an.3.1, NORTHSTAR §4/§12): per-phase decision-touch counters.
     *  At every variable decision in CSearch_{sat,opt_sat,opt} the two
     *  look_ahead_correct calls classify the children; these record, per phase:
     *    *_decisions  every classified decision (loop iteration reaching the
     *                 count[0]/count[1] test);
     *    *_free       both-feasible — BranchingFunction consulted (all phases);
     *    *_bothinf    both-infeasible — consulted ONLY in opt_sat (sat forces
     *                 bit=0, opt truncates the candidate);
     *    *_forced     exactly one side feasible — feasibility-forced, the bias
     *                 is never consulted.
     *  Partition invariant: free + bothinf + forced == decisions (per phase).
     *  The opt phase's free counter is the EXISTING opt_free_sum (M0g) — not
     *  duplicated here. PURE INSTRUMENTATION like the M0g block above:
     *  per-worker, race-free, never read inside any decision — the PRNG
     *  stream, oracle accounting, and branching outcomes are untouched
     *  (faithfulness §1.1/§1.2). */
    uint64_t sat_decisions;    /* sat:     all classified decisions             */
    uint64_t sat_free;         /* sat:     both-feasible (consulted)            */
    uint64_t sat_bothinf;      /* sat:     both-infeasible (forced to 0)        */
    uint64_t sat_forced;       /* sat:     single-side forced                   */
    uint64_t optsat_decisions; /* opt_sat: all classified decisions             */
    uint64_t optsat_free;      /* opt_sat: both-feasible (consulted)            */
    uint64_t optsat_bothinf;   /* opt_sat: both-infeasible (ALSO consulted)     */
    uint64_t optsat_forced;    /* opt_sat: single-side forced                   */
    uint64_t opt_decisions;    /* opt:     all classified decisions             */
    uint64_t opt_bothinf;      /* opt:     both-infeasible (candidate truncated)*/
    uint64_t opt_forced;       /* opt:     single-side forced                   */

    /** bd 0o8: per-worker cap on the classical Grover-round sample count
     *  (4j²+1) used by CSearch_{sat,opt_sat,opt}. 0 == unbounded (the exact
     *  O(4j²) rejection sim; legacy behavior). When > 0 a round draws at most
     *  `cap` candidates, bounding the O(n·j²) classical wall-time that makes
     *  large-n (large-j) solves intractable (NORTHSTAR §11, bd 0o8). It does
     *  NOT touch the 2j+1 oracle charge (applied in ctg BEFORE search_function,
     *  CLAUDE.md §1.2) -- the oracle count is unchanged; only the per-round
     *  classical success probability for rare improvers (p < ~1/cap) is reduced.
     *  Copied from mod->opt_sample_cap at ctg entry (per-worker, race-free). */
    int64_t opt_sample_cap;

    /** bd 0o8.3: per-worker monotonic-ns deadline that lets the wall cap
     *  (mod->stopping_time) interrupt a Grover round IN PROGRESS, not only
     *  between rounds (SearchLib.c). 0 == OFF (the strict no-op for every
     *  faithful/exact run; stopping_time <= 0). When armed it is
     *  t1_ns + stopping_time·1e9 -- the SAME monotonic basis as the existing
     *  between-rounds total_time check, so the two agree. Each CSearch_* sample
     *  loop checks it every CBQS_DEADLINE_CHUNK candidates and breaks once
     *  cbqs_monotonic_ns() >= deadline_ns; the truncated round is an APPROXIMATE
     *  outcome (faithfulness-of-outcome is RUN-POLICY-waived for wall-capped
     *  runs) but the 2j+1 oracle charge (applied in ctg) is UNCHANGED. Written
     *  once per worker from the read-only mod->stopping_time then read -- the
     *  same race-free pattern as opt_sample_cap (no shared mod-> writes). */
    uint64_t deadline_ns;

    /** bd w29 (M5 / 71e): per-worker continuous opt-radius DECAY schedule.
     *  enabled == 0 is the strict no-op default (static lever path). When
     *  enabled, ctg recomputes ctx->branching_stats_opt.bias BETWEEN rounds in
     *  the opt phase from this spec (see opt_radius_schedule_t). Per-worker write
     *  at propagation time, then read between rounds — race-free, like
     *  opt_sample_cap (no shared mod-> writes on the hot path). */
    opt_radius_schedule_t opt_radius_schedule;

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
 * @brief Set per-variable branching weights (signed logit offsets theta_i)
 *
 * Copies the provided array into the context AS-IS and stores it (no L1
 * normalization, no non-negativity -- the values are signed additive offsets
 * consumed by BranchingFunction; M0f, NORTHSTAR §4). Frees any existing weights
 * array first. Pass NULL/0 to clear weights.
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
 * bd w29 (M5 / 71e): continuous opt-radius DECAY schedule
 * ============================================================ */

/**
 * @brief Install the continuous opt-radius decay schedule on this context.
 *
 * Runtime data (NORTHSTAR §1.6), propagated once per worker via
 * _propagate_phase_params. When @p enabled != 0, ctg recomputes the opt-phase
 * bias BETWEEN Grover rounds from this spec (faithful between-round classical
 * write; the inner sampler is byte-unchanged). enabled == 0 is the strict no-op
 * (the static opt_branching_radius lever path). r_start/r_end/gamma must be > 0
 * when enabled (validated at the Python set-time boundary).
 *
 * @param ctx     Solver context (NULL is a no-op).
 * @param enabled Non-zero to arm the schedule; 0 to leave the static lever.
 * @param r_start Target radius at oracle fraction t=0 (broad).
 * @param r_end   Target radius at oracle fraction t=1 (tight).
 * @param gamma   Decay-shape exponent (1.0 == linear).
 */
void solver_ctx_set_opt_radius_schedule(solver_ctx_t *ctx, int enabled,
                                        double r_start, double r_end, double gamma);

/**
 * @brief Pure evaluator: target radius at normalized oracle fraction @p ratio.
 *
 * r(t) = r_end + (r_start - r_end) * (1 - clamp(t,0,1))^gamma. Deterministic and
 * side-effect-free (depends only on @p s and @p ratio) — this purity is what
 * makes the radius CONSTANT within a Grover round (it is evaluated only at the
 * top of the between-round ctg loop). When r_start == r_end it returns r_start
 * EXACTLY (no arithmetic), so the schedule degenerates to the constant lever
 * bit-for-bit. @p s must be non-NULL.
 */
double opt_radius_schedule_eval(const opt_radius_schedule_t *s, double ratio);

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
 * @brief Set the portfolio worker index for this context
 *
 * Stored on the context and consumed by solver_ctx_init_prng(), which jumps
 * the master PRNG stream worker_id times so each portfolio worker draws an
 * independent (non-overlapping) sequence. Must be called BEFORE
 * solver_ctx_init_prng(). worker_id == 0 reproduces the legacy stream, so
 * single-worker runs stay bit-for-bit deterministic.
 *
 * @param ctx Solver context (NULL-safe)
 * @param worker_id 0-based worker index
 */
void solver_ctx_set_worker_id(solver_ctx_t *ctx, int worker_id);

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
