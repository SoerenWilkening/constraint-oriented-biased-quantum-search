#ifndef BRANCHING_H
#define BRANCHING_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "intarray.h"
//#include "SearchLib.h"
#include "definitions.h"
#include "state.h"

typedef struct {
    double objective_factor;
    double *obj_dependent;

    double constraint_factor;
    double *constraint_dependent;

    double bias_factor;
    double bias;

    double look_factor;
} BranchingStats_t;

extern BranchingStats_t BranchingStats; // branching stats as global variable

void set_factors(double objective_factor, double constraint_factor, double bias_factor, double look_factor);

void set_bias(double bias);

void set_obj_dependence(double *dependence, int n);

void set_constraint_dependence(double *dependence, int n);

double BranchingFunction(int index, int bit_S, int bit_T, int diffcount);

double StateProbability(state_t *state, state_t *threshold);

state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);
/* TODO:
     -> all the other branching rules
*/

#endif