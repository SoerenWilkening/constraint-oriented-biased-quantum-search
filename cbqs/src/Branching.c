

#include "Branching.h"
#include "solver_ctx.h"

BranchingStats_t BranchingStats = {
    .branching_weights = NULL,
    .num_weights = 0,
    .branching_factor = 1.0,
    .bias_factor = 1,
    .bias = 5,
    .look_factor = 0.0
};

double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold){
    state->prob = 1.;
    for (size_t j = 0; j < state->vector.bits; ++j) {
        if (sw_tstbit(state->branch, j) == 1) {

            state->prob *= BranchingFunction(
                j,
                sw_tstbit(state->vector, j),
                sw_tstbit(threshold->vector, j),
                0, &ctx->branching_stats
            );
        }
    }
    return state->prob;
}

state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states,
                size_t *new_number, state_t *threshold, int sense) {
    state_t *up = calloc(number_states, sizeof(state_t));
    size_t a = 0;

    for (size_t i = 0; i < number_states; ++i) {
        if (bnb[i].tot_profit < threshold->tot_profit) {
            up[a].tot_profit = bnb[i].tot_profit;
            sw_clear(up[a].vector);
            sw_clear(up[a].branch);
            up[a].vector = sw_set(bnb[i].vector);
            up[a].branch = sw_set(bnb[i].branch);
            StateProbability(ctx, &up[a], threshold);

            a++;
        }
    }
    *new_number = a;
    if (a == 0) {
        free_state(up, number_states);
        return NULL;
    }
    up = realloc(up, a * sizeof(state_t));
    return up;
}
