#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include <stdint.h>

#include "SearchLib.h"
#include "model.h"
#include "Expression.h"
#include "definitions.h"

/* ---------- incumbents tests ---------- */

static void test_init_incumbents(void **state) {
    (void)state;

    int arr[4] = {1, 0, 1, 0};
    state_t *initial = init_state(0, arr, 4);

    incumbents_t *inc = init_incumbents(4, initial);
    assert_non_null(inc);
    assert_int_equal(inc->head, 0);
    assert_true(inc->allocated >= 1);

    free_incumbents(inc);
    free_state(initial, 1);
}

static void test_incumbents_initial_state(void **state) {
    (void)state;

    int arr[4] = {1, 0, 1, 0};
    state_t *initial = init_state(0, arr, 4);

    incumbents_t *inc = init_incumbents(4, initial);

    /* The first state in incumbents should match the initial state */
    assert_int_equal(sw_tstbit(inc->states[0].vector, 0), 1);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 1), 0);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 2), 1);
    assert_int_equal(sw_tstbit(inc->states[0].vector, 3), 0);

    free_incumbents(inc);
    free_state(initial, 1);
}

/* ---------- M0d (bd 8an.1.4): oracle-budget accumulator ---------- */

/* 5-variable all-feasible knapsack (mirrors test_integration.c). Constraint
 * 2*(x0..x4) <= 33 is trivially satisfiable; objective minimizes -2*(x0..x4). */
static model_t *build_knapsack_5var(void) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < 5; i++) { add_variable(con_expr, i); multiply_constant(con_expr, 2); }
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 33);
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_expr = init_expression();
    for (int i = 0; i < 5; i++) { add_variable(obj_expr, i); multiply_constant(obj_expr, 2); }
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
    mod->depth_look_ahead = 0;
    mod->stopping_time = 1e6;   /* wall-clock stop is disabled in ctg anyway */
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);
    return mod;
}

/* Drive ctg once with budget T and a fixed seed; return the per-worker count. */
static size_t run_ctg_oracle_count(int budget, uint64_t seed) {
    model_t *mod = build_knapsack_5var();
    mod->M = budget;

    int arr[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, arr, 5);

    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = seed;
    solver_ctx_init_prng(ctx);

    incumbents_t *inc = init_incumbents(5, cur_sol);
    ctg(ctx, mod, cur_sol, NULL, inc);
    size_t count = ctx->oracle_count;

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
    return count;
}

/* The never-reset total_oracles accumulator must cap cumulative oracles at the
 * budget mod->M regardless of how often the search improves -- the exact bug the
 * old reset-on-improvement m_tot could not catch (NORTHSTAR §11). Assert: the
 * budget is reached, overshoot is at most ~one Grover round, the count is
 * deterministic under a fixed seed, and it scales with the budget. */
static void test_ctg_oracle_budget(void **state) {
    (void)state;
    const int T = 200;

    size_t c1 = run_ctg_oracle_count(T, 0xABCDEFULL);
    size_t c2 = run_ctg_oracle_count(T, 0xABCDEFULL);   /* same seed */
    size_t c_big = run_ctg_oracle_count(4 * T, 0xABCDEFULL);

    assert_true(c1 >= (size_t) T);              /* budget actually reached */
    assert_true(c1 < (size_t) (2 * T));         /* overshoot <= ~one round */
    assert_int_equal((int) c1, (int) c2);       /* deterministic under fixed seed */
    assert_true(c_big >= (size_t) (4 * T));      /* larger budget => budget reached */
    assert_true(c_big > c1);                     /* cumulative cap scales with T */
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_incumbents),
        cmocka_unit_test(test_incumbents_initial_state),
        cmocka_unit_test(test_ctg_oracle_budget),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
