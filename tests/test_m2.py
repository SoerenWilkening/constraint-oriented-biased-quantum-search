"""Tests for the M2 hypothesis-check harness (benchmarks/m2.py, bd 8an.3.3).

Stub-based — no C extension, no real solves (mirrors tests/test_metric.py).
Covers: schedule resolution, run-set persistence round-trip (exactly what the
§6 metric duck-types), sweep resume, the M2b decision-touch report, and the
verdict wiring (matched seeds + strict xcheck by default).
"""
import json
import math
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import m2  # noqa: E402
from benchmarks.m2 import (  # noqa: E402
    anchored_instances,
    decision_touch_report,
    load_run_set_dir,
    record_to_result,
    register_schedule,
    resolve_params,
    result_to_record,
    run_sweep,
    save_run_set,
    write_touch_csv,
)


def _dt(sat=(0, 0, 0, 0), opt_sat=(10, 4, 2, 4), opt=(20, 15, 0, 5)):
    """decision_touch stub: per phase (decisions, free, bothinf, forced)."""
    out = {}
    for phase, (d, f, b, x) in (("sat", sat), ("opt_sat", opt_sat), ("opt", opt)):
        consulted = f + (b if phase == "opt_sat" else 0)
        out[phase] = {"decisions": d, "free": f, "bothinf": b, "forced": x,
                      "touch_fraction": (consulted / d) if d else None}
    return out


def _result(seed=1, objective=90.0, feasible=True, history=((50.0, 10), (90.0, 40)),
            final_incumbents=((90.0, True), (80.0, True)), decision_touch=None,
            with_bd=True):
    bd = None
    if with_bd:
        bd = {"n": 10, "opt_candidates": 5, "opt_free_sum": 15,
              "decision_touch": decision_touch or _dt(),
              "per_worker": [{"should": "be dropped"}]}
    return types.SimpleNamespace(
        seed=seed, objective=objective, feasible=feasible, oracle_calls=123,
        history=[tuple(h) for h in history],
        final_incumbents=[tuple(f) for f in final_incumbents],
        branch_diagnostics=bd,
    )


# --------------------------------------------------------------------------- #
# Schedule resolution
# --------------------------------------------------------------------------- #

def test_resolve_params_scalars_pass_through():
    out = resolve_params({"opt_branching_radius": 8.0, "opt_switch_oracles": 100},
                         10, None, None, None)
    assert out == {"opt_branching_radius": 8.0, "opt_switch_oracles": 100}


def test_resolve_params_callable_values_get_instance_args():
    seen = {}

    def weights(n, c1, c2, c3):
        seen["args"] = (n, c1, c2, c3)
        return [0.5] * n

    out = resolve_params({"opt_branching_weights": weights}, 4, "C1", "C2", "C3")
    assert out["opt_branching_weights"] == [0.5] * 4
    assert seen["args"] == (4, "C1", "C2", "C3")


def test_resolve_params_whole_factory():
    factory = lambda n, c1, c2, c3: {"opt_branching_radius": float(n) / 2}
    assert resolve_params(factory, 10, None, None, None) == {"opt_branching_radius": 5.0}


def test_register_schedule_rejects_duplicates():
    name = "__test_sched__"
    try:
        register_schedule(name, lambda n, c1, c2, c3: {})
        with pytest.raises(ValueError):
            register_schedule(name, lambda n, c1, c2, c3: {})
    finally:
        m2.SCHEDULES.pop(name, None)


# --------------------------------------------------------------------------- #
# Anchored instance set
# --------------------------------------------------------------------------- #

def test_anchored_instances_requires_all_three_anchors():
    baselines = {
        (10, 0): {"B_I": 100.0, "L_I": 0.0, "default_PI": 0.5},
        (10, 1): {"B_I": 100.0, "L_I": 0.0, "default_PI": None},      # pending freeze
        (3000, 0): {"B_I": 100.0, "L_I": None, "default_PI": None},   # bd 0o8
        (20, 0): {"B_I": 100.0, "L_I": 0.0, "default_PI": 0.4},
    }
    assert anchored_instances(baselines) == [(10, 0), (20, 0)]


# --------------------------------------------------------------------------- #
# Persistence round-trip
# --------------------------------------------------------------------------- #

def test_record_roundtrip_preserves_metric_surface():
    r = _result(seed=3)
    rec = result_to_record(r)
    back = record_to_result(json.loads(json.dumps(rec)))  # through real JSON
    assert back.seed == 3
    assert back.history == [(50.0, 10), (90.0, 40)]
    assert all(isinstance(o, int) for (_v, o, *_) in back.history)
    assert back.final_incumbents == [(90.0, True), (80.0, True)]
    assert back.objective == pytest.approx(90.0)
    assert back.feasible is True
    assert back.branch_diagnostics["decision_touch"]["opt"]["free"] == 15


def test_record_drops_bulky_per_worker():
    rec = result_to_record(_result())
    assert "per_worker" not in rec["branch_diagnostics"]


def test_save_load_run_set_dir(tmp_path):
    d = str(tmp_path / "rs")
    save_run_set(d, 10, 0, [_result(seed=s) for s in (1, 2)], schedule_id="default")
    save_run_set(d, 20, 1, [_result(seed=1)], schedule_id="default",
                 resolved_params={"opt_branching_radius": 8.0})
    loaded = load_run_set_dir(d)
    assert set(loaded) == {(10, 0), (20, 1)}
    assert [r.seed for r in loaded[(10, 0)]] == [1, 2]
    payload = json.load(open(os.path.join(d, "20_1.json")))
    assert payload["resolved_params"] == {"opt_branching_radius": 8.0}


def test_save_run_set_serializes_array_params(tmp_path):
    np = pytest.importorskip("numpy")
    d = str(tmp_path / "rs")
    save_run_set(d, 10, 0, [_result()], schedule_id="theta",
                 resolved_params={"opt_branching_weights": np.array([0.25, -0.5])})
    payload = json.load(open(os.path.join(d, "10_0.json")))
    assert payload["resolved_params"]["opt_branching_weights"] == [0.25, -0.5]


def test_load_run_set_dir_fails_loud_on_missing_or_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_run_set_dir(str(tmp_path / "nope"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError):
        load_run_set_dir(str(empty))


# --------------------------------------------------------------------------- #
# Sweep + resume
# --------------------------------------------------------------------------- #

def test_run_sweep_resume_skips_existing(tmp_path, monkeypatch):
    d = str(tmp_path / "sweep")
    calls = []

    def fake_candidate(n, index, seeds, factory, **kw):
        calls.append((n, index))
        return [_result(seed=s) for s in seeds], {"opt_branching_radius": 8.0}

    monkeypatch.setattr(m2, "run_candidate_seed_bank", fake_candidate)
    instances = [(10, 0), (10, 1)]
    out1 = run_sweep("cand", {"opt_branching_radius": 8.0}, instances,
                     out_dir=d, seeds=(1, 2), log=lambda *a: None)
    assert out1 == {"done": instances, "skipped": []}
    assert calls == instances

    out2 = run_sweep("cand", {"opt_branching_radius": 8.0}, instances,
                     out_dir=d, seeds=(1, 2), log=lambda *a: None)
    assert out2 == {"done": [], "skipped": instances}
    assert calls == instances        # no re-solve

    manifest = json.load(open(os.path.join(d, "manifest.json")))
    assert manifest["schedule_id"] == "cand"
    assert manifest["seeds"] == [1, 2]


def test_run_sweep_default_uses_default_runner(tmp_path, monkeypatch):
    d = str(tmp_path / "sweep")
    seen = []

    def fake_default(n, index, seeds, **kw):
        seen.append((n, index))
        return [_result(seed=s) for s in seeds]

    import benchmarks.baselines as baselines_mod
    monkeypatch.setattr(baselines_mod, "run_default_seed_bank", fake_default)
    out = run_sweep("default", None, [(10, 0)], out_dir=d, seeds=(1,),
                    log=lambda *a: None)
    assert out["done"] == [(10, 0)] and seen == [(10, 0)]
    payload = json.load(open(os.path.join(d, "10_0.json")))
    assert payload["schedule_id"] == "default"
    assert payload["resolved_params"] is None


# --------------------------------------------------------------------------- #
# Decision-touch report (M2b)
# --------------------------------------------------------------------------- #

def test_decision_touch_report_pools_and_recomputes_fraction():
    run_sets = {
        (10, 0): [_result(decision_touch=_dt(opt=(10, 5, 0, 5))),
                  _result(decision_touch=_dt(opt=(30, 5, 0, 25)))],
        (10, 1): [_result(decision_touch=_dt(opt=(60, 20, 0, 40)))],
        (20, 0): [_result(decision_touch=_dt(opt=(10, 10, 0, 0)))],
    }
    rows = decision_touch_report(run_sets)
    by = {(r["n"], r["phase"]): r for r in rows}
    opt10 = by[(10, "opt")]
    # pooled-counter fraction (30/100), NOT the mean of per-run fractions
    assert opt10["decisions"] == 100 and opt10["free"] == 30
    assert opt10["touch_fraction"] == pytest.approx(0.30)
    assert opt10["instances"] == 2 and opt10["runs"] == 3
    # opt_sat counts bothinf as consulted: (4+2)/10 per stub run
    os10 = by[(10, "opt_sat")]
    assert os10["touch_fraction"] == pytest.approx((os10["free"] + os10["bothinf"])
                                                   / os10["decisions"])
    # sat never ran -> None, not 0.0
    assert by[(10, "sat")]["touch_fraction"] is None
    assert by[(20, "opt")]["touch_fraction"] == pytest.approx(1.0)


def test_decision_touch_report_raises_on_pre_m2a_records():
    stale = _result()
    stale.branch_diagnostics = {"n": 10}          # no decision_touch key
    with pytest.raises(ValueError, match="decision_touch"):
        decision_touch_report({(10, 0): [stale]})


def test_write_touch_csv(tmp_path):
    rows = decision_touch_report({(10, 0): [_result()]})
    path = write_touch_csv(rows, str(tmp_path / "touch.csv"))
    lines = open(path).read().strip().splitlines()
    assert lines[0].startswith("n,phase,decisions")
    assert len(lines) == 1 + 3                    # header + 3 phases


# --------------------------------------------------------------------------- #
# Verdict wiring
# --------------------------------------------------------------------------- #

def _bl(B_I=100.0, L_I=0.0, default_PI=0.5):
    return {"B_I": B_I, "B_I_method": "hexaly", "L_I": L_I, "default_PI": default_PI}


def _bank(obj, fincs, seeds=(1, 2, 3)):
    """One instance's seed bank: a single feasible incumbent at oracle 0, so the
    bounded integral collapses to PI == γ(obj) exactly (mirrors test_metric)."""
    return [_result(seed=s, objective=obj, history=((obj, 0),),
                    final_incumbents=fincs) for s in seeds]


def _write_bank(d, key, bank, schedule_id):
    save_run_set(d, key[0], key[1], bank, schedule_id=schedule_id)


def _baselines_csv(tmp_path, rows):
    path = str(tmp_path / "frozen.csv")
    with open(path, "w") as fh:
        fh.write("size,index,B_I,B_I_method,L_I,default_PI,default_cap\n")
        for (n, i), e in sorted(rows.items()):
            fh.write(f"{n},{i},{e['B_I']},{e['B_I_method']},{e['L_I']},"
                     f"{e['default_PI']},\n")
    return path


def test_verdict_from_dirs_end_to_end(tmp_path):
    # candidate uniformly better (PI 0.2 vs frozen 0.5), default re-scores to frozen.
    cand_dir, def_dir = str(tmp_path / "cand"), str(tmp_path / "def")
    baselines = {}
    for i in range(3):
        key = (10, i)
        baselines[key] = _bl(default_PI=(0.5, 0.6, 0.7)[i])
        _write_bank(cand_dir, key, _bank((80, 70, 60)[i],
                                         ((100.0, True), (90.0, True), (80.0, True))), "cand")
        _write_bank(def_dir, key, _bank((50, 40, 30)[i],
                                        ((100.0, True), (95.0, True), (90.0, True))), "default")
    frozen = _baselines_csv(tmp_path, baselines)
    out = m2.verdict_from_dirs(cand_dir, def_dir, baselines_path=frozen,
                               require_largest_n=False)
    assert out["overall_pass"] is True
    assert out["default_xcheck_failures"] == []
    assert out["candidate_PI"][(10, 0)] == pytest.approx(0.2)
    # the summary printer accepts the real verdict shape
    lines = []
    m2.summarize_verdict(out, log=lines.append)
    assert any("overall_pass: True" in ln for ln in lines)


def test_verdict_scores_never_feasible_candidate_as_regression(tmp_path):
    # bd 8an.8: a candidate that finds NO feasible point on a default-feasible
    # instance (order_pii_desc @ 70_0) flows through the verdict as a
    # feasibility regression + §8.3 tail collapse — it must never raise and
    # must never pass.
    cand_dir, def_dir = str(tmp_path / "cand"), str(tmp_path / "def")
    baselines = {}
    for i in range(2):
        key = (10, i)
        baselines[key] = _bl(default_PI=(0.4, 0.6)[i])
        _write_bank(def_dir, key, _bank((60, 40)[i], ((100.0, True), (95.0, True))),
                    "default")
    # instance 0: candidate fine; instance 1: candidate never feasible
    _write_bank(cand_dir, (10, 0), _bank(80, ((100.0, True), (90.0, True))),
                "cand")
    _write_bank(cand_dir, (10, 1),
                [_honest_infeasible(seed=s) for s in (1, 2, 3)], "cand")
    frozen = _baselines_csv(tmp_path, baselines)
    out = m2.verdict_from_dirs(cand_dir, def_dir, baselines_path=frozen,
                               require_largest_n=False)
    assert out["overall_pass"] is False
    ps = out["aggregation"]["per_size"][10]
    assert ps["feasibility_regressed"] is True
    assert out["floor"]["per_size"][10]["stratum_pass"] is False
    # the summary printer accepts the regression shape
    lines = []
    m2.summarize_verdict(out, log=lines.append)
    assert any("overall_pass: False" in ln for ln in lines)


def test_verdict_from_dirs_strict_xcheck_default_on(tmp_path):
    # default side drifts from the frozen PI -> strict xcheck (DEFAULT) raises.
    cand_dir, def_dir = str(tmp_path / "cand"), str(tmp_path / "def")
    key = (10, 0)
    baselines = {key: _bl(default_PI=0.5)}
    _write_bank(cand_dir, key, _bank(80, ((100.0, True), (90.0, True))), "cand")
    _write_bank(def_dir, key, _bank(80, ((100.0, True), (95.0, True))), "default")  # PI 0.2 != 0.5
    frozen = _baselines_csv(tmp_path, baselines)
    with pytest.raises(ValueError, match="strict_xcheck"):
        m2.verdict_from_dirs(cand_dir, def_dir, baselines_path=frozen,
                             require_largest_n=False)


def test_verdict_from_dirs_enforces_matched_seeds(tmp_path):
    cand_dir, def_dir = str(tmp_path / "cand"), str(tmp_path / "def")
    key = (10, 0)
    baselines = {key: _bl()}
    _write_bank(cand_dir, key, _bank(80, ((100.0, True),), seeds=(1, 2, 3)), "cand")
    _write_bank(def_dir, key, _bank(50, ((100.0, True),), seeds=(4, 5, 6)), "default")
    frozen = _baselines_csv(tmp_path, baselines)
    with pytest.raises(ValueError):
        m2.verdict_from_dirs(cand_dir, def_dir, baselines_path=frozen,
                             require_largest_n=False)


# --------------------------------------------------------------------------- #
# Candidate runner seed validation (no solve needed — fails before loading)
# --------------------------------------------------------------------------- #

def test_run_candidate_seed_bank_rejects_seed_zero():
    with pytest.raises(ValueError, match="seed"):
        m2.run_candidate_seed_bank(10, 0, (0, 1), {"opt_branching_radius": 4.0})


# --------------------------------------------------------------------------- #
# Verification guard (bd 8an.3.5 lesson: variable_order accepted infeasible
# solutions and the harness scored them — verified=False must FAIL LOUD)
# --------------------------------------------------------------------------- #

def test_run_sweep_rejects_unverified_results(tmp_path, monkeypatch):
    d = str(tmp_path / "sweep")

    def fake_candidate(n, index, seeds, factory, **kw):
        bad = [_result(seed=s) for s in seeds]
        for r in bad:
            r.verified = False
            r.violations = ["Post-solve verification FAILED"]
        return bad, {"opt_variable_priorities": [1.0]}

    monkeypatch.setattr(m2, "run_candidate_seed_bank", fake_candidate)
    with pytest.raises(ValueError, match="verification"):
        run_sweep("corrupt", {"opt_variable_priorities": [1.0]}, [(10, 0)],
                  out_dir=d, seeds=(1,), log=lambda *a: None)
    assert not os.path.exists(os.path.join(d, "10_0.json"))  # never persisted


def _honest_infeasible(seed=1):
    """A run that HONESTLY found no feasible point within budget (bd 8an.8):
    feasible=False, empty history, no feasible final incumbent — global_opt
    holds the all-zeros init residue, which verify_solution rightly flags
    (verified=False). This is a legitimate, scoreable lever outcome (§6 item 5
    never-feasible sentinel + §6.6 feasibility tier), NOT the 8an.3.5
    corruption signature (feasible=True ∧ verified=False)."""
    r = _result(seed=seed, objective=0.0, feasible=False, history=(),
                final_incumbents=((0.0, False), (0.0, False)))
    r.verified = False
    r.violations = ["Post-solve verification FAILED: solution violates one "
                    "or more constraints"]
    return r


def test_run_sweep_persists_honest_infeasible_results(tmp_path, monkeypatch):
    # bd 8an.8 (order_pii_desc @ 70_0): failure-to-find-feasibility must
    # PERSIST so the metric can score the feasibility regression — only
    # feasible=True ∧ verified=False is run-set corruption.
    d = str(tmp_path / "sweep")

    def fake_candidate(n, index, seeds, factory, **kw):
        return [_honest_infeasible(seed=s) for s in seeds], \
            {"opt_variable_priorities": [1.0]}

    monkeypatch.setattr(m2, "run_candidate_seed_bank", fake_candidate)
    out = run_sweep("hostile_order", {"opt_variable_priorities": [1.0]},
                    [(70, 0)], out_dir=d, seeds=(1,), log=lambda *a: None)
    assert out["done"] == [(70, 0)]
    assert os.path.exists(os.path.join(d, "70_0.json"))


def test_load_run_set_dir_accepts_honest_infeasible_records(tmp_path):
    d = str(tmp_path / "rs")
    save_run_set(d, 70, 0, [_honest_infeasible()], schedule_id="hostile_order")
    loaded = load_run_set_dir(d)
    assert (70, 0) in loaded
    assert loaded[(70, 0)][0].feasible is False
    assert loaded[(70, 0)][0].verified is False


def test_require_verified_rejects_infeasible_with_scored_history(tmp_path):
    # Adversarial inverse (workflow review of bd 8an.8): feasible=False is only
    # "honest" with an EMPTY scored surface. The metric scores history /
    # final_incumbents, NOT result.feasible — a feasible=False+verified=False
    # record carrying feasible scored entries is impossible under correct
    # operation (every scored entry gates on the cur_sol->feasible that wins
    # global_opt) and must stay fatal, or bogus-feasible data slips into the
    # metric behind an infeasible top-level flag.
    d = str(tmp_path / "rs")
    r = _honest_infeasible()
    r.history = [(90.0, 5)]                       # non-empty scored surface
    save_run_set(d, 70, 0, [r], schedule_id="corrupt")
    with pytest.raises(ValueError, match="verification"):
        load_run_set_dir(d)


def test_require_verified_rejects_infeasible_with_feasible_incumbent(tmp_path):
    d = str(tmp_path / "rs")
    r = _honest_infeasible()
    r.final_incumbents = [(0.0, False), (90.0, True)]   # feasible scored entry
    save_run_set(d, 70, 0, [r], schedule_id="corrupt")
    with pytest.raises(ValueError, match="verification"):
        load_run_set_dir(d)


def test_run_sweep_mixed_bank_corrupt_result_still_raises(tmp_path, monkeypatch):
    # The real 70_0 bank is MIXED (5/7 honest-infeasible, 2/7 feasible). The
    # guard discriminates PER RESULT: one corrupt result hiding in an
    # otherwise-honest bank must still crash the sweep (bd 8an.3.5), and
    # nothing may persist.
    d = str(tmp_path / "sweep")

    def fake_candidate(n, index, seeds, factory, **kw):
        corrupt = _result(seed=seeds[-1])         # feasible=True default
        corrupt.verified = False
        return [_honest_infeasible(seed=s) for s in seeds[:-1]] + [corrupt], {}

    monkeypatch.setattr(m2, "run_candidate_seed_bank", fake_candidate)
    with pytest.raises(ValueError, match="verification"):
        run_sweep("mixed_corrupt", {}, [(70, 0)], out_dir=d, seeds=(1, 2, 3),
                  log=lambda *a: None)
    assert not os.path.exists(os.path.join(d, "70_0.json"))


def test_run_sweep_mixed_bank_honest_and_feasible_persists(tmp_path, monkeypatch):
    # ...and the mirror: honest-infeasible seeds alongside verified feasible
    # seeds (the actual 70_0 shape) persist and reload cleanly.
    d = str(tmp_path / "sweep")

    def fake_candidate(n, index, seeds, factory, **kw):
        ok = _result(seed=seeds[-1])
        ok.verified = True
        return [_honest_infeasible(seed=s) for s in seeds[:-1]] + [ok], {}

    monkeypatch.setattr(m2, "run_candidate_seed_bank", fake_candidate)
    out = run_sweep("mixed_honest", {}, [(70, 0)], out_dir=d, seeds=(1, 2, 3),
                    log=lambda *a: None)
    assert out["done"] == [(70, 0)]
    loaded = load_run_set_dir(d)
    assert [r.verified for r in loaded[(70, 0)]] == [False, False, True]


def test_record_roundtrip_preserves_verified():
    r = _result()
    r.verified = True
    rec = json.loads(json.dumps(result_to_record(r)))
    assert rec["verified"] is True
    assert record_to_result(rec).verified is True


def test_load_run_set_dir_rejects_known_invalid_records(tmp_path):
    d = str(tmp_path / "rs")
    r = _result()
    r.verified = False
    save_run_set(d, 10, 0, [r], schedule_id="corrupt")
    with pytest.raises(ValueError, match="verification"):
        load_run_set_dir(d)


def test_pre_guard_records_without_verified_still_load(tmp_path):
    # Run-sets written before the guard carry no "verified" key -> None -> pass.
    d = str(tmp_path / "rs")
    save_run_set(d, 10, 0, [_result()], schedule_id="legacy")
    payload = json.load(open(os.path.join(d, "10_0.json")))
    for rec in payload["records"]:
        rec.pop("verified", None)
    json.dump(payload, open(os.path.join(d, "10_0.json"), "w"))
    assert (10, 0) in load_run_set_dir(d)


# --------------------------------------------------------------------------- #
# bd 8an.9: the m2 CLI defaults run-default/run-candidate to the WARM start
# (matching the canonical warm baselines_frozen.csv); --cold opts out.
# --------------------------------------------------------------------------- #

def _stub_cli(monkeypatch):
    captured = {}

    def fake_run_sweep(*a, **k):
        captured.update(k)
        return {"done": [], "skipped": []}

    monkeypatch.setattr(m2, "run_sweep", fake_run_sweep)
    monkeypatch.setattr(m2, "load_frozen_baselines",
                        lambda p: {(10, 0): {"B_I": 1.0, "L_I": 0.0, "default_PI": 0.1,
                                             "default_cap": 0, "protocol": "warm"}})
    monkeypatch.setattr(m2, "anchored_instances", lambda t: [(10, 0)])
    return captured


def test_m2_cli_run_default_defaults_to_warm(monkeypatch, tmp_path):
    captured = _stub_cli(monkeypatch)
    m2._main(["run-default", "--out-dir", str(tmp_path), "--sizes", "10", "--seeds", "1"])
    assert captured["warm"] is True      # WARM is the default (bd 8an.9)


def test_m2_cli_cold_flag_opts_out(monkeypatch, tmp_path):
    captured = _stub_cli(monkeypatch)
    m2._main(["run-default", "--cold", "--out-dir", str(tmp_path), "--sizes", "10", "--seeds", "1"])
    assert captured["warm"] is False     # --cold reproduces the archived cold baselines
