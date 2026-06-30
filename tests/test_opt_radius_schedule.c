/*
 * test_opt_radius_schedule.c — bd w29 (M5 / 71e): continuous oracle-indexed
 * opt-radius DECAY lever.
 *
 * Faithfulness contract under test (CLAUDE.md §1.1/§1.2/§1.5, NORTHSTAR §12 M5):
 *   (1) opt_radius_schedule_eval is a PURE function of (spec, ratio) — this is
 *       what makes the radius CONSTANT within a Grover round (it is consulted
 *       only at the top of the between-round ctg loop). Endpoints, midpoint,
 *       decay-shape (gamma), clamping, and the r_start==r_end degeneracy.
 *   (2) NEGATIVE CONTROL: a schedule with r_start==r_end==r* reproduces the
 *       STATIC constant-radius arm BIT-FOR-BIT (identical oracle_count, final
 *       state, and incumbent trajectory under a fixed seed). This is the
 *       "schedule degenerates to constant" guarantee.
 *   (3) LIVENESS: a real decay (r_start != r_end) actually drives the opt-phase
 *       bias between rounds — after ctg the realized opt bias has moved toward
 *       radius_to_bias(n, r_end), i.e. the hook fired and the radius tightened.
 *
 * The inner sampler (Branching.h / quantum_search.c / approximate_state_sampler.c)
 * is byte-unchanged; this lever only writes ctx->branching_stats_opt.bias BETWEEN
 * rounds, which BranchingFunction READS unchanged.
 */
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include <stdint.h>
#include <math.h>

#include "SearchLib.h"
#include "model.h"
#include "Expression.h"
#include "definitions.h"
#include "solver.h"
#include "solver_ctx.h"
#include "state.h"

/* ---------- (1) pure evaluator ---------- */

static void test_eval_endpoints_and_midpoint(void **state) {
    (void)state;
    /* r(t) = r_end + (r_start - r_end)*(1-t)^gamma; gamma=1 => linear. */
    opt_radius_schedule_t s = {.enabled = 1, .r_start = 8.0, .r_end = 2.0, .gamma = 1.0};
    assert_float_equal(opt_radius_schedule_eval(&s, 0.0), 8.0, 1e-12);  /* broad at t=0 */
    assert_float_equal(opt_radius_schedule_eval(&s, 1.0), 2.0, 1e-12);  /* tight at t=1 */
    assert_float_equal(opt_radius_schedule_eval(&s, 0.5), 5.0, 1e-12);  /* linear midpoint */
}

static void test_eval_clamps_ratio(void **state) {
    (void)state;
    opt_radius_schedule_t s = {.enabled = 1, .r_start = 8.0, .r_end = 2.0, .gamma = 1.0};
    /* Out-of-range ratios clamp to [0,1] — never extrapolate past the endpoints. */
    assert_float_equal(opt_radius_schedule_eval(&s, -0.5), 8.0, 1e-12);
    assert_float_equal(opt_radius_schedule_eval(&s, 1.5), 2.0, 1e-12);
}

static void test_eval_gamma_shape(void **state) {
    (void)state;
    /* Shape semantics (verified against r(t)=r_end+(r_start-r_end)*(1-t)^gamma):
     *   gamma < 1 stays BROADER longer (gentle early, steep near t=1): at t=0.5
     *             the radius is closer to r_start than linear.
     *   gamma > 1 tightens EARLY (steep early, gentle near t=1): at t=0.5 the
     *             radius is closer to r_end than linear.
     * Both still hit the same endpoints. */
    opt_radius_schedule_t gentle = {.enabled = 1, .r_start = 8.0, .r_end = 2.0, .gamma = 0.5};
    opt_radius_schedule_t steep  = {.enabled = 1, .r_start = 8.0, .r_end = 2.0, .gamma = 2.0};
    double lin = 5.0;  /* gamma=1 midpoint */
    double mid_gentle = opt_radius_schedule_eval(&gentle, 0.5);
    double mid_steep  = opt_radius_schedule_eval(&steep, 0.5);
    assert_true(mid_gentle > lin);   /* stays broad (closer to r_start=8) */
    assert_true(mid_steep  < lin);   /* tightens early (closer to r_end=2) */
    /* endpoints invariant to gamma */
    assert_float_equal(opt_radius_schedule_eval(&gentle, 0.0), 8.0, 1e-12);
    assert_float_equal(opt_radius_schedule_eval(&gentle, 1.0), 2.0, 1e-12);
    assert_float_equal(opt_radius_schedule_eval(&steep, 0.0), 8.0, 1e-12);
    assert_float_equal(opt_radius_schedule_eval(&steep, 1.0), 2.0, 1e-12);
}

static void test_eval_constant_degeneracy(void **state) {
    (void)state;
    /* r_start == r_end => constant r* at EVERY ratio and EVERY gamma (the
     * negative-control guarantee: schedule IS the static lever). */
    opt_radius_schedule_t s = {.enabled = 1, .r_start = 2.0, .r_end = 2.0, .gamma = 3.3};
    for (double t = 0.0; t <= 1.0; t += 0.1) {
        assert_float_equal(opt_radius_schedule_eval(&s, t), 2.0, 0.0);  /* exact */
    }
}

static void test_eval_is_pure(void **state) {
    (void)state;
    /* Determinism: identical (spec, ratio) => identical output, no hidden state.
     * This purity is what guarantees the radius is CONSTANT within a round. */
    opt_radius_schedule_t s = {.enabled = 1, .r_start = 7.0, .r_end = 1.5, .gamma = 1.7};
    double a = opt_radius_schedule_eval(&s, 0.37);
    double b = opt_radius_schedule_eval(&s, 0.37);
    assert_float_equal(a, b, 0.0);
}

/* ---------- ctg scaffold (mirrors test_searchlib.c knapsack) ---------- */

/* 5-var knapsack: all-zeros feasible (Σ2x_i <= 33), so ctg enters the opt phase
 * (stage 3) immediately and the schedule hook fires from the first opt round. */
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
    mod->stopping_time = 1e6;   /* wall-cap opt-in (>0); 1e6 s effectively OFF */
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_expr);
    return mod;
}

/* radius_to_bias(n, r) — the SAME formula the Python harness and the ctg hook use. */
static double radius_to_bias(int n, double r) { return (double)n / r - 2.0; }

/* One ctg run under a fixed seed/budget. `sched_enabled` arms the decay schedule
 * (r_start..r_end..gamma); the static opt bias is ALWAYS pre-set to
 * radius_to_bias(n, static_r) so the constant arm and the r_start==r_end schedule
 * arm share an identical initial opt bias. Returns the final oracle_count, the
 * post-run opt bias, and (via out params) the final state for bit-for-bit checks. */
typedef struct {
    size_t oracle_count;
    double final_opt_bias;
    int64_t final_profit;
    uint64_t final_bits;     /* packed 5-bit final assignment */
    int head;                /* incumbent count */
} ctg_outcome_t;

static ctg_outcome_t run_ctg(int budget, uint64_t seed, double static_r,
                             int sched_enabled, double r_start, double r_end, double gamma) {
    model_t *mod = build_knapsack_5var();
    mod->M = budget;

    int arr[5] = {0, 0, 0, 0, 0};
    state_t *cur_sol = init_state(0, arr, 5);

    solver_ctx_t *ctx = solver_ctx_create();
    ctx->seed = seed;
    solver_ctx_init_prng(ctx);

    /* Shared initial opt bias for both arms (the static constant radius). */
    solver_ctx_set_opt_bias(ctx, radius_to_bias(5, static_r));
    if (sched_enabled) {
        solver_ctx_set_opt_radius_schedule(ctx, 1, r_start, r_end, gamma);
    }

    incumbents_t *inc = init_incumbents(5, cur_sol);
    ctg(ctx, mod, cur_sol, NULL, inc);

    ctg_outcome_t out;
    out.oracle_count = ctx->oracle_count;
    out.final_opt_bias = ctx->branching_stats_opt.bias;
    out.final_profit = cur_sol->tot_profit;
    out.final_bits = 0;
    for (int i = 0; i < 5; i++) {
        if (sw_tstbit(cur_sol->vector, i)) out.final_bits |= (1u << i);
    }
    out.head = inc->head;

    free_incumbents(inc);
    free_state(cur_sol, 1);
    solver_ctx_free(ctx);
    free_model(mod);
    return out;
}

/* ---------- (2) negative control: schedule == constant BIT-FOR-BIT ---------- */

static void test_schedule_constant_is_bit_for_bit(void **state) {
    (void)state;
    const int T = 400;
    const uint64_t seed = 0xC0FFEEULL;
    const double r_star = 2.0;

    /* Static arm: schedule OFF, opt bias = radius_to_bias(5, r*). */
    ctg_outcome_t stat = run_ctg(T, seed, r_star, 0, 0, 0, 1.0);
    /* Schedule arm: schedule ON with r_start==r_end==r* (degenerate => constant). */
    ctg_outcome_t deg  = run_ctg(T, seed, r_star, 1, r_star, r_star, 1.0);

    assert_int_equal((int)stat.oracle_count, (int)deg.oracle_count);   /* same oracle axis */
    assert_int_equal((int)stat.final_profit, (int)deg.final_profit);   /* same objective  */
    assert_int_equal((int)stat.final_bits, (int)deg.final_bits);       /* same assignment */
    assert_int_equal(stat.head, deg.head);                             /* same #incumbents */
    /* Final opt bias identical: static never rewrote it; degenerate schedule
     * rewrote it to the SAME radius_to_bias(5, r*) every round. */
    assert_float_equal(stat.final_opt_bias, deg.final_opt_bias, 0.0);
    assert_float_equal(deg.final_opt_bias, radius_to_bias(5, r_star), 1e-12);
}

/* ---------- (3) liveness: a real decay drives the opt bias between rounds ---- */

static void test_decay_moves_opt_bias(void **state) {
    (void)state;
    const int T = 400;
    const uint64_t seed = 0xC0FFEEULL;

    /* Decay 8 -> 2 over the run. bias = n/r - 2 INCREASES as r decreases, so the
     * post-run opt bias must sit strictly above the broad-start bias and below
     * (or at) the tight-end bias — proving the between-round hook actually fired
     * and tightened the radius (CONSTANT-within-round but VARYING across rounds). */
    ctg_outcome_t dec = run_ctg(T, seed, 8.0, 1, 8.0, 2.0, 1.0);
    double bias_start = radius_to_bias(5, 8.0);   /* broad: 5/8 - 2 = -1.375 */
    double bias_end   = radius_to_bias(5, 2.0);   /* tight: 5/2 - 2 =  0.5   */

    assert_true(dec.final_opt_bias > bias_start);             /* moved off the broad start */
    assert_true(dec.final_opt_bias <= bias_end + 1e-9);       /* never past the tight end  */
    /* By the terminal round total_oracles ~ M => ratio ~ 1 => bias ~ bias_end. */
    assert_float_equal(dec.final_opt_bias, bias_end, 0.2);
}

/* A decay schedule must NOT equal the broad constant arm (it is a different
 * trajectory) — guards against the hook being a silent no-op. */
static void test_decay_differs_from_broad_constant(void **state) {
    (void)state;
    const int T = 400;
    const uint64_t seed = 0xC0FFEEULL;
    ctg_outcome_t broad = run_ctg(T, seed, 8.0, 0, 0, 0, 1.0);          /* constant r=8 */
    ctg_outcome_t dec   = run_ctg(T, seed, 8.0, 1, 8.0, 2.0, 1.0);      /* decay 8 -> 2 */
    /* The decay tightens the radius, changing the realized opt bias vs constant-8. */
    assert_true(dec.final_opt_bias != broad.final_opt_bias);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_eval_endpoints_and_midpoint),
        cmocka_unit_test(test_eval_clamps_ratio),
        cmocka_unit_test(test_eval_gamma_shape),
        cmocka_unit_test(test_eval_constant_degeneracy),
        cmocka_unit_test(test_eval_is_pure),
        cmocka_unit_test(test_schedule_constant_is_bit_for_bit),
        cmocka_unit_test(test_decay_moves_opt_bias),
        cmocka_unit_test(test_decay_differs_from_broad_constant),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
