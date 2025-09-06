//
// Created by Sören Wilkening on 06.09.25.
//

#include "quantum_search.h"



size_t sampling(const double *probs, size_t numStates, size_t *measured_index) {
	double random = (double) (rand() % 1234567) / 1234567;
	double cumulated = 0;
	for (size_t i = 0; i < numStates; ++i) {
		cumulated += probs[i];
		if (cumulated >= random) {
			*measured_index = i;
			return i;
		}
	}
	*measured_index = numStates;
	return numStates;
}

state_t *amplitude_amplification(state_t *states, size_t numStates, size_t calls, size_t *measured_index) {
	if (states == NULL || numStates == 0) return NULL;

	state_t *result;
	double amp_factor;
	double total_prob = 0;
	double *prob = malloc(numStates * sizeof(double));

	for (size_t i = 0; i < numStates; ++i) total_prob += states[i].prob;

	amp_factor = pow(sin((2 * calls + 1) * asin(sqrt(total_prob))), 2) / total_prob;

	for (size_t i = 0; i < numStates; ++i) prob[i] = states[i].prob * amp_factor;

	size_t measurement = sampling(prob, numStates, measured_index);
	free(prob);

	if (measurement == numStates)
		return NULL;
	else {
		result = copy_state(&states[measurement]);
		return result;
	}
}

state_t *QSearch(state_t *states, size_t numStates, size_t *iterations, size_t *rounds, size_t M, size_t *measured_index) {
	fflush(stdout);
	size_t m, j, m_tot;
	m_tot = 0;
	double c = 6. / 5;
	*rounds = 0;
	*iterations = 0;

	state_t *result;

	while (m_tot < M) {
		++(*rounds);
		m = ceil(pow(c, *rounds));
		j = rand() % m + 1;
		*iterations += j;
		m_tot += 2 * j + 1;

		result = amplitude_amplification(states, numStates, j, measured_index);

		if (result != NULL) return result;
	}
	return NULL;
}