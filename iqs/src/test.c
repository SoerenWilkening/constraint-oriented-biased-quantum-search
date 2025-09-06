#include "constraint.h"
#include "local_search.h"

int main(){
	srand(clock());

	int arr[5];
	for (int i = 0; i < 5; ++i) arr[i] = 0;
	state_t *sol = init_state(0, arr, 5);
	sol->tot_profit = INT64_MAX;
	sol->feasible = 0;

	// generate simple 0-1 knapsack instance
	expression_t *expr = init_expression();
	add_variable(expr, 0);
	multiply_constant(expr, 2);
	add_variable(expr, 1);
	multiply_constant(expr, 2);
	add_variable(expr, 2);
	multiply_constant(expr, 2);
	add_variable(expr, 3);
	multiply_constant(expr, 2);
	add_variable(expr, 4);
	multiply_constant(expr, 2);

	add_sense_to_expression(expr, LOWER);
	add_rhs_to_expression(expr, 33);
	new_constraints_t con = init_new_constraint();
	add_expression_to_constraints(&con, expr);

	multiply_constant(expr, -1);
	new_constraints_t obj = init_new_constraint();
	add_expression_to_constraints(&obj, expr);


	size_t total_oracle_application = 0;
	quantum_local_search(&obj, &con, sol, 2, &total_oracle_application);
	printf("%zu ", total_oracle_application);
	print_state(sol);
	printf("\n");

	free_state(sol, 1);

    return 0;
}