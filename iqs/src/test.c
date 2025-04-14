#include "constraint.h"

int main(){
    expression_t *expr = init_expression();

	int arr[5];
	for (int i = 0; i < 5; ++i) arr[i] = 1;
	state_t *sol = init_state(0, arr, 5);

    for (int i = 0; i < 5; i++){
        add_variable(expr, i);
    }
	multiply_constant(expr, -1);
	add_sense_to_expression(expr, LOWER);
	add_rhs_to_expression(expr, 3);
	merge_expression(expr);

	new_constraints_t con = init_new_constraint();
	add_expression_to_constraints(&con, expr);
	add_expression_to_constraints(&con, expr);
	new_constraints_t con2 = copy_new_constraint(&con);
	print_new_constraint(&con);
	print_new_constraint(&con2);

	printf("%d\n", num_satisfied_constrains(&con2, sol));
	printf("%lld\n", objective_value(&con2, sol));

	free_constraints(&con);

    free_expression(expr);
    return 0;
}