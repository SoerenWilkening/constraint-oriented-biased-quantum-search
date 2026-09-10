"""Tests for the frozen baseline-table builder (M0b, NORTHSTAR §6/§11).

Unit tests are self-contained (synthetic result CSVs written to tmp). The
integration test reads the real committed CSVs and is skipped unless a
CBQS-benchmarks clone is available via CBQS_BENCHMARKS_DIR.
"""
import csv
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
import baselines as B  # noqa: E402

_SCHEMA = ["size", "index", "obj", "time", "oracles", "preprocess-time", "method"]


def _res(history):
    """Minimal OptimizeResult stand-in (the anchor logic only reads .history)."""
    return types.SimpleNamespace(history=list(history))


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


# --------------------------------------------------------------------------- #
# L_I / default-PI anchors from CBQS-default seed-bank runs (bd 8an.1.16)
# --------------------------------------------------------------------------- #

def test_first_feasible_objective():
    assert B.first_feasible_objective(_res([(40, 100), (80, 500)])) == 40.0
    assert B.first_feasible_objective(_res([])) is None  # never feasible


def test_default_instance_anchors_ok():
    # B_I=100, L_I=median(first-feasible[40,60,50])=50, D_I=50, T_I=1000.
    # per-run PI: run1=0.70, run2=0.60, run3=1.00 -> default_PI=median=0.70.
    results = [_res([(40, 100), (80, 500)]),   # 100 + 1.0*400 + 0.4*500 = 700 -> 0.70
               _res([(60, 200), (90, 600)]),   # 200 + 0.8*400 + 0.2*400 = 600 -> 0.60
               _res([(50, 300)])]              # 300 + 1.0*700        = 1000 -> 1.00
    a = B.default_instance_anchors(results, B_I=100, n=10, T_I=1000)
    assert a["status"] == "ok"
    assert a["L_I"] == 50.0
    assert a["default_PI"] == pytest.approx(0.70)
    assert a["n_feasible_runs"] == 3


def test_default_instance_anchors_never_feasible():
    a = B.default_instance_anchors([_res([]), _res([])], B_I=100, n=10, T_I=1000)
    assert a["status"] == "never_feasible" and a["L_I"] is None and a["default_PI"] is None


def test_default_instance_anchors_dropped_when_L_ge_B():
    # median first-feasible == B_I -> drop (non-discriminating, >= boundary).
    results = [_res([(100, 5)]), _res([(100, 9)]), _res([(100, 7)])]
    a = B.default_instance_anchors(results, B_I=100, n=10, T_I=1000)
    assert a["status"] == "dropped_L_ge_B" and a["L_I"] == 100.0 and a["default_PI"] is None


def test_freeze_default_anchors_fills_drops_and_empties(tmp_path):
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI\n"
        "10,0,100,hexaly,,\n"   # feasible -> ok
        "10,1,100,hexaly,,\n"   # L_I == B_I -> dropped (omitted)
        "10,2,100,hexaly,,\n"   # never feasible -> empty anchors
    )

    def run_fn(n, index, seeds):
        if index == 0:
            return [_res([(40, 100), (80, 500)]), _res([(60, 200), (90, 600)]), _res([(50, 300)])]
        if index == 1:
            return [_res([(100, 5)]), _res([(100, 9)]), _res([(100, 7)])]
        return [_res([]), _res([])]

    out = tmp_path / "out.csv"
    summary = B.freeze_default_anchors(seeds=(0, 1, 2), frozen_path=str(frozen),
                                       out_path=str(out), run_fn=run_fn)
    table = B.load_frozen_baselines(str(out))
    assert table[(10, 0)]["L_I"] == 50.0
    # default_PI = median per-run PI at the REAL budget T(10) (the orchestrator uses oracle_budget,
    # not the T_I=1000 of the unit test) — compute the expectation the same way to avoid a magic #.
    import statistics as _st
    from metric import compute_primal_integral, oracle_budget
    _T = oracle_budget(10)
    _expected = _st.median([compute_primal_integral(h, 100, 50, _T) for h in (
        [(40, 100), (80, 500)], [(60, 200), (90, 600)], [(50, 300)])])
    assert table[(10, 0)]["default_PI"] == pytest.approx(_expected)
    assert (10, 1) not in table  # L_I >= B_I dropped from the table
    assert (10, 2) in table       # kept, but anchors EMPTY -> never silently 0 (8an.1.16 guard)
    assert table[(10, 2)]["L_I"] is None and table[(10, 2)]["default_PI"] is None
    assert summary["ok"] == [(10, 0)]
    assert summary["dropped"] and summary["dropped"][0][:2] == (10, 1)
    assert summary["never_feasible"] == [(10, 2)]


def test_freeze_default_anchors_partial_sizes_keeps_others(tmp_path):
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI\n"
        "10,0,100,hexaly,,\n"
        "100,0,200,gurobi,123,0.5\n"   # already-frozen anchors for n=100
    )
    out = tmp_path / "out.csv"
    # only recompute n=10; n=100's existing anchors must survive verbatim.
    B.freeze_default_anchors(seeds=(0,), frozen_path=str(frozen), out_path=str(out), sizes=[10],
                             run_fn=lambda n, i, s: [_res([(50, 100)])])
    table = B.load_frozen_baselines(str(out))
    assert table[(100, 0)]["L_I"] == 123.0 and table[(100, 0)]["default_PI"] == 0.5
    assert table[(10, 0)]["L_I"] == 50.0


def test_freeze_default_anchors_requires_frozen_table(tmp_path):
    with pytest.raises(FileNotFoundError):
        B.freeze_default_anchors(frozen_path=str(tmp_path / "nope.csv"), run_fn=lambda *a: [])


# --------------------------------------------------------------------------- #
# bd 0o8: opt_sample_cap governance + calibration
# --------------------------------------------------------------------------- #

def test_load_frozen_backward_compat_no_cap_column(tmp_path):
    """A legacy 6-column table (no default_cap) loads as cap 0 = faithful (no crash)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI\n"
        "10,0,100,hexaly,50,0.5\n"
    )
    table = B.load_frozen_baselines(str(frozen))
    assert table[(10, 0)]["default_cap"] == 0


def test_freeze_default_anchors_records_cap(tmp_path):
    """Freezing at opt_sample_cap=C records C in default_cap and flags the run approximate."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap\n"
        "10,0,100,hexaly,,,\n"
    )
    out = tmp_path / "out.csv"
    summary = B.freeze_default_anchors(seeds=(0,), frozen_path=str(frozen), out_path=str(out),
                                       opt_sample_cap=500,
                                       run_fn=lambda n, i, s: [_res([(40, 100), (90, 500)])])
    table = B.load_frozen_baselines(str(out))
    assert table[(10, 0)]["default_cap"] == 500
    assert summary["approximate"] is True and summary["cap"] == 500
    assert summary["anchored_cap"] == 500


def test_freeze_default_anchors_cap_zero_writes_empty(tmp_path):
    """cap=0 (exact) writes an EMPTY default_cap cell (diffable; loads back as 0)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text("size,index,B_I,B_I_method,L_I,default_PI,default_cap\n10,0,100,hexaly,,,\n")
    out = tmp_path / "out.csv"
    B.freeze_default_anchors(seeds=(0,), frozen_path=str(frozen), out_path=str(out),
                             run_fn=lambda n, i, s: [_res([(40, 100), (90, 500)])])
    assert ",0\n" not in out.read_text()  # no literal cap 0 written
    assert B.load_frozen_baselines(str(out))[(10, 0)]["default_cap"] == 0


def test_freeze_default_anchors_rejects_mixed_cap(tmp_path):
    """GOVERNANCE: recomputing one size at cap>0 while another anchored size stays at cap 0
    would mix faithful + approximate anchors — must raise (bd 0o8 must_fix)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap\n"
        "10,0,100,hexaly,,,\n"
        "100,0,200,gurobi,123,0.5,\n"   # already-frozen FAITHFUL (cap 0) anchor for n=100
    )
    with pytest.raises(ValueError, match="MIXED-cap"):
        B.freeze_default_anchors(seeds=(0,), frozen_path=str(frozen), out_path=str(tmp_path / "o.csv"),
                                 sizes=[10], opt_sample_cap=500,
                                 run_fn=lambda n, i, s: [_res([(40, 100), (90, 500)])])


def test_freeze_default_anchors_uniform_cap_ok(tmp_path):
    """Re-freezing ALL anchored sizes at the SAME cap is allowed and records it everywhere."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap\n"
        "10,0,100,hexaly,,,\n"
        "100,0,200,gurobi,123,0.5,\n"
    )
    out = tmp_path / "out.csv"
    B.freeze_default_anchors(seeds=(0,), frozen_path=str(frozen), out_path=str(out),
                             opt_sample_cap=500,  # sizes=None -> recompute every size at 500
                             run_fn=lambda n, i, s: [_res([(40, 100), (190 if n == 100 else 90, 500)])])
    table = B.load_frozen_baselines(str(out))
    assert table[(10, 0)]["default_cap"] == 500
    assert table[(100, 0)]["default_cap"] == 500  # re-frozen at the same cap, not kept verbatim


# --------------------------------------------------------------------------- #
# bd 8an.9: warm (general_greedy) vs cold (0^n) start — protocol provenance + guard
# --------------------------------------------------------------------------- #

def test_load_frozen_protocol_defaults_cold_for_legacy_table(tmp_path):
    """A table without a `protocol` column loads as 'cold' (every pre-8an.9 freeze was cold)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap\n"
        "10,0,100,hexaly,50,0.5,\n"
    )
    table = B.load_frozen_baselines(str(frozen))
    assert table[(10, 0)]["protocol"] == "cold"


def test_freeze_default_anchors_records_warm_protocol(tmp_path):
    """Freezing with warm=True KEEPS the cold L_I and re-scores default_PI warm against it; tags the
    row 'warm' and flags the summary warm (bd 8an.9 keep-cold-L_I decision)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap,protocol\n"
        "10,0,100,hexaly,50,,,cold\n"           # cold L_I=50 present (no default_PI yet)
    )
    out = tmp_path / "out.csv"
    summary = B.freeze_default_anchors(seeds=(1,), frozen_path=str(frozen), out_path=str(out),
                                       warm=True,
                                       run_fn=lambda n, i, s: [_res([(60, 100), (90, 500)])])
    table = B.load_frozen_baselines(str(out))
    assert table[(10, 0)]["protocol"] == "warm"
    assert table[(10, 0)]["L_I"] == 50.0                 # cold L_I KEPT (not recomputed warm)
    assert table[(10, 0)]["default_PI"] is not None       # warm default_PI filled
    assert summary["protocol"] == "warm" and summary["warm"] is True
    assert summary["anchored_protocol"] == "warm"


def test_freeze_default_anchors_cold_protocol_by_default(tmp_path):
    """warm=False (default) tags rows 'cold' and writes an EMPTY protocol cell (loads back 'cold')."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text("size,index,B_I,B_I_method,L_I,default_PI,default_cap,protocol\n10,0,100,hexaly,,,,\n")
    out = tmp_path / "out.csv"
    summary = B.freeze_default_anchors(seeds=(1,), frozen_path=str(frozen), out_path=str(out),
                                       run_fn=lambda n, i, s: [_res([(40, 100), (90, 500)])])
    assert ",cold\n" not in out.read_text()      # cold written as empty (diffable; loads as cold)
    assert B.load_frozen_baselines(str(out))[(10, 0)]["protocol"] == "cold"
    assert summary["protocol"] == "cold" and summary["warm"] is False


def test_freeze_default_anchors_rejects_mixed_protocol(tmp_path):
    """GOVERNANCE (8an.9): re-freezing one size's default_PI WARM while another keeps a COLD
    default_PI mixes non-comparable scored values — must raise (guard keys on default_PI)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap,protocol\n"
        "10,0,100,hexaly,50,,,cold\n"          # cold L_I, default_PI to be filled warm
        "100,0,200,gurobi,80,0.5,,cold\n"      # already-scored COLD default_PI for n=100
    )
    with pytest.raises(ValueError, match="MIXED-protocol"):
        B.freeze_default_anchors(seeds=(1,), frozen_path=str(frozen), out_path=str(tmp_path / "o.csv"),
                                 sizes=[10], warm=True,
                                 run_fn=lambda n, i, s: [_res([(60, 100), (90, 500)])])


def test_freeze_default_anchors_uniform_warm_ok(tmp_path):
    """Re-freezing ALL scored sizes warm against their kept cold L_I tags every row 'warm'."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap,protocol\n"
        "10,0,100,hexaly,50,,,cold\n"          # cold L_I=50 kept
        "100,0,200,gurobi,80,0.5,,cold\n"      # cold L_I=80 kept; cold default_PI re-scored warm
    )
    out = tmp_path / "out.csv"
    B.freeze_default_anchors(seeds=(1,), frozen_path=str(frozen), out_path=str(out),
                             warm=True,  # sizes=None -> recompute every size's default_PI warm
                             run_fn=lambda n, i, s: [_res([(60, 100), (190 if n == 100 else 90, 500)])])
    table = B.load_frozen_baselines(str(out))
    assert table[(10, 0)]["protocol"] == "warm" and table[(10, 0)]["L_I"] == 50.0
    assert table[(100, 0)]["protocol"] == "warm" and table[(100, 0)]["L_I"] == 80.0  # cold L_I kept


def test_default_anchors_l_i_override_keeps_cold_floor(tmp_path):
    """bd 8an.9: with L_I_override the cold L_I is KEPT and only default_PI is (re)scored against it
    — and a warm greedy that lands ON B_I no longer triggers the spurious L>=B drop."""
    # warm runs whose first-feasible == B_I (greedy optimal) would be dropped by the cold path...
    warm_runs = [_res([(100, 0), (100, 50)]) for _ in range(3)]  # history[0]=100==B_I
    cold_path = B.default_instance_anchors(warm_runs, B_I=100, n=10)
    assert cold_path["status"] == "dropped_L_ge_B"               # warm L_I = 100 == B_I -> dropped
    # ...but with the cold L_I kept, it scores fine against the lower cold floor.
    kept = B.default_instance_anchors(warm_runs, B_I=100, n=10, L_I_override=50.0)
    assert kept["status"] == "ok" and kept["L_I"] == 50.0
    import math as _m
    assert _m.isfinite(kept["default_PI"])


def test_warm_skeleton_keeps_cold_li_blanks_pi_then_freeze_single_protocol(tmp_path):
    """The bd 8an.9 warm re-freeze keeps the cold L_I, blanks default_PI in the skeleton, and fills
    warm default_PI per size against that cold L_I — never tripping the (default_PI-keyed) guard."""
    import refreeze_largen as R
    cold = tmp_path / "baselines_frozen.csv"
    cold.write_text(
        "size,index,B_I,B_I_method,L_I,default_PI,default_cap,protocol\n"
        "10,0,100,hexaly,50,0.5,,cold\n"
        "20,0,200,hexaly,80,0.4,,cold\n"
        "1000,0,9999,gurobi,,,,\n"          # large-n B_I-only: no L_I -> kept verbatim, skipped warm
    )
    warm = tmp_path / "baselines_frozen_warm.csv"
    R._seed_warm_skeleton(str(warm), src_path=str(cold))
    skel = B.load_frozen_baselines(str(warm))
    assert skel[(10, 0)]["L_I"] == 50.0 and skel[(10, 0)]["default_PI"] is None  # L_I KEPT, PI blanked
    assert skel[(20, 0)]["L_I"] == 80.0 and skel[(20, 0)]["default_PI"] is None
    assert skel[(1000, 0)]["B_I"] == 9999.0

    def mock_run(n, i, s):
        return [_res([(60, 100), (90, 500)]) for _ in s]   # feasible warm history

    for n in (10, 20):   # per-size, in place — must NOT raise MIXED-protocol
        summ = B.freeze_default_anchors(sizes=[n], seeds=(1,), frozen_path=str(warm),
                                        warm=True, run_fn=mock_run)
        assert summ["anchored_protocol"] == "warm"
    final = B.load_frozen_baselines(str(warm))
    assert final[(10, 0)]["protocol"] == "warm" and final[(10, 0)]["L_I"] == 50.0  # cold L_I kept
    assert final[(20, 0)]["protocol"] == "warm" and final[(20, 0)]["L_I"] == 80.0
    assert final[(10, 0)]["default_PI"] is not None                                 # warm PI filled
    assert final[(1000, 0)]["L_I"] is None                                          # large-n untouched


def test_assess_cap_convergence_converges():
    """_assess picks the SMALLER cap of the first consecutive pair within tol."""
    rows = [{"cap": 10, "default_PI": 0.90}, {"cap": 20, "default_PI": 0.80},
            {"cap": 40, "default_PI": 0.795}, {"cap": 80, "default_PI": 0.793}]
    cap, converged, bias = B._assess_cap_convergence(rows, tol=0.02)
    assert converged is True and cap == 20          # |0.795-0.80|/0.80 = 0.6% <= 2%
    assert bias == pytest.approx(0.00625, rel=1e-3)


def test_assess_cap_convergence_not_converged():
    """Monotone-but-never-flattening PI -> not converged; recommend the largest cap."""
    rows = [{"cap": 10, "default_PI": 0.9}, {"cap": 20, "default_PI": 0.6},
            {"cap": 40, "default_PI": 0.3}]
    cap, converged, bias = B._assess_cap_convergence(rows, tol=0.02)
    assert converged is False and cap == 40 and bias is not None


def test_assess_cap_convergence_skips_non_finite_pi():
    """Rows with None/inf default_PI (never-feasible-at-this-cap) are ignored."""
    rows = [{"cap": 10, "default_PI": None}, {"cap": 20, "default_PI": float("inf")},
            {"cap": 40, "default_PI": 0.5}]
    cap, converged, _ = B._assess_cap_convergence(rows, tol=0.02)
    assert converged is False and cap == 40  # only one usable point


def test_calibrate_cap_sweeps_and_recommends(tmp_path):
    """calibrate_cap runs the seed bank per cap and its recommendation matches _assess on
    the realized per-cap default_PI (ties the wiring to the convergence logic, no magic #)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text("size,index,B_I,B_I_method,L_I,default_PI,default_cap\n10,0,100,hexaly,,,\n")

    # bigger cap -> better second incumbent -> lower (converging) PI; L_I fixed at 50.
    second = {10: 70, 20: 85, 40: 88, 80: 89}

    def run_fn(n, index, seeds, cap):
        return [_res([(50, 1), (second[cap], 500)])]

    res = B.calibrate_cap(10, 0, caps=[10, 20, 40, 80], seeds=(0,), frozen_path=str(frozen),
                          run_fn=run_fn, tol=0.02)
    assert [r["cap"] for r in res["caps"]] == [10, 20, 40, 80]
    assert all(r["default_PI"] is not None for r in res["caps"])
    exp_cap, exp_conv, _ = B._assess_cap_convergence(res["caps"], 0.02)
    assert res["recommended_cap"] == exp_cap and res["converged"] == exp_conv


def test_calibrate_cap_requires_b_i(tmp_path):
    """Fail-loud: calibrating an instance with no frozen B_I raises (nothing to anchor)."""
    frozen = tmp_path / "frozen.csv"
    frozen.write_text("size,index,B_I,B_I_method,L_I,default_PI,default_cap\n10,0,,,,,\n")
    with pytest.raises(ValueError, match="No frozen B_I"):
        B.calibrate_cap(10, 0, caps=[10, 20], frozen_path=str(frozen), run_fn=lambda *a: [])


class _FakeModel:
    """Stand-in for cbqs.Model so the freeze-path build plumbing is testable without a clone."""
    def __init__(self):
        self.seed = 0

    def set_param(self, *_a, **_k):
        pass

    def solve(self):
        return types.SimpleNamespace(history=[(1, 1)], oracle_calls=1, objective=1)


def _patch_build(monkeypatch, recorder):
    """Patch eq29_loader.load_eq29/build_model; build records its `vectorized` kwarg."""
    import eq29_loader as L
    monkeypatch.setattr(L, "load_eq29", lambda n, i, br=None: ([[0]], [[0]], [[0]]))

    def fake_build(c1, c2, c3, vectorized=None):
        recorder.append(vectorized)
        return _FakeModel()

    monkeypatch.setattr(L, "build_model", fake_build)


def test_run_default_seed_bank_forces_vectorized_by_default(monkeypatch):
    """bd 0o8 build-path fix: the freeze forces build_model(vectorized=True) so dense n<1000
    instances build via the fast matmul path (>2.5min O(n^2) loop at n=500 -> ~0.9s). The two
    paths build the SAME QCQP (eq29_loader equivalence tests), so anchors are unchanged."""
    seen = []
    _patch_build(monkeypatch, seen)
    B.run_default_seed_bank(500, 0, seeds=(1, 2))
    assert seen == [True, True]  # one build per seed, all vectorized


def test_run_default_seed_bank_vectorized_override(monkeypatch):
    """vectorized=False keeps the legacy O(n^2) loop build (exact-reproduction escape hatch)."""
    seen = []
    _patch_build(monkeypatch, seen)
    B.run_default_seed_bank(500, 0, seeds=(1,), vectorized=False)
    assert seen == [False]


def test_seed_bank_rejects_entropy_seed_zero(monkeypatch):
    """bd cjz: Model seed 0 means 'auto-generate from entropy' — a non-reproducible trajectory
    whose result still reports the REQUESTED seed, so matched-seed checks downstream are blind
    to it. A seed bank exists to be replayed (§13): run_default_seed_bank must fail loud on a
    0 (or negative) member, and the canonical DEFAULT_SEED_BANK must not contain one."""
    assert 0 not in B.DEFAULT_SEED_BANK
    assert all(s >= 1 for s in B.DEFAULT_SEED_BANK)
    assert len(B.DEFAULT_SEED_BANK) % 2 == 1  # odd: single-value median (see bank docstring)
    seen = []
    _patch_build(monkeypatch, seen)
    with pytest.raises(ValueError, match="entropy"):
        B.run_default_seed_bank(500, 0, seeds=(0, 1))
    with pytest.raises(ValueError, match="entropy"):
        B.run_default_seed_bank(500, 0, seeds=(-3,))
    assert seen == []  # rejected before any build/solve


_HAS_INSTANCES = bool(os.environ.get("CBQS_BENCHMARKS_DIR")) and os.path.isdir(
    os.path.join(os.environ.get("CBQS_BENCHMARKS_DIR", ""),
                 "Paper_general_constraints", "instances", "10_0"))


@pytest.mark.skipif(not _HAS_INSTANCES, reason="CBQS_BENCHMARKS_DIR instances not available")
def test_real_default_anchors_n10_end_to_end():
    """Real n=10 CBQS-default run over a tiny seed bank → first-feasible parses, the anchor status
    is one of the valid kinds, and any computed default_PI sits in the metric's [-0.5, 1] range.
    Uses the real T(n) budget (M=-1) — n=10 is trivially cheap (NORTHSTAR §1.2: never a capped M)."""
    pytest.importorskip("cbqs")
    results = B.run_default_seed_bank(10, 0, seeds=(1, 2, 3), M=-1, num_workers=2)
    # harness contract: every history is feasible-only and oracle-ascending.
    for r in results:
        oracles = [o for (_v, o) in r.history]
        assert oracles == sorted(oracles)
    frozen = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "baselines_frozen.csv")
    table = B.load_frozen_baselines(frozen)
    if (10, 0) not in table or table[(10, 0)]["B_I"] is None:
        pytest.skip("no B_I for (10,0) in frozen table")
    a = B.default_instance_anchors(results, B_I=table[(10, 0)]["B_I"], n=10)
    assert a["status"] in ("ok", "dropped_L_ge_B", "default_unreliable", "never_feasible")
    if a["status"] == "ok":
        assert -0.5 <= a["default_PI"] <= 1.0
        assert a["L_I"] < table[(10, 0)]["B_I"]


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


def test_calibrate_floor_artifact_and_admissible_fraction(tmp_path, monkeypatch):
    """M1 'floor calibrated' (bd 8an.2, amended bd 8an.3.8): calibrate_floor measures, per size,
    the default's own per-portfolio lift vs the pooled objective-space spread — via the metric's
    own producers — and reports max_admissible_fraction = min_lift/spread_obj. Under the TAIL
    floor this no longer pins EXPLORE_FLOOR_FRACTION (default-vs-default passes structurally);
    the artifact remains the diversity diagnostic that documents the noise landscape the tail
    floor's band is scaled by. Converged sizes are recorded unmeasurable."""
    frozen = tmp_path / "frozen.csv"
    with open(frozen, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["size", "index", "B_I", "B_I_method", "L_I", "default_PI"])
        w.writerow([10, 0, 100, "hexaly", 1, 0.5])     # anchored -> calibrated
        w.writerow([20, 0, 100, "hexaly", 1, 0.5])     # anchored, converged portfolio
        w.writerow([30, 0, 100, "hexaly", "", ""])     # NOT anchored -> excluded

    def fake_run(n, _i, seeds):
        if n == 10:
            # two seeds, per-portfolio finals: lifts (best - median) = 10 and 20.
            return [types.SimpleNamespace(final_incumbents=[(100, True), (90, True), (80, True)], seed=1),
                    types.SimpleNamespace(final_incumbents=[(120, True), (100, True), (95, True)], seed=2)]
        # n == 20: fully converged portfolio -> IQR 0 -> unmeasurable.
        return [types.SimpleNamespace(final_incumbents=[(90, True), (90, True), (90, True)], seed=1)]

    out = B.calibrate_floor(sizes=[10, 20, 30], run_fn=fake_run,
                            frozen_path=str(frozen), out_path=str(tmp_path / "floor.csv"))
    rec10 = out["per_size"][10]
    # spread([100,90,80,120,100,95]) pooled per instance; lifts median over 2 seeds = 15.
    assert rec10["status"] == "ok" and rec10["spread_obj"] > 0
    assert rec10["min_lift"] == pytest.approx(15.0)   # median(10, 20)
    assert rec10["max_admissible_fraction"] == pytest.approx(15.0 / rec10["spread_obj"])
    assert out["per_size"][20]["status"] == "unmeasurable"
    assert 30 not in out["per_size"]                   # un-anchored sizes are excluded
    assert out["max_admissible_fraction"] == pytest.approx(rec10["max_admissible_fraction"])
    # artifact round-trips
    with open(tmp_path / "floor.csv") as f:
        rows = list(csv.DictReader(f))
    assert {r["size"] for r in rows} == {"10", "20"}
    assert [r for r in rows if r["size"] == "20"][0]["status"] == "unmeasurable"
