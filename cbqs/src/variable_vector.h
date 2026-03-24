#ifndef VARIABLE_VECTOR_H
#define VARIABLE_VECTOR_H

#include <stdlib.h>
#include "definitions.h"

typedef struct {
	int *indices;
	int *lb;
	int *ub;
	int *vtype;
	int n;
} c_variable_vector_t;

c_variable_vector_t c_variable_vector_init(int n);
void c_variable_vector_free(c_variable_vector_t *vv);

#endif /* VARIABLE_VECTOR_H */
