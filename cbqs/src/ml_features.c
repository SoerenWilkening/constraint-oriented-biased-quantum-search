/**
 * ml_features.c - C-level feature extraction for ML branching parameter prediction
 *
 * Single-pass extraction of per-variable and instance-level features from
 * compiled constraint data. Matches the Python FeatureExtractor output exactly.
 */

#include "ml_features.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ------------------------------------------------------------------ */
/* Helper: iterate clauses of constraint cnstr, calling body for each  */
/* clause with (factor, variable_indices[], clause_len).               */
/* ------------------------------------------------------------------ */

/**
 * Accumulate per-variable coefficient data from a constraint set.
 *
 * For each variable in each clause, records the absolute coefficient.
 * Tracks: degree (count), coeff_sum, coeff_max, coeff_min, coeff_count.
 * Also builds co-occurrence: for each variable, a bitset of which other
 * variables share a constraint.
 */
static void scan_constraints(
    const new_constraints_t *con,
    int n_vars,
    /* per-variable accumulators (length n_vars each) */
    double *degree,         /* constraint count */
    double *coeff_sum,      /* sum of |coeff| */
    double *coeff_max,      /* max |coeff| */
    double *coeff_min,      /* min |coeff|, init to -1 meaning unset */
    int *coeff_count,       /* number of coefficient observations */
    /* co-occurrence: bitset per variable, length n_vars * ((n_vars+63)/64) */
    uint64_t *co_occur,
    int co_occur_stride,    /* number of uint64_t words per variable */
    /* instance-level accumulators */
    double *all_coeff_sum,
    double *all_coeff_sq_sum,
    int *all_coeff_count,
    double *all_coeff_max
)
{
    uint32_t C = con->num_constraints;

    for (uint32_t cnstr = 0; cnstr < C; cnstr++) {
        size_t clause_offset = (cnstr == 0) ? 0 : con->clause_offset[cnstr - 1];
        uint32_t n_clauses = con->num_clauses[cnstr];

        /* Collect all variables appearing in this constraint */
        /* Use a temporary array; max realistic size bounded by total clauses */
        int vars_buf[4096];
        int n_vars_in_con = 0;

        for (uint32_t cls = 0; cls < n_clauses; cls++) {
            size_t ci = clause_offset + cls;
            int64_t factor = con->factors[ci];
            double abs_coeff = (factor < 0) ? (double)(-factor) : (double)factor;
            uint32_t cl_len = con->clause_length[ci];

            /* Instance-level coefficient stats */
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

                /* Per-variable stats */
                degree[var_idx] += 1.0;
                coeff_sum[var_idx] += abs_coeff;
                coeff_count[var_idx]++;
                if (abs_coeff > coeff_max[var_idx])
                    coeff_max[var_idx] = abs_coeff;
                if (coeff_min[var_idx] < 0 || abs_coeff < coeff_min[var_idx])
                    coeff_min[var_idx] = abs_coeff;

                /* Track for co-occurrence */
                if (n_vars_in_con < 4096)
                    vars_buf[n_vars_in_con++] = (int)var_idx;
            }
        }

        /* Build co-occurrence from vars_buf */
        for (int i = 0; i < n_vars_in_con; i++) {
            int vi = vars_buf[i];
            for (int j = 0; j < n_vars_in_con; j++) {
                int vj = vars_buf[j];
                if (vi != vj) {
                    co_occur[vi * co_occur_stride + (vj >> 6)] |=
                        (1ULL << (vj & 63));
                }
            }
        }
    }
}

/**
 * Scan objective constraints for per-variable objective coefficients.
 * Also counts variables with nonzero objective coefficient (for obj_density).
 */
static void scan_objective(
    const new_constraints_t *obj,
    int n_vars,
    double *obj_coeff,     /* per-variable: sum of |coeff| in objective */
    int *obj_var_count      /* output: count of variables with nonzero obj coeff */
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

    /* Count variables with nonzero objective coefficient */
    for (int i = 0; i < n_vars; i++) {
        if (obj_coeff[i] > 0.0)
            (*obj_var_count)++;
    }
}

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

    /* Allocate per-variable accumulators */
    double *degree     = calloc(n_vars, sizeof(double));
    double *coeff_sum  = calloc(n_vars, sizeof(double));
    double *coeff_max  = calloc(n_vars, sizeof(double));
    double *coeff_min  = calloc(n_vars, sizeof(double));
    int    *coeff_cnt  = calloc(n_vars, sizeof(int));
    double *obj_coeff  = calloc(n_vars, sizeof(double));

    /* Initialize coeff_min to -1 (unset sentinel) */
    for (int i = 0; i < n_vars; i++)
        coeff_min[i] = -1.0;

    /* Co-occurrence bitset */
    int co_stride = (n_vars + 63) / 64;
    uint64_t *co_occur = calloc((size_t)n_vars * co_stride, sizeof(uint64_t));

    /* Instance-level accumulators */
    double all_coeff_sum = 0, all_coeff_sq_sum = 0, all_coeff_max = 0;
    int all_coeff_count = 0;

    /* Scan constraints */
    scan_constraints(con, n_vars,
                     degree, coeff_sum, coeff_max, coeff_min, coeff_cnt,
                     co_occur, co_stride,
                     &all_coeff_sum, &all_coeff_sq_sum,
                     &all_coeff_count, &all_coeff_max);

    /* Scan objective */
    int obj_var_count = 0;
    scan_objective(obj, n_vars, obj_coeff, &obj_var_count);

    /* Zero the output arrays */
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

        /* Count co-occurring variables from bitset */
        int n_co = 0;
        for (int w = 0; w < co_stride; w++) {
            uint64_t bits = co_occur[i * co_stride + w];
            /* popcount */
            while (bits) {
                n_co++;
                bits &= bits - 1;
            }
        }
        out_var[row + 8] = (double)n_co;
    }

    /* avg_neighbor_degree (column 7) - needs degree to be filled first */
    for (int i = 0; i < n_vars; i++) {
        int row = i * ML_NUM_VAR_FEATURES;
        int n_co = (int)out_var[row + 8];
        if (n_co == 0) continue;
        double sum_deg = 0;
        for (int w = 0; w < co_stride; w++) {
            uint64_t bits = co_occur[i * co_stride + w];
            while (bits) {
                int bit = w * 64 + __builtin_ctzll(bits);
                if (bit < n_vars)
                    sum_deg += degree[bit];
                bits &= bits - 1;
            }
        }
        out_var[row + 7] = sum_deg / n_co;
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
    out_inst[3] = out_inst[2]; /* same as constraint_density */
    out_inst[4] = (n_vars > 0) ? (double)obj_var_count / n_vars : 0.0;

    /* integer_variable_fraction */
    int n_integer = 0;
    for (int i = 0; i < n_vars; i++)
        if (vars[i].is_integer) n_integer++;
    out_inst[5] = (n_vars > 0) ? (double)n_integer / n_vars : 0.0;

    /* Coefficient statistics */
    if (all_coeff_count > 0) {
        double cmean = all_coeff_sum / all_coeff_count;
        double cvar = all_coeff_sq_sum / all_coeff_count - cmean * cmean;
        out_inst[6] = cmean;
        out_inst[7] = (cvar > 0) ? sqrt(cvar) : 0.0;
        out_inst[8] = all_coeff_max;
    }

    /* Bounds tightness */
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

    /* Clean up */
    free(degree);
    free(coeff_sum);
    free(coeff_max);
    free(coeff_min);
    free(coeff_cnt);
    free(obj_coeff);
    free(co_occur);
}
