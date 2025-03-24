#ifndef STATE_H
#define STATE_H
#include "intarray.h"

typedef struct {
    double prob;
    int64_t tot_profit;
    array_t vector;
    array_t branch;
} state_t;

int min(int a, int b);
int compare(int64_t obj, int64_t thr, int sense);

void free_state(state_t *state, size_t numStates);
state_t *init_state(int64_t ObjVal, const int *array, int n);
state_t *copy_state(state_t *state);
void print_state(state_t *state);
state_t *read_states(char **name, int num_files, size_t *NumberStatesFinal, int n);
//state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);

#endif