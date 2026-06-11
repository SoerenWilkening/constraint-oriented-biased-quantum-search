"""Tests for the M3 agent-loop harness (benchmarks/m3.py, bd 8an.4).

Stub-based — no C extension, no real solves (mirrors tests/test_metric.py and
tests/test_m2.py). This module covers bd 8an.4.1: the scalar SELECTION FITNESS
derived from a score_verdict() dict. The fitness is PURE over the verdict dict
(it never solves and never calls score_verdict — the caller does that and fails
loud on its raises, landmine #2), so it is fully testable with canned dicts.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import m3  # noqa: E402
from benchmarks.m3 import fitness  # noqa: E402


# --------------------------------------------------------------------------- #
# Canned verdict builders — exactly the slice fitness() reads from the real
# score_verdict() dict (metric.py:550-566 aggregation, :847-... floor).
# --------------------------------------------------------------------------- #

def _agg_rec(W=0.0, median_PI=0.3, feasibility_regressed=False, lost=(), J=5):
    return {
        "W": float(W), "median_PI": median_PI, "n_jointly_feasible": J,
        "n_default_feasible": J + len(lost), "n_candidate_feasible": J,
        "feasibility_regressed": bool(feasibility_regressed),
        "lost_feasibility": list(lost), "worst_regression": 0.0,
        "margin": 0.05, "gate_B_pass": not feasibility_regressed,
    }


def _floor_rec(stratum_pass=True, frac=1.0):
    return {"n_instances": 5, "n_instances_evaluable": 5, "n_instances_passing": 5,
            "instance_pass_fraction": frac, "instance_deltas": {}, "per_seed_delta": {},
            "band": 0.1, "spread_obj": 1.0, "stratum_pass": stratum_pass}


def _verdict(agg_per_size, floor_per_size=None, overall_pass=None):
    """Assemble a score_verdict()-shaped dict from per-size aggregation recs.

    floor defaults to an all-passing floor over the same strata; overall_pass
    defaults to (no feasibility regression AND every gate_B passes AND floor
    passes) — the real AND structure (metric.py:1120).
    """
    if floor_per_size is None:
        floor_per_size = {n: _floor_rec() for n in agg_per_size}
    agg_pass = all(r["gate_B_pass"] for r in agg_per_size.values())
    floor_pass = all(r["stratum_pass"] for r in floor_per_size.values()
                     if r["stratum_pass"] is not None)
    if overall_pass is None:
        overall_pass = agg_pass and floor_pass
    return {
        "overall_pass": overall_pass,
        "aggregation": {"per_size": agg_per_size, "overall_pass": agg_pass},
        "floor": {"per_size": floor_per_size, "overall_pass": floor_pass,
                  "skipped_sizes": []},
    }


# --------------------------------------------------------------------------- #
# Hard gate dominates: a fully-passing candidate outranks any non-passing one.
# --------------------------------------------------------------------------- #

def test_passing_candidate_outranks_failing_even_with_lower_soft_scores():
    # passing but marginal: small positive W, passes all gates
    passing = _verdict({10: _agg_rec(W=1.0, median_PI=0.30)})
    # failing: huge W but a gate_B failure (worst_regression style) forces fail
    failing_rec = _agg_rec(W=14.0, median_PI=0.01)
    failing_rec["gate_B_pass"] = False
    failing = _verdict({10: failing_rec}, overall_pass=False)
    assert fitness(passing) > fitness(failing)


# --------------------------------------------------------------------------- #
# Feasibility is the dominant graded key (§6 item 5): a feasibility regression
# sinks a candidate below one with no regression, regardless of W.
# --------------------------------------------------------------------------- #

def test_feasibility_regression_dominates_huge_W():
    # candidate A: no feasibility regression, tiny W
    a = _verdict({10: _agg_rec(W=0.5, feasibility_regressed=False)})
    # candidate B: regresses feasibility on 2 instances, enormous W on the rest
    b = _verdict({10: _agg_rec(W=14.0, feasibility_regressed=True, lost=[(10, 3), (10, 7)])},
                 overall_pass=False)
    assert fitness(a) > fitness(b)


def test_fewer_lost_feasibility_ranks_higher():
    one = _verdict({10: _agg_rec(W=2.0, feasibility_regressed=True, lost=[(10, 1)])},
                   overall_pass=False)
    three = _verdict({10: _agg_rec(W=9.0, feasibility_regressed=True,
                                   lost=[(10, 1), (10, 2), (10, 3)])},
                     overall_pass=False)
    assert fitness(one) > fitness(three)


# --------------------------------------------------------------------------- #
# Within feasibility-equal candidates, higher W ranks higher; median PI breaks
# W ties (lower PI better).
# --------------------------------------------------------------------------- #

def test_higher_W_ranks_higher_when_feasibility_equal():
    lo = _verdict({10: _agg_rec(W=3.0, median_PI=0.2), 20: _agg_rec(W=3.0, median_PI=0.2)})
    hi = _verdict({10: _agg_rec(W=9.0, median_PI=0.2), 20: _agg_rec(W=9.0, median_PI=0.2)})
    assert fitness(hi) > fitness(lo)


def test_median_pi_breaks_W_ties():
    # identical W, different median PI: lower PI (better gap closure) wins
    worse = _verdict({10: _agg_rec(W=5.0, median_PI=0.40)})
    better = _verdict({10: _agg_rec(W=5.0, median_PI=0.10)})
    assert fitness(better) > fitness(worse)


def test_W_normalized_across_unequal_strata_sizes():
    # W must be normalized by stratum J (J*(J+1)/2) so a big-J stratum's larger
    # raw W range doesn't swamp a small-J stratum. W=10 over J=5 (norm 10/15) is
    # a STRONGER win than W=10 over J=10 (norm 10/55).
    small = _verdict({10: _agg_rec(W=10.0, J=5)})
    big = _verdict({10: _agg_rec(W=10.0, J=10)})
    assert fitness(small) > fitness(big)


# --------------------------------------------------------------------------- #
# Floor is below §6.6 in the lexicographic order but still a graded signal.
# --------------------------------------------------------------------------- #

def test_floor_below_pi_in_priority():
    # candidate with better §6.6 (W) but worse floor still wins over the reverse,
    # because §6.6 dominates the floor (NORTHSTAR §6: §6.6 ⊳ §8.3).
    strong_pi_weak_floor = _verdict(
        {10: _agg_rec(W=9.0)}, {10: _floor_rec(stratum_pass=False, frac=0.0)},
        overall_pass=False)
    weak_pi_strong_floor = _verdict(
        {10: _agg_rec(W=1.0)}, {10: _floor_rec(stratum_pass=True, frac=1.0)},
        overall_pass=False)
    assert fitness(strong_pi_weak_floor) > fitness(weak_pi_strong_floor)


def test_floor_breaks_pi_ties():
    base = _agg_rec(W=5.0, median_PI=0.2)
    good_floor = _verdict({10: dict(base)}, {10: _floor_rec(frac=1.0)})
    bad_floor = _verdict({10: dict(base)}, {10: _floor_rec(stratum_pass=False, frac=0.2)},
                         overall_pass=False)
    assert fitness(good_floor) > fitness(bad_floor)


# --------------------------------------------------------------------------- #
# Robustness: NaN/inf must not corrupt the sort (empty-J stratum -> median NaN).
# --------------------------------------------------------------------------- #

def test_nan_median_pi_does_not_break_sorting():
    # total feasibility collapse: J empty -> median_PI is NaN AND feasibility
    # regressed. The NaN must be sanitized so the fitness is still totally
    # ordered (NaN comparisons are False and would corrupt sorted()).
    collapsed = _verdict(
        {10: _agg_rec(W=0.0, median_PI=float("nan"), feasibility_regressed=True,
                      lost=[(10, i) for i in range(5)], J=0)},
        overall_pass=False)
    healthy = _verdict({10: _agg_rec(W=1.0, median_PI=0.3)})
    f_collapsed = fitness(collapsed)
    f_healthy = fitness(healthy)
    assert f_healthy > f_collapsed
    # sortable in a list without raising / mis-ordering
    ordered = sorted([f_collapsed, f_healthy])
    assert ordered == [f_collapsed, f_healthy]


def test_fitness_is_deterministic_and_total_order():
    v = _verdict({10: _agg_rec(W=4.0), 20: _agg_rec(W=6.0)})
    assert fitness(v) == fitness(v)           # pure
    assert not (fitness(v) < fitness(v))      # irreflexive
    # a population sorts best-last under plain sorted(), best-first under reverse
    pop = [_verdict({10: _agg_rec(W=w)}) for w in (1.0, 9.0, 5.0)]
    fits = [fitness(v) for v in pop]
    best = max(fits)
    assert best == fitness(pop[1])            # W=9 is best


def test_fitness_exposes_components_for_audit():
    # the population log needs to show WHY a candidate ranked where it did
    f = fitness(_verdict({10: _agg_rec(W=3.0, median_PI=0.25)}))
    assert f.passes_gate is True
    assert f.lost_feasibility_total == 0
    assert math.isfinite(f.pi_rank)
    assert math.isfinite(f.pi_median)
    assert math.isfinite(f.floor_fraction)
