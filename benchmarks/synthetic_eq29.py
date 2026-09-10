"""Synthetic, matched-constraint-tightness Eq.29 instances for the M0g
scale-invariance test (bd 8an.1.7, NORTHSTAR §9).

NORTHSTAR §9 requires synthetic instances spanning n∈{10,100,1000,3000} with
**matched constraint tightness** (`c1/Σw1`, `c2/Σw2` fixed) so that the realized
Hamming-radius distribution and the free-decision fraction f(n) can be compared
across n. This module generates exactly such a *fixed family*: the same
generation distribution (average degree, weight law) at every n, fed through the
canonical Eq.29 build path (`benchmarks.eq29_loader.build_model`).

Tightness is matched **by construction**. The Eq.29 encoding (matching
`run_quantum.py` / `eq29_loader`) is

    objective : maximize  sum_{i>=j}   c1[i,j] x_i x_j
    <= (cap.) : sum_{i>=j} 2 c3[i,j] x_i x_j  <=  sum_{i>=j} c3[i,j]
    >= (cov.) : sum_{i>=j} 2 c2[i,j] x_i x_j  >=  sum_{i>=j} c2[i,j]

i.e. RHS = Σweight while the LHS weights are doubled, so each constraint pins the
feasible region at the **1/2-of-total-weight** isocontour *regardless of n* —
the tightness ratios `c1/Σw1 = c2/Σw2 = 1/2` are size-invariant. We only have to
hold the *generation distribution* fixed across n; this file does that.

Why a **fixed average degree** (sparse) family rather than the paper's dense
matrices: a dense instance has Θ(n²) quadratic terms (~4.5M at n=3000), which is
too heavy to build and solve inside a test. A fixed-average-degree family keeps
the term count Θ(n·d), tractable at n=3000, while still being a single matched
family across n — exactly what the §9 invariance test needs. (The paper's dense
instances are loaded separately via `eq29_loader` for the real M0b/M1 benchmark;
they are not what the scale-invariance test is about.)

The covering `>=` constraint is what makes f(n) non-trivial: it forces some
per-variable decisions (look-ahead leaves only one feasible value), so the
free-decision fraction is genuinely in (0,1) rather than ≈1 as it would be for a
single loose `<=` constraint.

Tightness is set explicitly (``cap_tightness`` / ``cov_tightness``), held FIXED
across n (so the family stays matched), and defaults to a reliably co-feasible
band. The Eq.29 paper's RHS=Σweight rule pins both constraints at the 1/2
isocontour, where the `<=`/`>=` pair leaves only a narrow feasible band — many
random instances are then infeasible (§3: "the covering constraint makes many
constructions infeasible"), which is faithful but starves the opt phase the
scale-invariance test needs to observe. We therefore loosen to ``cap_tightness``
of the max capacity mass and ``cov_tightness`` of the max covering mass; both are
fixed ratios, so tightness is still matched across n.
"""
import numpy as np

# A NumPy SeedSequence-derived stream per (n, index) keeps instances reproducible
# and statistically independent across sizes/indices without cross-talk.
_FAMILY_ENTROPY = 0x0CB_05_8A_17  # "CBQS 8an.1.7" — fixed family salt


def _lower_tri_sparse(rng, n, avg_degree, weight_low, weight_high):
    """A lower-triangular int64 matrix with ~avg_degree off-diagonal nonzeros
    per variable and a populated diagonal. Symmetric-pattern sparsity folded into
    the lower triangle (so build_model's i>=j sum sees each pair once)."""
    a = np.zeros((n, n), dtype=np.int64)
    # Diagonal (the p_ii / w_ii single-variable terms) is always present.
    a[np.diag_indices(n)] = rng.integers(weight_low, weight_high + 1, size=n)
    if n > 1 and avg_degree > 0:
        # Total off-diagonal (lower) nonzeros ≈ n*avg_degree/2 (each undirected
        # pair stored once). Cap at the number of available below-diagonal cells.
        max_pairs = n * (n - 1) // 2
        n_pairs = min(max_pairs, int(round(n * avg_degree / 2.0)))
        if n_pairs > 0:
            rows = np.empty(0, dtype=np.int64)
            cols = np.empty(0, dtype=np.int64)
            # Rejection-sample distinct (i>j) cells. For sparse families
            # collisions are rare; loop until we have enough distinct pairs.
            seen = set()
            while len(seen) < n_pairs:
                need = n_pairs - len(seen)
                ii = rng.integers(1, n, size=need * 2)
                jj = rng.integers(0, n - 1, size=need * 2)
                for i, j in zip(ii.tolist(), jj.tolist()):
                    if i > j:
                        seen.add((i, j))
                        if len(seen) >= n_pairs:
                            break
            for (i, j) in seen:
                a[i, j] = rng.integers(weight_low, weight_high + 1)
    return a


def make_matrices(n, index=0, avg_degree=8, weight_low=1, weight_high=10):
    """Generate the lower-triangular (c1, c2, c3) int64 matrices for a synthetic
    Eq.29 instance of size *n*, instance *index*.

    Same (avg_degree, weight law) at every n ⇒ matched family. Independent draws
    for c1 (objective), c2 (covering `>=` weights) and c3 (capacity `<=` weights).
    """
    ss = np.random.SeedSequence([_FAMILY_ENTROPY, int(n), int(index)])
    r1, r2, r3 = (np.random.default_rng(s) for s in ss.spawn(3))
    c1 = _lower_tri_sparse(r1, n, avg_degree, weight_low, weight_high)
    c2 = _lower_tri_sparse(r2, n, avg_degree, weight_low, weight_high)
    c3 = _lower_tri_sparse(r3, n, avg_degree, weight_low, weight_high)
    return c1, c2, c3


# Co-feasible default tightness band (validated bd 8an.1.7): capacity `<=` admits
# up to 60% of the max capacity mass, covering `>=` requires at least 35% of the
# max covering mass. A ~60%-density assignment satisfies both with margin, so
# random instances are reliably feasible while the covering constraint still
# forces enough decisions to keep f(n) in (0,1). Both are FIXED across n.
CAP_TIGHTNESS = 0.6
COV_TIGHTNESS = 0.35


def build_synthetic_model(n, index=0, avg_degree=8, weight_low=1, weight_high=10,
                          cap_tightness=CAP_TIGHTNESS, cov_tightness=COV_TIGHTNESS,
                          vectorized=None):
    """Build a closed cbqs ``Model`` for a synthetic matched-tightness Eq.29
    instance.

    Reuses the faithful Eq.29 LHS construction (``eq29_loader._eq29_lhs``:
    objective = Σc1·xx MAXIMIZE, `<=` = Σ2c3·xx, `>=` = Σ2c2·xx) but sets a
    tunable RHS = ``tightness`` · (max constraint mass) instead of the paper's
    fixed RHS=Σweight (1/2 isocontour), so the feasible band is wide enough for
    the opt phase to be observable. ``vectorized=None`` auto-selects the bilinear
    fast path at n≥1000 (same rule as the real loader).
    """
    from benchmarks.eq29_loader import _eq29_lhs, _use_vectorized
    from cbqs import Model, MAXIMIZE
    c1, c2, c3 = make_matrices(n, index, avg_degree, weight_low, weight_high)
    if vectorized is None:
        vectorized = _use_vectorized(n)
    il = np.tril_indices(n)
    # Max constraint mass = the all-ones LHS = Σ 2·weight over i>=j.
    le_rhs = int(round(cap_tightness * 2.0 * int(c3[il].sum())))
    ge_rhs = int(round(cov_tightness * 2.0 * int(c2[il].sum())))
    m = Model()
    x = m.add_variables(n)
    objective, le_lhs, ge_lhs = _eq29_lhs(x, c1, c2, c3, vectorized)
    m.set_objective(objective, sense=MAXIMIZE, validate=not vectorized)
    m.add_constraint(le_lhs <= le_rhs, validate=not vectorized)
    m.add_constraint(ge_lhs >= ge_rhs, validate=not vectorized)
    m.close()
    return m


def tightness(n, index=0, avg_degree=8, weight_low=1, weight_high=10,
              cap_tightness=CAP_TIGHTNESS, cov_tightness=COV_TIGHTNESS):
    """Return the realized (capacity, covering) tightness ratios = RHS / max-mass.

    Equal to (cap_tightness, cov_tightness) up to integer rounding, independent
    of n — this helper lets the test *assert* matched tightness rather than
    assume it (a guard against an accidental generator change, §1.5/§9)."""
    c1, c2, c3 = make_matrices(n, index, avg_degree, weight_low, weight_high)
    il = np.tril_indices(n)
    cap_mass = 2.0 * int(c3[il].sum())
    cov_mass = 2.0 * int(c2[il].sum())
    le_rhs = round(cap_tightness * cap_mass)
    ge_rhs = round(cov_tightness * cov_mass)
    cap_ratio = le_rhs / cap_mass if cap_mass else 0.0
    cov_ratio = ge_rhs / cov_mass if cov_mass else 0.0
    return cap_ratio, cov_ratio
