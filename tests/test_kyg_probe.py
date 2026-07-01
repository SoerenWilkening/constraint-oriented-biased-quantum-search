"""Unit tests for the bd kyg re-anchored (vs r=2) probe analysis (benchmarks/run_kyg_probe.py).

These lock in the two review-hardened choices (bd kyg review wf_51d87237) that differ from the
run_m4_n3000 template — a wrong analysis here would silently manufacture a false 'r=2 is the ceiling':
  (1) PER-PAIR common budget B (a stall-prone third arm must NOT collapse B for other comparisons);
  (2) read_budget = the ACTUAL run budget (constant levers need a DEEPER read to see headroom, not T).
Plus the feasibility-loss guard (an arm that sheds feasibility is not a free win) and the exact-zero
neg harness check.
"""
import numpy as np
import pytest

from benchmarks import run_kyg_probe as K


def _rec(history, oracle_calls, feasible=True):
    """A minimal solve-record dict as _cmp/_verdict consume it. history = [[value, oracle], ...]."""
    return {"history": [[float(v), int(o)] for v, o in history],
            "oracle_calls": int(oracle_calls), "feasible": bool(feasible)}


def test_read_budget_faithful_enters_headroom_region():
    # faithful: read at mult*T (deeper); wall: read at T (faithful cost axis).
    assert K._read_budget(1000, 1.0, None) == 1000
    assert K._read_budget(1000, 4.0, None) == 4000
    assert K._read_budget(1000, 4.0, 900.0) == 1000     # wall mode ignores budget_mult


def test_headroom_read_surfaces_deep_region_win_that_T_read_misses():
    # A constant lever identical to baseline UP TO T, then pulling ahead in [T, 4T].
    T = 1000
    base = [[100, 500], [100, 1000], [100, 2000], [100, 4000]]        # flat 100 the whole way
    arm = [[100, 500], [100, 1000], [110, 2000], [120, 4000]]         # pulls ahead only AFTER T
    recs = {(0, "C_r2", 7): _rec(base, 4000), (0, "arm", 7): _rec(arm, 4000)}
    idxs, seeds = [0], [7]
    # read at T=1000: identical -> Δ=0 (the INERT read the bug produced)
    at_T = K._cmp(recs, idxs, seeds, "arm", "C_r2", read_budget=T)
    assert at_T["median_delta"] == 0
    # read at 4T=4000: the deep-region advantage is visible
    at_4T = K._cmp(recs, idxs, seeds, "arm", "C_r2", read_budget=4 * T)
    assert at_4T["median_delta"] == 20


def test_per_pair_budget_ignores_a_stalled_third_arm():
    # baseline and arm both run deep and the arm is strictly better at the deep budget; a THIRD arm
    # stalls at 200 oracles. A global-min budget would clamp B=200 (pre-divergence, Δ=0); per-pair
    # must read arm-vs-baseline at their own common depth and see the win.
    base = [[100, 200], [100, 5000]]
    arm = [[100, 200], [130, 5000]]
    stall = [[100, 200]]                                              # halts early (wall interrupt)
    recs = {(0, "C_r2", 7): _rec(base, 5000),
            (0, "arm", 7): _rec(arm, 5000),
            (0, "stall", 7): _rec(stall, 200)}
    c = K._cmp(recs, [0], [7], "arm", "C_r2", read_budget=9989)
    assert c["median_delta"] == 30          # NOT collapsed to 0 by the stalled arm
    # and the presence of `stall` in the arm set does not change the arm-vs-baseline verdict
    v = K._verdict(3000, recs, [0], [7], read_budget=9989, arms=["C_r2", "arm", "stall"], T=9989)
    assert v["cmp_vs_C_r2"]["arm"]["median_delta"] == 30


def test_neg_harness_requires_exact_zero_every_cell():
    T = 1000
    exact = {(0, "C_r2", s): _rec([[100, 1000]], 1000) for s in (1, 2, 3)}
    exact.update({(0, "neg_r2_genome", s): _rec([[100, 1000]], 1000) for s in (1, 2, 3)})
    v = K._verdict(90, exact, [0], [1, 2, 3], read_budget=T, arms=["C_r2", "neg_r2_genome"], T=T)
    assert v["neg_harness_clean"] is True
    # a mixed-sign neg that nets a zero MEDIAN must NOT pass (the m4-style all-cell-zero guard)
    mixed = {(0, "C_r2", 1): _rec([[100, 1000]], 1000),
             (0, "C_r2", 2): _rec([[100, 1000]], 1000),
             (0, "neg_r2_genome", 1): _rec([[103, 1000]], 1000),     # +3
             (0, "neg_r2_genome", 2): _rec([[97, 1000]], 1000)}      # -3  (median 0, but NOT clean)
    v2 = K._verdict(90, mixed, [0], [1, 2], read_budget=T, arms=["C_r2", "neg_r2_genome"], T=T)
    assert v2["neg_harness_clean"] is False


def test_feasibility_shedding_arm_is_never_helps():
    # arm beats baseline where both feasible, but loses feasibility on an instance the baseline solves.
    T = 1000
    recs = {}
    for idx in range(4):
        for s in (1, 2, 3):
            recs[(idx, "C_r2", s)] = _rec([[100, 1000]], 1000, feasible=True)
            recs[(idx, "arm", s)] = _rec([[110, 1000]], 1000, feasible=True)   # +10 where feasible
    # instance 4: baseline feasible, arm has NO feasible incumbent by B (empty history)
    for s in (1, 2, 3):
        recs[(4, "C_r2", s)] = _rec([[100, 1000]], 1000, feasible=True)
        recs[(4, "arm", s)] = _rec([], 1000, feasible=False)
    idxs = [0, 1, 2, 3, 4]
    c = K._cmp(recs, idxs, [1, 2, 3], "arm", "C_r2", read_budget=T)
    # counted once per INSTANCE (the first infeasible seed drops the whole instance from `pairs`)
    assert c["arm_feas_loss"] == 1
    assert c["n_pairs"] == 4                            # only the 4 fully-feasible instances compared
    assert K._classify(c) != "HELPS"                    # feasibility shed => cannot be a free win


def test_hurts_requires_significance_symmetric_with_helps():
    # a single-sign-flip pattern that would NOT clear a p<=0.05 HELPS bar must NOT be labeled HURTS.
    T = 1000
    recs = {}
    for idx in range(3):
        for s in (1, 2, 3):
            recs[(idx, "C_r2", s)] = _rec([[100, 1000]], 1000)
            # arm slightly worse on some, tied on others -> weak, not significant
            val = 99 if idx == 0 else 100
            recs[(idx, "arm", s)] = _rec([[val, 1000]], 1000)
    c = K._cmp(recs, [0, 1, 2], [1, 2, 3], "arm", "C_r2", read_budget=T)
    # only 1/3 instances negative -> not seed-robust, not significant -> NEUTRAL not HURTS
    assert K._classify(c) == "NEUTRAL"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
