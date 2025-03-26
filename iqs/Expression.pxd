from libc.stdint cimport int64_t

cdef extern from "src/Expression.h":
	ctypedef struct expression_t:
		int64_t *literals;
		int *len_literal;
		int expr_size;

	expression_t *init_expression();
	void free_expression(expression_t *expr);
	void merge_expression(expression_t *expr);

	void add_constant(expression_t *expr, int64_t constant);
	void add_variable(expression_t *expr, int64_t index);
	void add_expression(expression_t *expr1, expression_t *expr2);

	void sub_constant(expression_t *expr, int64_t constant);
	void sub_variable(expression_t *expr, int64_t index);
	void sub_expression(expression_t *expr1, expression_t *expr2);

	void multiply_constant(expression_t *expr, int64_t constant);
	void multiply_variable(expression_t *expr, int64_t index);
