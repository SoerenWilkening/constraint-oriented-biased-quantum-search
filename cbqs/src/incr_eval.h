/*
 * incr_eval -- bd 0o8.2 (exact win A): incremental candidate-construction marginals.
 *
 * The CSearch_* candidate sweeps call look_ahead_correct()/evaluation() TWICE per
 * variable (assign=1 POSITIVE arm, assign=0 NEGATIVE arm), each re-scanning ALL of
 * the variable's clauses -- O(deg) per call, O(n^2) per candidate for the dense
 * bilinear Eq.29 family. This module maintains the SAME per-constraint marginals
 * incrementally as the sweep finalizes bits, so the per-position feasibility test
 * is O(C) reads and the only O(deg) work happens once per variable that is set to 1.
 *
 * BIT-FOR-BIT contract: incr_marginal() returns the IDENTICAL ret_total[] and
 * feasibility verdict that look_ahead_correct(item, 1/0, item, ...) computes via the
 * dense evaluation() (cbqs/src/solver.c) at depth_look_ahead==0. evaluation() itself
 * is UNCHANGED (it remains the depth>0 recursion path and the test oracle). This
 * fast path is used ONLY when depth_look_ahead==0 AND every clause has length <= 2
 * (bilinear); otherwise incr_create() returns NULL and the caller uses the dense path.
 *
 * Marginal algebra (verified by the cross-check test against evaluation()):
 *   POSITIVE arm (positive-factor clauses; charge at the LAST-rank member, all
 *   earlier members 1):  POS(v,c) = pos_acc[v,c]
 *     pos_acc init = sum of |diag positive factor| at v; on commit(u:=1), for each
 *     positive pair {u,w} with rank[u]<rank[w]: pos_acc[w,c] += |f|.
 *   NEGATIVE arm (negative-factor clauses; charge per member on all-earlier-1):
 *     NEG(v,c) = neg_cond[v,c] + neg_static[v,c]
 *     neg_static = |diag negative factor| + sum over negative pairs {v,w}, rank[w]>
 *       rank[v], of |f| (the unconditional later-pair part for the EARLIER endpoint);
 *     neg_cond init 0; on commit(u:=1), for each negative pair {u,w} rank[u]<rank[w]:
 *       neg_cond[w,c] += |f| (the conditional part for the LATER endpoint).
 */
#ifndef INCR_EVAL_H
#define INCR_EVAL_H

#include "constraint.h"
#include <stdint.h>

typedef struct incr_state incr_state_t;

/* Build the per-solve static structures (adjacency + static parts) for `con` under
 * traversal `order`/`rank` (NULL == identity, exactly as evaluation()). The sweep
 * MUST visit variables in rank order (position k => rank k). Returns NULL iff the
 * fast path does not apply (any clause length > 2) -- caller falls back to dense. */
incr_state_t *incr_create(new_constraints_t *con, int n, const int *order, const int *rank);

/* Reset the per-candidate accumulators (call once at the start of each candidate). */
void incr_reset(incr_state_t *st);

/* Marginals for `item` given the running `potentials`. Fills, for every constraint c:
 *   ret_total_pos[c] = POSITIVE-arm charge  (== look_ahead_correct(item,1,item,...) ret_total)
 *   ret_total_neg[c] = NEGATIVE-arm charge  (== look_ahead_correct(item,0,item,...) ret_total)
 * and sets *feas_pos / *feas_neg = 1 iff potentials[c] >= the corresponding charge for
 * ALL c (== the count incremented by look_ahead_correct). */
void incr_marginal(const incr_state_t *st, int item, const int64_t *potentials,
                   int64_t *ret_total_pos, int *feas_pos,
                   int64_t *ret_total_neg, int *feas_neg);

/* Commit item := bit. When bit==1, propagate |factor| into successors' accumulators
 * (O(out-degree of item)); when bit==0, a no-op (the contribution is *bit == 0). */
void incr_commit(incr_state_t *st, int item, int bit);

void incr_free(incr_state_t *st);

#endif /* INCR_EVAL_H */
