/*
 * test_deadline_interrupt.c -- bd 0o8.3: mid-round wall-clock deadline interrupt.
 *
 * The opt-in wall cap (mod->stopping_time) is checked only BETWEEN rounds in ctg,
 * so a single large-j Grover round runs uninterrupted (the 0o8 wall: a 600s cap
 * overshot to 19min at n=3000). bd 0o8.3 adds a per-worker ctx->deadline_ns that
 * each CSearch_* sample loop checks every CBQS_DEADLINE_CHUNK candidates, breaking
 * the round once the deadline passes. These tests pin the mechanism STRUCTURALLY
 * (no wall-clock timing -> not flaky, CLAUDE.md §2.2):
 *   1. deadline_ns == 0 (OFF, the strict no-op): the round runs the FULL 4j^2+1
 *      candidates -- bit-for-bit identical to pre-0o8.3 (every faithful/exact run).
 *   2. deadline_ns far in the FUTURE (armed but never fires): also full count --
 *      the clock read is side-effect-free on PRNG/oracle state, so the outcome is
 *      identical to OFF (this is why exact small-n determinism survives even though
 *      the C harness arms stopping_time = 1e6).
 *   3. deadline_ns in the PAST: the l==0 check fires immediately -> the round draws
 *      0 candidates (<< Leff; break index 0 is a multiple of CBQS_DEADLINE_CHUNK)
 *      and returns cleanly (no crash, no improvement) -- the truncation mechanism.
 *
 * ctx->opt_candidates increments exactly once per generated candidate
 * (solver.c:502, pure instrumentation) and *samples += l at exit, so both are
 * deterministic readouts of how many candidates the (possibly truncated) round drew.
 * The fixture mirrors test_opt_sample_cap.c: an unimprovable incumbent so CSearch_opt
 * never early-returns and (absent a deadline) runs the full sample budget.
 */
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

/* x0 + x1 + x2 <= 0, objective -(x0+x1+x2) MINIMIZE: the constraint pins the
 * unique feasible point (0,0,0), so the incumbent tot_profit=0 is unimprovable
 * and CSearch_opt runs the full (unless deadline-truncated) sample budget. */
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

/* Drive CSearch_opt once with j and a pre-armed ctx->deadline_ns; return the
 * realized candidate count (ctx->opt_candidates) and the *samples out-param. */
static uint64_t run_opt_with_deadline(int j, uint64_t deadline_ns, int *samples_out) {
    model_t *mod = build_small_model();
    solver_ctx_t *ctx = solver_ctx_create();
    assert_non_null(ctx);
    ctx->seed = 42;
    solver_ctx_init_prng(ctx);
    ctx->opt_sample_cap = 0;           /* exact: Leff == 4j^2+1 */
    ctx->deadline_ns = deadline_ns;    /* 0 OFF, past truncates, future inert */

    int arr[3] = {0, 0, 0};
    state_t *sol = init_state(0, arr, 3);
    sol->tot_profit = 0;
    sol->feasible = 1;
    int samples = 0;

    int res CBQS_UNUSED = CSearch_opt(ctx, sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);
    assert_int_equal(res, 0);          /* unimprovable incumbent -> no improvement */

    uint64_t count = ctx->opt_candidates;
    if (samples_out) *samples_out = samples;
    free_state(sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
    return count;
}

/* (1) OFF (deadline_ns == 0): full 4j^2+1, the strict no-op path. */
static void test_deadline_off_runs_full(void **state) {
    (void)state;
    int s = -1;
    assert_int_equal((int) run_opt_with_deadline(10, 0, &s), 4 * 10 * 10 + 1); /* 401 */
    assert_int_equal(s, 4 * 10 * 10 + 1);
}

/* (2) Armed but far in the FUTURE: never fires -> full count (outcome inert,
 * the clock read has no PRNG/oracle side effect). */
static void test_deadline_future_runs_full(void **state) {
    (void)state;
    int s = -1;
    assert_int_equal((int) run_opt_with_deadline(10, UINT64_MAX, &s), 4 * 10 * 10 + 1);
    assert_int_equal(s, 4 * 10 * 10 + 1);
}

/* (3) Deadline in the PAST: the l==0 check truncates the round to 0 candidates
 * (<< Leff = 4*50^2+1 = 10001), break index 0 is a multiple of CBQS_DEADLINE_CHUNK,
 * and the round returns cleanly. */
static void test_deadline_past_truncates(void **state) {
    (void)state;
    int s = -1;
    uint64_t Leff = (uint64_t) 4 * 50 * 50 + 1;          /* 10001 */
    uint64_t drawn = run_opt_with_deadline(50, 1u, &s);  /* deadline_ns = 1 ns (past) */
    assert_true(drawn < Leff);
    assert_int_equal((int) drawn, 0);                    /* broke at l == 0 */
    assert_int_equal(s, 0);
    assert_int_equal((int) (drawn % CBQS_DEADLINE_CHUNK), 0);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_deadline_off_runs_full),
        cmocka_unit_test(test_deadline_future_runs_full),
        cmocka_unit_test(test_deadline_past_truncates),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
