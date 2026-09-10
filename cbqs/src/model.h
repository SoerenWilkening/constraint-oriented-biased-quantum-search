//
// Created by Sören Wilkening on 08.09.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_MODEL_H
#define IMPROVED_QUANTUM_SEARCH_MODEL_H
#include <stdint.h>   /* int64_t qtg_applications (bd 9fi): depend on it directly,
                       * not transitively via constraint.h, so an include reorder
                       * can't silently break the field's declaration. */
#include "state.h"
#include "constraint.h"

typedef struct {
	double runtime;
	new_constraints_t *obj;
    new_constraints_t *con;
	state_t *initial_state;
	state_t *global_opt;
	size_t M;
    size_t opt_switch_oracles;  /* M0f: cumulative-oracle threshold (per worker) for the
                                 * opt_sat->opt exploit->explore switch in ctg, replacing the
                                 * hardcoded counter>10. SIZE_MAX disables the auto-switch.
                                 * NORTHSTAR §4: learned, in oracle units, bounded [0, alpha*T(n)]. */
    size_t opt_sample_cap;      /* bd 0o8: cap on the classical Grover-round sample count
                                 * (4j²+1) in CSearch_{sat,opt_sat,opt}; 0 == unbounded. Copied
                                 * to ctx->opt_sample_cap at ctg entry. Bounds the O(n·j²) sim
                                 * wall-time of large-j rounds WITHOUT touching the 2j+1 oracle
                                 * charge (CLAUDE.md §1.2). See solver_ctx.h / opt_sample_count. */
    int break_item;
	int n;
	double stopping_time;
	int stop_val;
	int depth_look_ahead;
	int num_workers;
	int ignore_constraint_search;
	int monte_carlo_estimate;
	int reset_delta;
	int max_delta;
    int solver;
    int64_t qtg_applications;   /* bd 9fi: post-parallel aggregation slot = max over
                                 * workers of the per-worker size_t oracle_count. int64
                                 * (not int) so a raw-API huge mod->M cannot truncate the
                                 * aggregate or overflow the Cython assignment. Must stay in
                                 * lockstep with Model.pxd's mirror (CLAUDE.md §1.2). */
    int max_worse_acceptances;
    int stopping_condition;
    int distance;
} model_t;

model_t *init_model(void);

void free_model(model_t *mod);

void print_model(model_t *mod);

#endif //IMPROVED_QUANTUM_SEARCH_MODEL_H
