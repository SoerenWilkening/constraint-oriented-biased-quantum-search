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

//int evaluation(int64_t *potentials, int* S, int64_t *S_value, int num){
int evaluation(constraint_list_t *con, unsigned int **indices, unsigned int *num_indices, state_t *cur_sol){
    int eval = 1;
    // check, if assignment does not exceed potentials
    for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
        for (int cls = 0; cls < num_indices[cnstr]; cls++){
            int index = indices[cnstr][cls]; // index of the clause of constraint cnstr
            int assigned = 1; // store, if all the previous items in the clause are assignmed to 1

            for (int i = 0; i < con->constraints[cnstr].literals[cls].len_literal - 2; i++){
                assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
            }
            if (con->constraints[cnstr].rhs_adapted < labs(con->constraints[cnstr].literals[cls].factor) * assigned){
                eval = 0;
                break;
            }
        }
    }
    return eval;
}

int update_potentials(constraint_list_t *con, unsigned int **indices, unsigned int *num_indices, state_t *cur_sol){
    // update the constraints rhs accordingly
    for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
        for (int cls = 0; cls < num_indices[cnstr]; cls++){
            int index = indices[cnstr][cls]; // index of the clause of constraint cnstr

            // only if all items are assigned to 1, adjust rhs
            int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
            for (int i = 0; i < con->constraints[cnstr].literals[cls].len_literal - 2; i++){
                assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
            }
            con->constraints[cnstr].rhs_adapted -= labs(con->constraints[cnstr].literals[cls].factor) * assigned;
        }
    }
    return 1;
}

int invert_update_potentials(constraint_list_t *con, unsigned int **indices, unsigned int *num_indices, state_t *cur_sol){
    // update the constraints rhs accordingly
    for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
        for (int cls = 0; cls < num_indices[cnstr]; cls++){
            int index = indices[cnstr][cls]; // index of the clause of constraint cnstr

            // only if all items are assigned to 1, adjust rhs
            int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
            for (int i = 0; i < con->constraints[cnstr].literals[cls].len_literal - 2; i++){
                assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
            }
            con->constraints[cnstr].rhs_adapted += labs(con->constraints[cnstr].literals[cls].factor) * assigned;
        }
    }
    return 1;
}


// look ahead to evaluate all possible solutions from certain position up to certain depth
//int look_ahead( int index, int next_assignment, int depth, int *count_solutions, int64_t *potentials,
//                int **S_plus, int64_t **S_plus_value, int *num_plus,
//                int **S_minus, int64_t **S_minus_value, int *num_minus){
int look_ahead( int index, int next_assignment, int depth, int *count_solutions, constraint_list_t *con,
                unsigned int ***positive_indices, unsigned int **num_positive_indices,
                unsigned int ***negative_indices, unsigned int **num_negative_indices,
                state_t *cur_sol){
    // check, if assignment does not exceed potentials
    int bool_;
    if (next_assignment) bool_ = evaluation(con, positive_indices[index], num_positive_indices[index], cur_sol);
    else bool_ = evaluation(con, negative_indices[index], num_negative_indices[index], cur_sol);

    if (bool_){
        if (index == depth) (*count_solutions)++;
        else{
            // adjust potentials to new solution
            if (next_assignment) {
                update_potentials(con, positive_indices[index], num_positive_indices[index], cur_sol);
                sw_setbit(cur_sol->vector, index); // set assignment to 1
            }
            else {
                update_potentials(con, negative_indices[index], num_negative_indices[index], cur_sol);
                sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
            }

            look_ahead(index + 1, 0, depth, count_solutions, con, positive_indices, num_positive_indices, negative_indices, num_negative_indices, cur_sol);
            look_ahead(index + 1, 1, depth, count_solutions, con, positive_indices, num_positive_indices, negative_indices, num_negative_indices, cur_sol);

            // reset potentials for proper use in sampling algorithm
            if (next_assignment) invert_update_potentials(con, positive_indices[index], num_positive_indices[index], cur_sol);
            else invert_update_potentials(con, negative_indices[index], num_negative_indices[index], cur_sol);
            sw_clrbit(cur_sol->vector, index); // reset assignment to 0
        }
    }

    return 1;
}

int CSearch(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
            constraint_list_t *con, constraint_list_t *obj,
            unsigned int ***positive_indices, unsigned int **num_positive_indices,
            unsigned int ***negative_indices, unsigned int **num_negative_indices,
            int **Indices, int *NumIndices, int *Fulfilled,
            int depth_look_ahead, solver_t solver
            ){

    for(int l = 0; l < 4 * j * j; l++){
//    for(int l = 0; l < 1; l++){
        // Store which bit from the previous solution is flipped
        int NumChanges = 0;
        int *ChangedBits = calloc(n, sizeof(int));

        // reset constraint rhs to initial values
        reset_rhs_adapted(con);

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
            // if depth look ahead is 0, it will check only the next assignment
            int count[2] = {0, 0};
            // look ahead to the left side
            fflush(stdout);
            look_ahead(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, positive_indices, num_positive_indices, negative_indices, num_negative_indices, new_sol);
            // look ahead to the right side
            look_ahead(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, positive_indices, num_positive_indices, negative_indices, num_negative_indices, new_sol);

//            printf("%d -> (%d %d) ", l, count[0], count[1]);

            // only counts needs to be checked, since they also include bool_plus and bool_minus
            // If all the constraints ar fulfilled by both assignments, "branch"
            if (count[0] > 0 && count[1] > 0){
//                printf("%f ", BranchingFunction(i, bit, 0, 0));
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

            // was a bit flipped?
            if (bit != new_bit) ChangedBits[NumChanges++] = i;

//            printf("%d| ", new_bit);
            int all_positive;
            if (new_bit) all_positive = update_potentials(con, positive_indices[i], num_positive_indices[i], new_sol);
            else all_positive = update_potentials(con, negative_indices[i], num_negative_indices[i], new_sol);
//            for (int cnstr = 0; cnstr < con->num_constraints; cnstr++) printf("%lld ", con->constraints[cnstr].rhs_adapted);
//            printf("\n");
        }
        // if the previous loop broke earlier, determine all bit changes
        for (int mn = i; mn < n; mn++) ChangedBits[NumChanges++] = mn;

        int64_t val = 0;
        int as1 = true;
//        print_state(new_sol);
        if (solver == OPTIMIZE) as1 = quantum_feasibility2(con, new_sol, n + 1, false);

        int NumChangedTerms = 0;
        int *ChangedTerms = calloc(NTerms, sizeof(int));
        if (as1 && solver == OPTIMIZE) val = ChangedObjVal(obj, new_sol, NumChanges, ChangedBits, Indices, NumIndices, Fulfilled, ChangedTerms, &NumChangedTerms);
        if (solver == SATISFY) {
            val = count_satisfyed_constraints(con, new_sol, n + 1, false, con->num_constraints - cur_sol->tot_profit);
        }
//        printf(" feasible = %d value = %lld\n", as1, val);

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


int ctg(
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
    int64_t initial_value = cur_sol->tot_profit;
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
            if (!sw_tstbit(cur_sol->vector, obj->constraints[0].literals[terms].variables[item]))
                assign = 0;
        }
        Fulfilled[terms] = assign;
    }

    // collect the objective term indices for every item
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
    // an item can appear more than once in a constraint (linear + quadratic terms ...)
    // simplifications can be made:
    //  - in a clause, items are always sorted in ascending order
    //  - non-linear factors only come into play, if the last non-assigned item is investigated
    //      -> only store index of clause for last item
    // for every constraint, for every item an array is needed to store all the clauses
    // categorize for positive and negative constraints
//    unsigned int *positive_indices[n][con->num_constraints];
    unsigned int ***positive_indices = malloc(n * sizeof(unsigned int **));
    unsigned int ***negative_indices = malloc(n * sizeof(unsigned int **));

//    unsigned int num_positive_indices[n][con->num_constraints];
    unsigned int **num_positive_indices = malloc(n * sizeof(unsigned int *));
    unsigned int **num_negative_indices = malloc(n * sizeof(unsigned int *));

    for (int item = 0; item < n; item++){
        positive_indices[item] = malloc(con->num_constraints * sizeof(unsigned int *));
        negative_indices[item] = malloc(con->num_constraints * sizeof(unsigned int *));

        num_positive_indices[item] = malloc(con->num_constraints * sizeof(unsigned int));
        num_negative_indices[item] = malloc(con->num_constraints * sizeof(unsigned int));

        for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
            constraint_t *constr = &con->constraints[cnstr];
            positive_indices[item][cnstr] = calloc(1, sizeof(unsigned int));
            negative_indices[item][cnstr] = calloc(1, sizeof(unsigned int));
            num_positive_indices[item][cnstr] = 0;
            num_negative_indices[item][cnstr] = 0;
            for(int cls = 0; cls < constr->num_literals; cls++){
                int cls_length = constr->literals[cls].len_literal - 2; // index of the last item in the clause
                int64_t factor = constr->literals[cls].factor;
                if (item == constr->literals[cls].variables[cls_length]){
                    if (factor < 0){
                        num_negative_indices[item][cnstr]++;
                        negative_indices[item][cnstr] = realloc(negative_indices[item][cnstr], num_negative_indices[item][cnstr] * sizeof(unsigned int));
                        negative_indices[item][cnstr][num_negative_indices[item][cnstr] - 1] = cls;
                    }else{
                        num_positive_indices[item][cnstr]++;
                        positive_indices[item][cnstr] = realloc(positive_indices[item][cnstr], num_positive_indices[item][cnstr] * sizeof(unsigned int));
                        positive_indices[item][cnstr][num_positive_indices[item][cnstr] - 1] = cls;
                    }
                }
            }
        }
    }


//    // plot test
//    printf("negative coefficients\n");
//    for (int item = 0; item < n; item++){
//        for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
//            printf("%d: %d-> ", item, cnstr);
//            for (int cls = 0; cls < num_negative_indices[item][cnstr]; cls++){
//                printf("%d ", negative_indices[item][cnstr][cls]);
//            }
//            printf("\n");
//        }
//    }
//    printf("positive coefficients\n");
//    for (int item = 0; item < n; item++){
//        for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
//            printf("%d: %d-> ", item, cnstr);
//            for (int cls = 0; cls < num_positive_indices[item][cnstr]; cls++){
//                printf("%d ", positive_indices[item][cnstr][cls]);
//            }
//            printf("\n");
//        }
//    }

    // Start sampling after preprocessing
    while (m_tot < M){
//    for (int i = 0; i < 1; i++){
        int m = ceil(pow(c, rounds));
        int j = rand() % (m + 1);
        m_tot += 2 * j + 1;
        *qtg_applications += 2 * j + 1;
        rounds++;
        int res = CSearch(
            new_sol, cur_sol, j, n, NTerms,
            con, obj,
            positive_indices, num_positive_indices,
            negative_indices, num_negative_indices,
            Indices, NumIndices, Fulfilled,
            depth_look_ahead, solver
        );
        if (res) {
            if (callback) {
                callback(cur_sol->tot_profit, *qtg_applications, (double)(clock() - start) / CLOCKS_PER_SEC);
            }
            m_tot = 0;
            rounds = 0;
            if((solver == SATISFY && cur_sol->tot_profit == con->num_constraints) || (new_sol->tot_profit >= stop_val && stop_val != -1)) {
                break;
            }
        }
    }
    for (int item = 0; item < n; item++){
        for (int cnstr = 0; cnstr < con->num_constraints; cnstr++){
            free(positive_indices[item][cnstr]);
            free(negative_indices[item][cnstr]);
        }
        free(positive_indices[item]);
        free(negative_indices[item]);
        free(num_positive_indices[item]);
        free(num_negative_indices[item]);
    }
    free(positive_indices);
    free(negative_indices);
    free(num_positive_indices);
    free(num_negative_indices);
    free(NumIndices);
    free(Indices);
    free(Fulfilled);
    free_state(new_sol, 0);
    fflush(stdout);
    return ! (cur_sol->tot_profit == initial_value);
}