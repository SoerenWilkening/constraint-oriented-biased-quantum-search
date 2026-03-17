/**
 * ml_features.c - Feature extraction for ML-based branching prediction
 *
 * Single-pass extraction of per-variable (n x 9) and instance-level (11,)
 * features from dyn_expression_t arrays and variable metadata.
 * Mirrors the Python FeatureExtractor in cbqs/ml/features.py exactly.
 */

#include "ml_features.h"
#include "definitions.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ============================================================================
 * Internal: per-variable coefficient accumulator
 * ============================================================================ */

typedef struct {
    double *vals;
    int count;
    int capacity;
} coeff_acc_t;

static void coeff_acc_init(coeff_acc_t *acc) {
    acc->vals = NULL;
    acc->count = 0;
    acc->capacity = 0;
}

static int coeff_acc_push(coeff_acc_t *acc, double val) {
    if (acc->count >= acc->capacity) {
        int new_cap = acc->capacity == 0 ? 8 : acc->capacity * 2;
        double *tmp = realloc(acc->vals, (size_t)new_cap * sizeof(double));
        if (!tmp) return -1;
        acc->vals = tmp;
        acc->capacity = new_cap;
    }
    acc->vals[acc->count++] = val;
    return 0;
}

static void coeff_acc_free(coeff_acc_t *acc) {
    free(acc->vals);
    acc->vals = NULL;
    acc->count = 0;
    acc->capacity = 0;
}

/* ============================================================================
 * Internal: per-variable co-occurrence set (sorted dynamic array of ints)
 * ============================================================================ */

typedef struct {
    int *ids;
    int count;
    int capacity;
} coset_t;

static void coset_init(coset_t *s) {
    s->ids = NULL;
    s->count = 0;
    s->capacity = 0;
}

static int coset_contains(const coset_t *s, int val) {
    for (int i = 0; i < s->count; i++) {
        if (s->ids[i] == val) return 1;
    }
    return 0;
}

static int coset_add(coset_t *s, int val) {
    if (coset_contains(s, val)) return 0;
    if (s->count >= s->capacity) {
        int new_cap = s->capacity == 0 ? 8 : s->capacity * 2;
        int *tmp = realloc(s->ids, (size_t)new_cap * sizeof(int));
        if (!tmp) return -1;
        s->ids = tmp;
        s->capacity = new_cap;
    }
    s->ids[s->count++] = val;
    return 0;
}

static void coset_free(coset_t *s) {
    free(s->ids);
    s->ids = NULL;
    s->count = 0;
    s->capacity = 0;
}

/* ============================================================================
 * Internal: iterate terms in a dyn_expression_t
 * ============================================================================ */

static inline const int64_t *expr_lits(const dyn_expression_t *e) {
    return (e->capacity == 0) ? e->inline_literals : e->literals;
}

static inline const int *expr_lens(const dyn_expression_t *e) {
    return (e->capacity == 0) ? e->inline_len_literal : e->len_literal;
}

/* ============================================================================
 * extract_features
 * ============================================================================ */

features_result_t extract_features(
    dyn_expression_t **obj_exprs, int n_obj,
    dyn_expression_t **con_exprs, int n_con,
    int n_vars,
    const double *lb, const double *ub, const int *vtype
) {
    features_result_t result;
    memset(&result, 0, sizeof(result));
    result.n_vars = n_vars;

    /* Handle zero-variable case */
    if (n_vars <= 0) {
        result.var_features = NULL;
        result.n_vars = 0;
        return result;
    }

    size_t feat_sz = (size_t)n_vars * NUM_VAR_FEATURES;
    result.var_features = calloc(feat_sz, sizeof(double));
    if (!result.var_features) {
        result.n_vars = 0;
        return result;
    }

    /* Per-variable accumulators */
    coeff_acc_t *var_coeffs = calloc((size_t)n_vars, sizeof(coeff_acc_t));
    coset_t *var_co = calloc((size_t)n_vars, sizeof(coset_t));
    if (!var_coeffs || !var_co) {
        free(result.var_features);
        free(var_coeffs);
        free(var_co);
        result.var_features = NULL;
        result.n_vars = 0;
        return result;
    }
    for (int i = 0; i < n_vars; i++) {
        coeff_acc_init(&var_coeffs[i]);
        coset_init(&var_co[i]);
    }

    /* --- Instance feature accumulators --- */
    /* all_coeffs: global constraint coefficient list for instance features */
    coeff_acc_t all_coeffs;
    coeff_acc_init(&all_coeffs);

    /* obj_vars: set of variables with nonzero objective coefficient */
    int *obj_var_seen = calloc((size_t)n_vars, sizeof(int));
    if (!obj_var_seen) {
        for (int i = 0; i < n_vars; i++) {
            coeff_acc_free(&var_coeffs[i]);
            coset_free(&var_co[i]);
        }
        free(var_coeffs);
        free(var_co);
        free(result.var_features);
        result.var_features = NULL;
        result.n_vars = 0;
        return result;
    }

    /* =========================================================
     * Pass over objective expressions
     * ========================================================= */
    for (int e = 0; e < n_obj; e++) {
        const dyn_expression_t *expr = obj_exprs[e];
        if (!expr) continue;
        const int64_t *lits = expr_lits(expr);
        const int *lens = expr_lens(expr);
        size_t n_terms = expr->expr_size;

        for (size_t t = 0; t < n_terms; t++) {
            int term_len = lens[t];
            if (term_len < 2) continue; /* constant term, no variables */
            int64_t coeff = lits[t * MAX_VARS_PER_TERM];
            double abs_coeff = fabs((double)coeff);

            for (int k = 1; k < term_len; k++) {
                int var_idx = (int)lits[t * MAX_VARS_PER_TERM + k];
                if (var_idx < 0 || var_idx >= n_vars) continue;
                /* col 4: objective coefficient (sum of abs coefficients) */
                result.var_features[var_idx * NUM_VAR_FEATURES + FEAT_OBJ_COEFF] += abs_coeff;
                /* Track for instance feature: objective density */
                if (coeff != 0) {
                    obj_var_seen[var_idx] = 1;
                }
            }
        }
    }

    /* =========================================================
     * Pass over constraint expressions
     * ========================================================= */

    /* Temporary buffer for vars_in_constraint per constraint */
    int *vars_in_con = calloc((size_t)n_vars, sizeof(int)); /* boolean flags */
    int *vars_list = malloc((size_t)n_vars * sizeof(int));   /* list of var indices */
    if (!vars_in_con || !vars_list) {
        /* cleanup and return empty */
        free(vars_in_con);
        free(vars_list);
        free(obj_var_seen);
        coeff_acc_free(&all_coeffs);
        for (int i = 0; i < n_vars; i++) {
            coeff_acc_free(&var_coeffs[i]);
            coset_free(&var_co[i]);
        }
        free(var_coeffs);
        free(var_co);
        free(result.var_features);
        result.var_features = NULL;
        result.n_vars = 0;
        return result;
    }

    for (int e = 0; e < n_con; e++) {
        const dyn_expression_t *expr = con_exprs[e];
        if (!expr) continue;
        const int64_t *lits = expr_lits(expr);
        const int *lens = expr_lens(expr);
        size_t n_terms = expr->expr_size;

        int vars_list_len = 0;

        for (size_t t = 0; t < n_terms; t++) {
            int term_len = lens[t];
            if (term_len < 2) continue; /* constant term */
            int64_t coeff = lits[t * MAX_VARS_PER_TERM];
            double abs_coeff = fabs((double)coeff);

            /* Instance feature: accumulate all constraint coefficients */
            coeff_acc_push(&all_coeffs, abs_coeff);

            for (int k = 1; k < term_len; k++) {
                int var_idx = (int)lits[t * MAX_VARS_PER_TERM + k];
                if (var_idx < 0 || var_idx >= n_vars) continue;

                /* col 0: degree (number of terms referencing this variable) */
                result.var_features[var_idx * NUM_VAR_FEATURES + FEAT_DEGREE] += 1.0;

                /* Accumulate coefficient for per-variable stats */
                coeff_acc_push(&var_coeffs[var_idx], abs_coeff);

                /* Track unique variables in this constraint */
                if (!vars_in_con[var_idx]) {
                    vars_in_con[var_idx] = 1;
                    vars_list[vars_list_len++] = var_idx;
                }
            }
        }

        /* Build co-occurrence: for each var in constraint, add all others */
        for (int i = 0; i < vars_list_len; i++) {
            int vi = vars_list[i];
            for (int j = 0; j < vars_list_len; j++) {
                int vj = vars_list[j];
                if (vi != vj) {
                    coset_add(&var_co[vi], vj);
                }
            }
        }

        /* Reset vars_in_con flags */
        for (int i = 0; i < vars_list_len; i++) {
            vars_in_con[vars_list[i]] = 0;
        }
    }

    free(vars_in_con);
    free(vars_list);

    /* =========================================================
     * Per-variable: coefficient statistics (cols 1-3)
     * ========================================================= */
    for (int i = 0; i < n_vars; i++) {
        coeff_acc_t *acc = &var_coeffs[i];
        if (acc->count > 0) {
            double sum = 0.0, mx = acc->vals[0], mn = acc->vals[0];
            for (int j = 0; j < acc->count; j++) {
                sum += acc->vals[j];
                if (acc->vals[j] > mx) mx = acc->vals[j];
                if (acc->vals[j] < mn) mn = acc->vals[j];
            }
            result.var_features[i * NUM_VAR_FEATURES + FEAT_COEFF_MEAN] = sum / acc->count;
            result.var_features[i * NUM_VAR_FEATURES + FEAT_COEFF_MAX] = mx;
            result.var_features[i * NUM_VAR_FEATURES + FEAT_COEFF_MIN] = mn;
        }
    }

    /* =========================================================
     * Per-variable: variable properties (cols 5-6)
     * ========================================================= */
    for (int i = 0; i < n_vars; i++) {
        result.var_features[i * NUM_VAR_FEATURES + FEAT_BOUNDS_WIDTH] = ub[i] - lb[i];
        result.var_features[i * NUM_VAR_FEATURES + FEAT_IS_INTEGER] =
            (vtype[i] == INTEGER) ? 1.0 : 0.0;
    }

    /* =========================================================
     * Per-variable: neighbor features (cols 7-8)
     * ========================================================= */
    for (int i = 0; i < n_vars; i++) {
        coset_t *co = &var_co[i];
        result.var_features[i * NUM_VAR_FEATURES + FEAT_NUM_CO_OCCURRING] = (double)co->count;
        if (co->count > 0) {
            double deg_sum = 0.0;
            int deg_count = 0;
            for (int j = 0; j < co->count; j++) {
                int idx = co->ids[j];
                if (idx >= 0 && idx < n_vars) {
                    deg_sum += result.var_features[idx * NUM_VAR_FEATURES + FEAT_DEGREE];
                    deg_count++;
                }
            }
            if (deg_count > 0) {
                result.var_features[i * NUM_VAR_FEATURES + FEAT_AVG_NEIGHBOR_DEGREE] =
                    deg_sum / deg_count;
            }
        }
    }

    /* =========================================================
     * Per-variable: z-score normalization per column
     * ========================================================= */
    for (int col = 0; col < NUM_VAR_FEATURES; col++) {
        double sum = 0.0;
        for (int i = 0; i < n_vars; i++) {
            sum += result.var_features[i * NUM_VAR_FEATURES + col];
        }
        double mean = sum / n_vars;

        double var_sum = 0.0;
        for (int i = 0; i < n_vars; i++) {
            double diff = result.var_features[i * NUM_VAR_FEATURES + col] - mean;
            var_sum += diff * diff;
        }
        double std = sqrt(var_sum / n_vars);

        if (std > 0.0) {
            for (int i = 0; i < n_vars; i++) {
                result.var_features[i * NUM_VAR_FEATURES + col] =
                    (result.var_features[i * NUM_VAR_FEATURES + col] - mean) / std;
            }
        } else {
            for (int i = 0; i < n_vars; i++) {
                result.var_features[i * NUM_VAR_FEATURES + col] = 0.0;
            }
        }
    }

    /* =========================================================
     * Instance-level features
     * ========================================================= */

    /* col 0: n_variables */
    result.inst_features[0] = (double)n_vars;

    /* col 1: n_constraints */
    result.inst_features[1] = (double)n_con;

    /* col 2: constraint_density */
    result.inst_features[2] = (n_vars > 0) ? (double)n_con / n_vars : 0.0;

    /* col 3: constraint_variable_ratio (same as density) */
    result.inst_features[3] = result.inst_features[2];

    /* col 4: objective_density */
    if (n_vars > 0) {
        int obj_count = 0;
        for (int i = 0; i < n_vars; i++) {
            if (obj_var_seen[i]) obj_count++;
        }
        result.inst_features[4] = (double)obj_count / n_vars;
    }

    /* col 5: integer_variable_fraction */
    if (n_vars > 0) {
        int n_int = 0;
        for (int i = 0; i < n_vars; i++) {
            if (vtype[i] == INTEGER) n_int++;
        }
        result.inst_features[5] = (double)n_int / n_vars;
    }

    /* cols 6-8: global constraint coefficient statistics */
    if (all_coeffs.count > 0) {
        double sum = 0.0, mx = all_coeffs.vals[0];
        for (int i = 0; i < all_coeffs.count; i++) {
            sum += all_coeffs.vals[i];
            if (all_coeffs.vals[i] > mx) mx = all_coeffs.vals[i];
        }
        double mean = sum / all_coeffs.count;
        result.inst_features[6] = mean;

        double var_sum = 0.0;
        for (int i = 0; i < all_coeffs.count; i++) {
            double diff = all_coeffs.vals[i] - mean;
            var_sum += diff * diff;
        }
        result.inst_features[7] = sqrt(var_sum / all_coeffs.count);
        result.inst_features[8] = mx;
    }

    /* cols 9-10: bounds tightness statistics */
    if (n_vars > 0) {
        double sum = 0.0;
        for (int i = 0; i < n_vars; i++) {
            sum += (ub[i] - lb[i]);
        }
        double mean = sum / n_vars;
        result.inst_features[9] = mean;

        double var_sum = 0.0;
        for (int i = 0; i < n_vars; i++) {
            double diff = (ub[i] - lb[i]) - mean;
            var_sum += diff * diff;
        }
        result.inst_features[10] = sqrt(var_sum / n_vars);
    }

    /* Cleanup */
    free(obj_var_seen);
    coeff_acc_free(&all_coeffs);
    for (int i = 0; i < n_vars; i++) {
        coeff_acc_free(&var_coeffs[i]);
        coset_free(&var_co[i]);
    }
    free(var_coeffs);
    free(var_co);

    return result;
}

void features_result_free(features_result_t *result) {
    if (result) {
        free(result->var_features);
        result->var_features = NULL;
        result->n_vars = 0;
    }
}
