#include "constraint.h"

int main(){
    expression_t *expr = init_expression();

    for (int i = 0; i < 5; i++){
        add_variable(expr, i);
    }
	merge_expression(expr);
	for (int i = 0; i < expr->expr_size; i++) {
		printf("%d %lld %lld\n", expr->len_literal[i], expr->literals[MAXCLAUSESIZE * i], expr->literals[MAXCLAUSESIZE * i + 1]);
	}

	new_constraints_t con = init_new_constraint();
	add_expression_to_constraints(&con, expr);
	add_expression_to_constraints(&con, expr);
//	add_expression_to_constraints(&con, expr);
	print_new_constraint(&con);

	free_constraints(&con);

    free_expression(expr);
    return 0;
}