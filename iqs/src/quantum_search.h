//
// Created by Sören Wilkening on 06.09.25.
//

#ifndef IMPROVED_QUANTUM_SEARCH_QUANTUM_SEARCH_H
#define IMPROVED_QUANTUM_SEARCH_QUANTUM_SEARCH_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include "intarray.h"
#include "definitions.h"
#include "state.h"

state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M, size_t *measured_index);

#endif //IMPROVED_QUANTUM_SEARCH_QUANTUM_SEARCH_H
