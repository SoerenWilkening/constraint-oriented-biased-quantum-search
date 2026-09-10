#ifndef BRANCHING_H
#define BRANCHING_H

#include <time.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdint.h>
#include "intarray.h"
//#include "SearchLib.h"
#include "definitions.h"
#include "state.h"

/*
 * Branching probability computation for quantum-inspired search.
 *
 * This module computes per-variable branching probabilities that guide the
 * quantum-inspired sampling algorithm. The scalar `bias` channel sets a base
 * probability `assignment_bias = (bias+1)/(bias+2)` (optionally blended with a
 * feasibility look-ahead term); the per-variable `branching_weights[i]` then
 * apply a SIGNED additive offset in logit space through a sigmoid:
 *
 *   value = sigma( logit(base) + branching_factor * branching_weights[i] )
 *
 * This decouples the per-variable channel from the scalar bias so enabling
 * weights cannot silently rescale the neighborhood radius (the pre-M0f convex
 * blend shared one denominator and did). With no/zero weights `value == base`
 * exactly. The result is conditioned on the current bit (bit_S) and threshold
 * bit (bit_T) to determine the branching direction. See BranchingFunction.
 *
 * StateProbability() combines per-bit probabilities into an overall state
 * probability by multiplying across all branched variables.
 */

/* Forward declaration for solver context (avoids circular include) */
struct solver_ctx;
typedef struct solver_ctx solver_ctx_t;

typedef struct {
    double *branching_weights;  /* Per-variable weights (NULL = no weights) */
    int num_weights;            /* Length of branching_weights (0 when NULL) */

    double branching_factor;    /* Factor for branching_weights term (default 1.0) */
    double bias_factor;         /* Factor for assignment_bias term (default 1.0) */
    double bias;                /* Assignment bias value (default 5.0) */
    double look_ahead_factor;   /* Factor for look-ahead term (default 0.0) */

    int *variable_order;        /* Iteration order for variables (NULL = identity) */
    int num_vars;               /* Length of variable_order (0 when NULL) */

    /* bd h8d: inverse permutation of variable_order -- variable_rank[var] is
     * the traversal position of `var`. evaluation()/look_ahead_correct() key
     * clause-closure on this rank so the potentials accounting stays
     * prefix-consistent with the (reordered) traversal. NULL whenever the
     * traversal is natural-equivalent (no order set, or identity order), which
     * keeps the default path on the exact pre-h8d code path bit-for-bit.
     * Invariant: variable_order non-identity  =>  variable_rank != NULL. */
    int *variable_rank;

    /* bd a0w (M5): ANGLE-PRECISION lever -- Ross-Selinger / gridsynth synthesis
     * of the QTG's per-variable rotation R_y(theta_i) to absolute accuracy
     * `eps` radians (T-count ~ 3*log2(1/eps)). <= 0 is the OFF switch and the
     * default, and leaves BranchingFunction BIT-FOR-BIT on the pre-a0w path.
     *
     * `dither` picks the ERROR STRUCTURE, which is what the physics turns on:
     *   0 (default) = COHERENT. Every variable's angle is displaced the same
     *       way, so the realized-radius error adds coherently (~ n*dtheta).
     *       This is the conservative model, and the exact one for the shipped
     *       uniform-angle schedule (theta_i == 0 => all n angles identical =>
     *       ONE synthesized circuit, reused, with ONE shared residual). It is
     *       implemented as a shared grid snap, which for a per-variable
     *       theta_i (branching_weights set) is a common-lattice model rather
     *       than literally one circuit -- still the coherent worst case.
     *   1 = INCOHERENT. Each variable gets an independent zero-mean residual in
     *       [-eps, eps), so the FIRST-ORDER radius error averages (~sqrt(n)).
     *       Physically this needs n SEPARATELY synthesized circuits even when
     *       the target angles coincide (a real compiler would reuse one), and
     *       it assumes the gridsynth residual is zero-mean and ~uniform within
     *       eps. Note a second-order coherent bias survives the averaging:
     *       E[sin^2((theta+eps*u)/2)] = (1 - cos(theta)*sinc(eps))/2 > p.
     * The SYSTEMATIC arm is therefore the headline for the shipped schedule;
     * the dithered arm prices an explicit engineering choice. See
     * branch_quantize_angle and benchmarks/ANGLE_PRECISION_FINDINGS.md. */
    double angle_precision_eps;
    int angle_precision_dither;
} BranchingStats_t;

/* Global BranchingStats removed in v2.0 -- all state lives in solver_ctx_t.branching_stats */

/* Clamp bound for the bounded-decisions invariant (NORTHSTAR §1.7/§8.2):
 * every returned probability stays in (BRANCH_EPS, 1 - BRANCH_EPS) by
 * construction, so the exploratory stage can never silently force an
 * assignment (value pinned to exactly 0 or 1). */
#define BRANCH_EPS 1e-9

static inline double branch_clamp(double v){
    if (v < BRANCH_EPS)       return BRANCH_EPS;
    if (v > 1.0 - BRANCH_EPS) return 1.0 - BRANCH_EPS;
    return v;
}

/*
 * branch_dither_u -- deterministic per-variable rounding offset in [-1, 1).
 *
 * Models the residual synthesis error of gridsynth when each variable's
 * rotation is synthesized separately: bounded by eps but pseudorandom within
 * it, not snapped to a shared grid. A PURE function of the variable index
 * (splitmix64 finalizer) -- it touches neither the solver PRNG stream nor any
 * global state, so a fixed seed still reproduces a solve bit-for-bit
 * (NORTHSTAR §8 determinism baseline) and the offsets are stable across
 * workers, phases and Grover rounds, exactly as a compiled circuit would be.
 */
static inline double branch_dither_u(int index){
    uint64_t z = (uint64_t)(uint32_t)index + 0x9E3779B97F4A7C15ULL;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    z =  z ^ (z >> 31);
    /* top 53 bits -> [0,1) exactly representable -> [-1, 1) */
    return (double)(z >> 11) * (2.0 / 9007199254740992.0) - 1.0;
}

/*
 * branch_quantize_angle -- apply finite R_y synthesis accuracy to a decision.
 *
 * The physical knob is the ANGLE, not the probability: the QTG prepares each
 * variable with R_y(theta_i) whose FLIP amplitude is sin(theta/2), so
 *
 *     p_flip = 1 - value = sin^2(theta/2),   theta = 2*asin(sqrt(1 - value)).
 *
 * Quantizing `value` on a uniform grid instead would be unfaithful and far too
 * coarse near p ~ 0 -- which is exactly where CBQS operates (p_flip = r/n, so
 * theta ~ 2*sqrt(r/n) shrinks like 1/sqrt(n)).
 *
 *   systematic (dither == 0): theta_q = 2*eps * round(theta / (2*eps))
 *                             -- a grid of spacing 2*eps, so |dtheta| <= eps.
 *   dithered   (dither != 0): theta_q = theta + eps * u(index),  |u| < 1
 *                             -- the same accuracy bound, zero-mean per variable.
 *
 * Both satisfy the Ross-Selinger contract |theta_q - theta| <= eps, which is
 * what a T-count of ~3*log2(1/eps) buys. sin^2(theta/2) is even and bounded, so
 * a negative or over-rotated theta_q is still a valid probability (no folding
 * needed); branch_clamp then keeps the result strictly inside (0,1) so BOUNDED
 * DECISIONS (NORTHSTAR §1.7) hold BY CONSTRUCTION even for a grid so coarse it
 * rounds theta to 0 -- the case that would otherwise force deterministic greedy.
 */
static inline double branch_quantize_angle(double value, double eps,
                                           int dither, int index){
    double p = 1.0 - value;
    if (p < 0.0)      p = 0.0;
    else if (p > 1.0) p = 1.0;

    double theta = 2.0 * asin(sqrt(p));
    double theta_q;
    if (dither) {
        theta_q = theta + eps * branch_dither_u(index);
    } else {
        double delta = 2.0 * eps;
        theta_q = delta * round(theta / delta);
    }
    double s = sin(0.5 * theta_q);
    return branch_clamp(1.0 - s * s);
}

/*
 * BranchingFunction -- Compute the branching probability for variable `index`.
 *
 * M0f reparameterization (NORTHSTAR §4): the per-variable channel is an
 * ADDITIVE LOGIT OFFSET through a sigmoid, decoupled from the scalar bias --
 * it is no longer a term in a shared-denominator convex blend (which let
 * enabling `branching_weights` silently rescale the radius via factor_sum).
 *
 *   base   = convex blend of the NON-per-variable channels only:
 *            (bias_factor * assignment_bias + look_ahead_factor * lookahead_0)
 *            / (bias_factor + look_ahead_factor)      [0.5 if that sum <= 0]
 *   value  = sigma( logit(base) + branching_factor * theta_i )   if theta != 0
 *          = base                                                 if theta == 0
 *
 * where:
 *   assignment_bias  = (bias + 1) / (bias + 2), a sigmoid-like term in (0,1)
 *   lookahead_0_prob = 1.0 if diffcount >= 0 (feasible), 0.0 otherwise
 *                      (diffcount == 0 disables look_ahead; all production call
 *                      sites pass diffcount == 0, so base == assignment_bias)
 *   theta_i          = branching_weights[index] -- a SIGNED per-variable offset
 *                      (no L1 normalization, no non-negativity); 0 if no weights
 *   branching_factor = gain on the per-variable channel (default 1.0 recovers
 *                      the NORTHSTAR §4 form; 0.0 disables the channel)
 *
 * Bit-for-bit baseline recovery: when the effective offset
 * `branching_factor * theta_i` is exactly 0 (no weights, all-zero weights, or
 * branching_factor == 0) the result is `base` with NO sigmoid round-trip, so
 * the golden BranchingFunction(i,0,0,0) == 6/7 at bias=5 is preserved exactly.
 * Both `base` (pre-logit) and `value` (post-sigmoid) are clamped to
 * (eps, 1-eps) so logit() stays finite and §1.7 holds by construction.
 *
 * The bit_S / bit_T logic flips the probability based on whether the current
 * candidate bit matches or opposes the threshold (best-known) bit:
 *   - bit_T == 0: P(0) = value, P(1) = 1 - value
 *   - bit_T == 1: P(0) = 1 - value, P(1) = value
 *
 * Returns: probability in (0, 1), used by StateProbability().
 */
static inline double BranchingFunction(int index, int bit_S, int bit_T, int diffcount, const BranchingStats_t *stats){
    double total_bias;
    double branching_factor = stats->branching_factor;
    double bias_factor = stats->bias_factor;
    double look_ahead_factor = stats->look_ahead_factor;

    if (diffcount == 0) look_ahead_factor = 0;

    double lookahead_0_probability = (diffcount < 0) ? 0.0 : 1.0;
    double assignment_bias = (stats->bias + 1.0) / (stats->bias + 2.0);

    /* Convex blend of the NON-per-variable channels (bias + look-ahead). The
     * per-variable weight term is NO LONGER part of this sum -- it enters
     * additively in logit space below, so enabling weights cannot rescale the
     * neighborhood radius (NORTHSTAR §1.5, §4). */
    double factor_sum = bias_factor + look_ahead_factor;
    double base;
    if (factor_sum <= 0.0) {
        base = 0.5;
    } else {
        base = (bias_factor * assignment_bias
                + look_ahead_factor * lookahead_0_probability) / factor_sum;
    }
    base = branch_clamp(base);  /* keep logit() finite + bounded by construction */

    /* Per-variable signed logit offset. When the effective offset is exactly
     * zero we return `base` directly (no sigmoid round-trip), recovering the
     * baseline bit-for-bit. */
    double theta = (stats->branching_weights != NULL && index < stats->num_weights)
                   ? stats->branching_weights[index] : 0.0;
    double offset = branching_factor * theta;
    double value;
    if (offset == 0.0) {
        value = base;
    } else {
        double z = log(base / (1.0 - base)) + offset;
        value = branch_clamp(1.0 / (1.0 + exp(-z)));
    }

    /* bd a0w (M5): finite R_y synthesis accuracy. eps <= 0 (the default) skips
     * this entirely, so the whole pre-a0w path -- including the NORTHSTAR §8
     * golden 6/7 at bias=5 -- is recovered BIT-FOR-BIT. */
    if (stats->angle_precision_eps > 0.0) {
        value = branch_quantize_angle(value, stats->angle_precision_eps,
                                      stats->angle_precision_dither, index);
    }

    /* Apply bit_S / bit_T branching logic */
    if (bit_T == 0) {
        total_bias = (bit_S == 0) ? value : (1.0 - value);
    } else {
        total_bias = (bit_S == 0) ? (1.0 - value) : value;
    }

    return total_bias;
}

/*
 * StateProbability -- Compute the overall probability of a candidate state.
 *
 * Multiplies per-bit branching probabilities across all branched variables
 * (those where state->branch[j] == 1). The result is stored in state->prob.
 *
 * Inputs:  ctx (solver context with branching stats),
 *          state (candidate), threshold (best-known solution)
 * Output:  state->prob = product of BranchingFunction() for each branched bit
 */
double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold);

state_t *updated(solver_ctx_t *ctx, state_t *bnb, size_t number_states, size_t *new_number, state_t *threshold, int sense);

#endif
