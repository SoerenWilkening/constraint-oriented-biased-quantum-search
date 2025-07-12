//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"

volatile sig_atomic_t stop_flag = 0;

void handle_signal(int signum) {
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
		callback_t callback) {
	state_t *new_sol = copy_state(cur_sol);
	int64_t initial_value = cur_sol->tot_profit;
	int n = cur_sol->vector.bits;
	int C = con->num_constraints;

	int count[2] = {0, 0};
	int64_t potentials[C];
	memcpy(potentials, con->rhs, con->num_constraints * sizeof(int64_t));
//	look_ahead_correct(0, 0, n - 1, &count[0], con, potentials, cur_sol);
//	look_ahead_correct(0, 1, n - 1, &count[1], con, potentials, cur_sol);
	printf("counts = %d %d\n", count[0], count[1]);

	free_state(new_sol, 0);
	return cur_sol->tot_profit != initial_value;
}


int ctg(
		state_t *cur_sol,
		new_constraints_t *con,
		new_constraints_t *obj,
		int M,
		int stopping_time,
		size_t *qtg_applications,
		int depth_look_ahead,
		solver_t solver,
		int64_t stop_val,
		callback_t callback,
		int *break_item) {
	state_t *new_sol = copy_state(cur_sol);
	int m_tot = 0;
	int n = cur_sol->vector.bits;
	int rounds = 0;
	double c = 6. / 5;

	int (*search_function)(state_t *, state_t *, int, int, int, new_constraints_t *, new_constraints_t *, int, int);

	clock_t start = clock();

	size_t NTerms = obj->num_clauses[0]; // number terms

	struct timespec t1, t2;
    clock_gettime(CLOCK_MONOTONIC, &t1);

	int pot_eval = initial_state_preparation(new_sol, cur_sol, con, 0, break_item);

	clock_gettime(CLOCK_MONOTONIC, &t2);
	double preprocess_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
	int res;

	int feasible = eval_constraints(con, cur_sol, n);
	if (!feasible) cur_sol->tot_profit = pot_eval;

	int stage = 1;
	if (solver == SATISFY) search_function = CSearch_sat;
	else if (solver == OPTIMIZE && !feasible) search_function = CSearch_opt_sat; // opt_sat
	else if (solver == OPTIMIZE && feasible) {
	    stage = 3;
	    search_function = CSearch_opt;
	}
	int direction = 1;
	int counter = -1;
	int updated = feasible;

	int method = ACCEPTONE;
	int num_accepted = 0;

	int number_states = 5;
	state_t *stored = init_large_state(n, number_states);
	if (method == ACCEPTMANY){
	    for (int i = 0; i < number_states; ++i) copy_state_inplace(&stored[i], cur_sol);
	    print_state(cur_sol);
	    free_state(cur_sol, 1);
	    cur_sol = stored;
	}
	if (M == 0){
	    free_state(new_sol, 0);
	    return feasible;
	}

	// Start sampling after initial_state_preparation
	double total_time = preprocess_time;
	while (m_tot < M && total_time < stopping_time) {
//	for (int i = 0; i < 20; ++i) {
		signal(SIGINT, handle_signal);
		signal(SIGTERM, handle_signal);

		if (stop_flag) return 0;

		int m = ceil(pow(c, rounds));
		int j;
		if (stage == 2) j = 1; // when improving constraint tightness, use only small constant number of grover iterations
		else j = rand() % (m + 1);
		m_tot += 2 * j + 1;
		*qtg_applications += 2 * j + 1;
		rounds++;
		res = search_function(
				new_sol, cur_sol, j, n, NTerms,
				con, obj,
				depth_look_ahead, direction
		);
        clock_gettime(CLOCK_MONOTONIC, &t2);
		total_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
		if (res) {
			if (callback && feasible && updated && method != ACCEPTMANY) {
				callback(cur_sol->tot_profit, *qtg_applications, total_time, preprocess_time);
			}
//			printf("%d %d\n", stage, num_accepted);
			if (stage == 3 && method == ACCEPTMANY) {
			    if (num_accepted == number_states - 1){
			        int64_t mini = 0;
					int index = 0;
				    for (int i = 0; i < number_states; ++i) {
						if (mini > stored[i].tot_profit){
							mini = stored[i].tot_profit;
							index = i;
						}
				    }
					if (index > 0) copy_state_inplace(&stored[0], &stored[index]);
				    for (int i = 1; i < number_states; ++i) copy_state_inplace(&stored[i], &stored[0]);
					cur_sol = stored;
					num_accepted = 0;
                    if (callback) callback(cur_sol->tot_profit, *qtg_applications, total_time, preprocess_time);
			    }
			    else{
				    num_accepted++;
//				    printf("\n%d accepted | ", num_accepted);
//				    print_state(cur_sol);
				    cur_sol = &stored[num_accepted];
				}
			}
			if (solver == OPTIMIZE && !feasible){
				feasible = eval_constraints(con, new_sol, n);
				if (feasible) {
//				    printf("Stage 2\n");
				    stage = 2;
				    if (callback) {
			        	callback(objective_value(obj, cur_sol), *qtg_applications, total_time, preprocess_time);
			        }
				    direction = -1;
				}
			}

			m_tot = 0;
			rounds = 0;
			if (feasible && ((solver == SATISFY && cur_sol->tot_profit == -con->num_constraints) ||
			    (cur_sol->tot_profit <= stop_val && stop_val != -1))) {
				break;
			}
		}
        // improve violations before optimizing
        if (solver == OPTIMIZE && counter > 10 && !updated) {
//            printf("Stage 3\n");
            stage = 3;
            search_function = CSearch_opt;
            cur_sol->tot_profit = objective_value(obj, cur_sol);
            if (method == ACCEPTMANY) for (int i = 1; i < number_states; ++i) copy_state_inplace(&stored[i], cur_sol);
            updated = 1;
        }
        if (solver == OPTIMIZE && feasible && !updated) counter++;
	}
//	free_state(stored, number_states);
//	print_state(cur_sol);
	free_state(new_sol, 0);
	return feasible;
}