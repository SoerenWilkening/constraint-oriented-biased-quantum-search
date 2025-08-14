#include "constraint.h"

int main(){
    expression_t *expr;

	int arr[5];
	for (int i = 0; i < 5; ++i) arr[i] = 1;
	state_t *sol = init_state(0, arr, 5);

	expression_t *e1 = init_expression();
	add_variable(e1, 3);
	multiply_variable(e1, 6);
	multiply_constant(e1, 2);
	add_variable(e1, 1);

	expression_t *e2 = init_expression();
	add_variable(e2, 3);
	multiply_constant(e2, 3);
	add_variable(e2, 4);

	print_expression(e1);
	print_expression(e2);

	expr = multiply_expressions(e1, e2);
	print_expression(e1);
	print_expression(e2);
	printf("\n");
	free_expression(e1);
	free_expression(e2);
	print_expression(expr);
//	new_constraints_t con = init_new_constraint();
//	add_expression_to_constraints(&con, expr);
//	add_expression_to_constraints(&con, expr);
//	new_constraints_t con2 = copy_new_constraint(&con);
//	print_new_constraint(&con);
//	print_new_constraint(&con2);
//
//	printf("%d\n", num_satisfied_constrains(&con2, sol));
//	printf("%lld\n", objective_value(&con2, sol));
//
//	free_constraints(&con);

    free_expression(expr);
    return 0;
}