/**
 * @file test_opt_sat_feasibility.c
 * @brief bd xjs: CSearch_opt_sat must not lie about cur_sol->feasible.
 *
 * ROOT CAUSE UNDER TEST (solver.c, the "lower violation was found" accept):
 *
 *     if ((cur_sol->tot_profit > total_violation) && (direction == 1 || feasible)) {
 *         ...
 *         cur_sol->feasible = 0;      <-- UNCONDITIONAL
 *         return 1;
 *     }
 *
 * With direction == -1 (stage 2, "tighten the slack of an already-feasible
 * incumbent") the guard `(direction == 1 || feasible)` can only be satisfied by
 * the local `feasible` -- i.e. the accepted candidate is PROVABLY feasible --
 * yet the accept stamps `cur_sol->feasible = 0`. The phase machine in ctg then
 * holds a state whose vector satisfies every constraint while its `feasible`
 * flag says otherwise, and the exploit->explore switch's fail-loud guard
 * (CLAUDE.md §5 phase-machine coupling) aborts the process.
 *
 * The property pinned here is the one that makes that guard unreachable BY
 * CONSTRUCTION (§2.1, §1 phase-machine coupling):
 *
 *     after EVERY accepted CSearch_opt_sat call,
 *         cur_sol->feasible == eval_constraints(con, cur_sol, n)
 *
 * plus the end-to-end ctg consequence on the bd xjs configuration
 * (MINIMIZE objective + an INFEASIBLE start, which a `>=` covering constraint
 * produces from 0^n). That is the only combination that reaches the corrupting
 * accept:
 *   - `<=` capacity models start feasible -> ctg enters stage 3 immediately and
 *     never runs opt_sat;
 *   - MAXIMIZE objectives are stored negated, so at the first-feasible handoff
 *     cur_sol->tot_profit < 0 <= total_violation and the stage-2 accept above
 *     can never fire.
 * "Cold" is incidental: a WARM general_greedy() start that comes out infeasible
 * reproduces it identically (measured; pinned in test_opt_switch_feasibility.py).
 *
 * The last test in this file covers a SECOND phase-machine desync that ctg's new
 * per-round coupling check surfaced, on the previously untested
 * ignore_constraint_search path.
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <cmocka.h>

#include "SearchLib.h"
#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "solver_ctx.h"
#include "definitions.h"

/* ------------------------------------------------------------------ *
 * Model: MINIMIZE sum_i (i+1)*x_i  subject to  sum_i x_i >= k.
 *
 * `>=` is stored the way Expression.pyx.__ge__ stores it: coefficients
 * negated and rhs = (sum of |negative factors|) - k = n - k for unit
 * weights (eval_constraint charges a negative factor as (1 - assigned)).
 * The objective keeps POSITIVE factors: the C core always minimizes
 * tot_profit, and MINIMIZE (sense=+1) is the identity mapping -- which is
 * what puts a positive value in cur_sol->tot_profit at first feasibility.
 * ------------------------------------------------------------------ */
static model_t *build_min_covering_model(int n, int k) {
    model_t *mod = init_model();

    expression_t *con_expr = init_expression();
    for (int i = 0; i < n; i++) { add_variable(con_expr, i); }
    multiply_constant(con_expr, -1);                /* factors -1 */
    add_sense_to_expression(con_expr, LOWER);
    add_rhs_to_expression(con_expr, n - k);         /* <=> sum x >= k */
    add_expression_to_constraints(mod->con, con_expr);

    /* MINIMIZE sum (i+1)*x_i: build each term separately, since
     * multiply_constant applies to every term already in the expression. */
    expression_t *obj_all = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *t = init_expression();
        add_variable(t, i);
        multiply_constant(t, i + 1);
        add_expression(obj_all, t);
        free_expression(t);
    }
    add_sense_to_expression(obj_all, LOWER);
    add_rhs_to_expression(obj_all, 0);
    add_expression_to_constraints(mod->obj, obj_all);

    preprocessing(n, mod->con);
    preprocessing(n, mod->obj);

    int *arr = calloc((size_t) n, sizeof(int));
    assert_non_null(arr);
    mod->initial_state = init_state(0, arr, n);
    mod->global_opt = init_state(0, arr, n);
    free(arr);

    mod->n = n;
    mod->depth_look_ahead = 0;
    mod->stopping_time = -1;        /* wall-clock stop OFF (oracle-indexed) */
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_expr);
    free_expression(obj_all);
    return mod;
}

/* Sanity: the covering encoding really does make 0^n infeasible and a
 * k-of-n point feasible -- otherwise every test below is vacuous. */
static void test_covering_encoding_sanity(void **state) {
    (void)state;
    const int n = 6, k = 3;
    model_t *mod = build_min_covering_model(n, k);

    int zeros[6] = {0, 0, 0, 0, 0, 0};
    int three[6] = {1, 1, 1, 0, 0, 0};
    int two[6]   = {1, 1, 0, 0, 0, 0};
    state_t *s0 = init_state(0, zeros, n);
    state_t *s3 = init_state(0, three, n);
    state_t *s2 = init_state(0, two, n);

    assert_int_equal(eval_constraints(mod->con, s0, n), 0);
    assert_int_equal(eval_constraints(mod->con, s2, n), 0);
    assert_int_equal(eval_constraints(mod->con, s3, n), 1);

    free_state(s0, 1);
    free_state(s2, 1);
    free_state(s3, 1);
    free_model(mod);
}

/*
 * THE INVARIANT (bd xjs): an accepted CSearch_opt_sat state's `feasible` flag
 * must agree with eval_constraints -- in BOTH directions.
 *
 * direction == -1 is the stage-2 "tighten the slack" mode ctg switches to at
 * first feasibility. Every accept there is provably feasible (the accept guard
 * requires the local `feasible`), so the flag must be 1.
 */
static void test_opt_sat_accept_feasible_flag_matches_eval(void **state) {
    (void)state;
    const int n = 6, k = 3;
    const int direction = -1;

    int accepts = 0;
    /* Sweep seeds so the assertion is not a single-trajectory accident. */
    for (uint64_t seed = 1; seed <= 64; ++seed) {
        model_t *mod = build_min_covering_model(n, k);

        /* Feasible incumbent (all ones) with a slack sentinel large enough
         * that a slack-reducing candidate is accepted. */
        int ones[6] = {1, 1, 1, 1, 1, 1};
        state_t *cur_sol = init_state(0, ones, n);
        cur_sol->feasible = 1;
        cur_sol->tot_profit = 1000;        /* sentinel > any reachable slack */
        assert_int_equal(eval_constraints(mod->con, cur_sol, n), 1);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);
        ctx->active_stats = &ctx->branching_stats_opt_sat;

        int samples = 0;
        for (int round = 0; round < 8; ++round) {
            int res = CSearch_opt_sat(ctx, cur_sol, 2, mod->con, mod->obj,
                                      0, direction, NULL, &samples);
            if (!res) continue;
            accepts++;
            /* The accepted vector satisfies every constraint... */
            assert_int_equal(eval_constraints(mod->con, cur_sol, n), 1);
            /* ...so the flag the phase machine reads must say so. */
            assert_int_equal(cur_sol->feasible, 1);
        }

        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
    /* Fail loudly if the sweep never exercised the accept path at all. */
    assert_true(accepts > 0);
}

/*
 * NEGATIVE CONTROL: direction == 1 (stage 1, "reduce the violation") must be
 * bit-for-bit unchanged. Reaching the same accept with direction == 1 implies
 * the candidate is INfeasible (a feasible candidate returns earlier, through
 * the dedicated first-feasibility branch), so the flag must stay 0 there.
 */
static void test_opt_sat_direction1_accept_flag_matches_eval(void **state) {
    (void)state;
    const int n = 6, k = 3;
    const int direction = 1;

    int accepts = 0;
    for (uint64_t seed = 1; seed <= 64; ++seed) {
        model_t *mod = build_min_covering_model(n, k);

        int zeros[6] = {0, 0, 0, 0, 0, 0};
        state_t *cur_sol = init_state(0, zeros, n);
        cur_sol->feasible = 0;
        cur_sol->tot_profit = 1000;
        assert_int_equal(eval_constraints(mod->con, cur_sol, n), 0);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);
        ctx->active_stats = &ctx->branching_stats_opt_sat;

        int samples = 0;
        for (int round = 0; round < 8; ++round) {
            int res = CSearch_opt_sat(ctx, cur_sol, 2, mod->con, mod->obj,
                                      0, direction, NULL, &samples);
            if (!res) continue;
            accepts++;
            assert_int_equal(cur_sol->feasible,
                             eval_constraints(mod->con, cur_sol, n));
        }

        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
    assert_true(accepts > 0);
}

/*
 * END-TO-END (the bd xjs repro, reduced to C): a cold 0^n start on a MINIMIZE
 * covering instance must reach feasibility in opt_sat, tighten in stage 2, and
 * cross the exploit->explore switch WITHOUT tripping ctg's fail-loud guard.
 *
 * Pre-fix this aborts the whole test binary -- which is the point: the guard is
 * correct, the state handed to it is not. Placed LAST so a pre-fix abort cannot
 * mask the unit-level RED above.
 */
static void test_ctg_cold_minimize_covering_crosses_switch(void **state) {
    (void)state;
    const int n = 6, k = 3;

    for (uint64_t seed = 1; seed <= 24; ++seed) {
        model_t *mod = build_min_covering_model(n, k);
        /* Keep the budget SMALL: ctg's Grover schedule grows j until the
         * remaining-budget clamp bites, and one round costs O(n*j^2) classical
         * samples, so a large M makes this test minutes long. M=300 with the
         * switch armed at 40 still covers the whole sequence under test --
         * reach feasibility in opt_sat, tighten in stage 2, cross the switch --
         * and was verified to still reproduce the pre-fix abort. */
        mod->M = 300;
        mod->opt_switch_oracles = 40;

        int zeros[6] = {0, 0, 0, 0, 0, 0};
        state_t *cur_sol = init_state(0, zeros, n);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);

        incumbents_t *inc = init_incumbents(n, cur_sol);
        int feasible = ctg(ctx, mod, cur_sol, NULL, inc);

        /* ctg returned (no abort) and the point it ends on is genuinely
         * feasible whenever it reports feasibility. */
        if (feasible) {
            assert_int_equal(eval_constraints(mod->con, cur_sol, n), 1);
            assert_int_equal(cur_sol->feasible, 1);
        }

        free_incumbents(inc);
        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
}

/* ================================================================== *
 * EQUAL constraints: the stage-1 violation predicate
 * ================================================================== *
 *
 * `potentials[c] == con->rhs[c]` means LHS_c == 0 ("nothing assigned"), NOT
 * "the equality holds". The pre-fix predicate
 *
 *     total_violation += potentials[c] != con->rhs[c] ? llabs(potentials[c]) : 0;
 *
 * therefore scored every LHS == 0 point as SATISFIED, so CSearch_opt_sat's
 * `feasible = (total_violation == 0)` declared the all-zeros vector feasible on
 * an `== R` model with R != 0 -- and (bd xjs) stamped that verdict onto
 * cur_sol->feasible, which ctg, run_sampling's per-worker final incumbent and
 * the history callback all read. EQUAL feasibility is `potentials[c] == 0`,
 * the predicate CSearch_opt's own `as1` uses and the one constraint.c's
 * eval_constraint means.
 */

/* Golden values for the pure predicate. `potentials[c] = rhs[c] - LHS_c`. */
static void test_potentials_total_violation_equal_golden(void **state) {
    (void)state;
    new_constraints_t con;
    memset(&con, 0, sizeof(con));
    int senses[1] = { EQUAL };
    int64_t rhs[1] = { 25 };
    con.num_constraints = 1;
    con.sense = senses;
    con.rhs = rhs;

    int64_t p[1];

    /* LHS == 0 (the all-zeros vector): potentials == rhs == 25. This is the
     * regression: it must score as a violation of 25, NOT as satisfied. */
    p[0] = 25;  assert_true(potentials_total_violation(&con, p) == 25);
    /* LHS == rhs: satisfied. */
    p[0] = 0;   assert_true(potentials_total_violation(&con, p) == 0);
    /* LHS below rhs by 7 / above rhs by 3: |potentials| either way. */
    p[0] = 7;   assert_true(potentials_total_violation(&con, p) == 7);
    p[0] = -3;  assert_true(potentials_total_violation(&con, p) == 3);

    /* rhs == 0 is the one case the old predicate got right (LHS == 0 IS the
     * solution there) -- pin that it still does. */
    rhs[0] = 0;
    p[0] = 0;   assert_true(potentials_total_violation(&con, p) == 0);
    p[0] = -4;  assert_true(potentials_total_violation(&con, p) == 4);
}

/* INERTNESS PIN (the blast-radius argument): with no EQUAL constraint the
 * predicate is byte-identical to the pre-fix one -- the changed branch is
 * guarded by `sense == EQUAL` and is unreachable. Eq.29 uses only `<=`/`>=`
 * (both stored as LOWER, `>=` via negated factors), so the frozen baselines
 * cannot move. */
static void test_potentials_total_violation_lower_unchanged(void **state) {
    (void)state;
    new_constraints_t con;
    memset(&con, 0, sizeof(con));
    int senses[2] = { LOWER, LOWER };
    int64_t rhs[2] = { 10, 0 };
    con.num_constraints = 2;
    con.sense = senses;
    con.rhs = rhs;

    int64_t p[2];
    /* both slack -> 0 (note p[0] == rhs[0] == 10, the cell the EQUAL branch
     * would have mis-scored; LOWER must be untouched by the fix) */
    p[0] = 10; p[1] = 0;   assert_true(potentials_total_violation(&con, p) == 0);
    p[0] = 3;  p[1] = 5;   assert_true(potentials_total_violation(&con, p) == 0);
    /* shortfalls sum as -min(0, p) */
    p[0] = -4; p[1] = 0;   assert_true(potentials_total_violation(&con, p) == 4);
    p[0] = -4; p[1] = -6;  assert_true(potentials_total_violation(&con, p) == 10);
    p[0] = 7;  p[1] = -6;  assert_true(potentials_total_violation(&con, p) == 6);
}

/* ------------------------------------------------------------------ *
 * MINIMIZE sum_i x_i  subject to  sum_i (i+1)*x_i == R.
 * The all-zeros start has LHS == 0 != R, i.e. it is INFEASIBLE -- which is
 * exactly what the pre-fix predicate denied.
 * ------------------------------------------------------------------ */
static model_t *build_min_equality_model(int n, int R) {
    model_t *mod = init_model();

    expression_t *con_all = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *t = init_expression();
        add_variable(t, i);
        multiply_constant(t, i + 1);
        add_expression(con_all, t);
        free_expression(t);
    }
    add_sense_to_expression(con_all, EQUAL);      /* Expression.pyx __eq__ */
    add_rhs_to_expression(con_all, R);
    add_expression_to_constraints(mod->con, con_all);

    expression_t *obj_all = init_expression();
    for (int i = 0; i < n; i++) { add_variable(obj_all, i); }
    add_sense_to_expression(obj_all, LOWER);
    add_rhs_to_expression(obj_all, 0);
    add_expression_to_constraints(mod->obj, obj_all);

    preprocessing(n, mod->con);
    preprocessing(n, mod->obj);

    int *arr = calloc((size_t) n, sizeof(int));
    assert_non_null(arr);
    mod->initial_state = init_state(0, arr, n);
    mod->global_opt = init_state(0, arr, n);
    free(arr);

    mod->n = n;
    mod->depth_look_ahead = 0;
    mod->stopping_time = -1;
    mod->stop_val = -1;
    mod->ignore_constraint_search = 0;
    mod->solver = OPTIMIZE;
    mod->break_item = 0;

    free_expression(con_all);
    free_expression(obj_all);
    return mod;
}

/* Premise check: eval_constraints -- the ground truth the accept must agree
 * with -- really does reject LHS == 0 on an `== R` model with R != 0. */
static void test_equality_encoding_sanity(void **state) {
    (void)state;
    const int n = 6, R = 7;
    model_t *mod = build_min_equality_model(n, R);

    int zeros[6] = {0, 0, 0, 0, 0, 0};
    int hit[6]   = {1, 0, 0, 0, 0, 1};   /* 1 + 6 == 7 */
    int over[6]  = {0, 0, 0, 0, 0, 1};   /* 6 != 7 */
    state_t *s0 = init_state(0, zeros, n);
    state_t *sh = init_state(0, hit, n);
    state_t *so = init_state(0, over, n);

    assert_int_equal(eval_constraints(mod->con, s0, n), 0);
    assert_int_equal(eval_constraints(mod->con, sh, n), 1);
    assert_int_equal(eval_constraints(mod->con, so, n), 0);

    free_state(s0, 1);
    free_state(sh, 1);
    free_state(so, 1);
    free_model(mod);
}

/* THE REGRESSION, end to end through CSearch_opt_sat: every accepted state's
 * `feasible` flag must agree with eval_constraints on an EQUAL model too.
 * Pre-fix the direction == 1 "was not feasible before, but now" branch fires on
 * the all-zeros candidate and stamps feasible = 1. */
static void test_opt_sat_equality_accept_flag_matches_eval(void **state) {
    (void)state;
    const int n = 6, R = 7;

    int accepts = 0;
    for (uint64_t seed = 1; seed <= 64; ++seed) {
        model_t *mod = build_min_equality_model(n, R);

        int zeros[6] = {0, 0, 0, 0, 0, 0};
        state_t *cur_sol = init_state(0, zeros, n);
        cur_sol->feasible = 0;
        cur_sol->tot_profit = 1000;      /* violation sentinel */
        assert_int_equal(eval_constraints(mod->con, cur_sol, n), 0);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);
        ctx->active_stats = &ctx->branching_stats_opt_sat;

        int samples = 0;
        for (int round = 0; round < 8; ++round) {
            int res = CSearch_opt_sat(ctx, cur_sol, 2, mod->con, mod->obj,
                                      0, 1, NULL, &samples);
            if (!res) continue;
            accepts++;
            assert_int_equal(cur_sol->feasible,
                             eval_constraints(mod->con, cur_sol, n));
        }

        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
    assert_true(accepts > 0);
}

/* ...and end to end through ctg: an `== R` model must never report a feasible
 * point that eval_constraints rejects (the §8-protected final incumbent /
 * history streams read exactly these fields). */
static void test_ctg_equality_never_reports_false_feasible(void **state) {
    (void)state;
    const int n = 6, R = 7;

    for (uint64_t seed = 1; seed <= 24; ++seed) {
        model_t *mod = build_min_equality_model(n, R);
        mod->M = 300;
        mod->opt_switch_oracles = 40;

        int zeros[6] = {0, 0, 0, 0, 0, 0};
        state_t *cur_sol = init_state(0, zeros, n);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);

        incumbents_t *inc = init_incumbents(n, cur_sol);
        int feasible = ctg(ctx, mod, cur_sol, NULL, inc);

        if (feasible || cur_sol->feasible) {
            assert_int_equal(eval_constraints(mod->con, cur_sol, n), 1);
            assert_int_equal(cur_sol->feasible, 1);
        }
        if (mod->global_opt->feasible) {
            assert_int_equal(eval_constraints(mod->con, mod->global_opt, n), 1);
        }

        free_incumbents(inc);
        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
}

/*
 * ignore_constraint_search starts ctg in stage 3 / CSearch_opt / stats_opt even
 * from an INFEASIBLE point (the flag skips the sat + opt_sat phases). CSearch_opt
 * nevertheless only accepts constraint-satisfying candidates, so its first accept
 * sets cur_sol->feasible = 1 -- which used to trip ctg's "first found feasible
 * solution" handoff and set stage = 2 + active_stats = stats_opt_sat WITHOUT
 * moving search_function, i.e. CSearch_opt running on the opt_sat bias
 * (NORTHSTAR §5 "wrong phase's stats", silent before the per-round coupling
 * check). The phase machine must stay in the objective phase.
 *
 * This path had NO end-to-end coverage before bd xjs.
 */
static void test_ctg_ignore_constraint_search_stays_in_opt_phase(void **state) {
    (void)state;
    const int n = 6, k = 3;

    for (uint64_t seed = 1; seed <= 16; ++seed) {
        model_t *mod = build_min_covering_model(n, k);
        /* Small budget for the same O(n*j^2) reason as above; this run never
         * leaves stage 3, so it would otherwise spend the whole budget on
         * ever-larger Grover rounds. */
        mod->M = 300;
        mod->opt_switch_oracles = 40;
        mod->ignore_constraint_search = 1;

        int zeros[6] = {0, 0, 0, 0, 0, 0};
        state_t *cur_sol = init_state(0, zeros, n);
        /* Premise: the start really is infeasible, so stage 3 is entered from
         * an infeasible point -- the configuration that desynced. */
        assert_int_equal(eval_constraints(mod->con, cur_sol, n), 0);

        solver_ctx_t *ctx = solver_ctx_create();
        ctx->seed = seed;
        solver_ctx_init_prng(ctx);

        incumbents_t *inc = init_incumbents(n, cur_sol);
        (void) ctg(ctx, mod, cur_sol, NULL, inc);   /* must not abort */

        /* CSearch_opt only accepts constraint-satisfying candidates, so any
         * state it moved to must still pass eval_constraints. */
        if (cur_sol->feasible) {
            assert_int_equal(eval_constraints(mod->con, cur_sol, n), 1);
        }

        free_incumbents(inc);
        free_state(cur_sol, 1);
        solver_ctx_free(ctx);
        free_model(mod);
    }
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_covering_encoding_sanity),
        cmocka_unit_test(test_opt_sat_accept_feasible_flag_matches_eval),
        cmocka_unit_test(test_opt_sat_direction1_accept_flag_matches_eval),
        cmocka_unit_test(test_ctg_cold_minimize_covering_crosses_switch),
        cmocka_unit_test(test_potentials_total_violation_equal_golden),
        cmocka_unit_test(test_potentials_total_violation_lower_unchanged),
        cmocka_unit_test(test_equality_encoding_sanity),
        cmocka_unit_test(test_opt_sat_equality_accept_flag_matches_eval),
        cmocka_unit_test(test_ctg_equality_never_reports_false_feasible),
        cmocka_unit_test(test_ctg_ignore_constraint_search_stays_in_opt_phase),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
