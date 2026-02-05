

#include "Branching.h"
#include "solver_ctx.h"

BranchingStats_t BranchingStats = {
    // objective dependent bias
    .objective_factor = 0,
    .obj_dependent = NULL,

    // constraint dependent bias
    .constraint_factor = 0,
    .constraint_dependent = NULL,

    // assignment dependent bias
    .bias_factor = 1,
    .bias = 5,

    // look ahead dependent bias
    .look_factor = 0.0
};

void set_bias(double bias){
    BranchingStats.bias = bias;
}

void set_factors(double objective_factor, double constraint_factor, double bias_factor, double look_factor){
    BranchingStats.objective_factor = objective_factor;
    BranchingStats.constraint_factor = constraint_factor;
    BranchingStats.bias_factor = bias_factor;
    BranchingStats.look_factor = look_factor;
}

void set_obj_dependence(double *dependence, int n){
    BranchingStats.obj_dependent = calloc(n, sizeof(double));
    for(int i = 0; i < n; i++){
        BranchingStats.obj_dependent[i] = dependence[i];
    }
}

void set_constraint_dependence(double *dependence, int n){
    BranchingStats.constraint_dependent = calloc(n, sizeof(double));
    for(int i = 0; i < n; i++){
        BranchingStats.constraint_dependent[i] = dependence[i];
    }
}

//double BranchingFunction(int index, int bit_T, int bit_S, int diffcount){
//    double total_bias, f = 0, q = 0;
//    double objective_factor = BranchingStats.objective_factor; // objective related
//    double constraint_factor = BranchingStats.constraint_factor; // constraint related
//    double bias_factor = BranchingStats.bias_factor;
//    double look_factor = BranchingStats.look_factor;
//    if (diffcount == 0) look_factor = 0;
//    double lookahead_0_probability = 0;
//
//    if (diffcount < 0) lookahead_0_probability = 0; // bias towards 1
//    else lookahead_0_probability = 1.; // bias towards 0
//
//    if (BranchingStats.obj_dependent != NULL){
//        f =  BranchingStats.obj_dependent[index];
//    }
//    if(BranchingStats.constraint_dependent != NULL){
//        q =  BranchingStats.constraint_dependent[index];
//    }
//    if (bit_T == 0){
//        if(bit_S == 0) {
//            total_bias = 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (BranchingStats.bias + 1.) / (BranchingStats.bias + 2.);
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
//        }
//        else {
//            total_bias = 1;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (BranchingStats.bias + 1.) / (BranchingStats.bias + 2.);
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
//        }
//    } else{
//        if(bit_S == 0) {
//            total_bias = 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * 1. / (BranchingStats.bias + 2.);
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
//        }
//        else {
//            total_bias = 1;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * 1. / (BranchingStats.bias + 2.);
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
//        }
//    }
//
//    return total_bias;
//}

double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold){
    state->prob = 1.;
//    printf("%f\n", ctx->branching_stats.bias);
    int count0 = 0;
    int count1 = 0;
    for (size_t j = 0; j < state->vector.bits; ++j) {
        if (sw_tstbit(state->branch, j) == 1) {

            state->prob *= BranchingFunction(
                j,
                sw_tstbit(state->vector, j),
                sw_tstbit(threshold->vector, j),
                0, &ctx->branching_stats
            );
//            if (sw_tstbit(state->vector, j) != sw_tstbit(threshold->vector, j)){
//                printf("%d -> 0 -> %f\n", j, BranchingFunction(
//                    j,
//                    sw_tstbit(state->vector, j),
//                    sw_tstbit(threshold->vector, j),
//                    0, &BranchingStats
//                ));
//                count0++;
//            }else{
//                printf("%d -> 1 -> %f\n", j, BranchingFunction(
//                    j,
//                    sw_tstbit(state->vector, j),
//                    sw_tstbit(threshold->vector, j),
//                    0, &BranchingStats
//                ));
//                count1++;
//            }
        }
    }
//    printf("%d %d %.15f\n", count0, count1, state->prob);
    return state->prob;
}

state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states,
                size_t *new_number, state_t *threshold, int sense) {
//    printf("%f\n", ctx->branching_stats.bias);
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