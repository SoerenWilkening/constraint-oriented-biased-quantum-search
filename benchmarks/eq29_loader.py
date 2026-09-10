"""Loader + model builder for the arXiv:2512.08384 (Eq. 29) quadratically-constrained
benchmark instances from github.com/SoerenWilkening/CBQS-benchmarks.

Instances live at
    <bench_root>/Paper_general_constraints/instances/{n}_{index}/{c1,c2,c3}.npy
(int64 dense matrices, git-LFS tracked). Eq. 29 mapping (matches run_quantum.py):

    objective : maximize  sum_{i>=j} c1[i,j] * x_i * x_j
    <= (cap.) : sum_{i>=j} 2*c3[i,j] * x_i * x_j  <=  sum_{i>=j} c3[i,j]
    >= (cov.) : sum_{i>=j} 2*c2[i,j] * x_i * x_j  >=  sum_{i>=j} c2[i,j]

NOTE the file gotcha: the <= ("capacity") constraint uses c3; the >= ("covering")
constraint uses c2. ``read_instance`` reproduces the canonical preprocessing
(efficiency-sort descending, then strict-upper-triangle zeroing) so we stay
consistent with the committed baseline result tables.

Scoped data fetch (the full repo is ~38 GiB — never a plain clone):
    GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/SoerenWilkening/CBQS-benchmarks
    git lfs pull --include="Paper_general_constraints/instances/**"
then point this loader at the clone via ``CBQS_BENCHMARKS_DIR`` or ``bench_root=``.
"""
import os
import numpy as np


def read_instance(inst_dir):
    """Load and canonically preprocess one Eq.29 instance directory.

    Returns (c1, c2, c3) as int64 lower-triangular matrices (strict upper zeroed),
    rows/cols permuted by descending efficiency = rowsum(c1)/(rowsum(c2)+rowsum(c3)).
    """
    c1 = np.load(os.path.join(inst_dir, "c1.npy"))
    c2 = np.load(os.path.join(inst_dir, "c2.npy"))
    c3 = np.load(os.path.join(inst_dir, "c3.npy"))
    efficiency = np.sum(c1, axis=1) / (np.sum(c2, axis=1) + np.sum(c3, axis=1))
    order = np.array(
        [i for _, i in sorted(zip(efficiency, range(len(efficiency))),
                              key=lambda t: t[0], reverse=True)]
    )
    c1 = np.tril(c1[np.ix_(order, order)])
    c2 = np.tril(c2[np.ix_(order, order)])
    c3 = np.tril(c3[np.ix_(order, order)])
    return c1, c2, c3


def default_bench_root():
    """Root of a CBQS-benchmarks clone, from the CBQS_BENCHMARKS_DIR env var."""
    return os.environ.get("CBQS_BENCHMARKS_DIR")


def instance_dir(n, index, bench_root=None):
    root = bench_root or default_bench_root()
    if not root:
        raise RuntimeError(
            "Set CBQS_BENCHMARKS_DIR (or pass bench_root=) to a CBQS-benchmarks clone."
        )
    return os.path.join(root, "Paper_general_constraints", "instances", f"{n}_{index}")


def load_eq29(n, index, bench_root=None):
    """Load instance {n}_{index} from a CBQS-benchmarks clone."""
    return read_instance(instance_dir(n, index, bench_root))


def eq29_rhs(c2, c3):
    """Constraint right-hand sides: (<=-RHS over c3, >=-RHS over c2).

    Both equal sum_{i>=j} of the respective matrix.
    """
    il = np.tril_indices(len(c2))
    return int(np.asarray(c3)[il].sum()), int(np.asarray(c2)[il].sum())


#: At/above this variable count, ``build_model`` defaults to the vectorized
#: bilinear (matmul) build instead of the O(n^2) Python triple-loop. Pinned as a
#: named constant so the auto-select decision is independently testable.
VECTORIZED_THRESHOLD = 1000


def _use_vectorized(n):
    """Auto-select the vectorized bilinear build path for large models.

    The O(n^2) Python triple-loop is fine for small/mid n but slow and
    memory-heavy at scale; at ``n >= VECTORIZED_THRESHOLD`` we build via the
    ``bilinear_reduce``/matmul fast path instead.
    """
    return n >= VECTORIZED_THRESHOLD


#: Largest |coefficient| that survives the constraint LHS ``*2`` without
#: overflowing int64 (2**62 - 1). The Python loop path raises OverflowError on
#: out-of-range coefficients via Expression._validate_numeric; the vectorized
#: path must fail just as loud rather than silently wrap (§2.1).
_INT64_HALF_MAX = (2 ** 63 - 1) // 2


def _times2_int64(a, name):
    """Return ``a * 2`` as a C-contiguous int64 array, raising on overflow.

    ``a`` is already int64; numpy would silently wrap ``a * 2`` past the int64
    range. We refuse to do that for a load-bearing constraint coefficient — the
    loop build path raises here too — so detect it before multiplying.
    """
    if np.any(a > _INT64_HALF_MAX) or np.any(a < -_INT64_HALF_MAX - 1):
        raise OverflowError(f"{name} coefficient*2 exceeds int64 range")
    return np.ascontiguousarray(a * 2)


def _eq29_lhs(x, c1, c2, c3, vectorized):
    """Build the three Eq.29 left-hand-side ``Expression`` objects over vector *x*.

    Returns ``(objective, le_lhs, ge_lhs)``::

        objective : sum_{i>=j}   c1[i,j] * x_i * x_j     (MAXIMIZE)
        le_lhs    : sum_{i>=j} 2*c3[i,j] * x_i * x_j     (<= eq29_rhs[0])
        ge_lhs    : sum_{i>=j} 2*c2[i,j] * x_i * x_j     (>= eq29_rhs[1])

    Inputs MUST be lower-triangular (strict upper zeroed), as produced by
    ``read_instance`` — both paths rely on that to realize the ``i>=j`` sum
    (the matmul path sums over every nonzero entry; the loop path filters
    ``i>=j``; with a lower-triangular matrix these coincide).

    With *vectorized* True, ``x @ (C @ x)`` (``bilinear_reduce``) emits each
    ``(i,j)`` term exactly once with no zero terms, so the caller may pass
    ``validate=False`` and skip the O(n^2) ``merge()``. The loop path is the
    reference build used at small n and for the equivalence test.

    Raises ``ValueError`` if any matrix is not square lower-triangular — the two
    paths only build the same quadratic form under that precondition (the matmul
    sums over every nonzero entry; the loop filters ``i>=j``), so we fail fast
    rather than silently emit a different QCQP (§2.1).
    """
    # Fail-fast on the lower-triangular precondition both build paths rely on.
    c1a = np.asarray(c1, dtype=np.int64)
    c2a = np.asarray(c2, dtype=np.int64)
    c3a = np.asarray(c3, dtype=np.int64)
    for name, a in (("c1", c1a), ("c2", c2a), ("c3", c3a)):
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            raise ValueError(f"{name} must be a square matrix, got shape {a.shape}")
        if np.any(np.triu(a, 1)):
            raise ValueError(
                f"{name} has nonzero strict-upper-triangle entries; build_model "
                f"requires lower-triangular input (use read_instance)."
            )

    if vectorized:
        c1m = np.ascontiguousarray(c1a)
        c3m = _times2_int64(c3a, "c3")
        c2m = _times2_int64(c2a, "c2")
        objective = x @ (c1m @ x)
        le_lhs = x @ (c3m @ x)
        ge_lhs = x @ (c2m @ x)
    else:
        objective = sum(int(c1[i][j]) * x[i] * x[j] for i in x for j in x if i >= j)
        le_lhs = sum(2 * int(c3[i][j]) * x[i] * x[j] for i in x for j in x if i >= j)
        ge_lhs = sum(2 * int(c2[i][j]) * x[i] * x[j] for i in x for j in x if i >= j)
    return objective, le_lhs, ge_lhs


def build_model(c1, c2, c3, vectorized=None):
    """Build the closed Eq.29 cbqs ``Model`` (objective + two quadratic constraints).

    Mirrors ``Paper_general_constraints/run_quantum.py``. The objective is MAXIMIZE.
    Inputs are the lower-triangular matrices returned by ``read_instance``.

    Parameters
    ----------
    vectorized : bool or None, optional
        Build-path selector. ``None`` (default) auto-selects via
        ``_use_vectorized(n)`` — the ``bilinear_reduce``/matmul fast path at
        ``n >= VECTORIZED_THRESHOLD``, the O(n^2) Python triple-loop below it.
        Pass ``True``/``False`` to force the choice (used by the equivalence
        test). The fast path passes ``validate=False`` to skip the O(n^2)
        ``merge()`` of already-clean ``bilinear_reduce`` output; the loop path
        keeps ``validate=True`` (its terms may include zero/duplicate forms).
    """
    from cbqs import Model, MAXIMIZE

    n = len(c1)
    if vectorized is None:
        vectorized = _use_vectorized(n)

    m = Model()
    x = m.add_variables(n)
    le_rhs, ge_rhs = eq29_rhs(c2, c3)
    objective, le_lhs, ge_lhs = _eq29_lhs(x, c1, c2, c3, vectorized)

    m.set_objective(objective, sense=MAXIMIZE, validate=not vectorized)
    m.add_constraint(le_lhs <= le_rhs, validate=not vectorized)
    m.add_constraint(ge_lhs >= ge_rhs, validate=not vectorized)
    m.close()
    return m
