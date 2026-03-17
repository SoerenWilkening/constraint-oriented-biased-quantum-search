/**
 * ml_features.h - C-level feature extraction for ML branching parameter prediction
 *
 * Extracts per-variable (n_vars x 9) and instance-level (11,) features from
 * compiled constraint data (new_constraints_t). Operates on post-close() data
 * to avoid Python loop overhead.
 */

#ifndef ML_FEATURES_H
#define ML_FEATURES_H

#include "constraint.h"

/* Number of per-variable features */
#define ML_NUM_VAR_FEATURES 9

/* Number of instance-level features */
#define ML_NUM_INST_FEATURES 11

/**
 * Per-variable metadata passed from Python.
 * Captures variable properties not stored in new_constraints_t.
 */
typedef struct {
    double lb;          /* Lower bound */
    double ub;          /* Upper bound */
    int is_integer;     /* 1 if INTEGER type, 0 otherwise */
} variable_meta_t;

/**
 * Result struct for feature extraction.
 * Caller allocates the output arrays.
 */
typedef struct {
    double *var_features;    /* (n_vars * 9) row-major */
    double *inst_features;   /* (11,) */
} features_result_t;

/**
 * Extract per-variable and instance-level features from compiled constraints.
 *
 * Per-variable features (9 columns, z-score normalized):
 *   0: degree               - Number of constraints containing this variable
 *   1: coeff_mean           - Mean |coefficient| across constraints
 *   2: coeff_max            - Max |coefficient|
 *   3: coeff_min            - Min |coefficient| (0 if not in any constraint)
 *   4: objective_coefficient - Sum of |coefficient| in objective
 *   5: bounds_width         - ub - lb
 *   6: is_integer           - 1.0 if integer, 0.0 otherwise
 *   7: avg_neighbor_degree  - Mean degree of co-occurring variables
 *   8: num_co_occurring_vars - Count of unique co-occurring variables
 *
 * Instance features (11, raw values):
 *   0: n_variables, 1: n_constraints, 2: constraint_density,
 *   3: constraint_variable_ratio, 4: objective_density,
 *   5: integer_variable_fraction, 6: coeff_mean, 7: coeff_std,
 *   8: coeff_max, 9: bounds_tightness_mean, 10: bounds_tightness_std
 *
 * @param obj      Compiled objective constraints
 * @param con      Compiled constraint data
 * @param vars     Per-variable metadata (length n_vars)
 * @param n_vars   Number of variables
 * @param out_var  Output: n_vars * 9 doubles, row-major (caller-allocated)
 * @param out_inst Output: 11 doubles (caller-allocated)
 */
void extract_features(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    double *out_var,
    double *out_inst
);

#endif /* ML_FEATURES_H */
