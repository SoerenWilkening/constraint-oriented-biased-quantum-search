#include "state.h"
#include <math.h>
#include <inttypes.h>

int min(int a, int b){
    return (a < b) ? a : b;
}

int compare(int64_t obj, int64_t thr, int sense) {
    return obj * sense < thr *sense;
}

void free_state(state_t *state, size_t numStates) {
	if (state == NULL) return;
    for (size_t i = 0; i < numStates; i++){
        sw_clear(state[i].vector);
        sw_clear(state[i].branch);
    }
    free(state);
}


state_t *init_state(int64_t ObjVal, const int *array, int n) {
    state_t *state = malloc(sizeof(state_t));
    state->tot_profit = ObjVal;
    state->prob = 1.;
    state->feasible = 0.;
    state->vector = sw_init(n);
    state->branch = sw_init(n);
    if (array != NULL) for (int i = 0; i < n; ++i) if (array[i] == 1) sw_setbit(state->vector, i);
    return state;
}

state_t *init_large_state(int n, int number_states){
	state_t *state = malloc(number_states * sizeof(state_t));
	for (int i = 0; i < number_states; ++i) {
		state[i].tot_profit = 0;
		state[i].prob = 1.;
        state[i].feasible = 0;
		state[i].vector = sw_init(n);
		state[i].branch = sw_init(n);
	}
	return state;
}

state_t *increse_large_state(state_t *state, int old_num_states, int new_num_states){
    state = realloc(state, new_num_states * sizeof(state_t));
    if (state == NULL){
        printf("failed reallocation\n");
        fflush(stdout);
        exit(1);
    }
    int n = state->vector.bits;
    for (int i = old_num_states; i < new_num_states; ++i) {
        state[i].tot_profit = 0;
        state[i].prob = 1.;
        state[i].feasible = 0;
        state[i].vector = sw_init(n);
        state[i].branch = sw_init(n);
    }
    return state;
}

state_t *copy_state(state_t *state){
    state_t *copy = malloc(sizeof(state_t));
    copy->tot_profit = state->tot_profit;
    copy->prob = state->prob;
    copy->vector = sw_set(state->vector);
    copy->branch = sw_set(state->branch);
	copy->feasible = state->feasible;
    return copy;
}

void copy_state_inplace(state_t *dest, state_t *src){
	dest->tot_profit = src->tot_profit;
	dest->prob = src->prob;
	dest->feasible = src->feasible;
	sw_set_inplace(dest->vector, src->vector);
	sw_set_inplace(dest->branch, src->branch);
}

void print_state(state_t *state){
    printf("%" PRId64 " %f %d %zu ", state->tot_profit, state->prob, state->feasible, state->vector.bits);
    sw_print(state->vector);
    printf(" ");
    sw_print(state->branch);
}

state_t *read_states(char **name, int num_files, size_t *NumberStatesFinal, int n) {
    state_t *parent;

    double placeholder;
    size_t estimate = 500000;
//    parent = calloc(estimate, sizeof(state_t));
    parent = init_large_state(n, estimate);
    if (parent == NULL) {
        printf("failed allocation\n");
        fflush(stdout);
        exit(1);
    }

    size_t count = 0;

    for (int x = 0; x < num_files; x++){
//        printf("file = %s\n", name[x]);
        fflush(stdout);
        FILE *file = fopen(name[x], "r");
        if (file == NULL){
            printf("failed reading\n");
            fflush(stdout);
            exit(1);
        }

        if (!file) return NULL;

        size_t i = count - 1;
        while (1) {
            i++;
            if (fscanf(file, "%lf ", &placeholder) != 1) {
                fclose(file);
                break;
            }
//            if (fabs(placeholder) < 0.1) printf("file = %s\n", name[x]);
//            printf("%d\n", placeholder);
            parent[i].tot_profit = (int64_t) placeholder;
//            parent[i].vector = sw_init(n);
//            parent[i].branch = sw_init(n);
            for (int j = 0; j < n; ++j) {
                int assignment = 0, branching = 0;
                fscanf(file, "%d %d ", &assignment, &branching);
                if (assignment) { sw_setbit(parent[i].vector, j);}
                else { sw_clrbit(parent[i].vector, j);}
                if (branching) { sw_setbit(parent[i].branch, j); }
                else { sw_clrbit(parent[i].branch, j); }
            }
            if (count == estimate - 1) {
                // increase the size of parent, if necessary
                increse_large_state(parent, estimate, 2 * estimate);
                estimate *= 2;
//                parent = realloc(parent, estimate * sizeof(state_t));
            }
            count++;
        }
    }
//    printf("count %d\n", count);
    *NumberStatesFinal = count;
    for (size_t i = count; i < estimate; i++){
        sw_clear(parent[i].vector);
        sw_clear(parent[i].branch);
    }
    parent = realloc(parent, count * sizeof(state_t));
    return parent;
}

//state_t *updated(state_t *bnb, size_t number_states,
//                size_t *new_number, state_t *threshold, int sense) {
//    state_t *up = calloc(number_states, sizeof(state_t));
//    size_t a = 0;
//    double total = 0;
//
//    for (size_t i = 0; i < number_states; ++i) {
//        if (bnb[i].tot_profit < threshold->tot_profit) {
//            up[a].tot_profit = bnb[i].tot_profit;
//            up[a].vector = sw_set(bnb[i].vector);
//            up[a].branch = sw_set(bnb[i].branch);
//            StateProbability(&up[a], threshold);
//
//            total += up[a].prob;
//            a++;
//        }
//    }
//    *new_number = a;
//    if (a == 0) {
//        free_state(up, number_states);
//        return NULL;
//    }
//    up = realloc(up, a * sizeof(state_t));
//    return up;
//}