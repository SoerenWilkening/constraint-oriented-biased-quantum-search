//
// Created by Sören Wilkening on 07.07.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H
#define IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include "intarray.h"
#include "definitions.h"
#include "Branching.h"
#include "constraint.h"
#include "state.h"
#include "solver.h"

int local_search(state_t *cur_sol,
                 new_constraints_t *con,
                 new_constraints_t *obj,
				 int distance,
                 int stopping_time,
                 solver_t solver,
                 int64_t stop_val,
                 callback_t callback);

#endif //IMPROVED_QUANTUM_SEARCH_LOCAL_SEARCH_H
