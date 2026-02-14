#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "Branching.h"
#include "definitions.h"

/*
 * Helper: build a small model with 3 variables, 1 constraint x0+x1+x2 <= 2,
 * objective -(x0+x1+x2).
 */
static model_t *build_small_model(void) {
    model_t *mod = init_model();

    /* Build constraint: x0 + x1 + x2 <= 2 */
    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    add_variable(con_expr, 1);
    add_variable(con_expr, 2);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 2);
    add_expression_to_constraints(mod->con, con_expr);

    /* Build objective: -(x0 + x1 + x2) -- minimize negative sum */
    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    multiply_constant(obj_expr, -1);
    add_variable(obj_expr, 1);
    multiply_constant(obj_expr, -1);
    add_variable(obj_expr, 2);
    multiply_constant(obj_expr, -1);
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

    /* Preprocessing for sampling */
    preprocessing(3, mod->con);
    preprocessing(3, mod->obj);

    /* Allocate states */
    int arr[3] = {0, 0, 0};
    mod->initial_state = init_state(0, arr, 3);
    mod->initial_state->tot_profit = INT64_MAX;
    mod->global_opt = init_state(0, arr, 3);
    mod->global_opt->tot_profit = INT64_MAX;

    mod->n = 3;
    mod->M = 10;
    mod->depth_look_ahead = 0;
    mod->stopping_time = 100;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);

    return mod;
}

/* test_initial_state_preparation: smoke test -- should not crash and should
 * produce a state with the correct number of bits */
static void test_initial_state_preparation(void **state) {
    (void)state;
    srand(42);

    model_t *mod = build_small_model();

    int result CBQS_UNUSED = initial_state_preparation(mod);

    /* The state should still have 3 bits */
    assert_int_equal(mod->initial_state->vector.bits, 3);

    /* global_opt should have been populated */
    assert_int_equal(mod->global_opt->vector.bits, 3);

    /* The function should have set feasible flag */
    /* (either feasible or not -- just verify it ran) */
    assert_true(mod->initial_state->feasible == 0 || mod->initial_state->feasible == 1);

    free_model(mod);
}

/* test_update_potentials: verify potentials are updated correctly */
static void test_update_potentials(void **state) {
    (void)state;

    /* Build a single constraint: x0 + x1 <= 3 */
    expression_t *expr = init_expression();
    add_variable(expr, 0);
    add_variable(expr, 1);
    add_sense_to_expression(expr, LOWER);
    add_rhs_to_expression(expr, 3);

    new_constraints_t con = init_new_constraint();
    add_expression_to_constraints(&con, expr);
    preprocessing(2, &con);

    /* Potentials start at rhs */
    int64_t potentials[1];
    potentials[0] = con.rhs[0]; /* = 3 */

    /* ret_total simulates one unit consumed */
    int64_t ret_total[1] = {1};

    /* PLAIN direction is -1, so potentials[0] += -1 * 1 = potentials - 1 */
    int result = update_potentials(&con, potentials, PLAIN, ret_total);
    assert_int_equal(result, 1);
    assert_int_equal(potentials[0], 2); /* 3 + (-1)*1 = 2 */

    /* INVERSE direction is 1, so potentials[0] += 1 * 1 = potentials + 1 */
    result = update_potentials(&con, potentials, INVERSE, ret_total);
    assert_int_equal(result, 1);
    assert_int_equal(potentials[0], 3); /* 2 + 1*1 = 3, back to original */

    free_expression(expr);
    free_constraints(&con);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_initial_state_preparation),
        cmocka_unit_test(test_update_potentials),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
