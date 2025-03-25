#include "Expression.h"

int main(){
    expression_t *expr = init_expression();
    expression_t *expr2 = init_expression();

    add_constant(expr, 100);
    add_constant(expr, 1300);
    add_variable(expr2, 1);
    add_variable(expr2, 2);

    multiply_constant(expr2, 13);
    multiply_variable(expr2, 3);
    add_expression(expr, expr2);

    for (int i = 0; i < expr->expr_size; i++){
        if (expr->len_literal[i] > 0){
            printf("%lld %lld %lld\n", expr->literals[i][0], expr->literals[i][1], expr->literals[i][2]);
        }
    }

    free(expr);
    return 0;
}