//
// Created by Sören Wilkening on 08.09.25.
//

#include "model.h"

model_t *init_model(){
    model_t *mod = malloc(sizeof(model_t));
    mod->bias_factor = 1.;
    mod->manual_bias_factor = 0.;
    mod->look_ahead_factor = 0.;
    mod->depth_look_ahead = 0.;
    mod->num_workers = 12;
    mod->n = 0;
    mod->runtime = 0.;
    mod->M = -1;
    mod->monte_carlo_estimate = 0;
    mod->ignore_constraint_search = 0;
    mod->manual_bias = NULL;
    mod->initial_state = NULL;
    mod->global_opt = NULL;
    mod->obj = NULL;
    mod->con = NULL;
    mod->max_delta = 7;
    mod->reset_delta = 1;

    return mod;
}


void free_model(model_t *mod){
    if (mod->manual_bias != NULL) free(mod->manual_bias);
    if (mod->initial_state != NULL) free_state(mod->initial_state, 1);
    if (mod->global_opt != NULL) free_state(mod->global_opt, 1);

    if (mod->obj != NULL) free_constraints(mod->obj);
    if (mod->con != NULL) free_constraints(mod->con);
    free(mod);
}