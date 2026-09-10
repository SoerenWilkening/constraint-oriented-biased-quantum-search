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

/* 5-variable knapsack (mirrors test_integration.c). NOTE the multiply_constant
 * INSIDE the loop compounds: coefficients are binary-weighted (32,16,8,4,2),
 * not uniform 2s. Constraint Σ w_i x_i <= 33 (all-zeros feasible; x0+x1 is
 * not); objective minimizes -Σ w_i x_i, internal range [-62, 0], optimum -32. */
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
    mod->stopping_time = 1e6;   /* ctg wall-cap is opt-in (>0); 1e6 s is effectively OFF */
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

/* ---------- bd lif: per-worker wall-clock telemetry (ctx->runtime) ---------- */

/* ctg must record its wall-clock telemetry in the PER-WORKER ctx->runtime, never
 * the shared mod->runtime. The old `mod->runtime = total_time` was an unlocked,
 * last-writer-wins write executed every loop iteration by all threading workers
 * (CLAUDE.md §5) -- the same race class as the qtg_applications counter fixed in
 * 8an.1.4. Pin the invariant deterministically without needing TSan: seed the
 * shared field with a sentinel, run ctg, and assert ctg left mod->runtime
 * UNTOUCHED while populating a positive ctx->runtime. On HEAD (pre-fix) ctg
 * overwrites mod->runtime, so mod->runtime != SENTINEL => this fails (RED). */
static void test_ctg_runtime_per_worker(void **state) {
    (void)state;
    model_t *mod = build_knapsack_5var();
    mod->M = 200;
    const double SENTINEL = -42.0;
    mod->runtime = SENTINEL;

    int arr[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, arr, 5);

    solver_ctx_t *ctx = solver_ctx_create();
    assert_true(ctx->runtime == 0.0);   /* fresh ctx: telemetry zero-initialised */
    ctx->seed = 0xC0FFEEULL;
    solver_ctx_init_prng(ctx);

    incumbents_t *inc = init_incumbents(5, cur_sol);
    ctg(ctx, mod, cur_sol, NULL, inc);

    /* ctg must NOT touch the shared field -- the race is gone. */
    assert_true(mod->runtime == SENTINEL);
    /* ... and MUST record this worker's wall-clock in its own ctx: the run spent
     * a 200-oracle budget over real search_function work, so elapsed > 0. */
    assert_true(ctx->runtime > 0.0);

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/* ---------- bd 4uf (NORTHSTAR §11 M0e): per-worker incumbent logging ---------- */

/* Capture buffer for the counting callback. ctg is driven single-threaded in
 * these tests, so plain statics are fine; reset cb_count before each run. */
#define CB_CAP 4096
static int64_t cb_values[CB_CAP];
static size_t cb_oracles[CB_CAP];
static size_t cb_count;

static void counting_callback(void *ctx_ptr) {
    solver_ctx_t *cb_ctx = (solver_ctx_t *) ctx_ptr;
    if (cb_count < CB_CAP) {
        cb_values[cb_count] = cb_ctx->callback_value;
        cb_oracles[cb_count] = cb_ctx->oracle_count;
    }
    cb_count++;
}

/* NORTHSTAR §11 M0e mandates PER-WORKER incumbent logging: the callback fires
 * for every feasible incumbent THIS worker finds, independent of the shared
 * mod->global_opt. Pre-seed global_opt strictly better than anything reachable
 * (internal-minimize: lower is better; the knapsack's best internal objective
 * is -10), so the old shared-gate code — callback only when cur_sol beats
 * global_opt inside update_lock — fires ZERO times (RED). Per-worker logging
 * fires on every worker-local feasible incumbent regardless (GREEN). This is
 * the C-level pin for the bd 4uf scheduling-dependent-history bug: events
 * dropped by the wall-time global gate are not necessarily dominated on the
 * per-worker oracle axis, so the merged best-of-P curve (and the §6 PI) was
 * non-deterministic under threading. */
static void test_callback_per_worker_incumbent_logging(void **state) {
    (void)state;
    model_t *mod = build_knapsack_5var();
    mod->M = 200;
    mod->global_opt->tot_profit = INT64_MIN / 2;   /* never beaten by any worker */

    int zeros[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, zeros, 5);
    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = 0xABCDEFULL;
    solver_ctx_init_prng(ctx);
    incumbents_t *inc = init_incumbents(5, cur_sol);

    cb_count = 0;
    ctg(ctx, mod, cur_sol, counting_callback, inc);

    /* The kill-shot: per-worker incumbents MUST be logged even though the
     * pre-seeded global_opt is never beaten (the shared gate logs nothing). */
    assert_true(cb_count >= 1);
    size_t recorded = cb_count < CB_CAP ? cb_count : CB_CAP;
    for (size_t i = 0; i < recorded; i++) {
        /* every ctg-path event carries THIS worker's incumbent value ... */
        assert_true(cb_values[i] != SOLVER_CTX_CALLBACK_VALUE_UNSET);
        /* ... which is a genuine objective: the knapsack's binary-weighted
         * coefficients (32,16,8,4,2) bound the internal objective to [-62, 0];
         * a stage-2 violation slack would be > 0 (and is feasible-gated out). */
        assert_true(cb_values[i] <= 0 && cb_values[i] >= -62);
        /* ... this worker's incumbents strictly tighten (internal-minimize) ... */
        if (i > 0) assert_true(cb_values[i] <= cb_values[i - 1]);
        /* ... and the per-worker oracle stamps never decrease. */
        if (i > 0) assert_true(cb_oracles[i] >= cb_oracles[i - 1]);
    }
    /* The last logged incumbent is the worker's final solution. */
    assert_true(cb_values[recorded - 1] == cur_sol->tot_profit);
    /* global_opt stays at the pre-seed: the callback provably no longer
     * depends on (or perturbs) the shared incumbent. */
    assert_true(mod->global_opt->tot_profit == INT64_MIN / 2);

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/* Infeasible-start variant: every logged event must be a genuine OBJECTIVE of a
 * feasible point — the first one being the recomputed first-feasible objective
 * (the SearchLib.c first-feasible fixup runs BEFORE the callback site), never a
 * stage-2 violation-slack (slack >= 0 travels with feasible==0 and is gated
 * out). Covering requires sum x >= 2 with internal objective -sum x, so any
 * feasible objective is <= -2 while any slack is >= 0 — disjoint ranges. */
static void test_callback_first_feasible_objective(void **state) {
    (void)state;
    model_t *mod = build_covering_5var();
    mod->M = 2000;
    mod->global_opt->tot_profit = INT64_MIN / 2;   /* never beaten */

    int zeros[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, zeros, 5);
    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = 0x5151ULL;
    solver_ctx_init_prng(ctx);
    incumbents_t *inc = init_incumbents(5, cur_sol);

    cb_count = 0;
    int feasible = ctg(ctx, mod, cur_sol, counting_callback, inc);

    assert_true(feasible);
    assert_true(cb_count >= 1);
    size_t recorded = cb_count < CB_CAP ? cb_count : CB_CAP;
    for (size_t i = 0; i < recorded; i++) {
        assert_true(cb_values[i] <= -2);   /* objective of a feasible point, not slack */
    }

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

/* ---------- M2a (bd 8an.3.1): per-phase decision-touch counters ---------- */

/* Contradictory model: {sum x <= 0, sum x >= n (negated-LOWER: factors -1,
 * rhs 0)}. At depth_look_ahead=0 EVERY variable decision is BOTH-INFEASIBLE:
 * assignment 1 exceeds the LE potential (0 < 1) and assignment 0 exceeds the
 * negated-GE potential (0 < 1). The phases handle this case differently
 * (solver.c): sat forces bit=0, opt_sat CONSULTS BranchingFunction, opt
 * truncates the candidate (break) -- which is exactly what the M2 taxonomy
 * must record. No feasible point exists, so violation > 0 for every candidate
 * and (with the sentinels below) no phase ever accepts: the candidate count is
 * the exact, RNG-free 4j^2+1. */
static model_t *build_contradictory_model(int n) {
    model_t *mod = init_model();

    expression_t *le_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(le_expr, i); }
    add_sense_to_expression(le_expr, LOWER);
    add_rhs_to_expression(le_expr, 0);          /* sum x <= 0 */
    add_expression_to_constraints(mod->con, le_expr);

    expression_t *ge_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(ge_expr, i); }
    multiply_constant(ge_expr, -1);             /* factors -1 */
    add_sense_to_expression(ge_expr, LOWER);
    add_rhs_to_expression(ge_expr, 0);          /* n - n = 0  =>  requires sum x >= n */
    add_expression_to_constraints(mod->con, ge_expr);

    expression_t *obj_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(obj_expr, i); }
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

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

    free_expression(le_expr);
    free_expression(ge_expr);
    free_expression(obj_expr);
    return mod;
}

/* All-forced model: sum x <= 0 with an all-zeros incumbent. Assignment 1 is
 * always infeasible (count[1]==0), assignment 0 always feasible (count[0]>0):
 * every decision is single-side FORCED, RNG-free. */
static model_t *build_allforced_model(int n) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(con_expr, i); }
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, 0);         /* sum x <= 0: only all-zeros feasible */
    add_expression_to_constraints(mod->con, con_expr);

    expression_t *obj_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(obj_expr, i); }
    add_sense_to_expression(obj_expr, LOWER);
    add_rhs_to_expression(obj_expr, 0);
    add_expression_to_constraints(mod->obj, obj_expr);

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

/* Snapshot of all 12 per-phase decision-touch counters. */
typedef struct {
    uint64_t sat_dec, sat_free, sat_binf, sat_forc;
    uint64_t os_dec, os_free, os_binf, os_forc;
    uint64_t opt_dec, opt_free, opt_binf, opt_forc;
} touch_t;

static void read_touch(const solver_ctx_t *ctx, touch_t *t) {
    t->sat_dec  = ctx->sat_decisions;    t->sat_free = ctx->sat_free;
    t->sat_binf = ctx->sat_bothinf;      t->sat_forc = ctx->sat_forced;
    t->os_dec   = ctx->optsat_decisions; t->os_free  = ctx->optsat_free;
    t->os_binf  = ctx->optsat_bothinf;   t->os_forc  = ctx->optsat_forced;
    t->opt_dec  = ctx->opt_decisions;    t->opt_free = ctx->opt_free_sum;
    t->opt_binf = ctx->opt_bothinf;      t->opt_forc = ctx->opt_forced;
}

/* The class partition must be exhaustive and disjoint in every phase:
 * free + bothinf + forced == decisions. */
static void assert_touch_invariant(const touch_t *t) {
    assert_int_equal((int)(t->sat_free + t->sat_binf + t->sat_forc), (int) t->sat_dec);
    assert_int_equal((int)(t->os_free  + t->os_binf  + t->os_forc),  (int) t->os_dec);
    assert_int_equal((int)(t->opt_free + t->opt_binf + t->opt_forc), (int) t->opt_dec);
}

/* Drive ONE direct CSearch_{sat,opt_sat,opt} call on `mod` with the matching
 * active_stats and return the touch counters. `which`: 1=sat, 2=opt_sat, 3=opt.
 * cur_tot_profit is the incumbent sentinel that suppresses (or not) accepts. */
static void run_one_phase_touch(model_t *mod, int which, int n, int j,
                                int64_t cur_tot_profit, int feasible,
                                uint64_t seed, touch_t *t) {
    int *arr = calloc((size_t) n, sizeof(int));
    state_t *cur_sol = init_state(0, arr, n);
    cur_sol->tot_profit = cur_tot_profit;
    cur_sol->feasible = feasible;
    free(arr);

    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = seed;
    solver_ctx_init_prng(ctx);

    int samples = 0;
    if (which == 1) {
        ctx->active_stats = &ctx->branching_stats_sat;
        (void) CSearch_sat(ctx, cur_sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);
    } else if (which == 2) {
        ctx->active_stats = &ctx->branching_stats_opt_sat;
        (void) CSearch_opt_sat(ctx, cur_sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);
    } else {
        ctx->active_stats = &ctx->branching_stats_opt;
        (void) CSearch_opt(ctx, cur_sol, j, mod->con, mod->obj, 0, 1, NULL, &samples);
    }

    read_touch(ctx, t);
    assert_touch_invariant(t);

    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
}

/* EXACT, RNG-free pins on the contradictory model: every decision is
 * both-infeasible. sat forces bit=0 and runs all n decisions per candidate;
 * opt_sat consults BranchingFunction on all n; opt truncates the candidate at
 * the FIRST decision (break) so exactly 1 decision per candidate. No accept
 * ever fires (no feasible point; sentinels below), so candidates == 4j^2+1.
 * NOTE: the opt leg drives CSearch_opt directly on an infeasible instance --
 * a counter unit test of the break-path accounting, not a phase-machine state
 * (ctg's feasibility gate forbids reaching opt infeasible in production). */
static void test_decision_touch_bothinf_taxonomy(void **state) {
    (void)state;
    const int n = 4, j = 2;
    const uint64_t cand = (uint64_t)(4 * j * j + 1);   /* 17 */
    touch_t t;

    /* sat: both-infeasible is feasibility-forced (bit=0), NOT consulted */
    run_one_phase_touch(build_contradictory_model(n), 1, n, j, INT64_MIN, 0, 0x5A7AULL, &t);
    assert_int_equal((int) t.sat_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_binf, (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_free, 0);
    assert_int_equal((int) t.sat_forc, 0);
    assert_int_equal((int) t.os_dec, 0);     /* other phases untouched */
    assert_int_equal((int) t.opt_dec, 0);

    /* opt_sat: both-infeasible IS consulted (bias-decided) */
    run_one_phase_touch(build_contradictory_model(n), 2, n, j, 0, 0, 0x05A7ULL, &t);
    assert_int_equal((int) t.os_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.os_binf, (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.os_free, 0);
    assert_int_equal((int) t.os_forc, 0);
    assert_int_equal((int) t.sat_dec, 0);
    assert_int_equal((int) t.opt_dec, 0);

    /* opt: both-infeasible truncates the candidate => exactly 1 decision each */
    run_one_phase_touch(build_contradictory_model(n), 3, n, j, 0, 1, 0x0057ULL, &t);
    assert_int_equal((int) t.opt_dec,  (int) cand);
    assert_int_equal((int) t.opt_binf, (int) cand);
    assert_int_equal((int) t.opt_free, 0);
    assert_int_equal((int) t.opt_forc, 0);
    assert_int_equal((int) t.sat_dec, 0);
    assert_int_equal((int) t.os_dec, 0);
}

/* EXACT, RNG-free pins on the all-forced model: every decision single-side
 * forced (count[1]==0, count[0]>0) in all three phases. sat (INT64_MIN
 * sentinel) and opt (all-zeros candidate == incumbent => no improvement) run
 * the full 4j^2+1 loop; opt_sat's first candidate is feasible-with-violation-0
 * and direction==1 ACCEPTS it => exactly 1 candidate, n decisions. */
static void test_decision_touch_forced_taxonomy(void **state) {
    (void)state;
    const int n = 4, j = 2;
    const uint64_t cand = (uint64_t)(4 * j * j + 1);   /* 17 */
    touch_t t;

    run_one_phase_touch(build_allforced_model(n), 1, n, j, INT64_MIN, 0, 0xF0C1ULL, &t);
    assert_int_equal((int) t.sat_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_forc, (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_free, 0);
    assert_int_equal((int) t.sat_binf, 0);

    run_one_phase_touch(build_allforced_model(n), 2, n, j, INT64_MAX, 0, 0x0FC1ULL, &t);
    assert_int_equal((int) t.os_dec,  (int) n);        /* accepts candidate 0 */
    assert_int_equal((int) t.os_forc, (int) n);
    assert_int_equal((int) t.os_free, 0);
    assert_int_equal((int) t.os_binf, 0);

    run_one_phase_touch(build_allforced_model(n), 3, n, j, 0, 1, 0x00C1ULL, &t);
    assert_int_equal((int) t.opt_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.opt_forc, (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.opt_free, 0);
    assert_int_equal((int) t.opt_binf, 0);
}

/* EXACT, RNG-free pins on the all-free model (loose constraint): every
 * decision is both-feasible => consulted in all three phases. sat (INT64_MIN
 * sentinel: val==-1 never accepted) and opt (all-zeros internal-optimal) run
 * the full 4j^2+1 loop; opt_sat's first candidate has violation 0 and
 * direction==1 accepts it => exactly 1 candidate. The opt leg also pins the
 * new opt_decisions against the EXISTING opt_free_sum (M0g): identical here. */
static void test_decision_touch_free_taxonomy(void **state) {
    (void)state;
    const int n = 4, j = 2;
    const uint64_t cand = (uint64_t)(4 * j * j + 1);   /* 17 */
    touch_t t;

    run_one_phase_touch(build_freeall_model(n), 1, n, j, INT64_MIN, 0, 0xFEE1ULL, &t);
    assert_int_equal((int) t.sat_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_free, (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.sat_binf, 0);
    assert_int_equal((int) t.sat_forc, 0);

    run_one_phase_touch(build_freeall_model(n), 2, n, j, INT64_MAX, 0, 0x0EE1ULL, &t);
    assert_int_equal((int) t.os_dec,  (int) n);        /* accepts candidate 0 */
    assert_int_equal((int) t.os_free, (int) n);
    assert_int_equal((int) t.os_binf, 0);
    assert_int_equal((int) t.os_forc, 0);

    run_one_phase_touch(build_freeall_model(n), 3, n, j, 0, 1, 0x00E1ULL, &t);
    assert_int_equal((int) t.opt_dec,  (int)(cand * (uint64_t) n));
    assert_int_equal((int) t.opt_free, (int)(cand * (uint64_t) n));   /* == opt_free_sum (M0g) */
    assert_int_equal((int) t.opt_binf, 0);
    assert_int_equal((int) t.opt_forc, 0);
}

/* End-to-end ctg on the infeasible-start covering instance: opt_sat must run
 * (and record decisions) before the feasibility-gated switch hands over to
 * opt; sat never runs under OPTIMIZE. The per-phase invariant holds on the
 * full mixed trajectory (PRNG-driven classes, so inequalities only). */
static void test_decision_touch_ctg_phases(void **state) {
    (void)state;
    model_t *mod = build_covering_5var();
    mod->M = 2000;
    mod->opt_switch_oracles = 50;

    int zeros[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, zeros, 5);
    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = 0x7AC3ULL;
    solver_ctx_init_prng(ctx);
    incumbents_t *inc = init_incumbents(5, cur_sol);

    int feasible = ctg(ctx, mod, cur_sol, NULL, inc);
    assert_true(feasible);

    touch_t t;
    read_touch(ctx, &t);
    assert_touch_invariant(&t);
    assert_int_equal((int) t.sat_dec, 0);      /* OPTIMIZE never runs CSearch_sat */
    assert_true(t.os_dec > 0);                 /* infeasible start => opt_sat ran */
    assert_true(t.opt_dec > 0);                /* switch fired => opt ran */

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
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
        cmocka_unit_test(test_ctg_runtime_per_worker),
        cmocka_unit_test(test_callback_per_worker_incumbent_logging),
        cmocka_unit_test(test_callback_first_feasible_objective),
        cmocka_unit_test(test_opt_switch_feasibility_gate),
        cmocka_unit_test(test_csearch_opt_diagnostics_exact),
        cmocka_unit_test(test_csearch_opt_diagnostics_flips),
        cmocka_unit_test(test_decision_touch_free_taxonomy),
        cmocka_unit_test(test_decision_touch_bothinf_taxonomy),
        cmocka_unit_test(test_decision_touch_forced_taxonomy),
        cmocka_unit_test(test_decision_touch_ctg_phases),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
