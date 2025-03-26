//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"
#include <time.h>

size_t sampling(const double *probs, size_t numStates) {
    double random = (double) (rand() % 1234567) / 1234567;
    double cumulated = 0;
    for (size_t i = 0; i < numStates; ++i) {
        cumulated += probs[i];
        if (cumulated >= random) return i;
    }
    return numStates;
}

state_t *amplitude_amplification(state_t *states, size_t numStates, size_t calls) {
    if (states == NULL || numStates == 0) return NULL;

    state_t *result;
    double amp_factor;
    double total_prob = 0;
    double *prob = malloc(numStates * sizeof(double));

    for (size_t i = 0; i < numStates; ++i) total_prob += states[i].prob;

    amp_factor = pow(sin((2 * calls + 1) * asin(sqrt(total_prob))), 2) / total_prob;

    for (size_t i = 0; i < numStates; ++i) prob[i] = states[i].prob * amp_factor;

    size_t measurement = sampling(prob, numStates);
    free(prob);

    if (measurement == numStates)
        return NULL;
    else {
        result = copy_state(&states[measurement]);
        return result;
    }
}

state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M) {
    fflush(stdout);
    size_t m, j, m_tot;
    m_tot = 0;
    double c = 6. / 5;
    *rounds = 0;
    *iterations = 0;

    state_t *result;

    while (m_tot < M) {
        ++(*rounds);
        m = ceil(pow(c, *rounds));
        j = rand() % m + 1;
        *iterations += j;
        m_tot += 2 * j + 1;

        result = amplitude_amplification(states, numStates, j);

        if (result != NULL) return result;
    }
    return NULL;
}

int evaluation(int64_t *potentials, int* S, int64_t *S_value, int num){
    int eval = 1;
    // check, if assignment does not exceed potentials
    for (int k = 0; k < num; k++){
        // if only one constraint is false: break
        if (potentials[S[k]] < labs(S_value[k])) {
            eval = 0;
            break;
        }
    }
    return eval;
}

int update_potentials(int64_t *potentials, int *S, int64_t *S_value, int num){
    int all_positive = 1;
    for (int k = 0; k < num; k++){
        potentials[S[k]] -= labs(S_value[k]);
        if (potentials[S[k]] < 0.) {
            all_positive = 0;
            break;
        }
    }
    return all_positive;
}

int invert_update_potentials(int64_t *potentials, int *S, int64_t *S_value, int num){
    for (int k = 0; k < num; k++){
        potentials[S[k]] += labs(S_value[k]);
    }
    return 1;
}


// look ahead to evaluate all possible solutions from certain position up to certain depth
int look_ahead( int index, int next_assignment, int depth, int *count_solutions, int64_t *potentials,
                int **S_plus, int64_t **S_plus_value, int *num_plus,
                int **S_minus, int64_t **S_minus_value, int *num_minus){
    // check, if assignment does not exceed potentials
    int bool_ = 1;
    if (next_assignment) bool_ *= evaluation(potentials, S_plus[index], S_plus_value[index], num_plus[index]);
    else bool_ *= evaluation(potentials, S_minus[index], S_minus_value[index], num_minus[index]);

    if (next_assignment) update_potentials(potentials, S_plus[index], S_plus_value[index], num_plus[index]);
    else update_potentials(potentials, S_minus[index], S_minus_value[index], num_minus[index]);

    if (bool_){
        if (index == depth) (*count_solutions)++;
        else{
            look_ahead(index + 1, 0, depth, count_solutions, potentials, S_plus, S_plus_value, num_plus, S_minus, S_minus_value, num_minus);
            look_ahead(index + 1, 1, depth, count_solutions, potentials, S_plus, S_plus_value, num_plus, S_minus, S_minus_value, num_minus);
        }
    }

    if (next_assignment) invert_update_potentials(potentials, S_plus[index], S_plus_value[index], num_plus[index]);
    else invert_update_potentials(potentials, S_minus[index], S_minus_value[index], num_minus[index]);
    return 1;
}


int CSearch(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
            constraint_list_t *con, constraint_list_t *obj,
            int **S_plus, int64_t **S_plus_value, int *num_plus,
            int **S_minus, int64_t **S_minus_value, int *num_minus,
            int **Indices, int *NumIndices, int *Fulfilled, int **forced,
            int depth_look_ahead, solver_t solver
            ){
    // potentials for every constraint
    int64_t potentials[con->num_constraints];

//    printf("bias = %f\n", BranchingStats.bias);

    for(int l = 0; l < 4 * j * j; l++){
        // Store which bit from the previous solution is flipped
        int NumChanges = 0;
        int *ChangedBits = calloc(n, sizeof(int));

        // initialize potentials
        for (int i = 0; i < con->num_constraints; i++) potentials[i] = con->constraints[i].rhs;

        // initialize new solution
        new_sol->tot_profit = cur_sol->tot_profit;
        sw_set_ui_0(new_sol->vector);

        int i;
        for(i = 0; i < n; i++){
            int bit = sw_tstbit(cur_sol->vector, i); // which bit has the current solution?
            double random_num = ((double) (rand() % 123456)) / 123455.;

            // Initialize new bit to be 0
            sw_clrbit(new_sol->vector, i);
            int new_bit = 0;

            // check, if assignment does not exceed potentials
            int bool_plus = evaluation(potentials, S_plus[i], S_plus_value[i], num_plus[i]);
            int bool_minus = evaluation(potentials, S_minus[i], S_minus_value[i], num_minus[i]);
            int count[2] = {0, 0};
            // look ahead to the left side
            if (bool_minus && depth_look_ahead > 0 && i >= 15) look_ahead(i, 0, min(i + depth_look_ahead, n - 1), &count[0], potentials, S_plus, S_plus_value, num_plus, S_minus, S_minus_value, num_minus);
            // look ahead to the right side
            if (bool_plus && depth_look_ahead > 0 && i >= 15) look_ahead(i, 1, min(i + depth_look_ahead, n - 1), &count[1], potentials, S_plus, S_plus_value, num_plus, S_minus, S_minus_value, num_minus);
            if (depth_look_ahead == 0 || i < 15){
                count[0] = bool_minus;
                count[1] = bool_plus;
            }
            // when both assignments dont lead to a feasible solution: break
//            if (count[0] == 0 && count[1] == 0  && solver == OPTIMIZE) break;

            // only counts needs to be checked, since they also include bool_plus and bool_minus
            // If all the constraints ar fulfilled by both assignments, "branch"
            if (count[0] > 0 && count[1] > 0){
                if (random_num > BranchingFunction(i, bit, 0, 0)){
                    sw_setbit(new_sol->vector, i);
                    new_bit = 1;
                } else{ sw_clrbit(new_sol->vector, i); }
            }
            // we are forced to go left, when only count[0] leads to a feasible solution
            // count[0] > 0 does not need to be checked, since both == 0 was checked prior
            if (count[1] == 0) {
                // but if left don't lead to feasible solution: break
                sw_clrbit(new_sol->vector, i);
                new_bit = 0;
            }
            // we are forced to go right, when only count[1] leads to feasible solution
            if (count[0] == 0){
                // but if right don't lead to feasible solution: break
                sw_setbit(new_sol->vector, i);
                new_bit = 1;
            }

            // we are forced to go left
            if (forced[0][i] && potentials[forced[1][i]] == 1.){
                // but if right don't lead to feasible solution: break
//                if (count[1] == 0 && solver == OPTIMIZE) break;
                sw_setbit(new_sol->vector, i);
                new_bit = 1;
            }

            // was a bit flipped?
            if (bit != new_bit) ChangedBits[NumChanges++] = i;

            int all_positive;
            if (new_bit) all_positive = update_potentials(potentials, S_plus[i], S_plus_value[i], num_plus[i]);
            else all_positive = update_potentials(potentials, S_minus[i], S_minus_value[i], num_minus[i]);
//            if (!all_positive && solver == OPTIMIZE) break;
        }
        // if the previous loop broke earlier, determine all bit changes
        for (int mn = i; mn < n; mn++) ChangedBits[NumChanges++] = mn;

        int64_t val = 0;
        int as1 = true;
        if (solver == OPTIMIZE) as1 = quantum_feasibility2(con, new_sol, n + 1, false);

        int NumChangedTerms = 0;
        int *ChangedTerms = calloc(NTerms, sizeof(int));
        if (as1 && solver == OPTIMIZE) val = ChangedObjVal(obj, new_sol, NumChanges, ChangedBits, Indices, NumIndices, Fulfilled, ChangedTerms, &NumChangedTerms);
        if (solver == SATISFY) {
            val = count_satisfyed_constraints(con, new_sol, n + 1, false, con->num_constraints - (int) cur_sol->tot_profit );
        }

        if (as1 && compare(cur_sol->tot_profit, val, obj->constraints->sense)){
            // If solution is updated, change the array of fulfilled terms
            for (int term = 0; term < NumChangedTerms; term++) Fulfilled[ChangedTerms[term]] = 1 - Fulfilled[ChangedTerms[term]];
            cur_sol->tot_profit = val;
            sw_clear(cur_sol->vector);
            cur_sol->vector = sw_set(new_sol->vector);

            free(ChangedTerms);
            free(ChangedBits);
            return 1;
        }
        free(ChangedTerms);
        free(ChangedBits);
    }
    return 0;
}


state_t *ctg(
                state_t *cur_sol,
                constraint_list_t *con,
                constraint_list_t *obj,
                int M,
                size_t *qtg_applications,
                int depth_look_ahead,
                solver_t solver,
                int64_t stop_val,
                callback_t callback){
    state_t *new_sol = copy_state(cur_sol);
    int m_tot = 0;
    int n = cur_sol->vector.bits;
    int rounds = 0;
    double c = 6. / 5;

    clock_t start = clock();

    int NTerms = obj->constraints[0].num_literals; // number terms
    // For the initial solution, determine the which objective terms are fulfilled
    int *Fulfilled = calloc(NTerms, sizeof(int)); // store if term is fulfilled
    for (int terms = 0; terms < NTerms; terms++){
        int assign = 1;
        // if any item of the term is unassigned, the term is not fulfilled
        for (int item = 0; item < obj->constraints[0].literals[terms].len_literal - 1; item++){
            if (!sw_tstbit(cur_sol->vector, (int) obj->constraints[0].literals[terms].variables[item]))
                assign = 0;
        }
        Fulfilled[terms] = assign;
    }

    // collect the term indices for every item
    int **Indices = calloc(n, sizeof(int *));
    int *NumIndices = calloc(n, sizeof(int)); // Number of terms containing respective item
    // Go through every item
    for (int item = 0; item < n; item++){
        Indices[item] = calloc(NTerms, sizeof(int));
        // test every term, if it contains the item
        for (int terms = 0; terms < NTerms; terms++){
            // check every literal of the term if it is the respective item
            for (int lits = 0; lits < obj->constraints[0].literals[terms].len_literal - 1; lits++){
                if (obj->constraints[0].literals[terms].variables[lits] == item){
                    Indices[item][NumIndices[item]++] = terms;
                    break;
                }
            }
        }
    }

    // preprocess the constraints for usage in the sampling routine
    // go through every item and collect all the constraint indices containing the items
    // sort indices by positive and negative coefficients
    int **forced = calloc(2, sizeof(int *));
    forced[0] = calloc(n, sizeof(int));
    forced[1] = calloc(n, sizeof(int));

    int *num_plus = calloc(n, sizeof(int));
    int *num_minus = calloc(n, sizeof(int));
    for (int i= 0; i < n; i++) {
        num_plus[i] = 0;
        num_minus[i] = 0;
    }

    int **S_plus  = calloc(n, sizeof(int *));
    for (int i = 0; i < n; i++) S_plus[i] = calloc(con->num_constraints, sizeof(int));
    int **S_minus = calloc(n, sizeof(int *));
    for (int i = 0; i < n; i++) S_minus[i] = calloc(con->num_constraints, sizeof(int));

    int64_t **S_plus_value = calloc(n, sizeof(long double *));
    for (int i = 0; i < n; i++) S_plus_value[i] = calloc(con->num_constraints, sizeof(int64_t));
    int64_t **S_minus_value = calloc(n, sizeof(long double *));
    for (int i = 0; i < n; i++) S_minus_value[i] = calloc(con->num_constraints, sizeof(int64_t));

    for (int item = 0; item < n; item++){
        for (int i = 0; i < con->num_constraints; i++){
            for (int j = 0; j < con->constraints[i].num_literals; j++){
                // only linear constraints
                if (con->constraints[i].literals[j].variables[0] == item){
                    if (con->constraints[i].literals[j].factor < 0) {
                        S_minus_value[item][num_minus[item]] = con->constraints[i].literals[j].factor;
                        S_minus[item][num_minus[item]++] = i;
                    }
                    else {
                        S_plus_value[item][num_plus[item]] = con->constraints[i].literals[j].factor;
                        S_plus[item][num_plus[item]++] = i;
                    }
                    break;
                }
                // literals are sorted by ascending item index
                if (con->constraints[i].literals[j].variables[0] > item) break;
            }

            // determine if the last literal of a constraint would be forced based on the remaining constraint
            int last_literal = con->constraints[i].num_literals - 1;
            int last_item = con->constraints[i].literals[last_literal].variables[0];
            if ((con->constraints[i].sense == EQUAL) && (item == last_item)){
                forced[0][item] = 1;
                forced[1][item] = i;
            }
        }
    }

    // Start sampling after preprocessing
    while (m_tot < M){
        int m = ceil(pow(c, rounds));
        int j = rand() % (m + 1);
        m_tot += 2 * j + 1;
        *qtg_applications += 2 * j + 1;
        rounds++;

        int res = CSearch(
            new_sol, cur_sol, j, n, NTerms,
            con, obj,
            S_plus, S_plus_value, num_plus,
            S_minus, S_minus_value, num_minus,
            Indices, NumIndices, Fulfilled, forced,
            depth_look_ahead, solver
        );
        if (res) {
            if (callback) {
                callback(new_sol->tot_profit, *qtg_applications, (double)(clock() - start) / CLOCKS_PER_SEC);
            }
            m_tot = 0;
            rounds = 0;
            if((solver == SATISFY && cur_sol->tot_profit == con->num_constraints) || (new_sol->tot_profit >= stop_val && stop_val != -1)) {
                break;
            }
        }
    }
    // Free everything
    for (int i = 0; i < n; i++){
        free(S_plus[i]);
        free(S_plus_value[i]);
        free(S_minus[i]);
        free(S_minus_value[i]);
        free(Indices[i]);
    }
    free(S_plus);
    free(S_plus_value);
    free(S_minus);
    free(S_minus_value);
    free(num_plus);
    free(num_minus);
    free(forced[0]);
    free(forced[1]);
    free(forced);
    free(NumIndices);
    free(Indices);
    free(Fulfilled);
//    printf("%f %f\n", time_prep, time_obj2);
    free_state(new_sol, 0);
//    printf("UpdateCount = %d\n", UpdateCount);
    fflush(stdout);
    return cur_sol;
}