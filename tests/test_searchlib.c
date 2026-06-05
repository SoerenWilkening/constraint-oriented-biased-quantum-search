#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include <stdint.h>

#include "SearchLib.h"
#include "model.h"
#include "Expression.h"
#include "definitions.h"
#include "solver.h"       /* CSearch_opt (M0g diagnostics test) */
#include "solver_ctx.h"   /* solver_ctx_t opt_* diagnostic counters */

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

/* ---------- M0f (bd 8an.1.6): opt_switch_oracles feasibility gate ---------- */

/* Covering instance whose all-zeros start is INFEASIBLE: sum x >= 2 encoded as
 * the negated-LOWER form (factors -1, rhs n-2). eval_constraint computes
 * total = sum(1 - x_i) = n - sum x and rejects total > rhs, i.e. sum x < 2.
 * Objective maximizes sum x (minimize -sum x). This is the only C path that can
 * reach the opt_sat->opt switch from an infeasible start, so it exercises the
 * §5 feasibility gate (the switch must NOT fire CSearch_opt while infeasible). */
static model_t *build_covering_5var(void) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < 5; i++) { add_variable(con_expr, i); }
    multiply_constant(con_expr, -1);            /* factors -1 */
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 3);         /* n - 2 = 3  =>  requires sum x >= 2 */
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_expr = init_expression();
    for (int i = 0; i < 5; i++) { add_variable(obj_expr, i); }
    multiply_constant(obj_expr, -1);            /* minimize -sum x = maximize sum x */
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
    mod->stopping_time = 1e6;
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);
    return mod;
}

/* With an infeasible all-zeros start and opt_switch_oracles set BELOW the cost
 * of reaching feasibility, the switch must not run CSearch_opt on an infeasible
 * point: ctg must reach feasibility in opt_sat first, then switch. The
 * unconditional fail-loud guard in ctg would abort() if the switch ever fired
 * infeasible (so this test, which completes normally, exercises that guard in
 * the asserts-live CI build). Assert the returned solution is genuinely
 * feasible and improves on the all-zeros start. */
static void test_opt_switch_feasibility_gate(void **state) {
    (void)state;
    model_t *mod = build_covering_5var();
    mod->M = 2000;
    mod->opt_switch_oracles = 1;   /* threshold met on round 1, BEFORE feasibility */

    int zeros[5] = {0, 0, 0, 0, 0};
    state_t *probe = init_state(0, zeros, 5);
    /* Precondition: the covering encoding really makes all-zeros infeasible and
     * a sum>=2 point feasible -- otherwise the test would not exercise the gate. */
    assert_int_equal(eval_constraints(mod->con, probe, 5), 0);
    int two[5] = {1, 1, 0, 0, 0};
    state_t *feas = init_state(0, two, 5);
    assert_int_equal(eval_constraints(mod->con, feas, 5), 1);
    free_state(probe, 1);
    free_state(feas, 1);

    state_t *cur_sol = init_state(0, zeros, 5);
    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = 0x5151ULL;
    solver_ctx_init_prng(ctx);
    incumbents_t *inc = init_incumbents(5, cur_sol);

    int feasible = ctg(ctx, mod, cur_sol, NULL, inc);

    /* ctg completed (no abort): the switch never fired infeasible. The final
     * solution is genuinely feasible (sum x >= 2). */
    assert_true(feasible);
    assert_int_equal(eval_constraints(mod->con, cur_sol, 5), 1);

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/* ---------- M0g (bd 8an.1.7): opt-phase branching diagnostics ---------- */

/* All-decisions-FREE model: constraint sum x <= 1000 is always satisfiable both
 * ways (n<=5 => max sum 5), so CSearch_opt's look-ahead leaves BOTH assignments
 * feasible for every variable => every decision is a "free" decision and no
 * variable is ever forced. The objective is internal-minimize sum x, so all-zeros
 * is already optimal and NO candidate ever improves => CSearch_opt never returns
 * early and runs its full 4j^2+1 candidate loop. Both properties make the
 * diagnostic counters exactly hand-computable. */
static model_t *build_freeall_model(int n) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(con_expr, i); }
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 1000);      /* loose: always feasible both ways */
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(obj_expr, i); }  /* +1 coeffs */
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);          /* min sum x */

    preprocessing(n, mod->con);
    preprocessing(n, mod->obj);

    int *arr = calloc((size_t) n, sizeof(int));
    mod->initial_state = init_state(0, arr, n);
    mod->initial_state->tot_profit = INT64_MAX;
    mod->global_opt = init_state(0, arr, n);
    mod->global_opt->tot_profit = INT64_MAX;
    free(arr);

    mod->n = n;
    mod->depth_look_ahead = 0;
    mod->stopping_time = 1e6;
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);
    return mod;
}

/* Drive ONE CSearch_opt call on the all-free model at the given bias and return
 * the per-worker diagnostic counters via out-params. */
static void run_one_csearch_opt(int n, int j, double bias, uint64_t seed,
                                uint64_t *cand, uint64_t *flip_sum,
                                uint64_t *flip_sumsq, uint64_t *free_sum) {
    model_t *mod = build_freeall_model(n);

    int *arr = calloc((size_t) n, sizeof(int));
    state_t *cur_sol = init_state(0, arr, n);   /* feasible all-zeros incumbent */
    cur_sol->tot_profit = 0;                    /* internal-optimal => no accept */
    cur_sol->feasible = 1;
    free(arr);

    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = seed;
    solver_ctx_init_prng(ctx);
    ctx->active_stats = &ctx->branching_stats_opt;   /* exercise the opt phase */
    solver_ctx_set_bias(ctx, bias);

    int samples = 0;
    int improved CBQS_UNUSED =
        CSearch_opt(ctx, cur_sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);

    *cand = ctx->opt_candidates;
    *flip_sum = ctx->opt_flip_sum;
    *flip_sumsq = ctx->opt_flip_sumsq;
    *free_sum = ctx->opt_free_sum;

    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/* EXACT, RNG-free pins. With all decisions free and no accept, ONE CSearch_opt
 * call generates exactly 4j^2+1 candidates, each with all n decisions free;
 * with a huge bias (flip prob 1/(bias+2) ~ 1e-9) no free variable flips.
 * Catches: accept-only counting (would give ~0/1 candidates), double-counting
 * (2x), wrong-phase accumulation (0), and a NumChanges<->NumFree swap (free_sum
 * would no longer equal candidates*n). The candidates and free_sum equalities do
 * NOT depend on the PRNG (free/forced classification is look-ahead-only). */
static void test_csearch_opt_diagnostics_exact(void **state) {
    (void)state;
    const int n = 5, j = 2;
    const uint64_t expect_cand = (uint64_t)(4 * j * j + 1);   /* 17 */
    uint64_t cand, flip_sum, flip_sumsq, free_sum;
    run_one_csearch_opt(n, j, 1e9, 0xD1A6ULL, &cand, &flip_sum, &flip_sumsq, &free_sum);

    assert_int_equal((int) cand, (int) expect_cand);               /* every candidate counted once */
    assert_int_equal((int) free_sum, (int)(expect_cand * (uint64_t) n)); /* all n free per candidate */
    assert_int_equal((int) flip_sum, 0);                           /* huge bias => no flips */
    assert_int_equal((int) flip_sumsq, 0);
}

/* Non-zero radius pins (catch flip-sum / sumsq arithmetic). With a near--1 bias
 * (flip prob ~1) most free variables flip, so the realized radius is large but
 * the count is still acceptance-unbiased (no accept => full loop). Inequalities,
 * not exact values, because the realized flips are PRNG-driven; they still pin:
 *  - candidates / free_sum exactly (RNG-free),
 *  - flip_sum substantial and bounded by candidates*n,
 *  - sumsq >= sum (true for nonneg integer NumChanges) AND the squares identity
 *    sumsq*candidates >= sum^2 (a build that set sumsq=sum would FAIL this here,
 *    since the mean realized radius > 1 makes candidates < flip_sum). */
static void test_csearch_opt_diagnostics_flips(void **state) {
    (void)state;
    const int n = 5, j = 2;
    const uint64_t expect_cand = (uint64_t)(4 * j * j + 1);   /* 17 */
    uint64_t cand, flip_sum, flip_sumsq, free_sum;
    run_one_csearch_opt(n, j, -0.9, 0xF11D5ULL, &cand, &flip_sum, &flip_sumsq, &free_sum);

    assert_int_equal((int) cand, (int) expect_cand);
    assert_int_equal((int) free_sum, (int)(expect_cand * (uint64_t) n));
    assert_true(flip_sum > 0);
    assert_true(flip_sum <= expect_cand * (uint64_t) n);             /* radius <= n per candidate */
    assert_true(flip_sum >= expect_cand * 3);                        /* flip prob 0.91 => mean ~4.5/candidate */
    assert_true(flip_sumsq >= flip_sum);                             /* x^2 >= x for nonneg ints */
    assert_true(flip_sumsq <= expect_cand * (uint64_t)(n * n));       /* NumChanges^2 <= n^2 */
    assert_true(flip_sumsq * cand >= flip_sum * flip_sum);            /* squares identity; sumsq!=sum guard */
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_incumbents),
        cmocka_unit_test(test_incumbents_initial_state),
        cmocka_unit_test(test_ctg_oracle_budget),
        cmocka_unit_test(test_opt_switch_feasibility_gate),
        cmocka_unit_test(test_csearch_opt_diagnostics_exact),
        cmocka_unit_test(test_csearch_opt_diagnostics_flips),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
