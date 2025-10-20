//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"
#include <pthread.h>
#include <Python.h>

pthread_mutex_t update_lock = PTHREAD_MUTEX_INITIALIZER;

volatile sig_atomic_t stop_flag = 0;

void handle_signal(int signum) {
	stop_flag = 1;
}

void reset_flag(){
    stop_flag = 0;
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
		int *break_item,
        state_t *global_opt,
        int ignore_constraint_search) {
	state_t *new_sol = copy_state(cur_sol);
	int m_tot = 0;
	int n = cur_sol->vector.bits;
	int rounds = 0;
	double c = 6. / 5;

	int (*search_function)(state_t *, state_t *, int, int, int, new_constraints_t *, new_constraints_t *, int, int, array_t *);

	clock_t start = clock();

	size_t NTerms = obj->num_clauses[0]; // number terms
	array_t fulfilled_objective_terms = sw_init(NTerms);

	struct timespec t1, t2;
    clock_gettime(CLOCK_MONOTONIC, &t1);

//	int pot_eval = initial_state_preparation(new_sol, cur_sol, con, obj, 0, break_item);

//    int pot_eval = eval_constraints(con, new_sol, n);

	clock_gettime(CLOCK_MONOTONIC, &t2);
	double preprocess_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
	int res;

	 int feasible = eval_constraints(con, cur_sol, n);
	// if (!feasible) cur_sol->tot_profit = pot_eval;

//    printf("ignore %d\n", ignore_constraint_search);
	int stage = 1;
	if (solver == SATISFY) search_function = CSearch_sat;
	if (solver == OPTIMIZE && !feasible) search_function = CSearch_opt_sat; // opt_sat
	if (solver == OPTIMIZE && feasible) {
	    prepare(obj, cur_sol, &fulfilled_objective_terms);
	    stage = 3;
	    search_function = CSearch_opt;
	}
	if (solver == OPTIMIZE && ignore_constraint_search) {
	    stage = 3;
	    cur_sol->tot_profit = 0;
	    global_opt->tot_profit = 0;
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
				depth_look_ahead, direction, &fulfilled_objective_terms
		);
//		printf("%lld %lld %lld %lld\n", m_tot, res, cur_sol->tot_profit, global_opt->tot_profit);
        clock_gettime(CLOCK_MONOTONIC, &t2);
		total_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
		if (res) {
			// update global_opt if better solution is found
			pthread_mutex_lock(&update_lock);
			int should_callback = 0;
			if (global_opt->tot_profit > cur_sol->tot_profit){
				global_opt->tot_profit = cur_sol->tot_profit;
				sw_set_inplace(global_opt->vector, cur_sol->vector);
				if (callback && feasible && updated && method != ACCEPTMANY) {
                    callback(global_opt->tot_profit, *qtg_applications, total_time, preprocess_time);
                }
			}
			pthread_mutex_unlock(&update_lock);

			if (solver == OPTIMIZE && !feasible){
				feasible = eval_constraints(con, new_sol, n);
				if (feasible) {
				    stage = 2;
				    pthread_mutex_lock(&update_lock);
				    int64_t val = objective_value(obj, cur_sol);
				    if (global_opt->tot_profit > val){
				        global_opt->tot_profit = val;
				        sw_set_inplace(global_opt->vector, cur_sol->vector);
				        if (callback) {
			        	    callback(objective_value(obj, cur_sol), *qtg_applications, total_time, preprocess_time);
			            }
                    }
				    pthread_mutex_unlock(&update_lock);
				    direction = -1;
				}
			}

			m_tot = 0;
			rounds = 0;
			if ((solver == SATISFY && cur_sol->tot_profit == - (int64_t) con->num_constraints) || feasible && (cur_sol->tot_profit <= stop_val && stop_val != -1)) {
				break;
			}
		}
        // improve violations before optimizing
        if (solver == OPTIMIZE && counter > 10 && !updated) {
            stage = 3;
            search_function = CSearch_opt;
            cur_sol->tot_profit = objective_value(obj, cur_sol);
	        prepare(obj, cur_sol, &fulfilled_objective_terms);
            if (method == ACCEPTMANY) for (int i = 1; i < number_states; ++i) copy_state_inplace(&stored[i], cur_sol);
            updated = 1;
        }
        if (solver == OPTIMIZE && feasible && !updated) counter++;
	}
	free_state(new_sol, 0);
	sw_clear(fulfilled_objective_terms);
	return feasible;
}