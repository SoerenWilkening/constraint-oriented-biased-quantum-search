/*
 * test_opt_sample_cap.c -- bd 0o8: the classical Grover-round sample cap.
 *
 * CSearch_{sat,opt_sat,opt} faithfully simulate a Grover round of j iterations
 * by drawing 4j^2+1 candidate states and returning the first improver. That sim
 * is O(n*j^2) per round, which makes large-n (large-j) solves intractable.
 * ctx->opt_sample_cap > 0 bounds the count to `cap` candidates WITHOUT touching
 * the 2j+1 oracle charge (which lives in ctg, before CSearch_*). These tests pin:
 *   1. cap == 0 reproduces the exact legacy count 4j^2+1 (faithfulness, §8).
 *   2. cap > 0 bounds the realized candidate count to min(4j^2+1, cap).
 *   3. a large j where the legacy `int` expression 4*j*j+1 would overflow
 *      (j > ~23170) is handled correctly under int64 + cap (latent-UB fix).
 *
 * ctx->opt_candidates increments exactly once per generated candidate
 * (solver.c, pure instrumentation), so it is the observable candidate count.
 * We drive an already-optimal incumbent so CSearch_opt never early-returns and
 * therefore runs the full (capped) sample budget.
 */
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "Branching.h"
#include "solver_ctx.h"
#include "definitions.h"
#include "prng.h"

/* x0 + x1 + x2 <= 0, objective -(x0+x1+x2) MINIMIZE. The constraint forces the
 * UNIQUE feasible point (0,0,0) (every variable is pinned to 0 by look-ahead),
 * so the incumbent (0,0,0)/tot_profit=0 is unimprovable: CSearch_opt never
 * early-returns and runs the full (capped) sample budget -- making
 * ctx->opt_candidates a clean, deterministic readout of the realized count. */
static model_t *build_small_model(void) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    add_variable(con_expr, 0);
    add_variable(con_expr, 1);
    add_variable(con_expr, 2);
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 0);
    add_expression_to_constraints(mod->con, con_expr);

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

/* Run CSearch_opt once on the unimprovable incumbent (0,0,0)=>tot_profit 0 (the
 * unique feasible point under x0+x1+x2<=0), so the loop never early-returns and
 * opt_candidates equals the realized (capped) sample budget. Returns that count. */
static uint64_t run_opt_count(int j, int64_t cap) {
    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);
    ctx->opt_sample_cap = cap;

    int arr[3] = {0, 0, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = 0;    /* unique feasible point: no candidate can beat it */
    sol->feasible = 1;
    int samples = 0;

    int res CBQS_UNUSED = CSearch_opt(ctx, sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);
    assert_int_equal(res, 0);  /* no improvement on an optimal incumbent */

    uint64_t count = ctx->opt_candidates;
    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
    return count;
}

/* cap == 0 reproduces the exact legacy budget 4j^2+1 (bit-for-bit faithful). */
static void test_cap_zero_is_legacy_count(void **state) {
    (void)state;
    assert_int_equal((int) run_opt_count(1, 0), 4 * 1 * 1 + 1);    /* 5   */
    assert_int_equal((int) run_opt_count(5, 0), 4 * 5 * 5 + 1);    /* 101 */
    assert_int_equal((int) run_opt_count(10, 0), 4 * 10 * 10 + 1); /* 401 */
}

/* cap > 0 bounds the count to min(4j^2+1, cap). */
static void test_cap_bounds_candidate_count(void **state) {
    (void)state;
    /* cap binds: 4*10^2+1 = 401 > 50 -> exactly 50 candidates. */
    assert_int_equal((int) run_opt_count(10, 50), 50);
    /* cap does not bind: 4*5^2+1 = 101 < 1000 -> full 101. */
    assert_int_equal((int) run_opt_count(5, 1000), 101);
    /* cap == 4j^2+1 exactly -> full count (boundary). */
    assert_int_equal((int) run_opt_count(5, 101), 101);
}

/* Large j where the legacy `int` 4*j*j+1 overflows (j>~23170): under int64 +
 * cap the loop bound is correct, so a small cap yields exactly `cap` candidates
 * and the call returns quickly instead of UB (negative/wrapped bound -> 0 iters,
 * or a multi-billion-iteration hang). */
static void test_cap_large_j_no_overflow(void **state) {
    (void)state;
    /* 4*30000^2+1 = 3.6e9 overflows int32; cap=100 must bound it to 100. */
    assert_int_equal((int) run_opt_count(30000, 100), 100);
    /* Even at INT_MAX-scale j the cap binds (no overflow, no hang). */
    assert_int_equal((int) run_opt_count(2000000, 7), 7);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_cap_zero_is_legacy_count),
        cmocka_unit_test(test_cap_bounds_candidate_count),
        cmocka_unit_test(test_cap_large_j_no_overflow),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
