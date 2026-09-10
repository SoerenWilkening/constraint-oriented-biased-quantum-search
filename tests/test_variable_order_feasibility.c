#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <stdint.h>
#include <cmocka.h>

#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "Branching.h"
#include "solver_ctx.h"
#include "definitions.h"
#include "prng.h"

/*
 * bd h8d (P1): feasibility consistency under variable reordering.
 *
 * The CSearch_* loops traverse variables in ctx->active_stats->variable_order,
 * but evaluation() used to key clause-closure on the NATURAL variable index
 * ("var < item" / "var > item"). With a non-identity order and a multi-variable
 * (quadratic) clause, the closure charge is applied at the wrong step (or never),
 * so the potentials accounting accepts eval_constraints-violating states as
 * feasible (the order_pii_desc.INVALID failure: claimed +83% vs B_I).
 *
 * Property under test (CLAUDE.md SS2.1, crash-worthy): ANY incumbent accepted by
 * a CSearch_* under ANY variable order must pass eval_constraints, and the
 * final objective can never beat the brute-force optimum.
 *
 * These tests use quadratic clauses (multiply_variable) -- the existing
 * test_csearch_ordering.c only builds linear clauses, where closure is trivial
 * and the bug cannot manifest.
 */

/* ------------------------------------------------------------------ */
/* Model A: minimize -(x0+x1) s.t. x0*x1 <= 0, n=2.                    */
/* Feasible: (0,0)=0, (1,0)=(0,1)=-1. (1,1)=-2 is INFEASIBLE.          */
/* Brute-force optimum: -1.                                            */
/* ------------------------------------------------------------------ */
static model_t *build_quadratic_model_2var(void) {
    model_t *mod = init_model();

    /* Constraint: x0*x1 <= 0 (single quadratic clause) */
    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    multiply_variable(con_expr, 1);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 0);
    add_expression_to_constraints(mod->con, con_expr);

    /* Objective: -x0 - x1 (minimized internally) */
    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    add_variable(obj_expr, 1);
    multiply_constant(obj_expr, -1);
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

    preprocessing(2, mod->con);
    preprocessing(2, mod->obj);

    int arr[2] = {0, 0};
    mod->initial_state = init_state(0, arr, 2);
    mod->initial_state->tot_profit = INT64_MAX;
    mod->global_opt = init_state(0, arr, 2);
    mod->global_opt->tot_profit = INT64_MAX;

    mod->n = 2;
    mod->M = 10;
    mod->depth_look_ahead = 0;
    mod->stopping_time = 100;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);
    return mod;
}

/* ------------------------------------------------------------------ */
/* Model B (n=3, mixed signs): minimize -(x0+x1+x2)                    */
/*   s.t.  x0*x2 + x1*x2 - x0*x1 <= 0                                  */
/* LHS: (0,0,0)=0 (1,0,0)=0 (0,1,0)=0 (0,0,1)=0 (1,1,0)=-1             */
/*      (1,0,1)=1 (0,1,1)=1 (1,1,1)=1                                  */
/* Feasible objectives: 0,-1,-1,-1,-2 -> brute optimum -2 at (1,1,0).  */
/* (1,1,1)=-3 is INFEASIBLE.                                           */
/* ------------------------------------------------------------------ */
static model_t *build_quadratic_model_3var(void) {
    model_t *mod = init_model();

    /* multiply_variable applies to ALL terms, so build each product term in
     * its own expression and merge with add_expression. */
    expression_t *t1 = init_expression();
    add_variable(t1, 0);
    multiply_variable(t1, 2);              /* +x0*x2 */
    expression_t *t2 = init_expression();
    add_variable(t2, 1);
    multiply_variable(t2, 2);              /* +x1*x2 */
    expression_t *t3 = init_expression();
    add_variable(t3, 0);
    multiply_variable(t3, 1);
    multiply_constant(t3, -1);             /* -x0*x1 */

    /* Merge terms into one constraint expression */
    expression_t *con_all = init_expression();
    add_expression(con_all, t1);
    add_expression(con_all, t2);
    add_expression(con_all, t3);
    add_sense_to_expression(con_all, LOWER);
    add_rhs_to_expression(con_all, 0);
    add_expression_to_constraints(mod->con, con_all);

    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    add_variable(obj_expr, 1);
    add_variable(obj_expr, 2);
    multiply_constant(obj_expr, -1);       /* minimize -(x0+x1+x2) */
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

    free_expression(t1);
    free_expression(t2);
    free_expression(t3);
    free_expression(con_all);
    free_expression(obj_expr);
    return mod;
}

/*
 * Drive CSearch_opt repeatedly from a feasible start and assert the SS2.1
 * property after every accepted improvement. `brute_opt` is the exhaustive
 * minimum over genuinely feasible states: the search may fail to reach it,
 * but can NEVER beat it.
 */
static void drive_opt_and_assert_feasible(model_t *mod, solver_ctx_t *ctx,
                                          int n, int64_t brute_opt,
                                          int depth_look_ahead) {
    int arr[8] = {0};
    state_t *sol = init_state(0, arr, n);
    sol->tot_profit = 0;     /* objective of all-zeros start */
    sol->feasible = 1;

    int samples = 0;
    int improved = 1;
    while (improved) {
        improved = 0;
        for (int iter = 0; iter < 400 && !improved; iter++) {
            improved = CSearch_opt(ctx, sol, 3, mod->con, mod->obj,
                                   depth_look_ahead, 1, NULL, &samples);
        }
        if (improved) {
            /* Accepted incumbent must be genuinely feasible (bd h8d). */
            assert_true(eval_constraints(mod->con, sol, n));
            /* And can never beat the brute-force optimum. */
            assert_true(sol->tot_profit >= brute_opt);
        }
    }
    assert_int_equal(sol->tot_profit, brute_opt);

    free_state(sol, 1);
}

/* The h8d repro: order [1,0] on Model A. Buggy closure never charges the
 * x0*x1 clause, accepts (1,1) at -2 < brute optimum -1. */
static void test_reordered_quadratic_never_accepts_infeasible(void **state) {
    (void)state;
    model_t *mod = build_quadratic_model_2var();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);

    double priorities[] = {1.0, 2.0};   /* descending argsort -> order [1,0] */
    solver_ctx_set_variable_order(ctx, priorities, 2);
    assert_int_equal(ctx->branching_stats.variable_order[0], 1);
    assert_int_equal(ctx->branching_stats.variable_order[1], 0);

    drive_opt_and_assert_feasible(mod, ctx, 2, -1, 0);

    solver_ctx_free(ctx);
    free_model(mod);
}

/* Identity order on Model A must already be correct (baseline pin). */
static void test_identity_quadratic_stays_feasible(void **state) {
    (void)state;
    model_t *mod = build_quadratic_model_2var();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);
    /* no order set: NULL = natural traversal */

    drive_opt_and_assert_feasible(mod, ctx, 2, -1, 0);

    solver_ctx_free(ctx);
    free_model(mod);
}

/* Mixed-sign quadratic clauses (positive AND negative factors) under several
 * non-identity orders: the NEGATIVE-arm charging must also be prefix-consistent
 * with the traversal order. */
static void test_reordered_mixed_sign_quadratic(void **state) {
    (void)state;
    /* order via priorities: {1,2,3}->[2,1,0], {2,3,1}->[1,0,2], {3,1,2}->[0,2,1] */
    double priority_sets[3][3] = {
        {1.0, 2.0, 3.0},
        {2.0, 3.0, 1.0},
        {3.0, 1.0, 2.0},
    };
    for (int p = 0; p < 3; p++) {
        model_t *mod = build_quadratic_model_3var();
        solver_ctx_t *ctx = solver_ctx_create();
        assert_non_null(ctx);
        ctx->seed = 1234 + p;
        solver_ctx_init_prng(ctx);
        solver_ctx_set_variable_order(ctx, priority_sets[p], 3);

        drive_opt_and_assert_feasible(mod, ctx, 3, -2, 0);

        solver_ctx_free(ctx);
        free_model(mod);
    }
}

/* depth_look_ahead > 0 exercises the look_ahead_correct recursion, which used
 * to walk natural successors (index+1) regardless of the traversal order. */
static void test_reordered_quadratic_with_lookahead_depth(void **state) {
    (void)state;
    model_t *mod = build_quadratic_model_3var();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 7;
    solver_ctx_init_prng(ctx);

    double priorities[] = {1.0, 2.0, 3.0};   /* order [2,1,0] */
    solver_ctx_set_variable_order(ctx, priorities, 3);

    drive_opt_and_assert_feasible(mod, ctx, 3, -2, 2);

    solver_ctx_free(ctx);
    free_model(mod);
}

/* CSearch_sat under reordering: potentials-driven accounting feeds the sat
 * objective too; property is the weaker "runs + final state evaluable", plus
 * the (1,1) state must never be reported as satisfying the quadratic con. */
static void test_reordered_sat_phase_consistency(void **state) {
    (void)state;
    model_t *mod = build_quadratic_model_2var();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 99;
    solver_ctx_init_prng(ctx);

    double priorities[] = {1.0, 2.0};
    solver_ctx_set_variable_order(ctx, priorities, 2);
    /* sat phase uses the sat stats; setter writes all three phases */
    ctx->active_stats = &ctx->branching_stats_sat;

    int arr[2] = {0, 0};
    state_t *sol = init_state(0, arr, 2);
    sol->tot_profit = 0;
    int samples = 0;
    for (int iter = 0; iter < 50; iter++) {
        (void)CSearch_sat(ctx, sol, 2, mod->con, mod->obj, 0, 1, NULL, &samples);
    }
    /* num_satisfied_constrains ground truth: tot_profit == -1 means the
     * constraint is reported satisfied; the stored vector must agree. */
    if (sol->tot_profit == -1) {
        assert_true(eval_constraints(mod->con, sol, 2));
    }

    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_identity_quadratic_stays_feasible),
        cmocka_unit_test(test_reordered_quadratic_never_accepts_infeasible),
        cmocka_unit_test(test_reordered_mixed_sign_quadratic),
        cmocka_unit_test(test_reordered_quadratic_with_lookahead_depth),
        cmocka_unit_test(test_reordered_sat_phase_consistency),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
