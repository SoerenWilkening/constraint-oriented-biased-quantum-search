/**
 * ml_features.h - C-level feature extraction and prediction for ML branching
 *
 * Provides two interfaces:
 *   1. extract_features() — returns raw features for testing/debugging
 *   2. predict_params()   — fused pipeline: features → poly → matmul → params
 */

#ifndef ML_FEATURES_H
#define ML_FEATURES_H

#include "constraint.h"

/* Number of per-variable features */
#define ML_NUM_VAR_FEATURES 9

/* Number of instance-level features */
#define ML_NUM_INST_FEATURES 11

/* Polynomial term counts for degree-2 expansion */
#define ML_VAR_TERMS  55   /* 1 + 9 + 36 + 9 */
#define ML_INST_TERMS 78   /* 1 + 11 + 55 + 11 */

/* Output dimensions */
#define ML_VAR_OUTPUTS  2  /* weight, priority_score */
#define ML_INST_OUTPUTS 3  /* bias_delta, branching_factor, bias_factor */

/**
 * Per-variable metadata passed from Python.
 */
typedef struct {
    double lb;
    double ub;
    int is_integer;
} variable_meta_t;

/**
 * Result struct for feature extraction (legacy interface).
 */
typedef struct {
    double *var_features;    /* (n_vars * 9) row-major */
    double *inst_features;   /* (11,) */
} features_result_t;

/**
 * Extract per-variable and instance-level features from compiled constraints.
 * (See ml_features.c for full documentation.)
 */
void extract_features(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    double *out_var,
    double *out_inst
);

/**
 * Fused prediction pipeline: features → polynomial → matmul → post-process.
 *
 * Computes all solver parameters in a single C call with no intermediate
 * allocations for the polynomial expansion.
 *
 * @param obj              Compiled objective constraints
 * @param con              Compiled constraint data
 * @param vars             Per-variable metadata (length n_vars)
 * @param n_vars           Number of variables
 * @param W_var            Weight matrix (2 x 55), row-major
 * @param W_inst           Weight matrix (3 x 78), row-major
 * @param delta_pct        Max bias delta as fraction of n/4 (e.g. 0.03)
 * @param out_weights      Output: per-variable branching weights (n_vars,), clipped >= 0
 * @param out_priorities   Output: variable priority ordering (n_vars,), argsort of scores
 * @param out_bias         Output: branching bias scalar
 * @param out_bf           Output: branching factor scalar
 * @param out_bif          Output: bias factor scalar
 */
void predict_params(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    const double *W_var,
    const double *W_inst,
    double delta_pct,
    double *out_weights,
    int *out_priorities,
    double *out_bias,
    double *out_bf,
    double *out_bif
);

#endif /* ML_FEATURES_H */
