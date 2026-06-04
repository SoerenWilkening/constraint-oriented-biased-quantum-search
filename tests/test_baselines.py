"""Tests for the frozen baseline-table builder (M0b, NORTHSTAR §6/§11).

Unit tests are self-contained (synthetic result CSVs written to tmp). The
integration test reads the real committed CSVs and is skipped unless a
CBQS-benchmarks clone is available via CBQS_BENCHMARKS_DIR.
"""
import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
import baselines as B  # noqa: E402

_SCHEMA = ["size", "index", "obj", "time", "oracles", "preprocess-time", "method"]


def _write_results_csv(path, rows):
    """Write a results CSV with the real schema. *rows* = (size, index, obj, method)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(_SCHEMA)
        for size, index, obj, method in rows:
            w.writerow([size, index, obj, 0.0, 0, 0.0, method])


def _append_raw_lines(path, lines):
    """Append verbatim lines to a CSV (for '#'-commented rows csv.writer would quote)."""
    with open(path, "a", newline="") as f:
        for line in lines:
            f.write(line + "\n")


def _bench_root_with(tmp_path, classical=None, res=None):
    """Build a fake <root>/Paper_general_constraints/plots/{*.csv} tree."""
    plots = tmp_path / "Paper_general_constraints" / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    if classical is not None:
        _write_results_csv(str(plots / "classical_comparison.csv"), classical)
    if res is not None:
        _write_results_csv(str(plots / "res.csv"), res)
    return str(tmp_path)


def test_b_i_is_max_over_non_cbqs_methods():
    """B_I = max obj over {gurobi,hexaly,simanneal}; iqs (CBQS) is excluded even
    when it reports a higher objective (matching CBQS is neutral, not a win)."""
    rows = [
        {"size": 100, "index": 0, "obj": 100.0, "method": "gurobi"},
        {"size": 100, "index": 0, "obj": 120.0, "method": "hexaly"},
        {"size": 100, "index": 0, "obj": 90.0, "method": "simanneal"},
        {"size": 100, "index": 0, "obj": 200.0, "method": "iqs"},  # CBQS — excluded
    ]
    b_i = B.compute_b_i(rows)
    assert b_i[(100, 0)] == (120.0, "hexaly")


def test_b_i_excludes_bound_and_modeling_time_rows():
    """*-bound (dual bounds) and *-modeling-time (timing) are not feasible primal
    objectives and must not inflate B_I."""
    rows = [
        {"size": 500, "index": 3, "obj": 100.0, "method": "gurobi"},
        {"size": 500, "index": 3, "obj": 500.0, "method": "gurobi-bound"},
        {"size": 500, "index": 3, "obj": 999.0, "method": "hexaly-modeling-time"},
    ]
    b_i = B.compute_b_i(rows)
    assert b_i[(500, 3)] == (100.0, "gurobi")


def test_b_i_takes_max_over_anytime_rows():
    """Multiple anytime incumbents per (size,index,method) -> B_I is the best."""
    rows = [
        {"size": 10, "index": 1, "obj": 50.0, "method": "gurobi"},
        {"size": 10, "index": 1, "obj": 80.0, "method": "gurobi"},
        {"size": 10, "index": 1, "obj": 110.0, "method": "gurobi"},
    ]
    b_i = B.compute_b_i(rows)
    assert b_i[(10, 1)][0] == 110.0


def test_b_i_omits_instances_without_non_cbqs_feasible_row():
    """An instance with only iqs/bound rows has no defined B_I and is omitted."""
    rows = [
        {"size": 3000, "index": 9, "obj": 1.0e9, "method": "iqs"},
        {"size": 3000, "index": 9, "obj": 2.0e9, "method": "gurobi-bound"},
    ]
    b_i = B.compute_b_i(rows)
    assert (3000, 9) not in b_i


def test_b_i_unions_both_csvs(tmp_path):
    """Both CSVs are read and unioned; an overlapping (size,index) takes the max
    across files (res.csv n<=1000, classical_comparison.csv n>=500 overlap at 500..1000)."""
    root = _bench_root_with(
        tmp_path,
        classical=[(1000, 0, 130.0, "hexaly"), (3000, 0, 5.0, "gurobi")],
        res=[(1000, 0, 100.0, "gurobi"), (10, 0, 7.0, "simanneal")],
    )
    rows = B.read_solver_results(B._csv_paths(root))
    b_i = B.compute_b_i(rows)
    assert b_i[(1000, 0)] == (130.0, "hexaly")  # union max across both files
    assert b_i[(3000, 0)][0] == 5.0
    assert b_i[(10, 0)] == (7.0, "simanneal")


def test_method_case_insensitive():
    """Method matching is case-insensitive (reader lowercases)."""
    rows = [{"size": 100, "index": 0, "obj": 42.0, "method": "GuRoBi"}]
    # read_solver_results lowercases; compute_b_i is fed already-lowercased rows,
    # but _is_bi_row must also tolerate stray case directly.
    assert B._is_bi_row("GuRoBi") is True
    assert B._is_bi_row("IQS") is False
    assert B._is_bi_row("Gurobi-Bound") is False


def test_csv_paths_requires_bench_root(monkeypatch):
    monkeypatch.delenv("CBQS_BENCHMARKS_DIR", raising=False)
    with pytest.raises(RuntimeError, match="CBQS_BENCHMARKS_DIR"):
        B._csv_paths()


def test_freeze_and_load_roundtrip(tmp_path):
    """freeze -> load preserves B_I & provenance; L_I/default_PI load as None (pending)."""
    root = _bench_root_with(
        tmp_path,
        res=[
            (10, 0, 110.0, "gurobi"),
            (10, 0, 90.0, "hexaly"),
            (10, 1, 5040079.0, "simanneal"),  # integral -> stored without .0
            (10, 2, 1.0, "iqs"),              # only CBQS -> omitted
        ],
    )
    out = str(tmp_path / "frozen.csv")
    B.freeze_baselines(bench_root=root, out_path=out, require_all=False)
    table = B.load_frozen_baselines(out)

    assert (10, 2) not in table                       # iqs-only omitted
    assert table[(10, 0)]["B_I"] == 110.0
    assert table[(10, 0)]["B_I_method"] == "gurobi"
    assert table[(10, 1)]["B_I"] == 5040079.0
    assert table[(10, 1)]["B_I_method"] == "simanneal"
    # L_I / default_PI are placeholders until the oracle-indexed harness lands
    for key in [(10, 0), (10, 1)]:
        assert table[key]["L_I"] is None
        assert table[key]["default_PI"] is None

    # integral B_I is written without a trailing .0 (diffable)
    with open(out) as f:
        text = f.read()
    assert "5040079," in text and "5040079.0" not in text


def test_read_solver_results_skips_commented_rows(tmp_path):
    """csv has no '#' comment handling; the real res.csv has ~2042 commented rows
    ('# 1000,0,...'). read_solver_results must skip them (not crash on int('# 1000'))
    and they must not anchor B_I — mirroring real iqs AND hexaly comment rows."""
    root = _bench_root_with(tmp_path, res=[(10, 0, 100.0, "gurobi")])
    res_path = os.path.join(root, "Paper_general_constraints", "plots", "res.csv")
    _append_raw_lines(res_path, [
        "# 10,0,2539818438,1.0,0,0.0,hexaly",   # commented hexaly — must NOT count
        "# 1000,0,2541739799,1.0,0,0.0,iqs",    # commented iqs
        "",                                      # blank line
    ])
    rows = B.read_solver_results([res_path])  # must not raise
    assert all(isinstance(r["size"], int) for r in rows)
    b_i = B.compute_b_i(rows)
    assert b_i[(10, 0)] == (100.0, "gurobi")    # the commented hexaly didn't win
    assert (1000, 0) not in b_i                 # commented iqs row ignored entirely


def test_unknown_quantum_methods_excluded():
    """Any method not EXACTLY in BI_METHODS — incl. the CBQS-family quantum solvers
    qbnb / nested-qs present in the real res.csv — is excluded, so it cannot anchor
    the non-CBQS frontier even with a higher objective (NORTHSTAR §6/§11)."""
    assert B._is_bi_row("qbnb") is False
    assert B._is_bi_row("nested-qs") is False
    assert B._is_bi_row("some-future-quantum-method") is False
    rows = [
        {"size": 20, "index": 0, "obj": 100.0, "method": "gurobi"},
        {"size": 20, "index": 0, "obj": 999.0, "method": "qbnb"},
        {"size": 20, "index": 0, "obj": 999.0, "method": "nested-qs"},
    ]
    assert B.compute_b_i(rows)[(20, 0)] == (100.0, "gurobi")


def test_b_i_skips_non_finite_obj():
    """-inf (failed/missing-anneal sentinel; ~371 in real res.csv) is not a feasible
    primal objective (§6) and must not anchor or crash B_I."""
    rows = [
        {"size": 50, "index": 7, "obj": float("-inf"), "method": "simanneal"},
        {"size": 50, "index": 7, "obj": 100.0, "method": "gurobi"},
    ]
    assert B.compute_b_i(rows)[(50, 7)] == (100.0, "gurobi")
    # an instance whose only qualifying rows are non-finite is omitted, not crashed
    only_inf = [{"size": 50, "index": 8, "obj": float("-inf"), "method": "simanneal"}]
    assert (50, 8) not in B.compute_b_i(only_inf)


def test_freeze_raises_on_missing_csvs(tmp_path):
    """Fail-loud (§2.1): a root with plots/ but no CSVs must crash, not write an
    empty header-only table."""
    root = _bench_root_with(tmp_path)  # plots/ exists, no CSVs
    with pytest.raises(FileNotFoundError, match="No result CSVs"):
        B.freeze_baselines(bench_root=root, out_path=str(tmp_path / "x.csv"))


def test_freeze_requires_all_csvs_by_default(tmp_path):
    """Fail-loud (§2.1): a partial pull (only one CSV) drops a whole size stratum;
    default require_all must crash. require_all=False freezes from what is present."""
    root = _bench_root_with(tmp_path, res=[(10, 0, 100.0, "gurobi")])
    with pytest.raises(FileNotFoundError, match="Partial benchmark data"):
        B.freeze_baselines(bench_root=root, out_path=str(tmp_path / "x.csv"))
    # explicit opt-out succeeds
    out = B.freeze_baselines(bench_root=root, out_path=str(tmp_path / "y.csv"),
                             require_all=False)
    assert B.load_frozen_baselines(out)[(10, 0)]["B_I"] == 100.0


def test_freeze_raises_when_no_bi_rows(tmp_path):
    """Fail-loud (§2.1): CSVs present but zero qualifying non-CBQS rows must crash."""
    root = _bench_root_with(tmp_path, res=[(10, 0, 1.0, "iqs")])  # CBQS-only
    with pytest.raises(ValueError, match="0 B_I instances"):
        B.freeze_baselines(bench_root=root, out_path=str(tmp_path / "x.csv"),
                           require_all=False)


_REAL_PLOTS = os.path.join(os.environ.get("CBQS_BENCHMARKS_DIR", ""),
                           "Paper_general_constraints", "plots")
_HAS_REAL = bool(os.environ.get("CBQS_BENCHMARKS_DIR")) and all(
    os.path.isfile(os.path.join(_REAL_PLOTS, name))
    for name in ("res.csv", "classical_comparison.csv")
)


@pytest.mark.skipif(not _HAS_REAL, reason="CBQS_BENCHMARKS_DIR with BOTH plots CSVs not available")
def test_real_baselines_sane():
    """Real committed CSVs: B_I parses (despite '#'-commented + -inf rows), is
    positive (Eq.29 MAXIMIZE), only ever a non-CBQS primal method, and spans the
    full paper size range incl. the large-n §6.6 stratum (M0b acceptance)."""
    rows = B.read_solver_results(B._csv_paths())  # must not raise on '#'/-inf rows
    assert rows, "no solver rows read"
    b_i = B.compute_b_i(rows)
    assert b_i, "no B_I computed"
    for (size, index), (val, method) in b_i.items():
        assert val > 0, f"B_I non-positive at ({size},{index}): {val}"
        assert method in B.BI_METHODS, f"B_I method {method} is not a non-CBQS primal solver"
    sizes = {s for (s, _) in b_i}
    assert {10, 100, 1000, 3000}.issubset(sizes), f"missing paper sizes; got {sorted(sizes)}"
