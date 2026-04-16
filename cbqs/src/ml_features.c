/**
 * ml_features.c - C-level feature extraction and prediction pipeline
 *
 * Two-phase extraction of per-variable and instance-level features from
 * compiled constraint data. Matches the Python FeatureExtractor output exactly.
 *
 * Phase 1: Scan coefficients + detect if any constraint contains all variables.
 * Phase 2: If a "full" constraint exists, compute co-occurrence analytically
 *          (O(n)); otherwise build co-occurrence bitset (O(n * stride)).
 *
 * predict_params() fuses the entire pipeline:
 *   features → degree-2 poly expansion → matmul → post-processing
 * without materializing any intermediate arrays.
 */

#include "ml_features.h"
#include "platform.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Route popcount through platform.h for MSVC/GCC/Clang/pure-C coverage */
#define POPCOUNT64(x) cbqs_popcount64(x)

/* ------------------------------------------------------------------ */
/* Phase 1: Scan coefficient statistics from constraints.             */
/* Returns the maximum number of unique variables in any constraint.  */
/* ------------------------------------------------------------------ */

static int scan_constraint_coeffs(
    const new_constraints_t *con,
    int n_vars,
    double *degree,
    double *coeff_sum,
    double *coeff_max,
    double *coeff_min,
    int *coeff_count,
    double *all_coeff_sum,
    double *all_coeff_sq_sum,
    int *all_coeff_count,
    double *all_coeff_max
)
{
    uint32_t C = con->num_constraints;
    int max_unique_vars = 0;

    int bit_stride = (n_vars + 63) / 64;
    uint64_t *unique_bits = malloc(bit_stride * sizeof(uint64_t));

    for (uint32_t cnstr = 0; cnstr < C; cnstr++) {
        size_t clause_offset = (cnstr == 0) ? 0 : con->clause_offset[cnstr - 1];
        uint32_t n_clauses = con->num_clauses[cnstr];

        memset(unique_bits, 0, bit_stride * sizeof(uint64_t));

        for (uint32_t cls = 0; cls < n_clauses; cls++) {
            size_t ci = clause_offset + cls;
            int64_t factor = con->factors[ci];
            double abs_coeff = (factor < 0) ? (double)(-factor) : (double)factor;
            uint32_t cl_len = con->clause_length[ci];

            *all_coeff_sum += abs_coeff;
            *all_coeff_sq_sum += abs_coeff * abs_coeff;
            (*all_coeff_count)++;
            if (abs_coeff > *all_coeff_max)
                *all_coeff_max = abs_coeff;

            for (uint32_t k = 0; k < cl_len; k++) {
                size_t vi = (cls == 0)
                    ? clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1) + k
                    : clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1)
                      + (CONSTRAINT_VARS_PER_CLAUSE - 1) * cls + k;
                uint32_t var_idx = con->variables[vi];
                if ((int)var_idx >= n_vars) continue;

                degree[var_idx] += 1.0;
                coeff_sum[var_idx] += abs_coeff;
                coeff_count[var_idx]++;
                if (abs_coeff > coeff_max[var_idx])
                    coeff_max[var_idx] = abs_coeff;
                if (coeff_min[var_idx] < 0 || abs_coeff < coeff_min[var_idx])
                    coeff_min[var_idx] = abs_coeff;

                unique_bits[var_idx >> 6] |= (1ULL << (var_idx & 63));
            }
        }

        int n_unique = 0;
        for (int w = 0; w < bit_stride; w++)
            n_unique += POPCOUNT64(unique_bits[w]);
        if (n_unique > max_unique_vars)
            max_unique_vars = n_unique;
    }

    free(unique_bits);
    return max_unique_vars;
}

/* ------------------------------------------------------------------ */
/* Phase 2a: Build co-occurrence bitset (sparse constraint path).     */
/* ------------------------------------------------------------------ */

static void build_cooccurrence(
    const new_constraints_t *con,
    int n_vars,
    uint64_t *co_occur,
    int co_stride
)
{
    uint32_t C = con->num_constraints;

    uint64_t *con_bitset = calloc(co_stride, sizeof(uint64_t));
    int vars_buf_cap = 4096;
    int *vars_buf = malloc(vars_buf_cap * sizeof(int));

    for (uint32_t cnstr = 0; cnstr < C; cnstr++) {
        size_t clause_offset = (cnstr == 0) ? 0 : con->clause_offset[cnstr - 1];
        uint32_t n_clauses = con->num_clauses[cnstr];
        int n_vars_in_con = 0;

        memset(con_bitset, 0, co_stride * sizeof(uint64_t));

        for (uint32_t cls = 0; cls < n_clauses; cls++) {
            size_t ci = clause_offset + cls;
            uint32_t cl_len = con->clause_length[ci];

            for (uint32_t k = 0; k < cl_len; k++) {
                size_t vi = (cls == 0)
                    ? clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1) + k
                    : clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1)
                      + (CONSTRAINT_VARS_PER_CLAUSE - 1) * cls + k;
                uint32_t var_idx = con->variables[vi];
                if ((int)var_idx >= n_vars) continue;

                if (n_vars_in_con >= vars_buf_cap) {
                    vars_buf_cap *= 2;
                    vars_buf = realloc(vars_buf, vars_buf_cap * sizeof(int));
                }
                vars_buf[n_vars_in_con++] = (int)var_idx;
                con_bitset[var_idx >> 6] |= (1ULL << (var_idx & 63));
            }
        }

        for (int i = 0; i < n_vars_in_con; i++) {
            int vi = vars_buf[i];
            uint64_t *row = co_occur + (size_t)vi * co_stride;
            for (int w = 0; w < co_stride; w++)
                row[w] |= con_bitset[w];
            row[vi >> 6] &= ~(1ULL << (vi & 63));
        }
    }

    free(con_bitset);
    free(vars_buf);
}

/* ------------------------------------------------------------------ */
/* Scan objective constraints.                                        */
/* ------------------------------------------------------------------ */

static void scan_objective(
    const new_constraints_t *obj,
    int n_vars,
    double *obj_coeff,
    int *obj_var_count
)
{
    uint32_t C = obj->num_constraints;
    *obj_var_count = 0;

    for (uint32_t cnstr = 0; cnstr < C; cnstr++) {
        size_t clause_offset = (cnstr == 0) ? 0 : obj->clause_offset[cnstr - 1];
        uint32_t n_clauses = obj->num_clauses[cnstr];

        for (uint32_t cls = 0; cls < n_clauses; cls++) {
            size_t ci = clause_offset + cls;
            int64_t factor = obj->factors[ci];
            double abs_coeff = (factor < 0) ? (double)(-factor) : (double)factor;
            uint32_t cl_len = obj->clause_length[ci];

            for (uint32_t k = 0; k < cl_len; k++) {
                size_t vi = (cls == 0)
                    ? clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1) + k
                    : clause_offset * (CONSTRAINT_VARS_PER_CLAUSE - 1)
                      + (CONSTRAINT_VARS_PER_CLAUSE - 1) * cls + k;
                uint32_t var_idx = obj->variables[vi];
                if ((int)var_idx >= n_vars) continue;
                obj_coeff[var_idx] += abs_coeff;
            }
        }
    }

    for (int i = 0; i < n_vars; i++) {
        if (obj_coeff[i] > 0.0)
            (*obj_var_count)++;
    }
}

/* ------------------------------------------------------------------ */
/* Internal: extract features into caller-provided buffers.           */
/* Shared by both extract_features() and predict_params().            */
/* ------------------------------------------------------------------ */

static void extract_features_internal(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    double *out_var,    /* n_vars * 9, row-major */
    double *out_inst    /* 11 doubles */
)
{
    /* Single contiguous allocation for all per-variable accumulators */
    size_t dbl_arrays = 5;
    size_t dbl_bytes = dbl_arrays * n_vars * sizeof(double);
    size_t int_bytes = n_vars * sizeof(int);
    char *block = calloc(1, dbl_bytes + int_bytes);

    double *degree    = (double *)(block);
    double *coeff_sum = (double *)(block + 1 * n_vars * sizeof(double));
    double *coeff_max = (double *)(block + 2 * n_vars * sizeof(double));
    double *coeff_min = (double *)(block + 3 * n_vars * sizeof(double));
    double *obj_coeff = (double *)(block + 4 * n_vars * sizeof(double));
    int    *coeff_cnt = (int *)(block + dbl_bytes);

    for (int i = 0; i < n_vars; i++)
        coeff_min[i] = -1.0;

    double all_coeff_sum = 0, all_coeff_sq_sum = 0, all_coeff_max = 0;
    int all_coeff_count = 0;

    int max_unique = scan_constraint_coeffs(
        con, n_vars,
        degree, coeff_sum, coeff_max, coeff_min, coeff_cnt,
        &all_coeff_sum, &all_coeff_sq_sum, &all_coeff_count, &all_coeff_max);

    int all_cooccur = (max_unique >= n_vars);

    int obj_var_count = 0;
    scan_objective(obj, n_vars, obj_coeff, &obj_var_count);

    memset(out_var, 0, (size_t)n_vars * ML_NUM_VAR_FEATURES * sizeof(double));
    memset(out_inst, 0, ML_NUM_INST_FEATURES * sizeof(double));

    /* Fill per-variable features (raw, before z-score) */
    for (int i = 0; i < n_vars; i++) {
        int row = i * ML_NUM_VAR_FEATURES;
        out_var[row + 0] = degree[i];
        out_var[row + 1] = (coeff_cnt[i] > 0) ? coeff_sum[i] / coeff_cnt[i] : 0.0;
        out_var[row + 2] = coeff_max[i];
        out_var[row + 3] = (coeff_min[i] < 0) ? 0.0 : coeff_min[i];
        out_var[row + 4] = obj_coeff[i];
        out_var[row + 5] = vars[i].ub - vars[i].lb;
        out_var[row + 6] = vars[i].is_integer ? 1.0 : 0.0;
    }

    if (all_cooccur) {
        double total_degree = 0;
        for (int i = 0; i < n_vars; i++)
            total_degree += degree[i];

        double inv_nco = 1.0 / (n_vars - 1);
        for (int i = 0; i < n_vars; i++) {
            int row = i * ML_NUM_VAR_FEATURES;
            out_var[row + 8] = (double)(n_vars - 1);
            out_var[row + 7] = (total_degree - degree[i]) * inv_nco;
        }
    } else {
        int co_stride = (n_vars + 63) / 64;
        uint64_t *co_occur = calloc((size_t)n_vars * co_stride, sizeof(uint64_t));

        build_cooccurrence(con, n_vars, co_occur, co_stride);

        for (int i = 0; i < n_vars; i++) {
            int row = i * ML_NUM_VAR_FEATURES;
            int n_co = 0;
            uint64_t *row_bits = co_occur + (size_t)i * co_stride;
            for (int w = 0; w < co_stride; w++)
                n_co += POPCOUNT64(row_bits[w]);
            out_var[row + 8] = (double)n_co;
        }

        for (int i = 0; i < n_vars; i++) {
            int row = i * ML_NUM_VAR_FEATURES;
            int n_co = (int)out_var[row + 8];
            if (n_co == 0) continue;
            double sum_deg = 0;
            uint64_t *row_bits = co_occur + (size_t)i * co_stride;
            for (int w = 0; w < co_stride; w++) {
                uint64_t bits = row_bits[w];
                while (bits) {
                    int bit = w * 64 + cbqs_ctz64(bits);
                    if (bit < n_vars)
                        sum_deg += degree[bit];
                    bits &= bits - 1;
                }
            }
            out_var[row + 7] = sum_deg / n_co;
        }

        free(co_occur);
    }

    /* Per-column z-score normalization */
    for (int col = 0; col < ML_NUM_VAR_FEATURES; col++) {
        double sum = 0, sq_sum = 0;
        for (int i = 0; i < n_vars; i++) {
            double v = out_var[i * ML_NUM_VAR_FEATURES + col];
            sum += v;
            sq_sum += v * v;
        }
        double mean = sum / n_vars;
        double variance = sq_sum / n_vars - mean * mean;
        double std = (variance > 0) ? sqrt(variance) : 0;
        if (std > 0) {
            for (int i = 0; i < n_vars; i++)
                out_var[i * ML_NUM_VAR_FEATURES + col] =
                    (out_var[i * ML_NUM_VAR_FEATURES + col] - mean) / std;
        } else {
            for (int i = 0; i < n_vars; i++)
                out_var[i * ML_NUM_VAR_FEATURES + col] = 0.0;
        }
    }

    /* Fill instance features */
    int n_con = (int)con->num_constraints;
    out_inst[0] = (double)n_vars;
    out_inst[1] = (double)n_con;
    out_inst[2] = (n_vars > 0) ? (double)n_con / n_vars : 0.0;
    out_inst[3] = out_inst[2];
    out_inst[4] = (n_vars > 0) ? (double)obj_var_count / n_vars : 0.0;

    int n_integer = 0;
    for (int i = 0; i < n_vars; i++)
        if (vars[i].is_integer) n_integer++;
    out_inst[5] = (n_vars > 0) ? (double)n_integer / n_vars : 0.0;

    if (all_coeff_count > 0) {
        double cmean = all_coeff_sum / all_coeff_count;
        double cvar = all_coeff_sq_sum / all_coeff_count - cmean * cmean;
        out_inst[6] = cmean;
        out_inst[7] = (cvar > 0) ? sqrt(cvar) : 0.0;
        out_inst[8] = all_coeff_max;
    }

    double bw_sum = 0, bw_sq_sum = 0;
    for (int i = 0; i < n_vars; i++) {
        double w = vars[i].ub - vars[i].lb;
        bw_sum += w;
        bw_sq_sum += w * w;
    }
    double bw_mean = bw_sum / n_vars;
    double bw_var = bw_sq_sum / n_vars - bw_mean * bw_mean;
    out_inst[9] = bw_mean;
    out_inst[10] = (bw_var > 0) ? sqrt(bw_var) : 0.0;

    free(block);
}

/* ------------------------------------------------------------------ */
/* Public API: extract_features (legacy, for testing).                */
/* ------------------------------------------------------------------ */

void extract_features(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    double *out_var,
    double *out_inst
)
{
    if (n_vars == 0) {
        memset(out_inst, 0, ML_NUM_INST_FEATURES * sizeof(double));
        return;
    }
    extract_features_internal(obj, con, vars, n_vars, out_var, out_inst);
}

/* ------------------------------------------------------------------ */
/* Fused degree-2 polynomial dot product.                             */
/* Computes w . poly_expand(x) without materializing the expansion.   */
/*                                                                    */
/* For n_feat features, the term layout in w is:                      */
/*   [0]:         intercept (1.0)                                     */
/*   [1..n]:      linear    (x_j)                                     */
/*   [n+1..]:     cross     (x_j * x_k, j < k)                       */
/*   [last n]:    squared   (x_j^2)                                   */
/* ------------------------------------------------------------------ */

static inline double poly2_dot(
    const double *x,       /* feature vector (n_feat,) */
    const double *w,       /* weight vector (n_terms,) */
    int n_feat
)
{
    double result = w[0];  /* intercept */

    /* Linear terms */
    for (int j = 0; j < n_feat; j++)
        result += w[1 + j] * x[j];

    /* Cross terms (j < k) */
    int idx = 1 + n_feat;
    for (int j = 0; j < n_feat; j++)
        for (int k = j + 1; k < n_feat; k++)
            result += w[idx++] * x[j] * x[k];

    /* Squared terms */
    int sq_offset = 1 + n_feat + n_feat * (n_feat - 1) / 2;
    for (int j = 0; j < n_feat; j++)
        result += w[sq_offset + j] * x[j] * x[j];

    return result;
}

/* ------------------------------------------------------------------ */
/* Sub-linear dot product for instance-level outputs.                 */
/* Computes w[0] + sum_j w[1+j] * g(x[j]) where:                     */
/*   g(x) = log(1 + |x|)  if bit j is set in ML_INST_LOG_FEATURES    */
/*   g(x) = x              otherwise (bounded features)              */
/* ------------------------------------------------------------------ */

static inline double log_linear_dot(
    const double *x,       /* feature vector (n_feat,) */
    const double *w,       /* weight vector (ML_INST_TERMS_SUBLINEAR,) */
    int n_feat
)
{
    double result = w[0];  /* intercept */

    for (int j = 0; j < n_feat; j++) {
        double g;
        if (ML_INST_LOG_FEATURES & (1u << j))
            g = log(1.0 + fabs(x[j]));
        else
            g = x[j];
        result += w[1 + j] * g;
    }

    return result;
}

/* ------------------------------------------------------------------ */
/* Argsort helper: sort indices by descending value.                  */
/* ------------------------------------------------------------------ */

static double *_argsort_values;  /* thread-local would be ideal, but qsort_r is non-portable */

static int cmp_desc(const void *a, const void *b)
{
    int ia = *(const int *)a;
    int ib = *(const int *)b;
    double va = _argsort_values[ia];
    double vb = _argsort_values[ib];
    if (va > vb) return -1;
    if (va < vb) return 1;
    return (ia < ib) ? -1 : (ia > ib) ? 1 : 0;  /* stable tie-break */
}

/* ------------------------------------------------------------------ */
/* Public API: predict_params (fused pipeline).                       */
/* ------------------------------------------------------------------ */

void predict_params(
    const new_constraints_t *obj,
    const new_constraints_t *con,
    const variable_meta_t *vars,
    int n_vars,
    const double *W_var,      /* (2, ML_VAR_TERMS) row-major */
    const double *W_inst,     /* (3, ML_INST_TERMS_SUBLINEAR) row-major */
    double delta_pct,
    double *out_weights,      /* (n_vars,) */
    int *out_priorities,      /* (n_vars,) */
    double *out_bias,
    double *out_bf,
    double *out_bif
)
{
    if (n_vars == 0) {
        *out_bias = 0.0;
        *out_bf = 0.0;
        *out_bif = 0.0;
        return;
    }

    /* Extract features into temporary buffers */
    double *var_feat = malloc((size_t)n_vars * ML_NUM_VAR_FEATURES * sizeof(double));
    double inst_feat[ML_NUM_INST_FEATURES];

    extract_features_internal(obj, con, vars, n_vars, var_feat, inst_feat);

    /* Per-variable: fused poly_expand + matmul */
    const double *w_weight = W_var;                      /* row 0 of W_var */
    const double *w_priority = W_var + ML_VAR_TERMS;     /* row 1 of W_var */

    double *priority_scores = malloc(n_vars * sizeof(double));

    for (int i = 0; i < n_vars; i++) {
        const double *x = var_feat + i * ML_NUM_VAR_FEATURES;
        double w = poly2_dot(x, w_weight, ML_NUM_VAR_FEATURES);
        double p = poly2_dot(x, w_priority, ML_NUM_VAR_FEATURES);

        out_weights[i] = (w > 0.0) ? w : 0.0;  /* max(0, weight) */
        priority_scores[i] = p;
        out_priorities[i] = i;  /* initialize for argsort */
    }

    /* Argsort by descending priority score */
    _argsort_values = priority_scores;
    qsort(out_priorities, n_vars, sizeof(int), cmp_desc);

    /* Instance-level: sub-linear log_linear_dot */
    const double *w_bias_delta = W_inst;                              /* row 0 */
    const double *w_bf = W_inst + ML_INST_TERMS_SUBLINEAR;            /* row 1 */
    const double *w_bif = W_inst + 2 * ML_INST_TERMS_SUBLINEAR;      /* row 2 */

    double bias_delta = log_linear_dot(inst_feat, w_bias_delta, ML_NUM_INST_FEATURES);
    double branching_factor = log_linear_dot(inst_feat, w_bf, ML_NUM_INST_FEATURES);
    double bias_factor = log_linear_dot(inst_feat, w_bif, ML_NUM_INST_FEATURES);

    /* Post-process bias */
    double base_bias = n_vars / 4.0;
    double bound = delta_pct * base_bias;
    if (bias_delta < -bound) bias_delta = -bound;
    if (bias_delta > bound) bias_delta = bound;
    *out_bias = base_bias + bias_delta;

    /* Clip factors to non-negative */
    *out_bf = (branching_factor > 0.0) ? branching_factor : 0.0;
    *out_bif = (bias_factor > 0.0) ? bias_factor : 0.0;

    free(var_feat);
    free(priority_scores);
}
