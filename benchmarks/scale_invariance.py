"""Scale-invariance measurement core for the radius lever (bd 8an.1.7, M0g).

Shared by ``tests/test_scale_invariance.py`` (the CI gate) and
``benchmarks/scale_invariance_characterization.py`` (the full n∈{10,100,1000,3000}
sweep + variance characterization). Keeping the measurement in one place avoids a
second, drift-prone copy of the solve/aggregate logic (CLAUDE.md §2.7).

What it measures (NORTHSTAR §9). For a synthetic matched-tightness Eq.29 instance
solved in the exploratory ``opt`` phase, the C core now records per candidate the
realized Hamming radius (``NumChanges``) and the count of both-feasible "free"
decisions; ``Model.solve`` pools these across the decorrelated workers into
``result.branch_diagnostics``. From that we derive, per instance:

  * ``r_mean`` / ``r_var`` — the realized Hamming-radius distribution.
  * ``f`` — the free-decision fraction f(n) = free decisions / (candidates · n).

The realized radius ≈ f(n)·r, so f(n) drift *is* radius drift; both are checked.

Empirical regime (validated bd 8an.1.7): the radius lever is scale-stable for
n≥100 (f≈0.99, r_mean≈r across n=100/1000/3000); n=10 sits in the small-n
compression regime (f≈0.5, ~43% radius compression — squarely in NORTHSTAR §4's
predicted 38–56% band), used as a drift control rather than asserted invariant.
"""
import statistics

import numpy as np

from benchmarks.synthetic_eq29 import build_synthetic_model, make_matrices


def _per_worker_estimates(branch_diagnostics, n):
    """Per-worker (f, r_mean) estimates from a result's branch_diagnostics.

    Each decorrelated worker is an independent sample of the same instance, so
    its own counters give an independent f/r estimate. Workers that never
    entered the opt phase (0 candidates) are dropped."""
    out = []
    for w in branch_diagnostics["per_worker"]:
        c = w["opt_candidates"]
        if c <= 0:
            continue
        r_mean = w["opt_flip_sum"] / c
        r_var = max(0.0, w["opt_flip_sumsq"] / c - r_mean * r_mean)
        f = w["opt_free_sum"] / (c * n)
        out.append({"f": f, "r_mean": r_mean, "r_var": r_var, "candidates": c})
    return out


def radius_profile(n, index=0, seed=0, *, radius=None, bias=None,
                   num_workers=8, M=2500, opt_switch_oracles=0,
                   avg_degree=8, weight_low=1, weight_high=10):
    """Solve one synthetic matched-tightness Eq.29 instance and return its
    opt-phase radius/f(n) profile.

    Exactly one of ``radius`` (sets bias = n/r − 2, the scale-stable lever) or
    ``bias`` (raw scalar bias — the drift-prone lever, NORTHSTAR §1.5) is used.
    ``opt_switch_oracles=0`` enters the opt phase as soon as a feasible point
    exists, maximizing opt-phase candidate samples under the capped budget ``M``.
    """
    if (radius is None) == (bias is None):
        raise ValueError("pass exactly one of radius= or bias=")
    m = build_synthetic_model(n, index=index, avg_degree=avg_degree,
                              weight_low=weight_low, weight_high=weight_high)
    m.seed = seed
    m.set_param("num_workers", num_workers)
    m.set_param("opt_switch_oracles", opt_switch_oracles)
    m.set_param("M", M)
    if radius is not None:
        m.set_param("branching_radius", float(radius))
    else:
        m.set_param("branching_bias", float(bias))
    r = m.solve()
    bd = r.branch_diagnostics
    workers = _per_worker_estimates(bd, n)
    return {
        "n": n,
        "index": index,
        "seed": seed,
        "feasible": bool(r.feasible),
        "objective": r.objective,            # best-of-portfolio objective
        "final_incumbents": r.final_incumbents,  # per-worker (value, feasible)
        "oracle_calls": r.oracle_calls,
        "opt_candidates": bd["opt_candidates"],
        "f": bd["free_fraction"],
        "r_mean": bd["radius_mean"],
        "r_var": bd["radius_var"],
        "workers": workers,            # per-worker f / r_mean / r_var estimates
    }


def collect_profiles(ns, *, n_instances=3, seeds=(0,), radius=None, bias=None,
                     num_workers=8, M=2500, **kw):
    """Profile every (n, instance, seed) combination.

    Returns ``{n: [profile, ...]}``. Profiles with no opt-phase candidates
    (instance never reached opt — e.g. infeasible) are kept but flagged via
    ``opt_candidates == 0`` so callers can report rather than silently drop them
    (CLAUDE.md §5 "no silent caps").
    """
    out = {}
    for n in ns:
        profs = []
        for index in range(n_instances):
            for seed in seeds:
                profs.append(radius_profile(
                    n, index=index, seed=seed, radius=radius, bias=bias,
                    num_workers=num_workers, M=M, **kw))
        out[n] = profs
    return out


def _instance_values(profiles, key):
    """Median value of *key* per instance (pooled over that instance's workers
    when the key is a per-worker quantity, else the instance-level value)."""
    vals = []
    for p in profiles:
        if p["opt_candidates"] == 0:
            continue
        if key in ("f", "r_mean", "r_var") and p["workers"]:
            vals.append(statistics.median(w[key] for w in p["workers"]))
        elif p[key] is not None:
            vals.append(p[key])
    return vals


def rel_spread(values):
    """(max − min) / |mean| — a scale-free spread used as the indistinguishability
    band. Returns inf for an empty/degenerate set."""
    values = [v for v in values if v is not None]
    if not values:
        return float("inf")
    mean = sum(values) / len(values)
    if mean == 0:
        return float("inf")
    return (max(values) - min(values)) / abs(mean)


def cross_n_summary(profiles_by_n, key):
    """For each n, the median-over-instances of *key*; plus the cross-n rel_spread
    and a Kruskal–Wallis p-value over the per-instance values (p>alpha ⇒ the
    distributions are not distinguishable). Kruskal is informational — with few
    instances the rel_spread band is the robust gate."""
    from scipy.stats import kruskal
    per_n_medians = {}
    per_n_values = {}
    for n, profs in profiles_by_n.items():
        vals = _instance_values(profs, key)
        per_n_values[n] = vals
        per_n_medians[n] = statistics.median(vals) if vals else None
    spread = rel_spread(list(per_n_medians.values()))
    # Kruskal needs ≥2 groups each with data and some variability.
    groups = [v for v in per_n_values.values() if len(v) >= 1]
    pval = None
    if len(groups) >= 2 and all(len(g) >= 1 for g in groups):
        try:
            if any(len(set(g)) > 1 for g in groups):
                pval = float(kruskal(*groups).pvalue)
        except ValueError:
            pval = None
    return {"per_n_median": per_n_medians, "rel_spread": spread, "kruskal_p": pval}
