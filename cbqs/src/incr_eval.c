/* incr_eval -- bd 0o8.2 (exact win A). See incr_eval.h for the marginal algebra. */
#include "incr_eval.h"
#include <stdlib.h>
#include <string.h>

struct incr_state {
    int n;
    size_t C;
    /* CSR adjacency keyed by the EARLIER-rank endpoint u: one directed edge per
     * bilinear pair {u,w} (rank[u] < rank[w]). */
    size_t   *adj_off;   /* [n+1] */
    int      *adj_w;     /* [E] later endpoint */
    uint32_t *adj_c;     /* [E] constraint */
    int64_t  *adj_absf;  /* [E] |factor| */
    uint8_t  *adj_pos;   /* [E] 1 = POSITIVE arm (pos_acc), 0 = NEGATIVE arm (neg_cond) */
    /* static per (var, constraint), index v*C + c */
    int64_t  *pos_diag;   /* reset value for pos_acc (positive diagonal) */
    int64_t  *neg_static; /* negative diagonal + later-negative-pair |f| (earlier endpoint) */
    /* per-candidate accumulators, index v*C + c */
    int64_t  *pos_acc;
    int64_t  *neg_cond;
};

static inline int rk(const int *rank, int v) { return rank ? rank[v] : v; }

static void incr_free_partial(incr_state_t *st) {
    if (!st) return;
    free(st->adj_off); free(st->adj_w); free(st->adj_c); free(st->adj_absf); free(st->adj_pos);
    free(st->pos_diag); free(st->neg_static); free(st->pos_acc); free(st->neg_cond);
    free(st);
}

incr_state_t *incr_create(new_constraints_t *con, int n, const int *order, const int *rank) {
    (void)order; /* edges are pre-oriented by rank at build; marginal/commit need only `rank`-built data */
    if (n <= 0) return NULL;
    const size_t C = con->num_constraints;
    const size_t CN = (size_t)n * C;

    incr_state_t *st = calloc(1, sizeof(*st));
    if (!st) return NULL;
    st->n = n; st->C = C;
    st->adj_off    = calloc((size_t)n + 1, sizeof(size_t));
    st->pos_diag   = calloc(CN, sizeof(int64_t));
    st->neg_static = calloc(CN, sizeof(int64_t));
    st->pos_acc    = malloc(CN * sizeof(int64_t));
    st->neg_cond   = malloc(CN * sizeof(int64_t));
    if (!st->adj_off || !st->pos_diag || !st->neg_static ||
        (CN && (!st->pos_acc || !st->neg_cond))) { incr_free_partial(st); return NULL; }

    /* Pass 1: detect applicability, fill static arrays, count out-degrees. */
    for (size_t c = 0; c < C; c++) {
        const size_t clause_offset = first_clause_index(con, c);
        const uint32_t nc = con->num_clauses[c];
        for (uint32_t cls = 0; cls < nc; cls++) {
            const size_t ci = clause_offset + cls;
            const int64_t f = con->factors[ci];
            if (f == 0) continue;                    /* no charge */
            const uint32_t len = con->clause_length[ci];
            int64_t absf = f < 0 ? -f : f;
            const int positive = (f > 0);
            if (len == 1) {
                int v = (int)con->variables[variable_index(cls, 0, clause_offset)];
                if (positive) st->pos_diag[(size_t)v * C + c] += absf;
                else          st->neg_static[(size_t)v * C + c] += absf;
            } else if (len == 2) {
                int a = (int)con->variables[variable_index(cls, 0, clause_offset)];
                int b = (int)con->variables[variable_index(cls, 1, clause_offset)];
                if (a == b) {                        /* x_i*x_i: idempotent -> diagonal (eq29) */
                    if (positive) st->pos_diag[(size_t)a * C + c] += absf;
                    else          st->neg_static[(size_t)a * C + c] += absf;
                } else {
                    int u = (rk(rank, a) <= rk(rank, b)) ? a : b;  /* earlier endpoint */
                    st->adj_off[u + 1]++;            /* one directed edge u->(later) */
                    if (!positive) st->neg_static[(size_t)u * C + c] += absf; /* earlier endpoint's later-pair part */
                }
            } else {
                incr_free_partial(st);               /* k-ary (>2): not bilinear -> dense fallback */
                return NULL;
            }
        }
    }

    /* prefix-sum out-degrees into CSR offsets */
    for (int v = 0; v < n; v++) st->adj_off[v + 1] += st->adj_off[v];
    const size_t E = st->adj_off[n];
    if (E) {
        st->adj_w    = malloc(E * sizeof(int));
        st->adj_c    = malloc(E * sizeof(uint32_t));
        st->adj_absf = malloc(E * sizeof(int64_t));
        st->adj_pos  = malloc(E * sizeof(uint8_t));
        if (!st->adj_w || !st->adj_c || !st->adj_absf || !st->adj_pos) { incr_free_partial(st); return NULL; }
    }

    /* Pass 2: fill edges (cursor per earlier endpoint). */
    size_t *cur = malloc((size_t)n * sizeof(size_t));
    if (n && !cur) { incr_free_partial(st); return NULL; }
    for (int v = 0; v < n; v++) cur[v] = st->adj_off[v];
    for (size_t c = 0; c < C; c++) {
        const size_t clause_offset = first_clause_index(con, c);
        const uint32_t nc = con->num_clauses[c];
        for (uint32_t cls = 0; cls < nc; cls++) {
            const size_t ci = clause_offset + cls;
            const int64_t f = con->factors[ci];
            if (f == 0 || con->clause_length[ci] != 2) continue;
            int a = (int)con->variables[variable_index(cls, 0, clause_offset)];
            int b = (int)con->variables[variable_index(cls, 1, clause_offset)];
            if (a == b) continue;                /* diagonal (handled in pass 1) -> no edge */
            int u = a, w = b;
            if (rk(rank, a) > rk(rank, b)) { u = b; w = a; }
            size_t e = cur[u]++;
            st->adj_w[e]    = w;
            st->adj_c[e]    = (uint32_t)c;
            st->adj_absf[e] = f < 0 ? -f : f;
            st->adj_pos[e]  = (f > 0) ? 1 : 0;
        }
    }
    free(cur);

    incr_reset(st);
    return st;
}

void incr_reset(incr_state_t *st) {
    const size_t CN = (size_t)st->n * st->C;
    memcpy(st->pos_acc, st->pos_diag, CN * sizeof(int64_t));
    memset(st->neg_cond, 0, CN * sizeof(int64_t));
}

void incr_marginal(const incr_state_t *st, int item, const int64_t *potentials,
                   int64_t *ret_total_pos, int *feas_pos,
                   int64_t *ret_total_neg, int *feas_neg) {
    const size_t C = st->C;
    const size_t base = (size_t)item * C;
    int fp = 1, fn = 1;
    for (size_t c = 0; c < C; c++) {
        int64_t p = st->pos_acc[base + c];
        int64_t ng = st->neg_cond[base + c] + st->neg_static[base + c];
        ret_total_pos[c] = p;
        ret_total_neg[c] = ng;
        if (potentials[c] < p)  fp = 0;
        if (potentials[c] < ng) fn = 0;
    }
    *feas_pos = fp;
    *feas_neg = fn;
}

void incr_commit(incr_state_t *st, int item, int bit) {
    if (bit != 1) return;                            /* contribution is |f| * bit */
    const size_t C = st->C;
    const size_t end = st->adj_off[item + 1];
    for (size_t e = st->adj_off[item]; e < end; e++) {
        const size_t idx = (size_t)st->adj_w[e] * C + st->adj_c[e];
        if (st->adj_pos[e]) st->pos_acc[idx]  += st->adj_absf[e];
        else                st->neg_cond[idx] += st->adj_absf[e];
    }
}

void incr_free(incr_state_t *st) { incr_free_partial(st); }
