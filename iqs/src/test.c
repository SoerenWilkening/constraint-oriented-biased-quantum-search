#include "Expression.h"

int main(){
    expression_t *expr = init_expression();


    for (int i = 0; i < 5; i++){
	    add_constant(expr, 3);
        add_variable(expr, i);
    }
	for (int i = 0; i < 10; i++){
		add_variable(expr, i);
	}
	expr = merge_expression(expr);
	for (int i = 0; i < expr->expr_size; i++) {
		printf("%d %lld %lld\n", expr->len_literal[i], expr->literals[3 * i], expr->literals[3 * i + 1]);
	}

    free_expression(expr);
    return 0;
}