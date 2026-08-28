/*
 * tests/test_angle_precision.c -- bd a0w (M5): the ANGLE-PRECISION lever.
 *
 * On hardware the QTG's per-variable rotation R_y(theta_i) is not exact: it is
 * synthesized by Ross-Selinger / gridsynth to an absolute accuracy `eps` at a
 * T-count ~3*log2(1/eps). This lever models that inside BranchingFunction by
 * quantizing THETA (never the probability `value`): the physical knob is the
 * angle, and a uniform grid in probability space is unfaithful and far too
 * coarse near p ~ 0, which is exactly where CBQS operates (p_flip = r/n).
 *
 *   p_flip = 1 - value = sin^2(theta/2)      (the QTG amplitude convention)
 *   systematic : theta_q = 2*eps * round(theta / (2*eps))   [|dtheta| <= eps]
 *   dithered   : theta_q = theta + eps * u(index)           [|dtheta| <= eps]
 *
 * These tests pin, in order of load-bearingness:
 *   (1) eps <= 0 is the OFF switch and is BIT-FOR-BIT the pre-a0w path -- the
 *       NORTHSTAR §8 branching golden 6/7 at bias=5 must survive exactly;
 *   (2) the synthesis-accuracy contract |theta_q - theta| <= eps in both modes;
 *   (3) BOUNDED DECISIONS (§1.7): every eps, including a grid so coarse it
 *       snaps theta to 0 at the n=3000 operating point, must leave the returned
 *       probability strictly inside (0,1) -- a naive grid would force greedy;
 *   (4) the dither is a DETERMINISTIC pure function of the variable index
 *       (reproducible under a fixed seed -> the §8 determinism baseline holds).
 */
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <string.h>

#include "Branching.h"
#include "solver_ctx.h"
#include "definitions.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* n=3000 at the shipped radius r~2: bias = n/r - 2 = 1498, p_flip = 2/3000. */
#define BIAS_N3000_R2 1498.0
#define P_N3000_R2    (2.0 / 3000.0)

static int ap_setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) return -1;
    *state = ctx;
    return 0;
}

static int ap_teardown(void **state) {
    solver_ctx_free((solver_ctx_t *)*state);
    *state = NULL;
    return 0;
}

/* Reference: the angle the lever quantizes, from the un-quantized probability. */
static double theta_of(double value) { return 2.0 * asin(sqrt(1.0 - value)); }

/* ============================================================
 * (1) OFF is bit-for-bit the pre-a0w path
 * ============================================================ */

/* Default-constructed stats must have the lever OFF. */
static void test_defaults_are_off(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    assert_true(ctx->branching_stats.angle_precision_eps == 0.0);
    assert_int_equal(ctx->branching_stats.angle_precision_dither, 0);
    assert_true(ctx->branching_stats_sat.angle_precision_eps == 0.0);
    assert_true(ctx->branching_stats_opt_sat.angle_precision_eps == 0.0);
    assert_true(ctx->branching_stats_opt.angle_precision_eps == 0.0);
}

/* THE golden (NORTHSTAR §8): bias=5, no weights => exactly 6/7, lever off. */
static void test_golden_6_over_7_preserved(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, 5.0);
    double v = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(v == 6.0 / 7.0);   /* bit-for-bit, not assert_float_equal */
}

/* eps <= 0 (and the untouched default) are the same OFF switch. */
static void test_nonpositive_eps_is_off(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, 5.0);
    double base = BranchingFunction(3, 0, 0, 0, &ctx->branching_stats);
    for (int dither = 0; dither <= 1; dither++) {
        solver_ctx_set_angle_precision(ctx, 0.0, dither);
        assert_true(BranchingFunction(3, 0, 0, 0, &ctx->branching_stats) == base);
        solver_ctx_set_angle_precision(ctx, -1.0, dither);
        assert_true(BranchingFunction(3, 0, 0, 0, &ctx->branching_stats) == base);
    }
}

/* The OFF path is byte-identical for the WHOLE (bit_S, bit_T) truth table and
 * through the per-variable weights path, not just the golden cell. */
static void test_off_matches_baseline_everywhere(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double w[4] = {0.7, -0.3, 0.0, 1.9};
    solver_ctx_set_bias(ctx, 5.0);
    solver_ctx_set_branching_weights(ctx, w, 4);
    double ref[4][2][2];
    for (int i = 0; i < 4; i++)
        for (int s = 0; s < 2; s++)
            for (int t = 0; t < 2; t++)
                ref[i][s][t] = BranchingFunction(i, s, t, 0, &ctx->branching_stats);
    solver_ctx_set_angle_precision(ctx, 0.0, 1);   /* dither armed but eps off */
    for (int i = 0; i < 4; i++)
        for (int s = 0; s < 2; s++)
            for (int t = 0; t < 2; t++)
                assert_true(BranchingFunction(i, s, t, 0, &ctx->branching_stats) == ref[i][s][t]);
}

/* ============================================================
 * (2) synthesis-accuracy contract: |theta_q - theta| <= eps
 * ============================================================ */

static void test_quantize_respects_eps(void **state) {
    (void)state;
    /* includes p -> 1 (theta -> pi), where a coarse grid pushes theta_q PAST pi
     * and the sin^2 branch folds back down -- the case the production path can
     * reach whenever a per-variable theta_i drives `value` toward 0. */
    const double values[] = {6.0 / 7.0, 0.5, 0.999, 1.0 - P_N3000_R2, 0.1,
                             1e-9, 1e-6, 0.001};
    const double epss[]   = {0.5, 0.25, 0.1, 0.03, 0.01, 0.001, 1e-5};
    for (size_t vi = 0; vi < sizeof(values) / sizeof(values[0]); vi++) {
        double theta = theta_of(values[vi]);
        for (size_t ei = 0; ei < sizeof(epss) / sizeof(epss[0]); ei++) {
            for (int dither = 0; dither <= 1; dither++) {
                for (int idx = 0; idx < 32; idx++) {
                    double vq = branch_quantize_angle(values[vi], epss[ei], dither, idx);
                    double theta_q = theta_of(vq);
                    /* theta_of() returns the PRINCIPAL branch in [0, pi]. sin^2
                     * is even and pi-symmetric, so a theta_q outside [0, pi]
                     * comes back folded; the accuracy contract must be checked
                     * against the nearest congruent representative. */
                    double d = fabs(theta_q - theta);
                    double folded = fabs((2.0 * M_PI - theta_q) - theta);
                    if (folded < d) d = folded;
                    /* the clamp caps |dtheta| at the extremes, never widens it */
                    assert_true(d <= epss[ei] + 1e-9);
                }
            }
        }
    }
}

/* Monotone convergence: v_q -> v as eps shrinks (both modes). */
static void test_monotone_convergence(void **state) {
    (void)state;
    const double v = 1.0 - P_N3000_R2;
    double prev_sys = 1.0, prev_dit = 1.0;
    for (double eps = 0.1; eps > 1e-7; eps /= 10.0) {
        double e_sys = fabs(branch_quantize_angle(v, eps, 0, 7) - v);
        double e_dit = fabs(branch_quantize_angle(v, eps, 1, 7) - v);
        assert_true(e_sys <= prev_sys + 1e-15);
        assert_true(e_dit <= prev_dit + 1e-15);
        prev_sys = e_sys; prev_dit = e_dit;
    }
    assert_true(prev_sys < 1e-6);
    assert_true(prev_dit < 1e-6);
}

/* ============================================================
 * (3) BOUNDED DECISIONS (§1.7) at every eps -- the fail-loud case
 * ============================================================ */

/* At n=3000, r=2 the angle is theta = 2*asin(sqrt(2/3000)) ~ 0.0516 rad. A grid
 * with eps >= theta/2 rounds it to ZERO: p_flip = 0, a deterministic greedy
 * assignment. The lever must clamp, never return exactly 0 or 1. */
static void test_bounded_decisions_coarse_grid_n3000(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, BIAS_N3000_R2);
    const double epss[] = {0.5, 0.25, 0.125, 0.0625, 0.03, 0.015, 0.008,
                           0.004, 0.002, 0.001, 1e-6};
    for (size_t ei = 0; ei < sizeof(epss) / sizeof(epss[0]); ei++) {
        for (int dither = 0; dither <= 1; dither++) {
            solver_ctx_set_angle_precision(ctx, epss[ei], dither);
            for (int idx = 0; idx < 256; idx++) {
                /* The (bit_S, bit_T) = (0,0) cell returns the decision value
                 * itself; that is where the (BRANCH_EPS, 1-BRANCH_EPS) bracket
                 * lives. The flipped cells return 1 - value, whose bracket is
                 * only exact up to one ulp (1 - (1 - 1e-9) == 9.9999997e-10),
                 * so those are held to the invariant that actually matters:
                 * STRICTLY inside (0, 1) -- never a forced assignment. */
                double v = BranchingFunction(idx, 0, 0, 0, &ctx->branching_stats);
                assert_true(v >= BRANCH_EPS);
                assert_true(v <= 1.0 - BRANCH_EPS);
                for (int s = 0; s < 2; s++) {
                    for (int t = 0; t < 2; t++) {
                        double p = BranchingFunction(idx, s, t, 0, &ctx->branching_stats);
                        assert_true(p > 0.0);
                        assert_true(p < 1.0);
                        assert_false(isnan(p));
                    }
                }
            }
        }
    }
}

/* The snap-to-zero case is REACHED (the test above would pass vacuously if the
 * grid never actually rounded theta to 0): a coarse systematic grid must pin
 * the flip probability at the clamp floor, not somewhere in the interior. */
static void test_systematic_grid_snaps_to_clamp(void **state) {
    (void)state;
    const double v = 1.0 - P_N3000_R2;             /* theta ~ 0.0516 */
    double vq = branch_quantize_angle(v, 0.5, 0, 11);
    assert_true(vq == 1.0 - BRANCH_EPS);           /* clamped, NOT exactly 1.0 */
    assert_true(1.0 - vq > 0.0);
}

/* Bounded decisions must also hold through the per-variable weights path. */
static void test_bounded_decisions_with_weights(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    double w[8] = {-40.0, -5.0, -0.5, 0.0, 0.5, 5.0, 40.0, 1e3};
    solver_ctx_set_bias(ctx, BIAS_N3000_R2);
    solver_ctx_set_branching_weights(ctx, w, 8);
    for (double eps = 0.5; eps > 1e-7; eps /= 4.0) {
        for (int dither = 0; dither <= 1; dither++) {
            solver_ctx_set_angle_precision(ctx, eps, dither);
            for (int i = 0; i < 8; i++) {
                double p = BranchingFunction(i, 0, 0, 0, &ctx->branching_stats);
                assert_true(p >= BRANCH_EPS && p <= 1.0 - BRANCH_EPS);
                assert_false(isnan(p));
            }
        }
    }
}

/* ============================================================
 * (4) the dither is a deterministic pure function of the index
 * ============================================================ */

static void test_dither_is_deterministic(void **state) {
    (void)state;
    for (int idx = 0; idx < 64; idx++) {
        double a = branch_dither_u(idx);
        double b = branch_dither_u(idx);
        assert_true(a == b);                       /* bit-for-bit reproducible */
        assert_true(a >= -1.0 && a < 1.0);
    }
}

/* Zero-mean-ish and actually varying: the sqrt(n) averaging the lever models
 * only holds if u is not a constant. */
static void test_dither_is_zero_mean_and_varying(void **state) {
    (void)state;
    const int N = 4096;
    double sum = 0.0;
    int distinct = 0;
    double first = branch_dither_u(0);
    for (int i = 0; i < N; i++) {
        double u = branch_dither_u(i);
        sum += u;
        if (u != first) distinct++;
    }
    assert_true(distinct > N / 2);
    assert_true(fabs(sum / N) < 0.05);             /* |mean| well inside 1/sqrt(N) x 3 */
}

/* With dither ON, different variables get different quantized angles; with it
 * OFF they all get the SAME one (the coherent/systematic case). */
static void test_dither_varies_per_index_systematic_does_not(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_bias(ctx, BIAS_N3000_R2);

    solver_ctx_set_angle_precision(ctx, 0.01, 0);
    double v0 = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    for (int i = 1; i < 32; i++)
        assert_true(BranchingFunction(i, 0, 0, 0, &ctx->branching_stats) == v0);

    solver_ctx_set_angle_precision(ctx, 0.01, 1);
    int differ = 0;
    double d0 = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    for (int i = 1; i < 32; i++)
        if (BranchingFunction(i, 0, 0, 0, &ctx->branching_stats) != d0) differ++;
    assert_true(differ >= 30);
}

/* The physics the sweep tests: systematic rounding is COHERENT (the realized
 * radius n*p_q is off by ~n*dp), dithered rounding AVERAGES (~sqrt(n)*dp). */
static void test_dither_averages_radius_error(void **state) {
    (void)state;
    const int n = 3000;
    const double v = 1.0 - P_N3000_R2, eps = 0.01;
    double sys = 0.0, dit = 0.0;
    for (int i = 0; i < n; i++) {
        sys += 1.0 - branch_quantize_angle(v, eps, 0, i);
        dit += 1.0 - branch_quantize_angle(v, eps, 1, i);
    }
    double r_exact = n * P_N3000_R2;               /* == 2 */
    double err_sys = fabs(sys - r_exact) / r_exact;
    double err_dit = fabs(dit - r_exact) / r_exact;
    /* The systematic grid is coherent, so its relative radius error is the full
     * 2*dtheta/theta; the dithered one must be strictly smaller here. */
    assert_true(err_dit < err_sys);
}

/* ============================================================
 * setters: per-phase, and the all-phases convenience
 * ============================================================ */

static void test_per_phase_setters(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_sat_angle_precision(ctx, 0.1, 0);
    solver_ctx_set_opt_sat_angle_precision(ctx, 0.2, 1);
    solver_ctx_set_opt_angle_precision(ctx, 0.3, 0);
    assert_true(ctx->branching_stats_sat.angle_precision_eps == 0.1);
    assert_int_equal(ctx->branching_stats_sat.angle_precision_dither, 0);
    assert_true(ctx->branching_stats_opt_sat.angle_precision_eps == 0.2);
    assert_int_equal(ctx->branching_stats_opt_sat.angle_precision_dither, 1);
    assert_true(ctx->branching_stats_opt.angle_precision_eps == 0.3);
    assert_int_equal(ctx->branching_stats_opt.angle_precision_dither, 0);

    solver_ctx_set_angle_precision(ctx, 0.05, 1);
    assert_true(ctx->branching_stats_sat.angle_precision_eps == 0.05);
    assert_true(ctx->branching_stats_opt_sat.angle_precision_eps == 0.05);
    assert_true(ctx->branching_stats_opt.angle_precision_eps == 0.05);
    assert_int_equal(ctx->branching_stats_opt.angle_precision_dither, 1);
}

static void test_setters_null_ctx_is_noop(void **state) {
    (void)state;
    solver_ctx_set_angle_precision(NULL, 0.1, 1);
    solver_ctx_set_sat_angle_precision(NULL, 0.1, 1);
    solver_ctx_set_opt_sat_angle_precision(NULL, 0.1, 1);
    solver_ctx_set_opt_angle_precision(NULL, 0.1, 1);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_defaults_are_off, ap_setup, ap_teardown),
        cmocka_unit_test_setup_teardown(test_golden_6_over_7_preserved, ap_setup, ap_teardown),
        cmocka_unit_test_setup_teardown(test_nonpositive_eps_is_off, ap_setup, ap_teardown),
        cmocka_unit_test_setup_teardown(test_off_matches_baseline_everywhere, ap_setup, ap_teardown),
        cmocka_unit_test(test_quantize_respects_eps),
        cmocka_unit_test(test_monotone_convergence),
        cmocka_unit_test_setup_teardown(test_bounded_decisions_coarse_grid_n3000, ap_setup, ap_teardown),
        cmocka_unit_test(test_systematic_grid_snaps_to_clamp),
        cmocka_unit_test_setup_teardown(test_bounded_decisions_with_weights, ap_setup, ap_teardown),
        cmocka_unit_test(test_dither_is_deterministic),
        cmocka_unit_test(test_dither_is_zero_mean_and_varying),
        cmocka_unit_test_setup_teardown(test_dither_varies_per_index_systematic_does_not, ap_setup, ap_teardown),
        cmocka_unit_test(test_dither_averages_radius_error),
        cmocka_unit_test_setup_teardown(test_per_phase_setters, ap_setup, ap_teardown),
        cmocka_unit_test(test_setters_null_ctx_is_noop),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
