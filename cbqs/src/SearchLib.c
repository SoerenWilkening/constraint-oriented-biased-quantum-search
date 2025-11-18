//
// Created by Sören Wilkening on 14.02.24.
//

#include "SearchLib.h"
#include <pthread.h>
#include <Python.h>

pthread_mutex_t update_lock = PTHREAD_MUTEX_INITIALIZER;

incumbents_t *init_incumbents(int n, state_t *initial){
    incumbents_t *init = malloc(sizeof(incumbents_t));
    init->head = 0;
    init->allocated = number_incumbents;
    init->num_states = 0;
    init->search_stage = malloc(number_incumbents * sizeof(int));
    init->states = init_large_state(n, number_incumbents);
    init->initial_samples = malloc(number_incumbents * sizeof(int));
    copy_state_inplace(&init->states[0], initial);
    return init;
}

void increase_incumbents(incumbents_t *incumbents){
    if (incumbents->head + 1 < incumbents->allocated) return;
    incumbents->states = increse_large_state(incumbents->states, incumbents->allocated, incumbents->allocated + number_incumbents);
    incumbents->search_stage = realloc(incumbents->search_stage, (incumbents->allocated + number_incumbents) * sizeof(int));
    incumbents->initial_samples = realloc(incumbents->initial_samples, (incumbents->allocated + number_incumbents) * sizeof(int));
    incumbents->allocated += number_incumbents;
}

void print_incumbents(incumbents_t *incumbents){
    for (int i = 0; i < incumbents->head + 1; ++i) {
        printf("%d %d | ", incumbents->search_stage[i], incumbents->initial_samples[i]);
        print_state(&incumbents->states[i]);
        printf("\n");
    }
}

void free_incumbents(incumbents_t *incumbents){
    free_state(incumbents->states, incumbents->num_states);
    free(incumbents->search_stage);
    free(incumbents->initial_samples);
    free(incumbents);
}

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
        state_t *global_opt,
        int ignore_constraint_search,
        incumbents_t *incumbents
        ) {
	int m_tot = 0;
	int n = cur_sol->vector.bits;
	int rounds = 0;
	double c = 6. / 5;

	int (*search_function)(state_t *, int, new_constraints_t *, new_constraints_t *, int, int, array_t *, int *);
 
//	size_t NTerms = obj->num_clauses[0]; // number terms
	array_t fulfilled_objective_terms = sw_init(obj->num_clauses[0]);

	struct timespec t1, t2;
    clock_gettime(CLOCK_MONOTONIC, &t1);

	int res;

    int feasible = eval_constraints(con, cur_sol, n);

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
	    cur_sol->tot_profit = objective_value(obj, cur_sol);
	    global_opt->tot_profit = 0;
	    search_function = CSearch_opt;
	}
	int direction = 1;
	int counter = -1;
	int updated = feasible;

	// Start sampling after initial_state_preparation
	double total_time = 0;
	int samples = 0;
	while (m_tot < M && total_time < stopping_time) {
//    for (int i = 0; i < 1; ++i) {
		signal(SIGINT, handle_signal);
		signal(SIGTERM, handle_signal);

		if (stop_flag) return 0;

		int m = ceil(pow(c, rounds));
		int j;
		if (stage == 2) j = 1; // when improving constraint tightness, use only small constant number of grover iterations
		else j = rand() % (m + 1);
		m_tot += 2 * j + 1;
		*qtg_applications += 2 * j + 1;
		res = search_function(
				cur_sol, j, con, obj,
				depth_look_ahead, direction, &fulfilled_objective_terms,
				&samples
		);
        clock_gettime(CLOCK_MONOTONIC, &t2);
		total_time = (t2.tv_sec - t1.tv_sec) + (t2.tv_nsec - t1.tv_nsec) / 1e9;
//        printf("%d %d %d %d %lld %d\n", stage, j, res, rounds, cur_sol->tot_profit, cur_sol->feasible);
		rounds++;
		if (res) {

            // first found feasible solution
            if (solver == OPTIMIZE && !feasible && cur_sol->feasible){
                stage = 2;
                cur_sol->tot_profit = objective_value(obj, cur_sol);
                direction = -1;
                feasible = 1;
            }
            
            // add solution to incumbent list
            increase_incumbents(incumbents);
            incumbents->search_stage[incumbents->head] = stage;
            incumbents->initial_samples[incumbents->head] = samples + 1;
            copy_state_inplace(&incumbents->states[incumbents->head + 1], cur_sol);
            incumbents->head++;
            samples = 0;
            
			// update global_opt if better solution is found
			pthread_mutex_lock(&update_lock);
			if (global_opt->tot_profit > cur_sol->tot_profit){
			    copy_state_inplace(global_opt, cur_sol);

				if (callback && global_opt->feasible) callback(global_opt->tot_profit, *qtg_applications, total_time, 0);
			}
			pthread_mutex_unlock(&update_lock);
			rounds = 0;

			m_tot = 0;
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
            updated = 1;
        }
        if (solver == OPTIMIZE && feasible && !updated) counter++;
	}
	incumbents->search_stage[incumbents->head] = -1; // last step, no better incumbents found
	incumbents->initial_samples[incumbents->head] = 0; // last step, no better incumbents found

	sw_clear(fulfilled_objective_terms);
	return feasible;
}