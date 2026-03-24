#ifndef VARIABLE_VECTOR_H
#define VARIABLE_VECTOR_H

#include <stdlib.h>
#include <stdint.h>
#include "definitions.h"
#include "Expression.h"

typedef struct {
	int *indices;
	int *lb;
	int *ub;
	int *vtype;
	int n;
} c_variable_vector_t;

c_variable_vector_t c_variable_vector_init(int n);
void c_variable_vector_free(c_variable_vector_t *vv);

/**
 * Bilinear reduce: M[m×n] @ (y[m], x[n]) → expression_t.
 * Produces terms [M[i,j], y[i], x[j]] for all nonzero M[i,j].
 * Matrix is row-major int64. Returns NULL on error.
 */
expression_t *bilinear_reduce(const int *y_indices, int m,
                              const int64_t *matrix,
                              const int *x_indices, int n);

/**
 * Linear reduce: coeffs[n] @ x[n] → expression_t.
 * Produces terms [coeffs[j], x[j]] for all nonzero coeffs[j].
 * Returns NULL on error.
 */
expression_t *linear_reduce(const int64_t *coeffs,
                            const int *x_indices, int n);

#endif /* VARIABLE_VECTOR_H */
