#include "variable_vector.h"
#include <stdio.h>

c_variable_vector_t c_variable_vector_init(int n) {
	c_variable_vector_t vv;
	vv.n = n;
	if (n <= 0) {
		vv.n = 0;
		vv.indices = NULL;
		vv.lb = NULL;
		vv.ub = NULL;
		vv.vtype = NULL;
		return vv;
	}
	vv.indices = calloc(n, sizeof(int));
	vv.lb = calloc(n, sizeof(int));
	vv.ub = calloc(n, sizeof(int));
	vv.vtype = calloc(n, sizeof(int));
	if (!vv.indices || !vv.lb || !vv.ub || !vv.vtype) {
		printf("c_variable_vector_init: allocation failed\n");
		fflush(stdout);
		exit(1);
	}
	return vv;
}

void c_variable_vector_free(c_variable_vector_t *vv) {
	free(vv->indices);
	free(vv->lb);
	free(vv->ub);
	free(vv->vtype);
	vv->indices = NULL;
	vv->lb = NULL;
	vv->ub = NULL;
	vv->vtype = NULL;
	vv->n = 0;
}
