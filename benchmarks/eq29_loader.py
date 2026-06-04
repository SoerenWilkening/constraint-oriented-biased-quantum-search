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


def build_model(c1, c2, c3):
    """Build the closed Eq.29 cbqs ``Model`` (objective + two quadratic constraints).

    Mirrors ``Paper_general_constraints/run_quantum.py``. The objective is MAXIMIZE.

    NOTE (perf): this is the O(n^2) Python build (~n^2/2 product terms); fine for
    small/mid n, but for n >= 1000 it is slow/memory-heavy — switch to the vectorized
    bilinear build path (M0a follow-up, NORTHSTAR §11) at scale.
    """
    from cbqs import Model, MAXIMIZE

    n = len(c1)
    m = Model()
    x = m.add_variables(n)
    m.set_objective(
        sum(int(c1[i][j]) * x[i] * x[j] for i in x for j in x if i >= j),
        sense=MAXIMIZE,
    )
    m.add_constraint(
        sum(2 * int(c3[i][j]) * x[i] * x[j] for i in x for j in x if i >= j)
        <= sum(int(c3[i][j]) for i in x for j in x if i >= j)
    )
    m.add_constraint(
        sum(2 * int(c2[i][j]) * x[i] * x[j] for i in x for j in x if i >= j)
        >= sum(int(c2[i][j]) for i in x for j in x if i >= j)
    )
    m.close()
    return m
