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
 * Helper: build a 5-variable knapsack problem (same as test.c).
 * Constraint: 2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4 <= 33
 * Objective: minimize -(2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4)
 * Known optimal: all variables = 1, objective = -10
 * Constraint is trivially satisfiable (all items fit: 2*5 = 10 <= 33).
 */
static model_t *build_knapsack_5var(void) {
    model_t *mod = init_model();

    /* Build constraint: 2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4 <= 33 */
    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    multiply_constant(con_expr, 2);
    add_variable(con_expr, 1);
    multiply_constant(con_expr, 2);
    add_variable(con_expr, 2);
    multiply_constant(con_expr, 2);
    add_variable(con_expr, 3);
    multiply_constant(con_expr, 2);
    add_variable(con_expr, 4);
    multiply_constant(con_expr, 2);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 33);
    add_expression_to_constraints(mod->con, con_expr);

    /* Build objective: -(2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4) */
    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    multiply_constant(obj_expr, 2);
    add_variable(obj_expr, 1);
    multiply_constant(obj_expr, 2);
    add_variable(obj_expr, 2);
    multiply_constant(obj_expr, 2);
    add_variable(obj_expr, 3);
    multiply_constant(obj_expr, 2);
    add_variable(obj_expr, 4);
    multiply_constant(obj_expr, 2);
    multiply_constant(obj_expr, -1);
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

    preprocessing(5, mod->con);
    preprocessing(5, mod->obj);

    int arr[5] = {0, 0, 0, 0, 0};
    mod->initial_state = init_state(0, arr, 5);
    mod->initial_state->tot_profit = INT64_MAX;
    mod->global_opt = init_state(0, arr, 5);
    mod->global_opt->tot_profit = INT64_MAX;

    mod->n = 5;
    mod->M = 10;
    mod->depth_look_ahead = 0;
    mod->stopping_time = 100;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);

    return mod;
}

/*
 * Helper: build a tighter 3-variable knapsack.
 * Constraint: 3*x0 + 3*x1 + 3*x2 <= 6 (at most 2 items)
 * Objective: minimize -(3*x0 + 3*x1 + 3*x2)
 */
static model_t *build_knapsack_3var_tight(void) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    multiply_constant(con_expr, 3);
    add_variable(con_expr, 1);
    multiply_constant(con_expr, 3);
    add_variable(con_expr, 2);
    multiply_constant(con_expr, 3);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 6);
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    multiply_constant(obj_expr, 3);
    add_variable(obj_expr, 1);
    multiply_constant(obj_expr, 3);
    add_variable(obj_expr, 2);
    multiply_constant(obj_expr, 3);
    multiply_constant(obj_expr, -1);
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

    preprocessing(3, mod->con);
    preprocessing(3, mod->obj);

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

/*
 * test_knapsack_feasibility: Solve the easy 5-variable knapsack and verify
 * the returned solution satisfies the constraint.
 * Per CONTEXT.md: "Integration tests verify feasibility only -- do not check
 * objective quality since solver is heuristic."
 */
static void test_knapsack_feasibility(void **state) {
    (void)state;
    srand(42);

    model_t *mod = build_knapsack_5var();

    initial_state_preparation(mod);

    /* Verify the solution satisfies all constraints */
    int feasible = eval_constraints(mod->con, mod->initial_state, 5);
    assert_int_equal(feasible, 1);

    /* Also check via the model's own feasibility flag */
    assert_int_equal(mod->initial_state->feasible, 1);

    free_model(mod);
}

/*
 * test_constraint_satisfaction_after_solve: Solve a tighter knapsack
 * (3*x0 + 3*x1 + 3*x2 <= 6, at most 2 items) and verify the solution
 * satisfies the constraint.
 */
static void test_constraint_satisfaction_after_solve(void **state) {
    (void)state;
    srand(42);

    model_t *mod = build_knapsack_3var_tight();

    initial_state_preparation(mod);

    /* Verify the solution satisfies the constraint */
    int feasible = eval_constraints(mod->con, mod->initial_state, 3);
    assert_int_equal(feasible, 1);

    /* Check feasibility flag set by the solver */
    assert_int_equal(mod->initial_state->feasible, 1);

    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_knapsack_feasibility),
        cmocka_unit_test(test_constraint_satisfaction_after_solve),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
