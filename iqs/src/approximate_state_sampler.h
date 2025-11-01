//
// Created by Sören Wilkening on 24.10.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_IQS_SRC_APPROXIMATE_STATE_SAMPLER_H_
#define IMPROVED_QUANTUM_SEARCH_IQS_SRC_APPROXIMATE_STATE_SAMPLER_H_

#include "state.h"
#include "constraint.h"
#include "solver.h"

#define STATE_BLOCK 16384

typedef struct {
  state_t *good;
  state_t *bad;
  size_t num_good;
  size_t num_bad;
  size_t allocated_good;
  size_t allocated_bad;
  double good_amplitude;
  double bad_amplitude;
  double delta;
  int samples_first_good;
  int good_count;
} approximate_state_t;


approximate_state_t *init_approximete_state(int n, double bias);

void print_approximate_state(approximate_state_t *state);

void free_approximate_state(approximate_state_t *state);

int CSearch_opt_sampler(approximate_state_t *state, state_t *cur_sol,
                        int samples,
                        new_constraints_t *con, new_constraints_t *obj,
                        int depth_look_ahead);

#endif //IMPROVED_QUANTUM_SEARCH_IQS_SRC_APPROXIMATE_STATE_SAMPLER_H_
