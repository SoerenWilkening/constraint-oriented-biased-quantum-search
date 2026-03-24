#include "variable_vector.h"
#include <stdio.h>
#include <stdint.h>

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

expression_t *bilinear_reduce(const int *y_indices, int m,
                              const int64_t *matrix,
                              const int *x_indices, int n) {
	if (!y_indices || !matrix || !x_indices || m < 0 || n < 0)
		return NULL;

	expression_t *expr = init_expression();
	if (!expr) return NULL;

	for (int i = 0; i < m; i++) {
		for (int j = 0; j < n; j++) {
			int64_t coeff = matrix[i * n + j];
			if (coeff == 0) continue;
			int64_t vars[2] = {(int64_t)y_indices[i], (int64_t)x_indices[j]};
			dyn_expr_add_term(expr, coeff, vars, 2);
		}
	}
	return expr;
}

expression_t *linear_reduce(const int64_t *coeffs,
                            const int *x_indices, int n) {
	if (!coeffs || !x_indices || n < 0)
		return NULL;

	expression_t *expr = init_expression();
	if (!expr) return NULL;

	for (int j = 0; j < n; j++) {
		if (coeffs[j] == 0) continue;
		int64_t var = (int64_t)x_indices[j];
		dyn_expr_add_term(expr, coeffs[j], &var, 1);
	}
	return expr;
}
