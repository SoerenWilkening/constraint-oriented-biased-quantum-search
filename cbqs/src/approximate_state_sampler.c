/*
 * Approximate State Sampler
 *
 * Generates approximate quantum state samples using classical simulation.
 * The core function CSearch_opt_sampler() constructs random solutions by
 * assigning variables left-to-right, using the same look-ahead feasibility
 * mechanism as solver.c (look_ahead_correct) combined with branching
 * probabilities to bias assignments toward feasible, high-quality solutions.
 *
 * Multiple samples are generated and classified as "good" (improving over
 * a threshold) or "bad" (not improving). The good/bad ratio approximates
 * the quantum state amplitude used by the Grover-style search.
 */

#include "approximate_state_sampler.h"
#include "solver_ctx.h"
#include "prng.h"

approximate_state_t *init_approximete_state(solver_ctx_t *ctx, int n, double bias) {
    ctx->branching_stats.bias = bias;
    approximate_state_t *appr = malloc(sizeof(approximate_state_t));
    
    appr->good = init_large_state(n, STATE_BLOCK);
    appr->bad = init_large_state(n, STATE_BLOCK);
    appr->allocated_good = STATE_BLOCK;
    appr->allocated_bad = STATE_BLOCK;
    appr->num_good = 0;
    appr->num_bad = 0;
    
    appr->good_amplitude = 0;
    appr->bad_amplitude = 0;
    appr->delta = 1; // no states/amplitudes collected yet

    appr->samples_first_good = -1;
    appr->good_count = 0;
    return appr;
}

void increase_number_of_good_states(approximate_state_t *state){
    if (state->num_good < state->allocated_good) return;
    state->allocated_good += STATE_BLOCK;
    state->good = increse_large_state(state->good, state->num_good, state->allocated_good);
}

void increase_number_of_bad_states(approximate_state_t *state){
    if (state->num_bad < state->allocated_bad) return;
    state->allocated_bad += STATE_BLOCK;
    state->bad = increse_large_state(state->bad, state->num_bad, state->allocated_bad);
}

void print_approximate_state(approximate_state_t *state) {
    printf("allocated =     %16zu %16zu\n", state->allocated_good, state->allocated_bad);
    printf("used =          %16zu %16zu\n", state->num_good, state->num_bad);
    printf("probability =   %.15f %.15f -> delta = %.8f -> %f parallel repetitions\n",
            state->good_amplitude, state->bad_amplitude, state->delta, 5 * 1. / (1 - state->delta));
    printf("first good =    %16d\n", state->samples_first_good);
    printf("good count =    %16d\n", state->good_count);

    printf("Good states:\n");
    for (int i = 0; i < 20; ++i) {
        print_state(&state->good[i]);
        printf("\n");
    }
    printf("Bad states:\n");
    for (int i = 0; i < 20; ++i) {
        print_state(&state->bad[i]);
        printf("\n");
    }
}

void free_approximate_state(approximate_state_t *state) {
    free_state(state->good, state->allocated_good);
    free_state(state->bad, state->allocated_bad);
    free(state);
}

int state_is_contained_in_good_list(approximate_state_t *appr, state_t *state){
    for (int i = 0; i < appr->num_good; ++i) {
        // go through every state individually
        
        if (appr->good[i].tot_profit != state->tot_profit) continue; // states already different
        else {
            // only check, when objective differs
            // check, if assignments differ
            size_t j = 0;
            for (j = 0; j < state->vector.n; ++j) {
                if (appr->good[i].vector.part[j] != state->vector.part[j]) break; // assignments differ
            }
            if (j == state->vector.n) return 1; // mathing state was found
        }
    }
    return 0;
}

int state_is_contained_in_bad_list(approximate_state_t *appr, state_t *state){
    for (int i = 0; i < appr->num_bad; ++i) {
        // go through every state individually
        
        if (appr->bad[i].tot_profit != state->tot_profit) continue; // states already different
        else {
            // only check, when objective differs
            // check, if assignments differ
            size_t j = 0;
            for (j = 0; j < state->vector.n; ++j) {
                if (appr->bad[i].vector.part[j] != state->vector.part[j]) break; // assignments differ
            }
            if (j == state->vector.n) return 1; // mathing state was found
        }
    }
    return 0;
}

int CSearch_opt_sampler(solver_ctx_t *ctx, approximate_state_t *state, state_t *cur_sol,
                        int samples,
                        new_constraints_t *con, new_constraints_t *obj,
                        int depth_look_ahead
) {
    int n = cur_sol->vector.bits;
    size_t C = con->num_constraints;
    int64_t *potentials = malloc(C * sizeof(int64_t));
    int64_t *ret_total1 = malloc(C * sizeof(int64_t));
    int64_t *ret_total2 = malloc(C * sizeof(int64_t));
    if (potentials == NULL || ret_total1 == NULL || ret_total2 == NULL) {
        free(potentials);
        free(ret_total1);
        free(ret_total2);
        return -1;  /* allocation failure */
    }
    memset(ret_total1, 0, C * sizeof(int64_t));
    memset(ret_total2, 0, C * sizeof(int64_t));
    
//    printf("num_samples = %d\n", samples);
    for (int l = 0; l < samples; l++) {
//        printf("samples = %d\n", l);
        state_t *new_sol = init_state(0, NULL, cur_sol->vector.bits);
        
        // Store which bit from the previous solution is flipped
        int NumChanges = 0;
        int *ChangedBits = calloc(n, sizeof(int));
        
        // reset constraint rhs to initial values
        memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));
        
        // initialize new solution
        new_sol->tot_profit = cur_sol->tot_profit;
        sw_set_ui_0(new_sol->vector);
        
        int i;
        for (i = 0; i < n; i++) {
            int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
            double random_num = prng_next_double();
            
            // Initialize new bit to be 0
            sw_clrbit(new_sol->vector, i);
            int new_bit = 0;
            
            // check, if assignment does not exceed potentials
            // if depth look ahead is 0, it will check only the next assignment
            int count[2] = {0, 0};
            // look ahead to the left side (natural traversal: this sampler
            // iterates i = 0..n-1 directly, so order/rank stay NULL, bd h8d)
            look_ahead_correct(i, 0, imin(i + depth_look_ahead, n - 1), &count[0], con, potentials, new_sol, ret_total1, NULL, NULL);
            // look ahead to the right side
            look_ahead_correct(i, 1, imin(i + depth_look_ahead, n - 1), &count[1], con, potentials, new_sol, ret_total2, NULL, NULL);
            
            // only counts needs to be checked, since they also include bool_plus and bool_minus
            // If all the constraints ar fulfilled by both assignments, "branch"
            if (count[0] > 0 && count[1] > 0) {
                sw_setbit(new_sol->branch, i);
                if (random_num > BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)) {
                    sw_setbit(new_sol->vector, i);
                    new_bit = 1;
                } else { sw_clrbit(new_sol->vector, i); }

            }else sw_clrbit(new_sol->branch, i);
            if (count[0] == 0 && count[1] == 0) break;
            // we are forced to go left, when only count[0] leads to a feasible solution
            // count[0] > 0 does not need to be checked, since both == 0 was checked prior
            if (count[1] == 0) {
                // but if left don't lead to feasible solution: break
                sw_clrbit(new_sol->vector, i);
                new_bit = 0;
            }
            // we are forced to go right, when only count[1] leads to feasible solution
            if (count[0] == 0) {
                // but if right don't lead to feasible solution: break
                sw_setbit(new_sol->vector, i);
                new_bit = 1;
            }
            
            // was a bit flipped?
            if (bit != new_bit) ChangedBits[NumChanges++] = i;
            
            int all_positive;
            if (new_bit) {
                update_potentials(con, potentials, PLAIN, ret_total2);
            } else
                update_potentials(con, potentials, PLAIN, ret_total1);
        }
        // if the previous loop broke earlier, determine all bit changes
        int as1 = (i == n);
        if (as1)
            for (int k = 0; k < con->num_constraints; ++k) {
                if (con->sense[k] == EQUAL) as1 &= potentials[k] == 0;
                else as1 &= potentials[k] >= 0;
            }
        
        int NumChangedTerms = 0;
        int *ChangedTerms = calloc(MINSIZE, sizeof(int));
        int64_t val = cur_sol->tot_profit;
        if (as1) val = objective_value(obj, new_sol);
        new_sol->feasible = as1;
        new_sol->tot_profit = val;
        StateProbability(ctx, new_sol, cur_sol);

        if (as1 && cur_sol->tot_profit > val) {
            // put good state into list of good states
            // If solution is updated, change the array of fulfilled terms
            if (state->samples_first_good == -1) state->samples_first_good = l;
            state->good_count++;
            if (!state_is_contained_in_good_list(state, new_sol)){
                increase_number_of_good_states(state); // allocate more space
                copy_state_inplace(&state->good[state->num_good], new_sol);
                state->num_good++;
                state->good_amplitude += new_sol->prob;
                state->delta -= new_sol->prob;
            }
        }else{
            // put bad state into list of bad states
            if (!state_is_contained_in_bad_list(state, new_sol)){
                increase_number_of_bad_states(state); // allocate more space
                copy_state_inplace(&state->bad[state->num_bad], new_sol);
                state->num_bad++;
                
                state->bad_amplitude += new_sol->prob;
                state->delta -= new_sol->prob;
            }
        }
        free_state(new_sol, 1);
    }
    free(potentials);
    free(ret_total1);
    free(ret_total2);
    return 0;
}