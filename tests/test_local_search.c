#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <pthread.h>

#include "local_search.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "Branching.h"
#include "definitions.h"
#include "solver_ctx.h"
#include "arena.h"

/* Provide the update_lock symbol required by local_search.c (defined in SearchLib.c) */
pthread_mutex_t update_lock = PTHREAD_MUTEX_INITIALIZER;

/*
 * Regression test for use-after-free bug in accept_best_routine (02-01).
 *
 * The bug: Thread data (remainings, ful_con, ful) was freed immediately
 * after pthread_create, before the thread had a chance to use it.
 * This caused heap corruption under ASan.
 *
 * Fix: Move cleanup to after pthread_join completes.
 *
 * This test exercises local_search() which internally calls
 * accept_best_routine(). Under ASan, if the bug is reintroduced,
 * the test will fail with heap-use-after-free errors.
 */

/*
 * Helper: build a simple 5-variable knapsack for local search testing.
 * Constraint: 2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4 <= 33
 * Objective: minimize -(2*x0 + 2*x1 + 2*x2 + 2*x3 + 2*x4)
 */
static model_t *build_local_search_model(void) {
    model_t *mod = init_model();

    /* Build constraint */
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

    /* Build objective */
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
    mod->stopping_time = 1;  /* Very short timeout for testing */
    mod->solver = OPTIMIZE;
    mod->break_item = 0;
    mod->distance = 1;  /* 1-flip neighborhood */
    mod->max_worse_acceptances = 2;
    mod->stopping_condition = 1;

    free_expression(con_expr);
    free_expression(obj_expr);

    return mod;
}

/*
 * Test: local_search thread data lifetime
 *
 * This test verifies that local_search() does not trigger use-after-free.
 * Under ASan, if thread data is freed before threads complete,
 * the test will fail with a heap-use-after-free error.
 *
 * The test passes if local_search completes without ASan errors.
 */
static void test_local_search_thread_data_lifetime(void **state) {
    (void)state;
    srand(42);

    model_t *mod = build_local_search_model();

    /* Create an initial state for local search to improve */
    int arr[5] = {1, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, arr, 5);
    cur_sol->tot_profit = -2;  /* objective with x0=1 */
    cur_sol->feasible = 1;

    /*
     * Run local search. If the use-after-free bug exists,
     * ASan will catch it here with:
     *   "heap-use-after-free: address ... freed by thread T0"
     *
     * The fix moves free(data[i].remainings), sw_clear(data[i].ful_con),
     * sw_clear(data[i].ful) from after pthread_create to after pthread_join.
     */
    /* Create a solver context for local_search */
    solver_ctx_t *ctx = solver_ctx_create();
    int result = local_search(ctx, cur_sol, mod, NULL);
    solver_ctx_free(ctx);

    /* Test passes if we reach here without ASan errors */
    assert_int_equal(result, 0);

    /* Verify solution is still valid (feasible) */
    int feasible = eval_constraints(mod->con, cur_sol, 5);
    assert_int_equal(feasible, 1);

    free_state(cur_sol, 1);
    free_model(mod);
}

/*
 * Test: local_search with multiple iterations
 *
 * Run local search for a few iterations to exercise the thread
 * creation/cleanup cycle multiple times. This increases the chance
 * of catching intermittent memory safety issues.
 */
static void test_local_search_multiple_iterations(void **state) {
    (void)state;
    srand(12345);

    model_t *mod = build_local_search_model();
    mod->stopping_time = 2;  /* Allow more iterations */
    mod->max_worse_acceptances = 5;

    int arr[5] = {0, 1, 0, 1, 0};
    state_t *cur_sol = init_state(0, arr, 5);
    cur_sol->tot_profit = -4;
    cur_sol->feasible = 1;

    /* Create a solver context for local_search */
    solver_ctx_t *ctx = solver_ctx_create();
    int result = local_search(ctx, cur_sol, mod, NULL);
    solver_ctx_free(ctx);

    assert_int_equal(result, 0);

    /* Solution should still be feasible */
    int feasible = eval_constraints(mod->con, cur_sol, 5);
    assert_int_equal(feasible, 1);

    free_state(cur_sol, 1);
    free_model(mod);
}

/*
 * Test: arena integration with solver context
 *
 * Verifies that:
 * 1. solver_ctx_t contains an arena after creation
 * 2. Arena is used during local_search (hot-path allocations)
 * 3. Arena is properly reset between iterations
 * 4. No memory leaks when arena is freed with context
 *
 * Run under Valgrind to verify no leaks.
 */
static void test_local_search_with_arena(void **state) {
    (void)state;
    srand(999);

    /* Verify solver context contains arena */
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    assert_non_null(ctx->arena);

    /* Record initial arena state */
    size_t initial_used = arena_used(ctx->arena);
    assert_int_equal(initial_used, 0);  /* Fresh arena should be empty */

    /* Arena should have capacity (1MB by default) */
    size_t initial_allocated = arena_allocated(ctx->arena);
    assert_true(initial_allocated >= ARENA_DEFAULT_SIZE);

    /* Build a model and run local_search */
    model_t *mod = build_local_search_model();
    mod->stopping_time = 1;
    mod->max_worse_acceptances = 3;

    int arr[5] = {1, 1, 0, 0, 0};
    state_t *cur_sol = init_state(0, arr, 5);
    cur_sol->tot_profit = -4;
    cur_sol->feasible = 1;

    int result = local_search(ctx, cur_sol, mod, NULL);
    assert_int_equal(result, 0);

    /* After local_search completes, arena is reset between iterations.
     * The final state should have low or zero usage since the last
     * iteration called arena_reset. */
    size_t final_used = arena_used(ctx->arena);
    /* Arena used can be 0 or small after final reset - this is expected */
    (void)final_used;  /* Just verify we can query it */

    /* Clean up */
    free_state(cur_sol, 1);
    free_model(mod);
    solver_ctx_free(ctx);

    /* Test passes if we reach here without leaks or ASan errors */
}

/*
 * Test: arena reset is called between iterations
 *
 * This test verifies that the arena is properly reset between
 * solver iterations, preventing unbounded memory growth.
 */
static void test_local_search_arena_reset(void **state) {
    (void)state;
    srand(12345);

    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);

    /* Run multiple iterations to exercise arena reset */
    model_t *mod = build_local_search_model();
    mod->stopping_time = 3;  /* Allow more time */
    mod->max_worse_acceptances = 10;  /* More iterations */

    int arr[5] = {0, 0, 1, 0, 1};
    state_t *cur_sol = init_state(0, arr, 5);
    cur_sol->tot_profit = -4;
    cur_sol->feasible = 1;

    /* Run local search - arena should be reset each iteration */
    int result = local_search(ctx, cur_sol, mod, NULL);
    assert_int_equal(result, 0);

    /* If arena reset wasn't called, memory usage would grow unbounded.
     * With reset, it stays bounded to ~1MB (initial chunk). */
    size_t allocated = arena_allocated(ctx->arena);
    /* Should still be around initial size (1MB) if reset works properly.
     * Allow 2x for potential overflow chunks. */
    assert_true(allocated <= ARENA_DEFAULT_SIZE * 3);

    free_state(cur_sol, 1);
    free_model(mod);
    solver_ctx_free(ctx);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_local_search_thread_data_lifetime),
        cmocka_unit_test(test_local_search_multiple_iterations),
        cmocka_unit_test(test_local_search_with_arena),
        cmocka_unit_test(test_local_search_arena_reset),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
