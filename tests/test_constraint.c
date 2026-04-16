#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "constraint.h"
#include "Expression.h"
#include "definitions.h"

/*
 * Helper: build a knapsack-style constraint from coefficients.
 *
 * Creates: coeffs[0]*x0 + coeffs[1]*x1 + ... + coeffs[n-1]*x(n-1)  sense  rhs
 *
 * Each variable term is built as a separate single-variable expression with
 * multiply_constant applied, then combined via add_expression.  This avoids
 * the multiply_constant-all-clauses pitfall (multiply_constant multiplies
 * ALL existing clauses in an expression).
 */
static expression_t *build_linear_expression(int n, int64_t *coeffs, int sense, int64_t rhs) {
    expression_t *combined = init_expression();
    for (int i = 0; i < n; i++) {
        if (coeffs[i] == 0) continue;
        expression_t *term = init_expression();
        add_variable(term, i);               /* 1*x_i */
        multiply_constant(term, coeffs[i]);  /* coeffs[i]*x_i */
        add_expression(combined, term);
        free_expression(term);
    }
    add_sense_to_expression(combined, sense);
    add_rhs_to_expression(combined, rhs);
    return combined;
}

static new_constraints_t build_knapsack_constraint(int n, int64_t *coeffs, int sense, int64_t rhs) {
    new_constraints_t con = init_new_constraint();
    expression_t *expr = build_linear_expression(n, coeffs, sense, rhs);
    add_expression_to_constraints(&con, expr);
    free_expression(expr);
    return con;
}

/* ------------------------------------------------------------------ */
/* test_init_new_constraint: verify init returns zeroed struct         */
/* ------------------------------------------------------------------ */
static void test_init_new_constraint(void **state) {
    (void)state;
    new_constraints_t con = init_new_constraint();
    assert_int_equal(con.num_constraints, 0);
    assert_non_null(con.factors);
    assert_non_null(con.num_clauses);
    assert_null(con.positive_indices);
    assert_null(con.negative_indices);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_add_single_expression: 2*x0 + 3*x1 <= 5                      */
/* ------------------------------------------------------------------ */
static void test_add_single_expression(void **state) {
    (void)state;
    int64_t coeffs[] = {2, 3};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    assert_int_equal(con.num_constraints, 1);
    assert_int_equal(con.sense[0], LOWER);
    assert_int_equal(con.rhs[0], 5);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_add_multiple_expressions: add 3 constraints                   */
/* ------------------------------------------------------------------ */
static void test_add_multiple_expressions(void **state) {
    (void)state;
    new_constraints_t con = init_new_constraint();

    for (int k = 0; k < 3; k++) {
        int64_t coeffs[] = {1, 1};
        expression_t *expr = build_linear_expression(2, coeffs, LOWER, k + 1);
        add_expression_to_constraints(&con, expr);
        free_expression(expr);
    }

    assert_int_equal(con.num_constraints, 3);
    assert_int_equal(con.rhs[0], 1);
    assert_int_equal(con.rhs[1], 2);
    assert_int_equal(con.rhs[2], 3);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_constraints_satisfied: x0 + x1 <= 2, state (1,0)        */
/* ------------------------------------------------------------------ */
static void test_eval_constraints_satisfied(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 2);

    preprocessing(2, &con);

    /* state: x0=1, x1=0 => sum=1 <= 2  => satisfied */
    int arr[] = {1, 0};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 1);  /* all satisfied */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_constraints_violated: x0 + x1 <= 0, state (1,1)         */
/* ------------------------------------------------------------------ */
static void test_eval_constraints_violated(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &con);

    /* state: x0=1, x1=1 => sum=2 > 0  => violated */
    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 0);  /* violated */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_objective_value: -1*x0 - 2*x1, state (1,1) => -3             */
/* ------------------------------------------------------------------ */
static void test_objective_value(void **state) {
    (void)state;
    int64_t coeffs[] = {-1, -2};
    new_constraints_t obj = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &obj);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    int64_t val = objective_value(&obj, sol);
    assert_int_equal(val, -3);

    free_state(sol, 1);
    free_constraints(&obj);
}

/* ------------------------------------------------------------------ */
/* test_objective_value_partial: 3*x0 + 5*x1, state (1,0) => 3       */
/* ------------------------------------------------------------------ */
static void test_objective_value_partial(void **state) {
    (void)state;
    int64_t coeffs[] = {3, 5};
    new_constraints_t obj = build_knapsack_constraint(2, coeffs, LOWER, 0);

    preprocessing(2, &obj);

    int arr[] = {1, 0};
    state_t *sol = init_state(0, arr, 2);

    int64_t val = objective_value(&obj, sol);
    assert_int_equal(val, 3);

    free_state(sol, 1);
    free_constraints(&obj);
}

/* ------------------------------------------------------------------ */
/* test_constraint_violation: x0 + x1 <= 1, state (1,1) => violation  */
/* ------------------------------------------------------------------ */
static void test_constraint_violation(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 1);

    preprocessing(2, &con);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    /* constraint_violation returns rhs - sum = 1 - 2 = -1 (negative means violated) */
    int violation = constraint_violation(&con, sol, 0);
    assert_true(violation < 0);  /* negative = violated */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_constraint_violation_satisfied: x0 + x1 <= 3, state (1,1)     */
/* ------------------------------------------------------------------ */
static void test_constraint_violation_satisfied(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 3);

    preprocessing(2, &con);

    int arr[] = {1, 1};
    state_t *sol = init_state(0, arr, 2);

    /* rhs - sum = 3 - 2 = 1 (positive = satisfied, slack = 1) */
    int violation = constraint_violation(&con, sol, 0);
    assert_true(violation >= 0);

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_preprocessing: verify index arrays are populated              */
/* ------------------------------------------------------------------ */
static void test_preprocessing(void **state) {
    (void)state;
    int64_t coeffs[] = {1, -2};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    assert_null(con.positive_indices);
    assert_null(con.negative_indices);

    preprocessing(2, &con);

    assert_non_null(con.positive_indices);
    assert_non_null(con.negative_indices);
    assert_non_null(con.positive_offsets);
    assert_non_null(con.negative_offsets);
    assert_non_null(con.num_positive_indices);
    assert_non_null(con.num_negative_indices);

    /* With 1*x0 and -2*x1, we should have at least 1 positive and 1 negative index */
    assert_true(con.positive_array_length > 0);
    assert_true(con.negative_array_length > 0);

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_preprocessing_exact_indices: verify exact index array contents */
/* for a small known problem with multiple constraints                */
/* ------------------------------------------------------------------ */
static void test_preprocessing_exact_indices(void **state) {
    (void)state;
    int n = 4;
    new_constraints_t con = init_new_constraint();

    /* Constraint 0: 2*x0 + 3*x1 - 1*x2 <= 5 */
    int64_t c0[] = {2, 3, -1, 0};
    expression_t *e0 = build_linear_expression(n, c0, LOWER, 5);
    add_expression_to_constraints(&con, e0);
    free_expression(e0);

    /* Constraint 1: -4*x1 + 5*x3 <= 10 */
    int64_t c1[] = {0, -4, 0, 5};
    expression_t *e1 = build_linear_expression(n, c1, LOWER, 10);
    add_expression_to_constraints(&con, e1);
    free_expression(e1);

    preprocessing(n, &con);

    uint64_t C = con.num_constraints;
    assert_int_equal(C, 2);

    /* x0: appears in constraint 0 with positive factor => 1 positive, 0 negative */
    assert_int_equal(con.num_positive_indices[0 * C + 0], 1);
    assert_int_equal(con.num_negative_indices[0 * C + 0], 0);
    assert_int_equal(con.num_positive_indices[0 * C + 1], 0);
    assert_int_equal(con.num_negative_indices[0 * C + 1], 0);

    /* x1: constraint 0 positive, constraint 1 negative */
    assert_int_equal(con.num_positive_indices[1 * C + 0], 1);
    assert_int_equal(con.num_negative_indices[1 * C + 0], 0);
    assert_int_equal(con.num_positive_indices[1 * C + 1], 0);
    assert_int_equal(con.num_negative_indices[1 * C + 1], 1);

    /* x2: constraint 0 negative */
    assert_int_equal(con.num_positive_indices[2 * C + 0], 0);
    assert_int_equal(con.num_negative_indices[2 * C + 0], 1);

    /* x3: constraint 1 positive */
    assert_int_equal(con.num_positive_indices[3 * C + 0], 0);
    assert_int_equal(con.num_positive_indices[3 * C + 1], 1);

    /* Verify total lengths */
    assert_int_equal(con.positive_array_length, 3);  /* x0:c0, x1:c0, x3:c1 */
    assert_int_equal(con.negative_array_length, 2);  /* x2:c0, x1:c1 */

    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_preprocessing_sparse_vs_dense: verify sparse produces same    */
/* clause mappings as dense for a multi-constraint problem            */
/* ------------------------------------------------------------------ */
static void test_preprocessing_sparse_vs_dense(void **state) {
    (void)state;
    int n = 6;
    new_constraints_t con_d = init_new_constraint();
    new_constraints_t con_s = init_new_constraint();

    /* Build identical constraints in both */
    int64_t c0[] = {1, -2, 3, 0, 0, 0};
    int64_t c1[] = {0, 0, 0, -1, 2, -3};
    int64_t c2[] = {1, 0, 0, 0, 0, 1};

    for (int pass = 0; pass < 2; pass++) {
        new_constraints_t *target = (pass == 0) ? &con_d : &con_s;
        expression_t *e;
        e = build_linear_expression(n, c0, LOWER, 10);
        add_expression_to_constraints(target, e);
        free_expression(e);
        e = build_linear_expression(n, c1, LOWER, 5);
        add_expression_to_constraints(target, e);
        free_expression(e);
        e = build_linear_expression(n, c2, LOWER, 3);
        add_expression_to_constraints(target, e);
        free_expression(e);
    }

    preprocessing(n, &con_d);
    preprocessing_sparse(n, &con_s);

    uint64_t C = con_d.num_constraints;

    /* Total index lengths must match */
    assert_int_equal(con_d.positive_array_length, con_s.positive_array_length);
    assert_int_equal(con_d.negative_array_length, con_s.negative_array_length);

    /* For each (item, cnstr): the clause indices stored must match */
    for (int item = 0; item < n; item++) {
        for (uint64_t cnstr = 0; cnstr < C; cnstr++) {
            /* Dense lookup */
            uint32_t npi_d = con_d.num_positive_indices[item * C + cnstr];
            uint32_t nni_d = con_d.num_negative_indices[item * C + cnstr];

            /* Sparse lookup */
            int64_t idx_pos = get_index(con_s.pos_cols, con_s.pos_rows, item, cnstr, con_s.nnz_pos, C);
            int64_t idx_neg = get_index(con_s.neg_cols, con_s.neg_rows, item, cnstr, con_s.nnz_neg, C);
            uint32_t npi_s = (idx_pos >= 0) ? con_s.num_positive_indices[idx_pos] : 0;
            uint32_t nni_s = (idx_neg >= 0) ? con_s.num_negative_indices[idx_neg] : 0;

            assert_int_equal(npi_d, npi_s);
            assert_int_equal(nni_d, nni_s);

            /* Check actual clause indices match */
            for (uint32_t k = 0; k < npi_d; k++) {
                uint32_t cls_d = con_d.positive_indices[con_d.positive_offsets[item * C + cnstr] + k];
                uint32_t cls_s = con_s.positive_indices[con_s.positive_offsets[idx_pos] + k];
                assert_int_equal(cls_d, cls_s);
            }
            for (uint32_t k = 0; k < nni_d; k++) {
                uint32_t cls_d = con_d.negative_indices[con_d.negative_offsets[item * C + cnstr] + k];
                uint32_t cls_s = con_s.negative_indices[con_s.negative_offsets[idx_neg] + k];
                assert_int_equal(cls_d, cls_s);
            }
        }
    }

    free_constraints(&con_d);
    free_constraints(&con_s);
}

/* ------------------------------------------------------------------ */
/* test_preprocessing_many_vars: verify with a larger problem (50 vars) */
/* that incremental evaluation still matches full recalc               */
/* ------------------------------------------------------------------ */
static void test_preprocessing_many_vars(void **state) {
    (void)state;
    int n = 50;
    new_constraints_t con = init_new_constraint();

    /* Build 3 constraints with various coefficients */
    int64_t *c0 = calloc(n, sizeof(int64_t));
    int64_t *c1 = calloc(n, sizeof(int64_t));
    int64_t *c2 = calloc(n, sizeof(int64_t));
    for (int i = 0; i < n; i++) {
        c0[i] = (i % 3 == 0) ? (i + 1) : ((i % 3 == 1) ? -(i + 1) : 0);
        c1[i] = (i % 5 == 0) ? (2 * i + 1) : 0;
        c2[i] = (i < 10) ? 1 : ((i > 40) ? -1 : 0);
    }

    expression_t *e;
    e = build_linear_expression(n, c0, LOWER, 100);
    add_expression_to_constraints(&con, e); free_expression(e);
    e = build_linear_expression(n, c1, LOWER, 200);
    add_expression_to_constraints(&con, e); free_expression(e);
    e = build_linear_expression(n, c2, LOWER, 5);
    add_expression_to_constraints(&con, e); free_expression(e);

    preprocessing(n, &con);

    /* Verify all offsets and counts are consistent */
    uint64_t C = con.num_constraints;
    uint32_t total_pos = 0, total_neg = 0;
    for (int item = 0; item < n; item++) {
        for (uint64_t cnstr = 0; cnstr < C; cnstr++) {
            uint32_t npi = con.num_positive_indices[item * C + cnstr];
            uint32_t nni = con.num_negative_indices[item * C + cnstr];
            if (npi > 0) {
                assert_true(con.positive_offsets[item * C + cnstr] + npi <= con.positive_array_length);
            }
            if (nni > 0) {
                assert_true(con.negative_offsets[item * C + cnstr] + nni <= con.negative_array_length);
            }
            total_pos += npi;
            total_neg += nni;
        }
    }
    assert_int_equal(total_pos, con.positive_array_length);
    assert_int_equal(total_neg, con.negative_array_length);

    /* Verify incremental evaluation still works with new preprocessing */
    int *arr = calloc(n, sizeof(int));
    for (int i = 0; i < n; i += 2) arr[i] = 1;
    state_t *sol = init_state(0, arr, n);

    int64_t *remainings = malloc(C * sizeof(int64_t));
    for (uint32_t i = 0; i < C; ++i)
        remainings[i] = constraint_violation(&con, sol, i);

    /* Test a few variable flips */
    for (int flip_var = 0; flip_var < n; flip_var += 7) {
        sw_flpbit(sol->vector, flip_var);

        int64_t *full_after = malloc(C * sizeof(int64_t));
        for (uint32_t i = 0; i < C; ++i)
            full_after[i] = constraint_violation(&con, sol, i);

        sw_flpbit(sol->vector, flip_var);
        array_t ful_con = sw_init(con.total_clauses);
        prepare_constraints(&con, sol, &ful_con);
        sw_flpbit(sol->vector, flip_var);

        int64_t *totals = calloc(C, sizeof(int64_t));
        array_t inv = sw_init(con.total_clauses);
        int *changed_con = calloc(MINSIZE, sizeof(int));
        int num_con_changes = 0;

        adjusted_constraint_violation(&con, flip_var,
            con.positive_indices, con.num_positive_indices,
            con.positive_offsets, sol, POSITIVE,
            totals, &ful_con, &changed_con, &num_con_changes, &inv);
        adjusted_constraint_violation(&con, flip_var,
            con.negative_indices, con.num_negative_indices,
            con.negative_offsets, sol, NEGATIVE,
            totals, &ful_con, &changed_con, &num_con_changes, &inv);

        for (uint32_t c = 0; c < C; ++c) {
            int64_t incremental_result = remainings[c] - totals[c];
            assert_int_equal(full_after[c], incremental_result);
        }

        sw_flpbit(sol->vector, flip_var);
        free(changed_con);
        sw_clear(inv);
        sw_clear(ful_con);
        free(totals);
        free(full_after);
    }

    free(remainings);
    free_state(sol, 1);
    free(arr);
    free(c0); free(c1); free(c2);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_eval_all_zero_state: x0 + x1 <= 5, state (0,0) => satisfied  */
/* ------------------------------------------------------------------ */
static void test_eval_all_zero_state(void **state) {
    (void)state;
    int64_t coeffs[] = {1, 1};
    new_constraints_t con = build_knapsack_constraint(2, coeffs, LOWER, 5);

    preprocessing(2, &con);

    int arr[] = {0, 0};
    state_t *sol = init_state(0, arr, 2);

    int result = eval_constraints(&con, sol, 2);
    assert_int_equal(result, 1);  /* 0 <= 5 satisfied */

    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_incremental_vs_full_recalc: INCR-03 correctness verification   */
/* Compares constraint_violation() full-recalc against                  */
/* adjusted_constraint_violation() incremental path for exact equality  */
/* ------------------------------------------------------------------ */
static void test_incremental_vs_full_recalc(void **state) {
    (void)state;
    int n = 8;
    new_constraints_t con = init_new_constraint();

    /* Constraint 0: 3*x0 + 2*x1 - 1*x2 + 4*x3 <= 6 */
    int64_t coeffs0[] = {3, 2, -1, 4, 0, 0, 0, 0};
    expression_t *e0 = build_linear_expression(n, coeffs0, LOWER, 6);
    add_expression_to_constraints(&con, e0);
    free_expression(e0);

    /* Constraint 1: -2*x0 + 5*x1 + 1*x4 + 3*x5 <= 8 */
    int64_t coeffs1[] = {-2, 5, 0, 0, 1, 3, 0, 0};
    expression_t *e1 = build_linear_expression(n, coeffs1, LOWER, 8);
    add_expression_to_constraints(&con, e1);
    free_expression(e1);

    /* Constraint 2: 1*x2 + 1*x3 + 1*x6 + 1*x7 <= 3 */
    int64_t coeffs2[] = {0, 0, 1, 1, 0, 0, 1, 1};
    expression_t *e2 = build_linear_expression(n, coeffs2, LOWER, 3);
    add_expression_to_constraints(&con, e2);
    free_expression(e2);

    /* Preprocess for incremental access */
    preprocessing(n, &con);

    /* Create solution: x0=1, x1=1, x3=1, x5=1 */
    int arr[] = {1, 1, 0, 1, 0, 1, 0, 0};
    state_t *sol = init_state(0, arr, n);

    uint32_t C = con.num_constraints;

    /* Compute baseline remainings using full-recalc */
    int64_t *remainings = malloc(C * sizeof(int64_t));
    for (uint32_t i = 0; i < C; ++i)
        remainings[i] = constraint_violation(&con, sol, i);

    /* Test flipping each variable individually and comparing paths */
    for (int flip_var = 0; flip_var < n; ++flip_var) {
        /* Flip the variable */
        sw_flpbit(sol->vector, flip_var);

        /* Full-recalc after flip */
        int64_t *full_after = malloc(C * sizeof(int64_t));
        for (uint32_t i = 0; i < C; ++i)
            full_after[i] = constraint_violation(&con, sol, i);

        /* Incremental after flip: prepare ful_con from ORIGINAL solution */
        sw_flpbit(sol->vector, flip_var); /* back to original */
        array_t ful_con = sw_init(con.total_clauses);
        prepare_constraints(&con, sol, &ful_con);
        sw_flpbit(sol->vector, flip_var); /* flip again */

        int64_t *totals = calloc(C, sizeof(int64_t));
        array_t inv = sw_init(con.total_clauses);
        int *changed_con = calloc(MINSIZE, sizeof(int));
        int num_con_changes = 0;

        adjusted_constraint_violation(&con, flip_var,
            con.positive_indices, con.num_positive_indices,
            con.positive_offsets, sol, POSITIVE,
            totals, &ful_con, &changed_con, &num_con_changes, &inv);
        adjusted_constraint_violation(&con, flip_var,
            con.negative_indices, con.num_negative_indices,
            con.negative_offsets, sol, NEGATIVE,
            totals, &ful_con, &changed_con, &num_con_changes, &inv);

        /* Compare: incremental = remainings[c] - totals[c] should match full_after[c] */
        for (uint32_t c = 0; c < C; ++c) {
            int64_t incremental_result = remainings[c] - totals[c];
            assert_int_equal(full_after[c], incremental_result);
        }

        /* Unflip to restore original state for next iteration */
        sw_flpbit(sol->vector, flip_var);

        free(changed_con);
        sw_clear(inv);
        sw_clear(ful_con);
        free(totals);
        free(full_after);
    }

    free(remainings);
    free_state(sol, 1);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_prealloc_large_expression: verify that a large expression      */
/* (exceeding MINARRAYSIZE) is stored correctly with pre-allocation    */
/* ------------------------------------------------------------------ */
static void test_prealloc_large_expression(void **state) {
    (void)state;
    int n = 60000;  /* exceeds MINARRAYSIZE (50000) */
    new_constraints_t con = init_new_constraint();

    /* Build a large linear expression: 1*x0 + 2*x1 + ... + n*x(n-1) */
    expression_t *expr = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *term = init_expression();
        add_variable(term, i);
        multiply_constant(term, (int64_t)(i + 1));
        add_expression(expr, term);
        free_expression(term);
    }
    add_sense_to_expression(expr, LOWER);
    add_rhs_to_expression(expr, 999);

    add_expression_to_constraints(&con, expr);

    /* Verify basic structure */
    assert_int_equal(con.num_constraints, 1);
    assert_int_equal(con.num_clauses[0], n);
    assert_int_equal(con.rhs[0], 999);
    assert_int_equal(con.sense[0], LOWER);

    /* Spot-check some factors and variables */
    assert_int_equal(con.factors[0], 1);
    assert_int_equal(con.factors[n - 1], n);
    assert_int_equal(con.variables[variable_index(0, 0, 0)], 0);
    assert_int_equal(con.variables[variable_index(n - 1, 0, 0)], n - 1);

    /* Verify capacity was pre-allocated (at least enough for n clauses) */
    assert_true(con.allocated_factors >= (size_t)n);
    assert_true(con.allocated_variables >= (size_t)n * (CONSTRAINT_VARS_PER_CLAUSE - 1));

    free_expression(expr);
    free_constraints(&con);
}

/* ------------------------------------------------------------------ */
/* test_prealloc_two_large_expressions: verify pre-allocation works    */
/* correctly when adding multiple large expressions sequentially       */
/* ------------------------------------------------------------------ */
static void test_prealloc_two_large_expressions(void **state) {
    (void)state;
    int n = 55000;  /* exceeds MINARRAYSIZE */
    new_constraints_t con = init_new_constraint();

    /* Add first large expression */
    expression_t *e1 = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *term = init_expression();
        add_variable(term, i);
        multiply_constant(term, 1);
        add_expression(e1, term);
        free_expression(term);
    }
    add_sense_to_expression(e1, LOWER);
    add_rhs_to_expression(e1, 100);
    add_expression_to_constraints(&con, e1);
    free_expression(e1);

    /* Add second large expression */
    expression_t *e2 = init_expression();
    for (int i = 0; i < n; i++) {
        expression_t *term = init_expression();
        add_variable(term, i);
        multiply_constant(term, 2);
        add_expression(e2, term);
        free_expression(term);
    }
    add_sense_to_expression(e2, LOWER);
    add_rhs_to_expression(e2, 200);
    add_expression_to_constraints(&con, e2);
    free_expression(e2);

    assert_int_equal(con.num_constraints, 2);
    assert_int_equal(con.num_clauses[0], n);
    assert_int_equal(con.num_clauses[1], n);
    assert_int_equal(con.rhs[0], 100);
    assert_int_equal(con.rhs[1], 200);

    /* Check factors for second constraint */
    size_t offset = first_clause_index(&con, 1);
    assert_int_equal(con.factors[offset], 2);
    assert_int_equal(con.factors[offset + n - 1], 2);

    /* Check variables for second constraint */
    assert_int_equal(con.variables[variable_index(0, 0, offset)], 0);
    assert_int_equal(con.variables[variable_index(n - 1, 0, offset)], n - 1);

    free_constraints(&con);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_init_new_constraint),
        cmocka_unit_test(test_add_single_expression),
        cmocka_unit_test(test_add_multiple_expressions),
        cmocka_unit_test(test_eval_constraints_satisfied),
        cmocka_unit_test(test_eval_constraints_violated),
        cmocka_unit_test(test_objective_value),
        cmocka_unit_test(test_objective_value_partial),
        cmocka_unit_test(test_constraint_violation),
        cmocka_unit_test(test_constraint_violation_satisfied),
        cmocka_unit_test(test_preprocessing),
        cmocka_unit_test(test_preprocessing_exact_indices),
        cmocka_unit_test(test_preprocessing_sparse_vs_dense),
        cmocka_unit_test(test_preprocessing_many_vars),
        cmocka_unit_test(test_eval_all_zero_state),
        cmocka_unit_test(test_incremental_vs_full_recalc),
        cmocka_unit_test(test_prealloc_large_expression),
        cmocka_unit_test(test_prealloc_two_large_expressions),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
