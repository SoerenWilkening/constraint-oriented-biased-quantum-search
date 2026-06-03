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
