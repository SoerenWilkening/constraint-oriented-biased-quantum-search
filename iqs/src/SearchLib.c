//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"

volatile sig_atomic_t stop_flag = 0;

void handle_signal(int signum){
    stop_flag = 1;
}

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


int bfs(
                state_t *cur_sol,
                new_constraints_t *con,
                new_constraints_t *obj,
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
    size_t NTerms = obj->num_clauses[0]; // number terms

    // For the initial solution, determine the which objective terms are fulfilled
    int *Fulfilled = calloc(NTerms, sizeof(int)); // store if term is fulfilled
	size_t clause_offset = first_clause_index(obj, 0);
	for (int cls = 0; cls < NTerms; cls++){
		size_t clause_index = clause_offset + cls;
        int assign = 1;
        // if any item of the term is unassigned, the term is not fulfilled
        for (int item = 0; item < obj->clause_length[clause_index]; item++){
			size_t var = obj->variables[variable_index(cls, item, clause_offset)];
	        if (!sw_tstbit(cur_sol->vector, var)) assign = 0;
		}
        Fulfilled[cls] = assign;
    }

    // collect the objective term indices for every item
    int **Indices = calloc(n, sizeof(int *));
    int *NumIndices = calloc(n, sizeof(int)); // Number of terms containing respective item
    // Go through every item
    for (int item = 0; item < n; item++){
        Indices[item] = calloc(NTerms, sizeof(int));
        // test every term, if it contains the item
        for (int cls = 0; cls < NTerms; cls++){
	        size_t clause_index = clause_offset + cls;
            // check every literal of the term if it is the respective item
	        for (int k = 0; k < obj->clause_length[clause_index]; ++k) {
		        size_t var = obj->variables[variable_index(cls, item, clause_offset)];
				if (var == item){
					Indices[item][NumIndices[item]++] = cls;
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
    // improvement: use 1d-array implementations:
    //      - positive_indices      -> 1d array storing indices
    //                              -> length not fixed
    //      - positive_offsets      -> 1d array storing location of values in "positive_indices" given (item, cnstr)
    //                              -> length fixed
    //      - num_positive_indices  -> 1d array storing number of values in "positive_indices" at location from
    //                              -> given (item, cnstr)
    //                              -> length fixed

    int C = con->num_constraints;
    unsigned int *positive_indices = calloc(2 * n * C * n, sizeof(unsigned int));
    unsigned int *negative_indices = calloc(2 * n * C * n, sizeof(unsigned int));

    unsigned int *positive_offsets = malloc(n * C * sizeof(unsigned int));
    unsigned int *negative_offsets = malloc(n * C * sizeof(unsigned int));

    unsigned int *num_positive_indices = malloc(n * C * sizeof(unsigned int));
    unsigned int *num_negative_indices = malloc(n * C * sizeof(unsigned int));

    size_t counter_positive = 0;
    size_t counter_negative = 0;
    for (int item = 0; item < n; item++){

        for (int cnstr = 0; cnstr < C; cnstr++){
			size_t clause_offset = first_clause_index(con, cnstr);
//            constraint_t *constr = &con->constraints[cnstr];

            unsigned int npi = 0;
            unsigned int nni = 0;
            for(int cls = 0; cls < con->num_clauses[cnstr]; cls++){
				size_t clause_index = clause_offset + cls;
//                int cls_length = constr->literals[cls].len_literal - 2; // index of the last item in the clause
//                size_t cls_length = con->clause_length[clause_index] - 1; // index of the last item in the clause
                int64_t factor = con->factors[clause_index];
                size_t prev_var = -1;
                for (int k = 0; k < con->clause_length[clause_index]; k++){
				    size_t var = con->variables[variable_index(cls, k, clause_offset)];

//                    if (item == constr->literals[cls].variables[cls_length]){
                    if (item == var && var != prev_var){
                        if (factor < 0){
                            // add index to "negative_indices"
                            negative_indices[counter_negative++] = cls;
                            nni++;
                        }else{
                            // add index to "positive_indices"
                            positive_indices[counter_positive++] = cls;
                            npi++;
                        }
                    }
                    prev_var = var;
                }
            }
            num_negative_indices[item * C + cnstr] = nni;
            negative_offsets[item * C + cnstr] = counter_negative - nni;
            num_positive_indices[item * C + cnstr] = npi;
            positive_offsets[item * C + cnstr] = counter_positive - npi;
        }
    }

    int count[2] = {0, 0};
    int64_t potentials[C];
    memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));
    look_ahead_correct(0, 0, n - 1, &count[0], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, cur_sol);
    look_ahead_correct(0, 1, n - 1, &count[1], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, cur_sol);
    printf("counts = %d %d\n", count[0], count[1]);

    free(positive_indices);
    free(positive_offsets);
    free(negative_indices);
    free(negative_offsets);
    free(num_positive_indices);
    free(num_negative_indices);
    free(NumIndices);
    free(Indices);
    free(Fulfilled);
    free_state(new_sol, 0);
    return ! (cur_sol->tot_profit == initial_value);
}


int ctg(
                state_t *cur_sol,
                new_constraints_t *con,
                new_constraints_t *obj,
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

    size_t NTerms = obj->num_clauses[0]; // number terms
    // For the initial solution, determine the which objective terms are fulfilled
    int *Fulfilled = calloc(NTerms, sizeof(int)); // store if term is fulfilled
	size_t clause_offset = first_clause_index(obj, 0);
	for (int cls = 0; cls < NTerms; cls++){
		size_t clause_index = clause_offset + cls;
        int assign = 1;
        // if any item of the term is unassigned, the term is not fulfilled
        for (int item = 0; item < obj->clause_length[clause_index]; item++){
			size_t var = obj->variables[variable_index(cls, item, clause_offset)];
	        if (!sw_tstbit(cur_sol->vector, var)) assign = 0;
		}
        Fulfilled[cls] = assign;
    }

    // collect the objective term indices for every item
    int **Indices = calloc(n, sizeof(int *));
    int *NumIndices = calloc(n, sizeof(int)); // Number of terms containing respective item
    // Go through every item
    for (int item = 0; item < n; item++){
        Indices[item] = calloc(NTerms, sizeof(int));
        // test every term, if it contains the item
        for (int cls = 0; cls < NTerms; cls++){
	        size_t clause_index = clause_offset + cls;
            // check every literal of the term if it is the respective item
	        for (int k = 0; k < obj->clause_length[clause_index]; ++k) {
		        size_t var = obj->variables[variable_index(cls, item, clause_offset)];
				if (var == item){
					Indices[item][NumIndices[item]++] = cls;
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
    // improvement: use 1d-array implementations:
    //      - positive_indices      -> 1d array storing indices
    //                              -> length not fixed
    //      - positive_offsets      -> 1d array storing location of values in "positive_indices" given (item, cnstr)
    //                              -> length fixed
    //      - num_positive_indices  -> 1d array storing number of values in "positive_indices" at location from
    //                              -> given (item, cnstr)
    //                              -> length fixed

    int C = con->num_constraints;
    unsigned int *positive_indices = calloc(2 * n * C * n, sizeof(unsigned int));
    unsigned int *negative_indices = calloc(2 * n * C * n, sizeof(unsigned int));

    unsigned int *positive_offsets = malloc(n * C * sizeof(unsigned int));
    unsigned int *negative_offsets = malloc(n * C * sizeof(unsigned int));

    unsigned int *num_positive_indices = malloc(n * C * sizeof(unsigned int));
    unsigned int *num_negative_indices = malloc(n * C * sizeof(unsigned int));

    size_t counter_positive = 0;
    size_t counter_negative = 0;
    for (int item = 0; item < n; item++){

        for (int cnstr = 0; cnstr < C; cnstr++){
			size_t clause_offset = first_clause_index(con, cnstr);

            unsigned int npi = 0;
            unsigned int nni = 0;
            for(int cls = 0; cls < con->num_clauses[cnstr]; cls++){
				size_t clause_index = clause_offset + cls;
                int64_t factor = con->factors[clause_index];
                size_t prev_var = -1;
                for (int k = 0; k < con->clause_length[clause_index]; k++){
				    size_t var = con->variables[variable_index(cls, k, clause_offset)];

                    if (item == var && var != prev_var){
                        if (factor < 0){
                            // add index to "negative_indices"
                            negative_indices[counter_negative++] = cls;
                            nni++;
                        }else{
                            // add index to "positive_indices"
                            positive_indices[counter_positive++] = cls;
                            npi++;
                        }
                    }
                    prev_var = var;
                }
            }
            num_negative_indices[item * C + cnstr] = nni;
            negative_offsets[item * C + cnstr] = counter_negative - nni;
            num_positive_indices[item * C + cnstr] = npi;
            positive_offsets[item * C + cnstr] = counter_positive - npi;
        }
    }

    clock_t t1 = clock();
    initial_state_preparation(
            new_sol, cur_sol, n, NTerms,
            con, obj,
            positive_indices, num_positive_indices, positive_offsets,
            negative_indices, num_negative_indices, negative_offsets,
            Indices, NumIndices, Fulfilled,
            4, solver
        );
    double preprocess_time = (double)(clock() - t1) / CLOCKS_PER_SEC;

    // Start sampling after initial_state_preparation
    while (m_tot < M){
        signal(SIGINT, handle_signal);
        signal(SIGTERM, handle_signal);

        if (stop_flag) return 0;

        int m = ceil(pow(c, rounds));
        int j = rand() % (m + 1);
        m_tot += 2 * j + 1;
        *qtg_applications += 2 * j + 1;
        rounds++;
        int res = CSearch_opt(
            new_sol, cur_sol, j, n, NTerms,
            con, obj,
            positive_indices, num_positive_indices, positive_offsets,
            negative_indices, num_negative_indices, negative_offsets,
            Indices, NumIndices, Fulfilled,
            depth_look_ahead, solver
        );
        if (res) {
            if (callback) {
                callback(cur_sol->tot_profit, *qtg_applications, (double)(clock() - start) / CLOCKS_PER_SEC, preprocess_time);
            }
            m_tot = 0;

            rounds = 0;
            if((solver == SATISFY && cur_sol->tot_profit == -con->num_constraints) || (cur_sol->tot_profit <= stop_val && stop_val != -1)) {
                break;
            }
        }
    }

    free(positive_indices);
    free(positive_offsets);
    free(negative_indices);
    free(negative_offsets);
    free(num_positive_indices);
    free(num_negative_indices);
    free(NumIndices);
    free(Indices);
    free(Fulfilled);
    free_state(new_sol, 0);
    return ! (cur_sol->tot_profit == initial_value);
}