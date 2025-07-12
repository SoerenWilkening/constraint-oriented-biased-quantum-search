#include "constraint.h"

int main(){
    expression_t *expr = init_expression();

	int arr[5];
	for (int i = 0; i < 5; ++i) arr[i] = 1;
	state_t *sol = init_state(0, arr, 5);

	expression_t *e1 = init_expression();
	add_variable(e1, 3);
	multiply_variable(e1, 5);
	multiply_variable(e1, 7);
	multiply_variable(e1, 2);
	add_expression(expr, e1);
	free_expression(e1);

	e1 = init_expression();
	add_variable(e1, 3);
	multiply_variable(e1, 5);
	multiply_variable(e1, 7);
	multiply_variable(e1, 1);
	add_expression(expr, e1);
	free_expression(e1);

	add_expression(expr, e1);

	for (int i = 5; i >= 0; i--){
		e1 = init_expression();
		add_variable(e1, i);
		multiply_variable(e1, i + 2);
		add_expression(expr, e1);
		free_expression(e1);

		e1 = init_expression();
		add_variable(e1, i);
		multiply_variable(e1, i + 1);
		add_expression(expr, e1);
		free_expression(e1);
	}
	multiply_constant(expr, 3);
	add_sense_to_expression(expr, LOWER);
	add_rhs_to_expression(expr, 3);
	print_expression(expr);
	merge_expression(expr);
	printf("\n");
	print_expression(expr);
	sort_expression(expr);
	printf("\n");
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