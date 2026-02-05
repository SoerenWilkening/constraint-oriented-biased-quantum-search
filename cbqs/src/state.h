#ifndef STATE_H
#define STATE_H
#include "intarray.h"
//#include "Branching.h"

typedef struct {
    double prob;
    int64_t tot_profit;
    array_t vector;
    array_t branch;
	int feasible;
} state_t;

int min(int a, int b);
int compare(int64_t obj, int64_t thr, int sense);

void free_state(state_t *state, size_t numStates);
state_t *init_state(int64_t ObjVal, const int *array, int n);
state_t *init_large_state(int n, int number_states);
state_t *increse_large_state(state_t *state,  int old_num_states, int new_num_states);
state_t *copy_state(state_t *state);
void copy_state_inplace(state_t *dest, state_t *src);
void print_state(state_t *state);
state_t *read_states(char **name, int num_files, size_t *NumberStatesFinal, int n);
/* Note: updated() is now declared in Branching.h with solver_ctx_t parameter */

#endif