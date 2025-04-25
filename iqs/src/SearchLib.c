//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"
#include <signal.h>

volatile sig_atomic_t stop_flag = 0;

void handle_signal(int signum){
    stop_flag = 1;
}

#define NEGATIVE 0
#define POSITIVE 1

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


// implementations of classical sampling search and benchmarking =======================================================
static inline int evaluation(new_constraints_t *con, int64_t *potentials, int item,
							 const unsigned int *indices,
							 const unsigned int *num_indices,
							 const unsigned int *offsets, state_t *cur_sol){
//    int eval = 1;
    size_t C = con->num_constraints;
    // check, if assignment does not exceed potentials
    for (int cnstr = 0; cnstr < C; cnstr++){
		int64_t total = 0;
	    size_t clause_offset = first_clause_index(con, cnstr);
        for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++){
            int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
	        size_t clause_index = clause_offset + index;

			int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
	        for (int i = 0; i < con->clause_length[clause_index]; i++){
		        size_t var = con->variables[variable_index(index, i, clause_offset)];
				if( var < item ) assigned *= sw_tstbit(cur_sol->vector, var);
//		        assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
	        }
//	        printf("%lld ", con->factors[clause_index] * assigned);
			total += labs(con->factors[clause_index]) * assigned;
//	        if (con->constraints[cnstr].rhs_adapted < labs(con->constraints[cnstr].literals[cls].factor) * assigned){
//	            return 0;
//            }
        }
//        printf("item = %d total = %lld\n", item, total);
	    if (potentials[cnstr] < total) return 0;
    }
    return 1;
}

static inline int update_potentials(new_constraints_t *con, int64_t *potentials, int item,
									const unsigned int *indices,
									const unsigned int *num_indices,
									const unsigned int *offsets, state_t *cur_sol,
									int bit, int negative){
    // careful: destinction between positive and negative coefficients
    // for non-linear clauses with negative coefficients there are two ways, s.t. potential has to be subtracted:
    //  -> consideres item is set to 0 or previous assignments of clause are set to 0
    // for positive coefficients subtraction is only possible if considered item is set to 1 AND all previous assignments
    // are set to 1
    // update potentials has to be called 3 times

	size_t C = con->num_constraints;
	// revert the constraints rhs accordingly
	for (int cnstr = 0; cnstr < C; cnstr++){
		size_t clause_offset = first_clause_index(con, cnstr);
		for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++){
			unsigned int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
			size_t clause_index = clause_offset + index;

			// only if all previous items are assigned to 1, adjust rhs
			int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
			int is_closed = 1; // check, if there are unassigned variables within the clause
//			if (negative == NEGATIVE) assigned = bit; //
//            for (int i = 0; i < con->constraints[cnstr].literals[cls].len_literal - 2; i++){
			for (int i = 0; i < con->clause_length[clause_index]; i++){
				size_t var = con->variables[variable_index(index, i, clause_offset)];
				if (var < item) assigned *= sw_tstbit(cur_sol->vector, var);
				if (var > item) is_closed = 0;
//                assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
			}
//			if (negative == NEGATIVE) potentials[cnstr] -= labs(con->factors[clause_index]) * (1 - assigned);
            if (negative == POSITIVE && is_closed || negative == NEGATIVE)
                potentials[cnstr] -= labs(con->factors[clause_index]) * assigned;
//			potentials[cnstr] -= labs(con->factors[clause_index]) * assigned;
//            con->constraints[cnstr].rhs_adapted += labs(con->constraints[cnstr].literals[cls].factor) * assigned;
		}
	}
    return 1;
}

static inline int invert_update_potentials(new_constraints_t *con, int64_t *potentials, int item,
										   const unsigned int *indices,
										   const unsigned int *num_indices,
										   const unsigned int *offsets, state_t *cur_sol,
									       int bit, int negative){
    size_t C = con->num_constraints;
    // revert the constraints rhs accordingly
    for (int cnstr = 0; cnstr < C; cnstr++){
		size_t clause_offset = first_clause_index(con, cnstr);
        for (int cls = 0; cls < num_indices[item * C + cnstr]; cls++){
            unsigned int index = indices[offsets[item * C + cnstr] + cls]; // index of the clause of constraint cnstr
	        size_t clause_index = clause_offset + index;

            // only if all previous items are assigned to 1, adjust rhs
            int assigned = 1; // store, if all the previous items in the clause are assignmed to 1
            int is_closed = 1; // check, if there are unassigned variables within the clause
//            if (negative == NEGATIVE) assigned = bit; //
//            for (int i = 0; i < con->constraints[cnstr].literals[cls].len_literal - 2; i++){
            for (int i = 0; i < con->clause_length[clause_index]; i++){
				size_t var = con->variables[variable_index(index, i, clause_offset)];
				if (var < item) assigned *= sw_tstbit(cur_sol->vector, var);
				if (var > item) is_closed = 0;
//                assigned *= sw_tstbit(cur_sol->vector, con->constraints[cnstr].literals[cls].variables[i]);
            }
//			if (negative == NEGATIVE) potentials[cnstr] += labs(con->factors[clause_index]) * (1 - assigned);
//			potentials[cnstr] += labs(con->factors[clause_index]) * assigned;
            if (negative == POSITIVE && is_closed || negative == NEGATIVE)
                potentials[cnstr] += labs(con->factors[clause_index]) * assigned;
//            con->constraints[cnstr].rhs_adapted += labs(con->constraints[cnstr].literals[cls].factor) * assigned;
        }
    }
    return 1;
}


// look ahead to evaluate all possible solutions from certain position up to certain depth
//int look_ahead_correct( int index, int next_assignment, int depth, int *count_solutions, int64_t *potentials,
//                int **S_plus, int64_t **S_plus_value, int *num_plus,
//                int **S_minus, int64_t **S_minus_value, int *num_minus){
int look_ahead_correct( int index, int next_assignment, int depth, int *count_solutions, new_constraints_t *con, int64_t *potentials,
                const unsigned int *positive_indices, const unsigned int *num_positive_indices, const unsigned int *positive_offsets,
                const unsigned int *negative_indices, const unsigned int *num_negative_indices, const unsigned int *negative_offsets,
                state_t *cur_sol){
    // check, if assignment does not exceed potentials
    int bool_;
    if (next_assignment) {
        sw_setbit(cur_sol->vector, index); // set assignment to 1
    }
    else {
        sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
    }
    bool_ = eval_constraints(con, cur_sol, index);
//    if (next_assignment) bool_ = evaluation(con, potentials, index, positive_indices, num_positive_indices, positive_offsets, cur_sol);
//        else bool_ = evaluation(con, potentials, index, negative_indices, num_negative_indices, negative_offsets, cur_sol);
//    printf("(%d,%d,%d)\n", index, next_assignment, bool_);

    if (bool_){
        if (index == depth) {
            (*count_solutions)++;
//            cur_sol->tot_profit = ;
//            print_state(cur_sol);
//            printf("\n");
//            printf("->%d", eval_constraints(con, cur_sol, depth));
        }
        else{
        // adjust potentials to new solution
//            if (next_assignment) {
//                update_potentials(con, potentials, index, positive_indices, num_positive_indices, positive_offsets, cur_sol, next_assignment, POSITIVE);
//                sw_setbit(cur_sol->vector, index); // set assignment to 1
//            }
//            else {
//                update_potentials(con, potentials, index, negative_indices, num_negative_indices, negative_offsets, cur_sol, next_assignment, NEGATIVE);
//                sw_clrbit(cur_sol->vector, index); // set assignment to 0 (just to make sure, it should already be 0)
//            }

            look_ahead_correct(index + 1, 0, depth, count_solutions, con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, cur_sol);
            look_ahead_correct(index + 1, 1, depth, count_solutions, con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, cur_sol);

            // reset potentials for proper use in sampling algorithm
//            if (next_assignment) {
//                invert_update_potentials(con, potentials, index, positive_indices, num_positive_indices, positive_offsets, cur_sol, next_assignment, POSITIVE);
//            }
//            else invert_update_potentials(con, potentials, index, negative_indices, num_negative_indices, negative_offsets, cur_sol, next_assignment, NEGATIVE);
        }
        sw_clrbit(cur_sol->vector, index); // reset assignment to 0
    }
//    printf("\n", index, next_assignment);
    return 1;
}


int preprocessing(state_t *new_sol, state_t *cur_sol, int n, int NTerms,
            new_constraints_t *con, new_constraints_t *obj,
            const unsigned int *positive_indices, const unsigned int *num_positive_indices, const unsigned int *positive_offsets,
            const unsigned int *negative_indices, const unsigned int *num_negative_indices, const unsigned int *negative_offsets,
            int **Indices, int *NumIndices, int *Fulfilled,
            int depth_look_ahead, solver_t solver
            ){

    int64_t potentials[con->num_constraints];
    // Store whicso h bit from the previous solution is flipped
    int NumChanges = 0;
    int *ChangedBits = calloc(n, sizeof(int));

    // reset constraint rhs to initial values
    memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

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
//        fflush(stdout);
        look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, new_sol);
        // look ahead to the right side
        if (count[1] != 0)
            look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, new_sol);

        // If all the constraints ar fulfilled by both assignments, "go to the right"
        if (count[0] > 0 && count[1] > 0){
            sw_setbit(new_sol->vector, i);
            new_bit = 1;
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

        int all_positive;
        if (new_bit) {
            update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol, new_bit, POSITIVE);
        }
        else update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol, new_bit, NEGATIVE);
    }
    int64_t val = 0;

    int NumChangedTerms = 0;
    int *ChangedTerms = calloc(NTerms, sizeof(int));
    if (solver == OPTIMIZE) val = objective_value(obj, new_sol);
    if (solver == SATISFY) val = -num_satisfied_constrains(con, new_sol);

//    for (int term = 0; term < NumChangedTerms; term++) Fulfilled[ChangedTerms[term]] = 1 - Fulfilled[ChangedTerms[term]];
    cur_sol->tot_profit = 0; // solution might be infeasible
    sw_clear(cur_sol->vector);
    cur_sol->vector = sw_set(new_sol->vector);

    free(ChangedTerms);
    free(ChangedBits);
    return 1;
}



int CSearch(state_t *new_sol, state_t *cur_sol, int j, int n, int NTerms,
            new_constraints_t *con, new_constraints_t *obj,
            const unsigned int *positive_indices, const unsigned int *num_positive_indices, const unsigned int *positive_offsets,
            const unsigned int *negative_indices, const unsigned int *num_negative_indices, const unsigned int *negative_offsets,
            int **Indices, int *NumIndices, int *Fulfilled,
            int depth_look_ahead, solver_t solver
            ){

    int64_t potentials[con->num_constraints];
    for(int l = 0; l < 4 * j * j; l++){
//    for(int l = 0; l < 1; l++){
        // Store whicso h bit from the previous solution is flipped
        int NumChanges = 0;
        int *ChangedBits = calloc(n, sizeof(int));

        // reset constraint rhs to initial values
        memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));

        // initialize new solution
        new_sol->tot_profit = cur_sol->tot_profit;
        sw_set_ui_0(new_sol->vector);

        int i;
        for(i = 0; i < n; i++){
//        for(i = 0; i < 2; i++){
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
            look_ahead_correct(i, 0, min(i + depth_look_ahead, n - 1), &count[0], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, new_sol);
            // look ahead to the right side
            look_ahead_correct(i, 1, min(i + depth_look_ahead, n - 1), &count[1], con, potentials, positive_indices, num_positive_indices, positive_offsets, negative_indices, num_negative_indices, negative_offsets, new_sol);

//            printf("%d -> (%d %d) ", i, count[0], count[1]);

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
            if (new_bit) {
                update_potentials(con, potentials, i, positive_indices, num_positive_indices, positive_offsets, new_sol, new_bit, POSITIVE);
//                update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol, new_bit, NEGATIVE);
            }
            else update_potentials(con, potentials, i, negative_indices, num_negative_indices, negative_offsets, new_sol, new_bit, NEGATIVE);
//            for (int cnstr = 0; cnstr < con->num_constraints; cnstr++) printf("%lld ", potentials[cnstr]);
//            printf("\n");
        }
        // if the previous loop broke earlier, determine all bit changes
        for (int mn = i; mn < n; mn++) ChangedBits[NumChanges++] = mn;

        int64_t val = 0;
        int as1 = true;
//        print_state(new_sol);
//        if (solver == OPTIMIZE) as1 = quantum_feasibility2(con, new_sol, n + 1, false);
        if (solver == OPTIMIZE) as1 = eval_constraints(con, new_sol, n);

        int NumChangedTerms = 0;
        int *ChangedTerms = calloc(NTerms, sizeof(int));
//        if (as1 && solver == OPTIMIZE) val = ChangedObjVal(obj, new_sol, NumChanges, ChangedBits, Indices, NumIndices, Fulfilled, ChangedTerms, &NumChangedTerms);
        if (solver == OPTIMIZE) val = objective_value(obj, new_sol);
        if (solver == SATISFY) {
//            val = count_satisfyed_constraints(con, new_sol, n + 1, false, con->num_constraints - cur_sol->tot_profit);
            val = -num_satisfied_constrains(con, new_sol);
        }
//        printf("%d %lld %lld %lld\n", as1, val, potentials[0], potentials[1]);
        if (as1 && cur_sol->tot_profit > val){
            // If solution is updated, change the array of fulfilled terms
//            for (int term = 0; term < NumChangedTerms; term++) Fulfilled[ChangedTerms[term]] = 1 - Fulfilled[ChangedTerms[term]];
            cur_sol->tot_profit = val;
            sw_clear(cur_sol->vector);
            cur_sol->vector = sw_set(new_sol->vector);
//            printf(" feasible = %d value = %lld %lld\n", as1, cur_sol->tot_profit, val);

            free(ChangedTerms);
            free(ChangedBits);
            return 1;
        }
        free(ChangedTerms);
        free(ChangedBits);
    }
    return 0;
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
    preprocessing(
            new_sol, cur_sol, n, NTerms,
            con, obj,
            positive_indices, num_positive_indices, positive_offsets,
            negative_indices, num_negative_indices, negative_offsets,
            Indices, NumIndices, Fulfilled,
            4, solver
        );
    double preprocess_time = (double)(clock() - t1) / CLOCKS_PER_SEC;

    // Start sampling after preprocessing
    while (m_tot < M){
        signal(SIGINT, handle_signal);
        signal(SIGTERM, handle_signal);

        if (stop_flag) return 0;

//    for (int i = 0; i < 1; i++){
        int m = ceil(pow(c, rounds));
        int j = rand() % (m + 1);
        m_tot += 2 * j + 1;
        *qtg_applications += 2 * j + 1;
        rounds++;
        int res = CSearch(
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