from libc.stdint cimport int64_t

cdef extern from "src/Expression.h":
	ctypedef struct expression_t:
		int64_t literals[100000 * 3];
		int len_literal[100000];
		int expr_size;

	expression_t *init_expression();

	void add_constant(expression_t *expr, int64_t constant);
	void add_variable(expression_t *expr, int64_t index);
	void add_expression(expression_t *expr1, expression_t *expr2);

	void sub_constant(expression_t *expr, int64_t constant);
	void sub_variable(expression_t *expr, int64_t index);
	void sub_expression(expression_t *expr1, expression_t *expr2);

	void multiply_constant(expression_t *expr, int64_t constant);
	void multiply_variable(expression_t *expr, int64_t index);
