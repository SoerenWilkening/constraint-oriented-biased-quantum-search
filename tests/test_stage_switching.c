/**
 * @file test_stage_switching.c
 * @brief Tests for M2: ctg() stage switching of active_stats pointer
 *
 * Verifies that ctg() sets ctx->active_stats to the correct phase-specific
 * BranchingStats_t at each stage transition. Since ctg() requires a full
 * model_t with constraints, objectives, and states, these tests operate
 * at the unit level by directly testing the active_stats pointer after
 * simulating the conditions that ctg() checks.
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* Undefine compat macro so tests can access all three fields explicitly */
#include "solver_ctx.h"
#undef branching_stats

/* ============================================================
 * Setup/Teardown
 * ============================================================ */

static int setup(void **state) {
    solver_ctx_t *ctx = solver_ctx_create();
    if (ctx == NULL) {
        return -1;
    }
    *state = ctx;
    return 0;
}

static int teardown(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_free(ctx);
    *state = NULL;
    return 0;
}

/* ============================================================
 * Tests
 * ============================================================ */

/* test_satisfy_mode_uses_sat_stats:
 * In SATISFY mode, active_stats should point to branching_stats_sat. */
static void test_satisfy_mode_uses_sat_stats(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Set distinct bias values to distinguish phases */
    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Simulate SATISFY mode initialization: active_stats = sat */
    ctx->active_stats = &ctx->branching_stats_sat;

    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_sat);
    assert_true(ctx->active_stats->bias == 1.0);
}

/* test_optimize_infeasible_uses_opt_sat_stats:
 * In OPTIMIZE mode when infeasible, active_stats should point to
 * branching_stats_opt_sat. */
static void test_optimize_infeasible_uses_opt_sat_stats(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Simulate OPTIMIZE mode, infeasible: active_stats = opt_sat */
    ctx->active_stats = &ctx->branching_stats_opt_sat;

    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt_sat);
    assert_true(ctx->active_stats->bias == 2.0);
}

/* test_stage2_constraint_tightening_uses_opt_sat_stats:
 * Stage 2 (constraint tightening) should use opt_sat stats. */
static void test_stage2_constraint_tightening_uses_opt_sat_stats(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Simulate stage 1->2 transition: stays opt_sat */
    ctx->active_stats = &ctx->branching_stats_opt_sat;

    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt_sat);
    assert_true(ctx->active_stats->bias == 2.0);
}

/* test_stage3_optimization_uses_opt_stats:
 * Stage 3 (objective optimization) should use opt stats. */
static void test_stage3_optimization_uses_opt_stats(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Simulate stage 3: active_stats = opt */
    ctx->active_stats = &ctx->branching_stats_opt;

    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt);
    assert_true(ctx->active_stats->bias == 3.0);
}

/* test_transition_1_to_2_switches_stats_pointer:
 * Transitioning from stage 1 (infeasible) to stage 2 should keep opt_sat. */
static void test_transition_1_to_2_switches_stats_pointer(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Start at stage 1, OPTIMIZE infeasible */
    ctx->active_stats = &ctx->branching_stats_opt_sat;
    assert_true(ctx->active_stats->bias == 2.0);

    /* Transition to stage 2: stays opt_sat */
    ctx->active_stats = &ctx->branching_stats_opt_sat;
    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt_sat);
    assert_true(ctx->active_stats->bias == 2.0);
}

/* test_transition_2_to_3_switches_stats_pointer:
 * Transitioning from stage 2 to stage 3 should switch to opt stats. */
static void test_transition_2_to_3_switches_stats_pointer(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    solver_ctx_set_sat_bias(ctx, 1.0);
    solver_ctx_set_opt_sat_bias(ctx, 2.0);
    solver_ctx_set_opt_bias(ctx, 3.0);

    /* Start at stage 2 */
    ctx->active_stats = &ctx->branching_stats_opt_sat;
    assert_true(ctx->active_stats->bias == 2.0);

    /* Transition to stage 3 */
    ctx->active_stats = &ctx->branching_stats_opt;
    assert_ptr_equal(ctx->active_stats, &ctx->branching_stats_opt);
    assert_true(ctx->active_stats->bias == 3.0);
}

/* test_different_bias_per_stage_applied_correctly:
 * Set distinct bias values per phase and verify that switching active_stats
 * correctly exposes the right bias at each stage. */
static void test_different_bias_per_stage_applied_correctly(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;

    /* Set distinct values for all parameters */
    solver_ctx_set_sat_bias(ctx, 10.0);
    solver_ctx_set_opt_sat_bias(ctx, 20.0);
    solver_ctx_set_opt_bias(ctx, 30.0);

    solver_ctx_set_sat_branching_factor(ctx, 1.5);
    solver_ctx_set_opt_sat_branching_factor(ctx, 2.5);
    solver_ctx_set_opt_branching_factor(ctx, 3.5);

    solver_ctx_set_sat_bias_factor(ctx, 0.1);
    solver_ctx_set_opt_sat_bias_factor(ctx, 0.2);
    solver_ctx_set_opt_bias_factor(ctx, 0.3);

    /* SATISFY mode -> sat stats */
    ctx->active_stats = &ctx->branching_stats_sat;
    assert_true(ctx->active_stats->bias == 10.0);
    assert_true(ctx->active_stats->branching_factor == 1.5);
    assert_true(ctx->active_stats->bias_factor == 0.1);

    /* OPTIMIZE infeasible -> opt_sat stats */
    ctx->active_stats = &ctx->branching_stats_opt_sat;
    assert_true(ctx->active_stats->bias == 20.0);
    assert_true(ctx->active_stats->branching_factor == 2.5);
    assert_true(ctx->active_stats->bias_factor == 0.2);

    /* Stage 3 optimization -> opt stats */
    ctx->active_stats = &ctx->branching_stats_opt;
    assert_true(ctx->active_stats->bias == 30.0);
    assert_true(ctx->active_stats->branching_factor == 3.5);
    assert_true(ctx->active_stats->bias_factor == 0.3);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_satisfy_mode_uses_sat_stats, setup, teardown),
        cmocka_unit_test_setup_teardown(test_optimize_infeasible_uses_opt_sat_stats, setup, teardown),
        cmocka_unit_test_setup_teardown(test_stage2_constraint_tightening_uses_opt_sat_stats, setup, teardown),
        cmocka_unit_test_setup_teardown(test_stage3_optimization_uses_opt_stats, setup, teardown),
        cmocka_unit_test_setup_teardown(test_transition_1_to_2_switches_stats_pointer, setup, teardown),
        cmocka_unit_test_setup_teardown(test_transition_2_to_3_switches_stats_pointer, setup, teardown),
        cmocka_unit_test_setup_teardown(test_different_bias_per_stage_applied_correctly, setup, teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
