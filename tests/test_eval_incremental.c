/*
 * bd 0o8.2 (exact win A): bit-for-bit cross-check of the incremental
 * candidate-construction marginals (incr_eval.c) against the UNCHANGED dense
 * look_ahead_correct()/evaluation() (cbqs/src/solver.c) at depth_look_ahead==0.
 *
 * The oracle is the REAL look_ahead_correct (must-fix #3): for every variable,
 * both assignments {0,1}, and across a running multi-variable sweep (potentials
 * advanced via update_potentials exactly as CSearch_opt does), assert
 * incr_marginal()'s ret_total[] AND feasibility verdict equal look_ahead_correct's
 * on EVERY call. Exercises both the POSITIVE arm (capacity `<=`, positive factors)
 * and the live NEGATIVE arm (a negated-LOWER `>=` covering constraint, negative
 * factors) under identity (rank==NULL) and a non-identity traversal order (rank!=NULL).
 */
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <stdint.h>
#include <string.h>
#include <cmocka.h>

#include "solver.h"
#include "model.h"
#include "constraint.h"
#include "Expression.h"
#include "solver_ctx.h"
#include "definitions.h"
#include "incr_eval.h"

/* Dense bilinear model: C0 = capacity (<=, positive factors, diagonal + all pairs),
 * C1 = covering (>= built as LOWER with negated factors -> NEGATIVE arm live). */
static model_t *build_dense_bilinear(int n, int64_t le_rhs, int64_t cov_rhs) {
    model_t *mod = init_model();

    /* C0: sum_i cap_ii x_i + sum_{i<j} cap_ij x_i x_j  <=  le_rhs   (positive) */
    expression_t *cap = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *t = init_expression();
        add_variable(t, i);
        multiply_variable(t, i);                       /* x_i*x_i: eq29-style diagonal */
        multiply_constant(t, 1 + ((i * 3 + 1) % 5));   /* positive diagonal */
        add_expression(cap, t);
        free_expression(t);
        for (int j = i + 1; j < n; j++) {
            expression_t *p = init_expression();
            add_variable(p, i);
            multiply_variable(p, j);
            multiply_constant(p, 1 + ((i * 7 + j * 2) % 6)); /* positive pair */
            add_expression(cap, p);
            free_expression(p);
        }
    }
    add_sense_to_expression(cap, LOWER);
    add_rhs_to_expression(cap, le_rhs);
    add_expression_to_constraints(mod->con, cap);
    free_expression(cap);

    /* C1: -(sum_i cov_ii x_i + sum_{i<j} cov_ij x_i x_j) <= -cov_rhs  (negative) */
    expression_t *cov = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *t = init_expression();
        add_variable(t, i);
        multiply_variable(t, i);                         /* x_i*x_i: eq29-style diagonal */
        multiply_constant(t, -(1 + ((i * 2 + 3) % 4)));  /* negative diagonal */
        add_expression(cov, t);
        free_expression(t);
        for (int j = i + 1; j < n; j++) {
            expression_t *p = init_expression();
            add_variable(p, i);
            multiply_variable(p, j);
            multiply_constant(p, -(1 + ((i * 5 + j * 3) % 5))); /* negative pair */
            add_expression(cov, p);
            free_expression(p);
        }
    }
    add_sense_to_expression(cov, LOWER);
    add_rhs_to_expression(cov, -cov_rhs);
    add_expression_to_constraints(mod->con, cov);
    free_expression(cov);

    /* trivial objective (unused by the eval cross-check) */
    expression_t *obj = init_expression();
    add_variable(obj, 0);
    multiply_constant(obj, -1);
    add_sense_to_expression(obj, LOWER);
    add_rhs_to_expression(obj, 0);
    add_expression_to_constraints(mod->obj, obj);
    free_expression(obj);

    preprocessing(n, mod->con);
    preprocessing(n, mod->obj);

    int arr[64] = {0};
    mod->initial_state = init_state(0, arr, n);
    mod->global_opt = init_state(0, arr, n);
    mod->n = n;
    mod->depth_look_ahead = 0;
    return mod;
}

/* Drive a full sweep under `order`/`rank`, cross-checking incr vs the dense oracle
 * at every (position, assignment). Returns the number of positions cross-checked. */
static int sweep_crosscheck(model_t *mod, int n, const int *order, const int *rank) {
    new_constraints_t *con = mod->con;
    const size_t C = con->num_constraints;

    incr_state_t *st = incr_create(con, n, order, rank);
    assert_non_null(st);                 /* bilinear -> fast path must apply */
    incr_reset(st);

    int arr[64] = {0};
    state_t *sol = init_state(0, arr, n);

    int64_t *pot = malloc(C * sizeof(int64_t));
    memcpy(pot, con->rhs, C * sizeof(int64_t));

    int64_t ref1[8] = {0}, ref2[8] = {0}, inc1[8] = {0}, inc2[8] = {0};
    uint64_t lcg = 0x9e3779b97f4a7c15ULL;   /* deterministic free-decision driver */
    int checked = 0;

    for (int k = 0; k < n; k++) {
        int item = order ? order[k] : k;

        /* reference (the REAL look_ahead_correct, depth_pos==k => single evaluation) */
        memset(ref1, 0, C * sizeof(int64_t));
        memset(ref2, 0, C * sizeof(int64_t));
        int cref0 = 0, cref1 = 0;
        look_ahead_correct(k, 0, k, &cref0, con, pot, sol, ref1, order, rank); /* NEG arm */
        look_ahead_correct(k, 1, k, &cref1, con, pot, sol, ref2, order, rank); /* POS arm */

        /* incremental */
        int cinc0 = 0, cinc1 = 0;
        incr_marginal(st, item, pot, inc2, &cinc1, inc1, &cinc0); /* POS->inc2/cinc1, NEG->inc1/cinc0 */

        for (size_t c = 0; c < C; c++) {
            assert_int_equal(inc1[c], ref1[c]);   /* NEGATIVE-arm ret_total */
            assert_int_equal(inc2[c], ref2[c]);   /* POSITIVE-arm ret_total */
        }
        assert_int_equal(cinc0, cref0);           /* assign=0 feasibility */
        assert_int_equal(cinc1, cref1);           /* assign=1 feasibility */
        checked++;

        /* decide new_bit exactly as CSearch_opt would classify it */
        int new_bit;
        if (cref0 == 0 && cref1 == 0) break;      /* dead end: sweep stops */
        else if (cref1 == 0) new_bit = 0;         /* forced 0 */
        else if (cref0 == 0) new_bit = 1;         /* forced 1 */
        else { lcg = lcg * 6364136223846793005ULL + 1; new_bit = (int)((lcg >> 33) & 1); }

        if (new_bit) sw_setbit(sol->vector, item); else sw_clrbit(sol->vector, item);
        incr_commit(st, item, new_bit);
        update_potentials(con, pot, PLAIN, new_bit ? ref2 : ref1);
    }

    free(pot);
    free_state(sol, 1);
    incr_free(st);
    return checked;
}

static void test_incremental_matches_dense_identity(void **state) {
    (void)state;
    int n = 6;
    model_t *mod = build_dense_bilinear(n, 200, 30);
    int checked = sweep_crosscheck(mod, n, NULL, NULL);   /* rank==NULL */
    assert_true(checked >= 1);
    free_model(mod);
}

static void test_incremental_matches_dense_reordered(void **state) {
    (void)state;
    int n = 6;
    /* a non-identity order + its inverse rank */
    int order[6] = {3, 0, 5, 1, 4, 2};
    int rank[6];
    for (int k = 0; k < n; k++) rank[order[k]] = k;
    model_t *mod = build_dense_bilinear(n, 200, 30);
    int checked = sweep_crosscheck(mod, n, order, rank);
    assert_true(checked >= 1);
    free_model(mod);
}

/* Loose rhs => full sweep, every position cross-checked (ret_total exercised fully). */
static void test_incremental_full_sweep_loose(void **state) {
    (void)state;
    int n = 7;
    model_t *mod = build_dense_bilinear(n, 1 << 20, 0);
    int checked_id = sweep_crosscheck(mod, n, NULL, NULL);
    assert_int_equal(checked_id, n);                      /* loose => no early break */
    free_model(mod);

    int order[7] = {6, 2, 0, 4, 1, 5, 3};
    int rank[7];
    for (int k = 0; k < n; k++) rank[order[k]] = k;
    model_t *mod2 = build_dense_bilinear(n, 1 << 20, 0);
    int checked_rk = sweep_crosscheck(mod2, n, order, rank);
    assert_int_equal(checked_rk, n);
    free_model(mod2);
}

/* k-ary (clause length 3) => incr_create must decline (dense fallback). */
static void test_incremental_declines_kary(void **state) {
    (void)state;
    int n = 4;
    model_t *mod = init_model();
    expression_t *e = init_expression();
    add_variable(e, 0);
    multiply_variable(e, 1);
    multiply_variable(e, 2);            /* x0*x1*x2 : length-3 clause */
    add_sense_to_expression(e, LOWER);
    add_rhs_to_expression(e, 0);
    add_expression_to_constraints(mod->con, e);
    free_expression(e);
    expression_t *obj = init_expression();
    add_variable(obj, 0); multiply_constant(obj, -1);
    add_sense_to_expression(obj, LOWER); add_rhs_to_expression(obj, 0);
    add_expression_to_constraints(mod->obj, obj);
    free_expression(obj);
    preprocessing(n, mod->con);
    preprocessing(n, mod->obj);
    int arr[4] = {0};
    mod->initial_state = init_state(0, arr, n);
    mod->global_opt = init_state(0, arr, n);
    mod->n = n;

    incr_state_t *st = incr_create(mod->con, n, NULL, NULL);
    assert_null(st);                    /* length>2 => not applicable */
    free_model(mod);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_incremental_matches_dense_identity),
        cmocka_unit_test(test_incremental_matches_dense_reordered),
        cmocka_unit_test(test_incremental_full_sweep_loose),
        cmocka_unit_test(test_incremental_declines_kary),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
