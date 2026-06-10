#ifndef BRANCHING_H
#define BRANCHING_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "intarray.h"
//#include "SearchLib.h"
#include "definitions.h"
#include "state.h"

/*
 * Branching probability computation for quantum-inspired search.
 *
 * This module computes per-variable branching probabilities that guide the
 * quantum-inspired sampling algorithm. The scalar `bias` channel sets a base
 * probability `assignment_bias = (bias+1)/(bias+2)` (optionally blended with a
 * feasibility look-ahead term); the per-variable `branching_weights[i]` then
 * apply a SIGNED additive offset in logit space through a sigmoid:
 *
 *   value = sigma( logit(base) + branching_factor * branching_weights[i] )
 *
 * This decouples the per-variable channel from the scalar bias so enabling
 * weights cannot silently rescale the neighborhood radius (the pre-M0f convex
 * blend shared one denominator and did). With no/zero weights `value == base`
 * exactly. The result is conditioned on the current bit (bit_S) and threshold
 * bit (bit_T) to determine the branching direction. See BranchingFunction.
 *
 * StateProbability() combines per-bit probabilities into an overall state
 * probability by multiplying across all branched variables.
 */

/* Forward declaration for solver context (avoids circular include) */
struct solver_ctx;
typedef struct solver_ctx solver_ctx_t;

typedef struct {
    double *branching_weights;  /* Per-variable weights (NULL = no weights) */
    int num_weights;            /* Length of branching_weights (0 when NULL) */

    double branching_factor;    /* Factor for branching_weights term (default 1.0) */
    double bias_factor;         /* Factor for assignment_bias term (default 1.0) */
    double bias;                /* Assignment bias value (default 5.0) */
    double look_ahead_factor;   /* Factor for look-ahead term (default 0.0) */

    int *variable_order;        /* Iteration order for variables (NULL = identity) */
    int num_vars;               /* Length of variable_order (0 when NULL) */

    /* bd h8d: inverse permutation of variable_order -- variable_rank[var] is
     * the traversal position of `var`. evaluation()/look_ahead_correct() key
     * clause-closure on this rank so the potentials accounting stays
     * prefix-consistent with the (reordered) traversal. NULL whenever the
     * traversal is natural-equivalent (no order set, or identity order), which
     * keeps the default path on the exact pre-h8d code path bit-for-bit.
     * Invariant: variable_order non-identity  =>  variable_rank != NULL. */
    int *variable_rank;
} BranchingStats_t;

/* Global BranchingStats removed in v2.0 -- all state lives in solver_ctx_t.branching_stats */

/* Clamp bound for the bounded-decisions invariant (NORTHSTAR §1.7/§8.2):
 * every returned probability stays in (BRANCH_EPS, 1 - BRANCH_EPS) by
 * construction, so the exploratory stage can never silently force an
 * assignment (value pinned to exactly 0 or 1). */
#define BRANCH_EPS 1e-9

static inline double branch_clamp(double v){
    if (v < BRANCH_EPS)       return BRANCH_EPS;
    if (v > 1.0 - BRANCH_EPS) return 1.0 - BRANCH_EPS;
    return v;
}

/*
 * BranchingFunction -- Compute the branching probability for variable `index`.
 *
 * M0f reparameterization (NORTHSTAR §4): the per-variable channel is an
 * ADDITIVE LOGIT OFFSET through a sigmoid, decoupled from the scalar bias --
 * it is no longer a term in a shared-denominator convex blend (which let
 * enabling `branching_weights` silently rescale the radius via factor_sum).
 *
 *   base   = convex blend of the NON-per-variable channels only:
 *            (bias_factor * assignment_bias + look_ahead_factor * lookahead_0)
 *            / (bias_factor + look_ahead_factor)      [0.5 if that sum <= 0]
 *   value  = sigma( logit(base) + branching_factor * theta_i )   if theta != 0
 *          = base                                                 if theta == 0
 *
 * where:
 *   assignment_bias  = (bias + 1) / (bias + 2), a sigmoid-like term in (0,1)
 *   lookahead_0_prob = 1.0 if diffcount >= 0 (feasible), 0.0 otherwise
 *                      (diffcount == 0 disables look_ahead; all production call
 *                      sites pass diffcount == 0, so base == assignment_bias)
 *   theta_i          = branching_weights[index] -- a SIGNED per-variable offset
 *                      (no L1 normalization, no non-negativity); 0 if no weights
 *   branching_factor = gain on the per-variable channel (default 1.0 recovers
 *                      the NORTHSTAR §4 form; 0.0 disables the channel)
 *
 * Bit-for-bit baseline recovery: when the effective offset
 * `branching_factor * theta_i` is exactly 0 (no weights, all-zero weights, or
 * branching_factor == 0) the result is `base` with NO sigmoid round-trip, so
 * the golden BranchingFunction(i,0,0,0) == 6/7 at bias=5 is preserved exactly.
 * Both `base` (pre-logit) and `value` (post-sigmoid) are clamped to
 * (eps, 1-eps) so logit() stays finite and §1.7 holds by construction.
 *
 * The bit_S / bit_T logic flips the probability based on whether the current
 * candidate bit matches or opposes the threshold (best-known) bit:
 *   - bit_T == 0: P(0) = value, P(1) = 1 - value
 *   - bit_T == 1: P(0) = 1 - value, P(1) = value
 *
 * Returns: probability in (0, 1), used by StateProbability().
 */
static inline double BranchingFunction(int index, int bit_S, int bit_T, int diffcount, const BranchingStats_t *stats){
    double total_bias;
    double branching_factor = stats->branching_factor;
    double bias_factor = stats->bias_factor;
    double look_ahead_factor = stats->look_ahead_factor;

    if (diffcount == 0) look_ahead_factor = 0;

    double lookahead_0_probability = (diffcount < 0) ? 0.0 : 1.0;
    double assignment_bias = (stats->bias + 1.0) / (stats->bias + 2.0);

    /* Convex blend of the NON-per-variable channels (bias + look-ahead). The
     * per-variable weight term is NO LONGER part of this sum -- it enters
     * additively in logit space below, so enabling weights cannot rescale the
     * neighborhood radius (NORTHSTAR §1.5, §4). */
    double factor_sum = bias_factor + look_ahead_factor;
    double base;
    if (factor_sum <= 0.0) {
        base = 0.5;
    } else {
        base = (bias_factor * assignment_bias
                + look_ahead_factor * lookahead_0_probability) / factor_sum;
    }
    base = branch_clamp(base);  /* keep logit() finite + bounded by construction */

    /* Per-variable signed logit offset. When the effective offset is exactly
     * zero we return `base` directly (no sigmoid round-trip), recovering the
     * baseline bit-for-bit. */
    double theta = (stats->branching_weights != NULL && index < stats->num_weights)
                   ? stats->branching_weights[index] : 0.0;
    double offset = branching_factor * theta;
    double value;
    if (offset == 0.0) {
        value = base;
    } else {
        double z = log(base / (1.0 - base)) + offset;
        value = branch_clamp(1.0 / (1.0 + exp(-z)));
    }

    /* Apply bit_S / bit_T branching logic */
    if (bit_T == 0) {
        total_bias = (bit_S == 0) ? value : (1.0 - value);
    } else {
        total_bias = (bit_S == 0) ? (1.0 - value) : value;
    }

    return total_bias;
}

/*
 * StateProbability -- Compute the overall probability of a candidate state.
 *
 * Multiplies per-bit branching probabilities across all branched variables
 * (those where state->branch[j] == 1). The result is stored in state->prob.
 *
 * Inputs:  ctx (solver context with branching stats),
 *          state (candidate), threshold (best-known solution)
 * Output:  state->prob = product of BranchingFunction() for each branched bit
 */
double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold);

state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);

#endif
