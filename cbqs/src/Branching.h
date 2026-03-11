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
 * quantum-inspired sampling algorithm. Each variable's probability of being
 * assigned 0 or 1 is determined by a weighted combination of three terms:
 *
 *   1. branching_weights[i] -- learned or prior per-variable importance
 *   2. assignment_bias      -- (bias + 1) / (bias + 2), favoring likely-good assignments
 *   3. look_ahead           -- feasibility look-ahead result (1.0 if feasible, 0.0 otherwise)
 *
 * The final probability is normalized by the sum of active factor weights,
 * then conditioned on the current bit (bit_S) and threshold bit (bit_T)
 * to determine the branching direction.
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
} BranchingStats_t;

/* Global BranchingStats removed in v2.0 -- all state lives in solver_ctx_t.branching_stats */

/*
 * BranchingFunction -- Compute the branching probability for variable `index`.
 *
 * Formula (3-term weighted average, normalized):
 *
 *   value = (branching_factor * w[index]
 *          + bias_factor * assignment_bias
 *          + look_ahead_factor * lookahead_0_probability) / factor_sum
 *
 * where:
 *   w[index]             = per-variable weight from branching_weights (0 if no weights)
 *   assignment_bias      = (bias + 1) / (bias + 2), a sigmoid-like term in (0.5, 1)
 *   lookahead_0_prob     = 1.0 if diffcount >= 0 (feasible), 0.0 otherwise
 *   factor_sum           = sum of active factor weights (those with non-NULL data)
 *
 * If branching_weights is NULL, the formula reduces to a 2-term average of
 * assignment_bias and look_ahead. If diffcount == 0, look_ahead is disabled.
 *
 * The bit_S / bit_T logic flips the probability based on whether the current
 * candidate bit matches or opposes the threshold (best-known) bit:
 *   - bit_T == 0: P(0) = value, P(1) = 1 - value
 *   - bit_T == 1: P(0) = 1 - value, P(1) = value
 *
 * Returns: probability in [0, 1], used by StateProbability().
 */
static inline double BranchingFunction(int index, int bit_S, int bit_T, int diffcount, const BranchingStats_t *stats){
    double total_bias;
    double branching_factor = stats->branching_factor;
    double bias_factor = stats->bias_factor;
    double look_ahead_factor = stats->look_ahead_factor;

    if (diffcount == 0) look_ahead_factor = 0;

    double lookahead_0_probability = (diffcount < 0) ? 0.0 : 1.0;
    double assignment_bias = (stats->bias + 1.0) / (stats->bias + 2.0);

    /* Compute factor sum for normalization */
    double factor_sum = bias_factor + look_ahead_factor;
    double w = 0.0;

    if (stats->branching_weights != NULL && index < stats->num_weights) {
        w = stats->branching_weights[index];
        factor_sum += branching_factor;
    }

    /* Guard against division by zero */
    if (factor_sum <= 0.0) {
        return 0.5;
    }

    double normalizer = 1.0 / factor_sum;

    /* 3-term (or 2-term) formula */
    double value = 0.0;
    if (stats->branching_weights != NULL && index < stats->num_weights) {
        value += normalizer * branching_factor * w;
    }
    value += normalizer * bias_factor * assignment_bias;
    value += normalizer * look_ahead_factor * lookahead_0_probability;

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
