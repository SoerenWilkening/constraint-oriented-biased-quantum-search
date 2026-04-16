/**
 * @file prng.c
 * @brief xoshiro256** PRNG implementation with thread-local state
 *
 * Reference implementation from https://prng.di.unimi.it/xoshiro256starstar.c
 * by David Blackman and Sebastiano Vigna.
 *
 * SplitMix64 seeding from https://prng.di.unimi.it/splitmix64.c
 */

#include "prng.h"

#include "platform.h"

/* ============================================================
 * Thread-local State
 * ============================================================ */

CBQS_THREAD_LOCAL prng_state_t g_prng_state;
CBQS_THREAD_LOCAL int g_prng_initialized = 0;

/* ============================================================
 * Internal Helper Functions
 * ============================================================ */

/**
 * @brief Rotate left (circular shift)
 *
 * @param x Value to rotate
 * @param k Number of bits to rotate
 * @return Rotated value
 */
static inline uint64_t rotl(const uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

/**
 * @brief SplitMix64 generator for state initialization
 *
 * This is a fast, high-quality 64-bit generator used to expand a single
 * seed value into the full 256-bit xoshiro256** state.
 *
 * Reference: https://prng.di.unimi.it/splitmix64.c
 *
 * @param state Pointer to 64-bit state (modified)
 * @return Next 64-bit random value
 */
static uint64_t splitmix64(uint64_t *state) {
    uint64_t z = (*state += 0x9e3779b97f4a7c15);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9;
    z = (z ^ (z >> 27)) * 0x94d049bb133111eb;
    return z ^ (z >> 31);
}

/**
 * @brief Internal next function operating on explicit state
 *
 * Used by prng_jump() to advance a state without touching thread-local storage.
 *
 * @param state State to advance
 * @return Generated value (unused in jump function)
 */
static inline uint64_t next_internal(prng_state_t *state) {
    uint64_t *s = state->s;
    const uint64_t result = rotl(s[1] * 5, 7) * 9;
    const uint64_t t = s[1] << 17;

    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = rotl(s[3], 45);

    return result;
}

/* ============================================================
 * Initialization Functions
 * ============================================================ */

void prng_seed_from_state(prng_state_t *state, uint64_t seed) {
    uint64_t sm_state = seed;
    state->s[0] = splitmix64(&sm_state);
    state->s[1] = splitmix64(&sm_state);
    state->s[2] = splitmix64(&sm_state);
    state->s[3] = splitmix64(&sm_state);
}

void prng_seed(uint64_t seed) {
    prng_seed_from_state(&g_prng_state, seed);
    g_prng_initialized = 1;
}

void prng_seed_thread(const prng_state_t *master, int thread_id) {
    /* Copy master state to thread-local storage */
    g_prng_state = *master;

    /* Apply jump function thread_id times for non-overlapping streams */
    for (int i = 0; i < thread_id; i++) {
        prng_jump(&g_prng_state);
    }

    g_prng_initialized = 1;
}

/* ============================================================
 * Generation Functions
 * ============================================================ */

uint64_t prng_next(void) {
    uint64_t *s = g_prng_state.s;

    /* xoshiro256** scrambler: rotl(s[1] * 5, 7) * 9 */
    const uint64_t result = rotl(s[1] * 5, 7) * 9;

    const uint64_t t = s[1] << 17;

    /* State update */
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = rotl(s[3], 45);

    return result;
}

double prng_next_double(void) {
    /*
     * Convert to [0.0, 1.0) using upper 53 bits.
     * IEEE 754 double has 53-bit mantissa precision.
     * 0x1.0p-53 = 2^-53 = 1.1102230246251565e-16
     */
    return (prng_next() >> 11) * 0x1.0p-53;
}

int prng_next_int(int max) {
    return (int)(prng_next_double() * max);
}

/* ============================================================
 * Jump Function
 * ============================================================ */

/*
 * Jump constants for xoshiro256**
 * These advance the state by 2^128 steps.
 * Reference: https://prng.di.unimi.it/xoshiro256starstar.c
 */
static const uint64_t JUMP[] = {
    0x180ec6d33cfd0aba, 0xd5a61266f0c9392c,
    0xa9582618e03fc9aa, 0x39abdc4529b1661c
};

void prng_jump(prng_state_t *state) {
    uint64_t s0 = 0;
    uint64_t s1 = 0;
    uint64_t s2 = 0;
    uint64_t s3 = 0;

    for (int i = 0; i < 4; i++) {
        for (int b = 0; b < 64; b++) {
            if (JUMP[i] & UINT64_C(1) << b) {
                s0 ^= state->s[0];
                s1 ^= state->s[1];
                s2 ^= state->s[2];
                s3 ^= state->s[3];
            }
            /* Advance state */
            next_internal(state);
        }
    }

    state->s[0] = s0;
    state->s[1] = s1;
    state->s[2] = s2;
    state->s[3] = s3;
}

/* ============================================================
 * Utility Functions
 * ============================================================ */

uint64_t prng_get_entropy_seed(void) {
    uint64_t seed;

    /* Try OS entropy source first (most portable across platforms) */
    if (cbqs_os_random_bytes(&seed, sizeof(seed)) == 0) {
        return seed;
    }

    /* Fallback to time-based (less random but works everywhere) */
    uint64_t ns = cbqs_monotonic_ns();
    seed = ns;
    seed ^= (uint64_t)cbqs_getpid() << 32;

    return seed;
}
