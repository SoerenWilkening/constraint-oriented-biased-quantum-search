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
} BranchingStats_t;

/* Global BranchingStats removed in v2.0 -- all state lives in solver_ctx_t.branching_stats */

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

double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold);

state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);

#endif
