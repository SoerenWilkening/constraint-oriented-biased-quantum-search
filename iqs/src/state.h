#ifndef STATE_H
#define STATE_H
#include "intarray.h"

typedef struct {
    double prob;
    int64_t tot_profit;
    array_t vector;
    array_t branch;
} state_t;

#endif