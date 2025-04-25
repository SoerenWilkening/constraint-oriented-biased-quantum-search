#include <state.h>

int min(int a, int b){
    return (a < b) ? a : b;
}

int compare(int64_t obj, int64_t thr, int sense) {
    return obj * sense < thr *sense;
}

void free_state(state_t *state, size_t numStates) {
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
    state->vector = sw_init(n);
    state->branch = sw_init(n);
    for (int i = 0; i < n; ++i) if (array[i] == 1) sw_setbit(state->vector, i);
    return state;
}

state_t *copy_state(state_t *state){
    state_t *copy = malloc(sizeof(state_t));
    copy->tot_profit = state->tot_profit;
    copy->prob = state->prob;
    copy->vector = sw_set(state->vector);
    copy->branch = sw_set(state->branch);
    return copy;
}

void print_state(state_t *state){
    printf("%lld %f ", state->tot_profit, state->prob);
    sw_print(state->vector);
}

state_t *read_states(char **name, int num_files, size_t *NumberStatesFinal, int n) {
    state_t *parent;

    int64_t placeholder;
    size_t estimate = 500000;
    parent = calloc(estimate, sizeof(state_t));

    size_t count = 0;

    for (int x = 0; x < num_files; x++){
        FILE *file = fopen(name[x], "r");
        if (!file) return NULL;

        for (size_t i = 0; i < estimate; ++i) {
            if (fscanf(file, "%lld ", &placeholder) != 1) {
                fclose(file);
                break;
            }
//            printf("%d \n", placeholder);
            parent[i].tot_profit = placeholder;
            parent[i].vector = sw_init(n);
            parent[i].branch = sw_init(n);
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
                estimate *= 2;
                parent = realloc(parent, estimate * sizeof(state_t));
            }
            count++;
        }
    }
    *NumberStatesFinal = count;
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