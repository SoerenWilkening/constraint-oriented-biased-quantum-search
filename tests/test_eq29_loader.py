"""Tests for the Eq.29 (arXiv:2512.08384) benchmark loader/model-builder (M0a).

The unit tests are self-contained (synthetic instances written to tmp). The
integration test loads the real 100_0 instance and is skipped unless a
CBQS-benchmarks clone is available via CBQS_BENCHMARKS_DIR.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
import eq29_loader as L  # noqa: E402


def _write_instance(d, c1, c2, c3):
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "c1.npy"), c1)
    np.save(os.path.join(d, "c2.npy"), c2)
    np.save(os.path.join(d, "c3.npy"), c3)


def _synthetic(n, seed):
    rng = np.random.default_rng(seed)
    c1 = rng.integers(1, 50, (n, n)); c1 = c1 + c1.T
    c2 = rng.integers(1, 20, (n, n)); c2 = c2 + c2.T
    c3 = rng.integers(1, 20, (n, n)); c3 = c3 + c3.T
    return c1, c2, c3


def _canon(expr):
    """Canonical {sorted-var-index-tuple: total-coeff} map of an Expression.

    Drops zero-coefficient terms and is order-/duplicate-insensitive, so two
    expressions compare equal iff they represent the same quadratic form. Only
    valid on a *pre-comparison* Expression (sense == -2), whose iteration yields
    plain ``[coeff, var, ...]`` term lists (no trailing sense/rhs scalars).
    """
    out = {}
    for term in expr:
        coeff = int(term[0])
        if coeff == 0:
            continue
        key = tuple(sorted(int(v) for v in term[1:]))
        out[key] = out.get(key, 0) + coeff
    return {k: v for k, v in out.items() if v != 0}


def _tril_form(M, factor):
    """Independent ground-truth {sorted-(i,j): factor*M[i,j]} over the lower
    triangle (i >= j), computed directly from the matrix (not via either build
    path) so it can pin a coordinated both-paths regression."""
    exp = {}
    for i, j in zip(*np.tril_indices(len(M))):
        key = tuple(sorted((int(i), int(j))))
        exp[key] = exp.get(key, 0) + factor * int(M[i, j])
    return {k: v for k, v in exp.items() if v != 0}


def test_read_instance_transform(tmp_path):
    """read_instance must efficiency-sort (desc) then zero the strict upper triangle."""
    n = 6
    c1, c2, c3 = _synthetic(n, seed=7)
    d = str(tmp_path / "6_0")
    _write_instance(d, c1, c2, c3)

    eff = c1.sum(1) / (c2.sum(1) + c3.sum(1))
    order = np.array([i for _, i in sorted(zip(eff, range(n)), key=lambda t: t[0], reverse=True)])
    expected = [np.tril(M[np.ix_(order, order)]) for M in (c1, c2, c3)]

    got = L.read_instance(d)
    for g, e in zip(got, expected):
        assert g.shape == (n, n)
        assert np.array_equal(g, e)
        assert np.all(np.triu(g, 1) == 0)  # strict upper triangle zeroed


def test_eq29_rhs_matches_lower_triangle_sum(tmp_path):
    n = 6
    c1, c2, c3 = _synthetic(n, seed=11)
    d = str(tmp_path / "6_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)
    le_rhs, ge_rhs = L.eq29_rhs(cc2, cc3)
    il = np.tril_indices(n)
    assert le_rhs == int(cc3[il].sum())
    assert ge_rhs == int(cc2[il].sum())


def test_build_model_closes(tmp_path):
    """build_model must construct objective + both quadratic constraints and close."""
    n = 6
    c1, c2, c3 = _synthetic(n, seed=3)
    d = str(tmp_path / "6_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)
    m = L.build_model(cc1, cc2, cc3)  # builds + closes without raising
    assert m is not None


def test_use_vectorized_threshold():
    """Auto-select uses the matmul fast path at n >= VECTORIZED_THRESHOLD only."""
    t = L.VECTORIZED_THRESHOLD
    assert t == 1000
    assert L._use_vectorized(t) is True
    assert L._use_vectorized(t - 1) is False
    assert L._use_vectorized(t + 1) is True


def test_vectorized_matches_loop_terms(tmp_path):
    """The vectorized (matmul) build must produce the SAME quadratic forms as
    the reference O(n^2) loop build — objective and both constraint LHSs."""
    from cbqs import Model

    n = 8
    c1, c2, c3 = _synthetic(n, seed=5)
    d = str(tmp_path / "8_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)

    mv = Model(); xv = mv.add_variables(n)
    obj_v, le_v, ge_v = L._eq29_lhs(xv, cc1, cc2, cc3, vectorized=True)

    ml = Model(); xl = ml.add_variables(n)
    obj_l, le_l, ge_l = L._eq29_lhs(xl, cc1, cc2, cc3, vectorized=False)

    assert _canon(obj_v) == _canon(obj_l)   # objective: sum_{i>=j} c1
    assert _canon(le_v) == _canon(le_l)     # capacity LHS: sum_{i>=j} 2*c3
    assert _canon(ge_v) == _canon(ge_l)     # covering LHS: sum_{i>=j} 2*c2

    # And the canonical objective really is the lower-triangular c1 form.
    expected = {}
    il = np.tril_indices(n)
    for i, j in zip(*il):
        key = tuple(sorted((int(i), int(j))))
        expected[key] = expected.get(key, 0) + int(cc1[i, j])
    assert _canon(obj_v) == {k: v for k, v in expected.items() if v != 0}


def test_build_model_vectorized_closes(tmp_path):
    """build_model(vectorized=True) must build + close via the validate=False
    fast path (exercises set_objective/add_constraint with validate=False)."""
    n = 12
    c1, c2, c3 = _synthetic(n, seed=9)
    d = str(tmp_path / "12_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)
    m = L.build_model(cc1, cc2, cc3, vectorized=True)
    assert m is not None


@pytest.mark.timeout(120)
def test_vectorized_scale_builds(tmp_path):
    """At n >= 1000 the default build auto-selects the matmul path and must
    build + close a dense instance (the O(n^2) loop is infeasible at scale)."""
    n = 1000
    c1, c2, c3 = _synthetic(n, seed=1)
    d = str(tmp_path / f"{n}_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)
    m = L.build_model(cc1, cc2, cc3)  # vectorized=None -> auto (n>=1000)
    assert m is not None


def test_constraint_lhs_independent_golden(tmp_path):
    """Pin each constraint LHS to an INDEPENDENT ground truth (not just
    vectorized==loop): capacity '<=' uses 2*c3, covering '>=' uses 2*c2, and the
    RHS (un-doubled) is c3-sum / c2-sum. This catches a coordinated both-paths
    regression — the c2/c3 swap and the dropped factor-2 (CLAUDE.md §5/§8) — that
    the differential equivalence test cannot see. Runs without CBQS_BENCHMARKS_DIR."""
    from cbqs import Model

    n = 8
    c1, c2, c3 = _synthetic(n, seed=5)
    d = str(tmp_path / "8_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)

    exp_le = _tril_form(cc3, 2)   # capacity <= : 2*c3
    exp_ge = _tril_form(cc2, 2)   # covering >= : 2*c2
    assert exp_le != exp_ge       # instance must discriminate c2 from c3

    for vec in (True, False):
        m = Model(); x = m.add_variables(n)
        _, le_lhs, ge_lhs = L._eq29_lhs(x, cc1, cc2, cc3, vectorized=vec)
        assert _canon(le_lhs) == exp_le   # binds c3 with factor 2 (not c2, not 1*)
        assert _canon(ge_lhs) == exp_ge   # binds c2 with factor 2 (not c3, not 1*)

    le_rhs, ge_rhs = L.eq29_rhs(cc2, cc3)
    il = np.tril_indices(n)
    assert le_rhs == int(cc3[il].sum())   # RHS is the un-doubled c3 sum
    assert ge_rhs == int(cc2[il].sum())   # RHS is the un-doubled c2 sum


@pytest.mark.parametrize("vec", [True, False])
def test_build_model_solves_consistent(tmp_path, vec):
    """End-to-end: build + solve, then assert self-consistent invariants on the
    returned incumbent (NOT equality across builds — the solver is a stochastic
    portfolio). Guards the objective sign/coefficients and, when feasible, the
    c3/<= & c2/>= constraint mapping on the validate=False vectorized path."""
    n = 12
    c1, c2, c3 = _synthetic(n, seed=7)
    d = str(tmp_path / "12_0")
    _write_instance(d, c1, c2, c3)
    cc1, cc2, cc3 = L.read_instance(d)
    le_rhs, ge_rhs = L.eq29_rhs(cc2, cc3)

    m = L.build_model(cc1, cc2, cc3, vectorized=vec)
    m.set_param("num_workers", 1)
    m.set_param("stopping_time", 2)
    r = m.solve()

    x = np.asarray(r.solution, dtype=np.int64)
    assert x.shape == (n,)
    # reported objective == the maximized c1 quadratic form on the reported x
    assert int(r.objective) == int(x @ (cc1 @ x))
    # a reported-feasible incumbent must satisfy BOTH constraints, recomputed
    # independently from the raw matrices (capacity uses c3, covering uses c2)
    if r.feasible:
        assert int(x @ ((2 * cc3) @ x)) <= le_rhs
        assert int(x @ ((2 * cc2) @ x)) >= ge_rhs


@pytest.mark.parametrize("vec", [True, False])
def test_build_model_rejects_non_lower_triangular(vec):
    """Fail-fast (§2.1): a non-lower-triangular (e.g. symmetric) matrix that
    bypassed read_instance must raise, since the two paths would otherwise build
    different quadratic forms from its strict-upper-triangle entries."""
    n = 4
    c1, c2, c3 = _synthetic(n, seed=3)  # _synthetic is symmetric (full), not tril
    with pytest.raises(ValueError, match="lower-triangular|square"):
        L.build_model(c1, c2, c3, vectorized=vec)


def test_build_model_rejects_coefficient_overflow(tmp_path):
    """Fail-fast (§2.1): a constraint coefficient whose *2 overflows int64 must
    raise (OverflowError) on the vectorized path, like the loop path does via
    Expression._validate_numeric — never silently wrap a load-bearing coeff."""
    n = 4
    c1, c2, c3 = _synthetic(n, seed=4)
    c3 = np.tril(c3.astype(np.int64))
    c3[0, 0] = (1 << 62) + 5  # 2*c3[0,0] overflows int64
    c2 = np.tril(c2.astype(np.int64))
    c1 = np.tril(c1.astype(np.int64))
    with pytest.raises(OverflowError):
        L.build_model(c1, c2, c3, vectorized=True)


_HAS_REAL = bool(os.environ.get("CBQS_BENCHMARKS_DIR")) and os.path.isdir(
    os.path.join(os.environ.get("CBQS_BENCHMARKS_DIR", ""),
                 "Paper_general_constraints", "instances", "100_0")
)


@pytest.mark.skipif(not _HAS_REAL, reason="CBQS_BENCHMARKS_DIR with instance 100_0 not available")
def test_real_instance_100_0():
    c1, c2, c3 = L.load_eq29(100, 0)
    assert c1.shape == (100, 100)
    assert c1.dtype == np.int64
    le_rhs, ge_rhs = L.eq29_rhs(c2, c3)
    assert le_rhs == 5032863   # sum_{i>=j} c3  (<= capacity RHS)
    assert ge_rhs == 5040079   # sum_{i>=j} c2  (>= covering RHS)
    m = L.build_model(c1, c2, c3)
    assert m is not None
