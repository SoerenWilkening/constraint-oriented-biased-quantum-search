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

//double BranchingFunction(int index, int bit_S, int bit_T, int diffcount, const BranchingStats_t *stats);

static inline double BranchingFunction(int index, int bit_S, int bit_T, int diffcount, const BranchingStats_t *stats){
    
//    printf("bias = %f\n", BranchingStats.bias);
    double total_bias, f = 0, q = 0;
    double objective_factor = stats->objective_factor; // objective related
    double constraint_factor = stats->constraint_factor; // constraint related
    double bias_factor = stats->bias_factor;
    double look_factor = stats->look_factor;
    if (diffcount == 0) look_factor = 0;
    double lookahead_0_probability = 0;

    if (diffcount < 0) lookahead_0_probability = 0; // bias towards 1
    else lookahead_0_probability = 1.; // bias towards 0

    if (stats->obj_dependent != NULL){
        f =  stats->obj_dependent[index];
    }
    if(stats->constraint_dependent != NULL){
        q =  stats->constraint_dependent[index];
    }
    if (bit_T == 0){
        if(bit_S == 0) {
            // both bits 0
            total_bias = (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias = 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
        }
        else {
            // bit1 = 0, bit2 = 1
            total_bias = 1. / (stats->bias + 2.);
//            total_bias = 1;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
        }
    } else{
        if(bit_S == 0) {
            // bit1 = 1, bit2 = 0
            total_bias = 1. / (stats->bias + 2.);
//            total_bias = 1;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias -= 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
        }
        else {
            // both bits 1
            total_bias = (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias = 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * objective_factor * f;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * constraint_factor * q;
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * bias_factor * (stats->bias + 1.) / (stats->bias + 2.);
//            total_bias += 1. / (objective_factor + constraint_factor + bias_factor + look_factor) * look_factor * lookahead_0_probability;
        }
    }

    return total_bias;
}

double StateProbability(state_t *state, state_t *threshold);

//state_t *updated(state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);
/* TODO:
     -> all the other branching rules
*/

#endif