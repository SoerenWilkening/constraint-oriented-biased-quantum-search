/**
 * @file prng.h
 * @brief xoshiro256** PRNG with thread-local state
 *
 * This module provides a high-quality pseudo-random number generator using the
 * xoshiro256** algorithm. State is stored in thread-local storage, enabling
 * deterministic parallel execution when combined with jump functions.
 *
 * Reference: https://prng.di.unimi.it/xoshiro256starstar.c
 * Authors: David Blackman, Sebastiano Vigna
 */

#ifndef PRNG_H
#define PRNG_H

#include <stdint.h>
#include "definitions.h"

/**
 * @brief xoshiro256** PRNG state (256 bits = 4 x 64 bits)
 */
typedef struct {
    uint64_t s[4];
} prng_state_t;

/**
 * @brief Thread-local PRNG state (one per thread)
 *
 * Automatically instantiated for each thread. Use prng_seed() or
 * prng_seed_thread() to initialize before generating random numbers.
 */
extern CBQS_THREAD_LOCAL prng_state_t g_prng_state;

/**
 * @brief Thread-local initialization flag
 *
 * Set to 1 after prng_seed() or prng_seed_thread() is called.
 * Check this before generating random numbers if uncertain about init state.
 */
extern CBQS_THREAD_LOCAL int g_prng_initialized;

/* ============================================================
 * Initialization Functions
 * ============================================================ */

/**
 * @brief Initialize thread-local PRNG state from 64-bit seed
 *
 * Uses SplitMix64 to expand the 64-bit seed into 256-bit state.
 * Sets g_prng_initialized to 1.
 *
 * @param seed 64-bit seed value (any value including 0 is valid)
 */
void prng_seed(uint64_t seed);

/**
 * @brief Initialize a specific PRNG state from 64-bit seed
 *
 * Uses SplitMix64 to expand the 64-bit seed into 256-bit state.
 * Useful for initializing a master state before deriving thread states.
 *
 * @param state State struct to initialize
 * @param seed 64-bit seed value
 */
void prng_seed_from_state(prng_state_t *state, uint64_t seed);

/**
 * @brief Initialize thread-local state by jumping from master state
 *
 * Copies the master state to thread-local storage, then applies the jump
 * function thread_id times. This produces independent streams that are
 * guaranteed not to overlap for 2^128 values per stream.
 *
 * Sets g_prng_initialized to 1.
 *
 * @param master Master PRNG state (typically from solver context)
 * @param thread_id Thread index (0-based). Thread 0 gets master state,
 *                  thread N gets state jumped N times.
 */
void prng_seed_thread(const prng_state_t *master, int thread_id);

/* ============================================================
 * Generation Functions
 * ============================================================ */

/**
 * @brief Generate next 64-bit random value
 *
 * Uses the xoshiro256** algorithm. Advances thread-local state.
 *
 * @return Random 64-bit unsigned integer (full range)
 */
uint64_t prng_next(void);

/**
 * @brief Generate random double in [0.0, 1.0)
 *
 * Uses upper 53 bits for IEEE 754 double mantissa precision.
 * Result is uniformly distributed in the half-open interval.
 *
 * @return Random double in [0.0, 1.0)
 */
double prng_next_double(void);

/**
 * @brief Generate random int in [0, max)
 *
 * Uses prng_next_double() scaled by max.
 *
 * @param max Upper bound (exclusive). Must be > 0.
 * @return Random int in [0, max)
 */
int prng_next_int(int max);

/* ============================================================
 * Jump Function
 * ============================================================ */

/**
 * @brief Advance PRNG state by 2^128 steps
 *
 * This is the jump function for xoshiro256**. It advances the state
 * as if prng_next() were called 2^128 times. Used to create independent
 * parallel streams that won't overlap.
 *
 * @param state State to advance (modified in place)
 */
void prng_jump(prng_state_t *state);

/* ============================================================
 * Utility Functions
 * ============================================================ */

/**
 * @brief Get non-deterministic seed from system entropy
 *
 * Attempts to read from the OS entropy source (/dev/urandom on POSIX,
 * BCryptGenRandom on Windows). Falls back to combining cbqs_monotonic_ns()
 * and cbqs_getpid() if the OS source is unavailable.
 *
 * Use this when user doesn't provide a seed and non-deterministic
 * behavior is acceptable/desired.
 *
 * @return 64-bit entropy seed
 */
uint64_t prng_get_entropy_seed(void);

#endif /* PRNG_H */
