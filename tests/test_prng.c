/**
 * @file test_prng.c
 * @brief Unit tests for xoshiro256** PRNG implementation
 *
 * Tests cover:
 * - Seeding produces valid non-zero state
 * - prng_next_double returns values in [0.0, 1.0)
 * - prng_next_int returns values in [0, max)
 * - Determinism: same seed produces same sequence
 * - Different seeds produce different sequences
 * - Jump function produces distinct parallel streams
 * - Entropy seed produces non-zero, varying values
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "prng.h"

/* ============================================================
 * Setup/Teardown (reset thread-local state)
 * ============================================================ */

static int prng_setup(void **state) {
    (void)state;
    /* Reset thread-local PRNG state for clean test isolation */
    g_prng_initialized = 0;
    for (int i = 0; i < 4; i++) {
        g_prng_state.s[i] = 0;
    }
    return 0;
}

static int prng_teardown(void **state) {
    (void)state;
    return 0;
}

/* ============================================================
 * Test: prng_seed_produces_nonzero_state
 * ============================================================ */

/**
 * Verify that seeding produces a non-zero state and sets initialized flag.
 */
static void test_prng_seed_produces_nonzero_state(void **state) {
    (void)state;

    prng_seed(12345);

    /* At least one state element should be non-zero */
    int has_nonzero = 0;
    for (int i = 0; i < 4; i++) {
        if (g_prng_state.s[i] != 0) {
            has_nonzero = 1;
            break;
        }
    }
    assert_true(has_nonzero);

    /* Initialized flag should be set */
    assert_int_equal(g_prng_initialized, 1);
}

/* ============================================================
 * Test: prng_next_double_in_range
 * ============================================================ */

/**
 * Verify that prng_next_double returns values in [0.0, 1.0).
 */
static void test_prng_next_double_in_range(void **state) {
    (void)state;

    prng_seed(42);

    for (int i = 0; i < 1000; i++) {
        double val = prng_next_double();
        assert_true(val >= 0.0);
        assert_true(val < 1.0);
    }
}

/* ============================================================
 * Test: prng_next_int_in_range
 * ============================================================ */

/**
 * Verify that prng_next_int returns values in [0, max).
 */
static void test_prng_next_int_in_range(void **state) {
    (void)state;

    prng_seed(42);

    const int max = 100;
    for (int i = 0; i < 1000; i++) {
        int val = prng_next_int(max);
        assert_true(val >= 0);
        assert_true(val < max);
    }
}

/* ============================================================
 * Test: prng_deterministic_with_same_seed
 * ============================================================ */

/**
 * Verify that the same seed produces the same sequence.
 */
static void test_prng_deterministic_with_same_seed(void **state) {
    (void)state;

    uint64_t first_run[10];
    uint64_t second_run[10];

    /* First run with seed 42 */
    prng_seed(42);
    for (int i = 0; i < 10; i++) {
        first_run[i] = prng_next();
    }

    /* Second run with same seed */
    prng_seed(42);
    for (int i = 0; i < 10; i++) {
        second_run[i] = prng_next();
    }

    /* All values should match */
    for (int i = 0; i < 10; i++) {
        assert_true(first_run[i] == second_run[i]);
    }
}

/* ============================================================
 * Test: prng_different_seeds_produce_different_output
 * ============================================================ */

/**
 * Verify that different seeds produce different sequences.
 */
static void test_prng_different_seeds_produce_different_output(void **state) {
    (void)state;

    uint64_t seed1_values[5];
    uint64_t seed2_values[5];

    /* First seed */
    prng_seed(1);
    for (int i = 0; i < 5; i++) {
        seed1_values[i] = prng_next();
    }

    /* Different seed */
    prng_seed(2);
    for (int i = 0; i < 5; i++) {
        seed2_values[i] = prng_next();
    }

    /* At least one value should differ */
    int has_difference = 0;
    for (int i = 0; i < 5; i++) {
        if (seed1_values[i] != seed2_values[i]) {
            has_difference = 1;
            break;
        }
    }
    assert_true(has_difference);
}

/* ============================================================
 * Test: prng_jump_produces_distinct_streams
 * ============================================================ */

/**
 * Verify that prng_seed_thread with different thread_ids produces
 * distinct (non-overlapping) streams from the same master state.
 */
static void test_prng_jump_produces_distinct_streams(void **state) {
    (void)state;

    /* Create master state */
    prng_state_t master;
    prng_seed_from_state(&master, 100);

    uint64_t thread0_values[5];
    uint64_t thread1_values[5];

    /* Thread 0: uses master state directly */
    prng_seed_thread(&master, 0);
    for (int i = 0; i < 5; i++) {
        thread0_values[i] = prng_next();
    }

    /* Thread 1: jumps once from master state */
    prng_seed_thread(&master, 1);
    for (int i = 0; i < 5; i++) {
        thread1_values[i] = prng_next();
    }

    /* Sequences should differ (jump gives 2^128 non-overlapping values) */
    int has_difference = 0;
    for (int i = 0; i < 5; i++) {
        if (thread0_values[i] != thread1_values[i]) {
            has_difference = 1;
            break;
        }
    }
    assert_true(has_difference);
}

/**
 * Verify the portfolio-worker decorrelation contract that solver_ctx_init_prng
 * relies on (bd 8an.1.3): from one master state, prng_seed_thread(master, k)
 * for k = 0..3 must produce (a) pairwise-distinct streams, (b) reproducible
 * streams (re-seeding the same k repeats it), and (c) k == 0 must reproduce the
 * plain master stream exactly, so single-worker runs stay bit-for-bit
 * deterministic (CLAUDE.md §8).
 */
static void test_prng_worker_streams_distinct_and_reproducible(void **state) {
    (void)state;

    enum { NW = 4, NV = 6 };   /* NW worker ids 0..3; NV values sampled per worker */
    uint64_t first[NW][NV];

    prng_state_t master;
    prng_seed_from_state(&master, 0xC0FFEEULL);

    for (int w = 0; w < NW; w++) {
        prng_seed_thread(&master, w);
        for (int i = 0; i < NV; i++) {
            first[w][i] = prng_next();
        }
    }

    /* (a) distinct: every pair of workers differs in at least one value */
    for (int a = 0; a < NW; a++) {
        for (int b = a + 1; b < NW; b++) {
            int differs = 0;
            for (int i = 0; i < NV; i++) {
                if (first[a][i] != first[b][i]) { differs = 1; break; }
            }
            assert_true(differs);
        }
    }

    /* (b) reproducible: re-seeding the same worker repeats its stream exactly */
    for (int w = 0; w < NW; w++) {
        prng_seed_thread(&master, w);
        for (int i = 0; i < NV; i++) {
            assert_true(prng_next() == first[w][i]);
        }
    }

    /* (c) worker 0 == plain master stream (legacy single-stream behavior) */
    prng_state_t legacy;
    prng_seed_from_state(&legacy, 0xC0FFEEULL);
    g_prng_state = legacy;       /* no jump: this is what worker 0 must match */
    g_prng_initialized = 1;
    for (int i = 0; i < NV; i++) {
        assert_true(prng_next() == first[0][i]);
    }
}

/* ============================================================
 * Test: prng_get_entropy_seed_nonzero
 * ============================================================ */

/**
 * Verify that prng_get_entropy_seed returns non-zero, varying values.
 */
static void test_prng_get_entropy_seed_nonzero(void **state) {
    (void)state;

    uint64_t seed1 = prng_get_entropy_seed();
    uint64_t seed2 = prng_get_entropy_seed();

    /* Both should be non-zero */
    assert_true(seed1 != 0);
    assert_true(seed2 != 0);

    /* They should differ with very high probability (from /dev/urandom) */
    /* Note: This could theoretically fail if entropy returns same value twice,
     * but probability is astronomically low (2^-64) */
    assert_true(seed1 != seed2);
}

/* ============================================================
 * Test: prng_seed_from_state_works
 * ============================================================ */

/**
 * Verify prng_seed_from_state initializes a state correctly.
 */
static void test_prng_seed_from_state_works(void **state) {
    (void)state;

    prng_state_t st;
    prng_seed_from_state(&st, 999);

    /* All state elements should be initialized (very unlikely all zero) */
    int has_nonzero = 0;
    for (int i = 0; i < 4; i++) {
        if (st.s[i] != 0) {
            has_nonzero = 1;
            break;
        }
    }
    assert_true(has_nonzero);
}

/* ============================================================
 * Test: prng_consistency_across_functions
 * ============================================================ */

/**
 * Verify that prng_next_double uses prng_next correctly.
 * Same seed should give deterministic double sequence.
 */
static void test_prng_consistency_across_functions(void **state) {
    (void)state;

    double first_run[5];
    double second_run[5];

    prng_seed(777);
    for (int i = 0; i < 5; i++) {
        first_run[i] = prng_next_double();
    }

    prng_seed(777);
    for (int i = 0; i < 5; i++) {
        second_run[i] = prng_next_double();
    }

    for (int i = 0; i < 5; i++) {
        assert_true(first_run[i] == second_run[i]);
    }
}

/* ============================================================
 * Main: cmocka test runner
 * ============================================================ */

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(
            test_prng_seed_produces_nonzero_state,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_next_double_in_range,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_next_int_in_range,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_deterministic_with_same_seed,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_different_seeds_produce_different_output,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_jump_produces_distinct_streams,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_worker_streams_distinct_and_reproducible,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_get_entropy_seed_nonzero,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_seed_from_state_works,
            prng_setup, prng_teardown),
        cmocka_unit_test_setup_teardown(
            test_prng_consistency_across_functions,
            prng_setup, prng_teardown),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
