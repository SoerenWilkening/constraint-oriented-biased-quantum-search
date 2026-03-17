/**
 * ml_features.h - Feature extraction for ML-based branching prediction
 *
 * Computes per-variable (n x 9) and instance-level (11,) features from
 * dyn_expression_t arrays and variable metadata. Mirrors the Python
 * FeatureExtractor in cbqs/ml/features.py.
 *
 * Per-variable features are z-score normalized per column.
 */

#ifndef ML_FEATURES_H
#define ML_FEATURES_H

#include <stddef.h>
#include "dyn_expr.h"

/* Number of per-variable features */
#define NUM_VAR_FEATURES  9

/* Number of instance-level features */
#define NUM_INST_FEATURES 11

/* Per-variable feature column indices */
#define FEAT_DEGREE              0
#define FEAT_COEFF_MEAN          1
#define FEAT_COEFF_MAX           2
#define FEAT_COEFF_MIN           3
#define FEAT_OBJ_COEFF           4
#define FEAT_BOUNDS_WIDTH         5
#define FEAT_IS_INTEGER           6
#define FEAT_AVG_NEIGHBOR_DEGREE  7
#define FEAT_NUM_CO_OCCURRING     8

/**
 * Result struct returned by extract_features().
 *
 * var_features: heap-allocated array of n_vars * NUM_VAR_FEATURES doubles,
 *               row-major (var_features[i * NUM_VAR_FEATURES + col]).
 *               Z-score normalized per column. NULL if n_vars == 0.
 *
 * inst_features: array of NUM_INST_FEATURES doubles (instance-level features).
 *
 * Caller must free var_features when done.
 */
typedef struct {
    double *var_features;           /* n_vars x 9, row-major, z-score normalized */
    double inst_features[NUM_INST_FEATURES];
    int n_vars;
} features_result_t;

/**
 * Extract per-variable and instance-level features from expressions.
 *
 * Operates directly on dyn_expression_t arrays and variable metadata.
 * Per-variable features are z-score normalized per column; zero-variance
 * columns are set to zero.
 *
 * Parameters:
 *   obj_exprs    - array of pointers to objective expressions
 *   n_obj        - number of objective expressions
 *   con_exprs    - array of pointers to constraint expressions
 *   n_con        - number of constraint expressions
 *   n_vars       - number of variables
 *   lb           - lower bounds array (length n_vars)
 *   ub           - upper bounds array (length n_vars)
 *   vtype        - variable type array (INTEGER or FRACTIONAL, length n_vars)
 *
 * Returns:
 *   features_result_t with allocated var_features (caller must free).
 *   On allocation failure, var_features is NULL and n_vars is 0.
 */
features_result_t extract_features(
    dyn_expression_t **obj_exprs, int n_obj,
    dyn_expression_t **con_exprs, int n_con,
    int n_vars,
    const double *lb, const double *ub, const int *vtype
);

/**
 * Free the var_features array in a features_result_t.
 */
void features_result_free(features_result_t *result);

#endif /* ML_FEATURES_H */
