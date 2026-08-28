"""M3 candidate pre-scoring gate (bd 8an.4.2, NORTHSTAR §10).

Before a candidate schedule is *scored* (≈20 min–3.6 h per candidate over the
anchored strata), it must clear the §10 pre-scoring gate. This module composes
that gate into one :func:`admit` returning a :class:`GateResult`:

  (i)   **param / lever allow-list** (PURE) — the candidate may set ONLY faithful
        runtime levers (the 6 ORACLE-PRICED phase-aware suffixes × {unprefixed,
        sat_, opt_sat_, opt_} plus ``opt_switch_oracles``; the a0w
        ``angle_precision_*`` suffixes are phase-aware but priced on the T-count
        axis, so they are excluded — see ``_UNPRICED_AXIS_SUFFIXES``). Overriding the budget/cost/termination
        model (``M``, ``num_workers``, ``opt_sample_cap``, …) is a faithfulness
        breach: it would void the equal-``T(n)`` A/B price (NORTHSTAR §5/§1.6).
        For the parametric proposer the §1.4 feature allow-list also holds BY
        CONSTRUCTION (only whitelisted features get coefficients); enforcing
        feature provenance on *generated code* is the LLM-proposer's job (bd
        8an.4.7).
  (iii) **scale-invariance end-to-end** (SOLVE) — the candidate's realized
        opt-phase Hamming-radius distribution and free-decision fraction f(n)
        must be indistinguishable across the scale-stable sizes (NORTHSTAR §9).
        Anti-vacuous: a candidate that drives instances infeasible yields no opt
        profiles and must FAIL on coverage, never "pass by absence of data".
  (iv)  **θ radius-neutrality / lever fidelity** (PURE over the same summary) —
        the realized opt radius must match the candidate's TARGET radius at every
        scale-stable n; a per-variable θ that silently shifts the radius
        (M0f coupling) is caught here, reusing the data already collected.

The value-clamp gate (§10) holds structurally in C (``Branching.h`` ``branch_clamp``
/ ``BRANCH_EPS`` for any θ, unit-tested in ``test_branching.c``) — no per-candidate
Python check is needed. The largest-n strict gate stays dormant until bd 0o8
freezes the n≥500 anchors (scored, not gated here).

Decision logic is pure over resolved params / a summary dict, so it is fully
unit-tested without the C extension; only :func:`scale_invariance_summary`
solves.
"""
import math

#: Mirror of ``cbqs.phase_params.DEFAULTS`` for the flat-layout fallback below.
#: ``tests/test_candidate_gate.py`` pins the two in sync — if they drift, a flat
#: import silently computes a DIFFERENT legal lever surface than a package one.
_FALLBACK_DEFAULTS = {
    "branching_weights": None, "branching_factor": 1.0, "bias_factor": 1.0,
    "branching_bias": 5.0, "branching_radius": None, "variable_priorities": None,
    "angle_precision_eps": None, "angle_precision_dither": False,
}

try:  # package import (pytest / installed) vs flat script import
    from cbqs.phase_params import PHASES, DEFAULTS
except ImportError:  # pragma: no cover - flat layout fallback
    PHASES = ("sat", "opt_sat", "opt")
    DEFAULTS = dict(_FALLBACK_DEFAULTS)


# --------------------------------------------------------------------------- #
# (i) Legal lever surface (NORTHSTAR §1.6/§5) — the COMPLETE set a candidate may
# set, derived from the phase-aware suffixes (cbqs/phase_params.py DEFAULTS) so
# it cannot drift from the C param surface.
#
# TRAPDOOR (bd a0w): deriving the surface from DEFAULTS means every NEW phase
# suffix becomes candidate-settable by default. That is right for levers priced
# by the equal-T(n) ORACLE A/B, and WRONG for anything that moves cost on a
# different axis. Such suffixes are subtracted here and listed in
# _FAITHFULNESS_BREACH_PARAMS instead.
# --------------------------------------------------------------------------- #

#: Phase suffixes that exist on the Model but are NOT candidate-settable levers.
#: ``angle_precision_{eps,dither}`` (bd a0w) sets the Ross-Selinger synthesis
#: accuracy of the QTG's R_y rotations: coarser angles buy a cheaper circuit on
#: the **T-count-per-oracle** axis, which the equal-``T(n)`` oracle A/B does not
#: price. Letting a tuned candidate set it would buy objective with unpriced
#: circuit cost — the "no free relabel" breach NORTHSTAR §1.1 forbids. It is a
#: HARNESS/run-level knob (like ``M`` and ``opt_sample_cap``), swept on its own
#: axis by ``benchmarks/run_a0w_precision_probe.py``.
_UNPRICED_AXIS_SUFFIXES = frozenset({"angle_precision_eps", "angle_precision_dither"})

_LEVER_SUFFIXES = frozenset(DEFAULTS) - _UNPRICED_AXIS_SUFFIXES  # the 6 phase-aware levers

#: Every legal candidate-settable param: each lever unprefixed + per phase, plus
#: the global exploit→explore switch point (a bounded oracle count, §4).
LEGAL_LEVER_PARAMS = frozenset(
    list(_LEVER_SUFFIXES)
    + [f"{phase}_{suffix}" for phase in PHASES for suffix in _LEVER_SUFFIXES]
    + ["opt_switch_oracles"]
)

#: Params that exist on the Model but are a FAITHFULNESS BREACH for a candidate
#: to set — overriding the budget/cost/termination model would void the equal-
#: ``T(n)`` A/B price (NORTHSTAR §5) or change the cost model the metric assumes.
#: ``look_ahead_factor`` is dead (diffcount=0 zeroes it) — not a faithful lever.
_FAITHFULNESS_BREACH_PARAMS = frozenset({
    "M", "num_workers", "opt_sample_cap", "stop_val", "stopping_time",
    "stopping_condition", "timeout", "depth_look_ahead",
    "ignore_constraint_search", "monte_carlo_estimate", "max_delta",
    "reset_delta", "max_worse_acceptances", "distance", "look_ahead_factor",
} | _UNPRICED_AXIS_SUFFIXES
  | {f"{phase}_{suffix}" for phase in PHASES for suffix in _UNPRICED_AXIS_SUFFIXES})

# --------------------------------------------------------------------------- #
# Scale-invariance indistinguishability bands (calibrated bd 8an.1.7, reused
# from tests/test_scale_invariance.py). The positive control sits at ~0.03;
# these bands separate stable from drifting by >3×.
# --------------------------------------------------------------------------- #
TOL_RMEAN = 0.10          #: cross-n rel_spread of realized opt radius mean
TOL_F = 0.10              #: cross-n rel_spread of free-decision fraction f(n)
MIN_COVERAGE = 0.5        #: min fraction of profiles that must reach the opt phase
RADIUS_FIDELITY_BAND = 0.20   #: |realized − target| / target at a scale-stable n


class GateResult:
    """Outcome of :func:`admit`. ``ok`` iff no check produced a reason.

    ``reasons`` is a flat list of human-readable failures (prefixed by the check
    that raised them); ``params`` is the resolved candidate param dict at the
    sample size; ``scale_summary`` is the (possibly injected) scale-invariance
    summary, kept for the §13 audit log.
    """

    __slots__ = ("ok", "reasons", "params", "scale_summary")

    def __init__(self, ok, reasons, params=None, scale_summary=None):
        self.ok = bool(ok)
        self.reasons = list(reasons)
        self.params = params
        self.scale_summary = scale_summary

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return (f"GateResult(ok={self.ok}, reasons={self.reasons!r})")


# --------------------------------------------------------------------------- #
# (i) param / lever allow-list — pure
# --------------------------------------------------------------------------- #

def check_param_allowlist(params):
    """Reject a candidate whose resolved params set anything but a faithful lever.

    Returns ``(ok, reasons)``. A budget/cost/termination override is reported as
    a named faithfulness breach (NORTHSTAR §5); any other illegal key as
    not-a-runtime-lever (§1.6).
    """
    reasons = []
    for key in sorted(set(params) - LEGAL_LEVER_PARAMS):
        if any(key.endswith(suffix) for suffix in _UNPRICED_AXIS_SUFFIXES):
            reasons.append(
                f"{key!r}: the angle-precision lever moves cost on the "
                f"Ross-Selinger T-count-per-oracle axis, which the equal-T(n) "
                f"ORACLE A/B does not price (NORTHSTAR §1.1/§5) — it is a "
                f"harness-level knob, not a candidate lever")
        elif key in _FAITHFULNESS_BREACH_PARAMS:
            reasons.append(
                f"{key!r}: overriding the budget/cost/termination model breaks "
                f"equal-T(n) faithfulness (NORTHSTAR §5) — a candidate may set "
                f"only runtime levers")
        else:
            reasons.append(
                f"{key!r}: not a legal runtime lever (NORTHSTAR §1.6/§5; legal = "
                f"the 6 phase-aware levers {sorted(_LEVER_SUFFIXES)} unprefixed "
                f"or per-phase, plus 'opt_switch_oracles')")
    return (not reasons, reasons)


# --------------------------------------------------------------------------- #
# (iii) scale-invariance — pure decision over a summary
# --------------------------------------------------------------------------- #

def check_scale_invariance(summary, *, tol_rmean=TOL_RMEAN, tol_f=TOL_F,
                           min_coverage=MIN_COVERAGE):
    """Pass iff the realized opt radius and f(n) are indistinguishable across n
    AND feasibility coverage is high enough to make that measurement meaningful.

    ``summary`` is the dict from :func:`scale_invariance_summary` (or a stub):
    ``{"r_mean": {"rel_spread": float, ...}, "f": {"rel_spread": float, ...},
    "coverage": {n: fraction}}``. The coverage guard is the anti-vacuous defense
    (landmine #12): without it, a candidate that makes most instances infeasible
    yields a near-empty profile set whose rel_spread reads clean.
    """
    reasons = []
    coverage = summary.get("coverage", {})
    low = {n: round(c, 3) for n, c in coverage.items() if c < min_coverage}
    if low:
        reasons.append(
            f"feasibility coverage below {min_coverage} at {low} — too few "
            f"opt-phase profiles to measure scale-invariance (anti-vacuous; "
            f"a candidate that drives instances infeasible must FAIL, not pass "
            f"by absence of data)")
    r_spread = summary.get("r_mean", {}).get("rel_spread", float("inf"))
    if not math.isfinite(r_spread) or r_spread > tol_rmean:
        reasons.append(
            f"realized opt-radius rel_spread {r_spread} > {tol_rmean} across n "
            f"(radius distribution drifts with size — NORTHSTAR §9)")
    f_spread = summary.get("f", {}).get("rel_spread", float("inf"))
    if not math.isfinite(f_spread) or f_spread > tol_f:
        reasons.append(
            f"free-fraction f(n) rel_spread {f_spread} > {tol_f} across n "
            f"(f(n) drift is a §9 rejection criterion)")
    return (not reasons, reasons)


# --------------------------------------------------------------------------- #
# (iv) θ radius-neutrality / lever fidelity — pure decision over the same summary
# --------------------------------------------------------------------------- #

def check_radius_realization(summary, target_by_n, *, band=RADIUS_FIDELITY_BAND):
    """Pass iff realized opt radius ≈ the candidate's target radius at each
    scale-stable n.

    ``target_by_n`` maps n → the radius the candidate's scalar setting predicts
    (empty / missing entries skip that n — e.g. the candidate left the opt radius
    at the default). A per-variable θ that shifts the realized radius away from
    the set radius (the M0f coupling failure) is caught here, reusing the
    ``per_n_median`` realized radii already collected — no extra solves.
    """
    if not target_by_n:
        return (True, [])
    reasons = []
    realized = summary.get("r_mean", {}).get("per_n_median", {})
    for n, target in target_by_n.items():
        r = realized.get(n)
        if r is None or target in (None, 0):
            continue
        rel = abs(r - target) / abs(target)
        if rel > band:
            reasons.append(
                f"n={n}: realized opt radius {r:.3f} vs target {target:.3f} "
                f"(|Δ|/target {rel:.3f} > {band}) — the radius lever is not "
                f"faithful (θ radius-coupling or a bias/radius mismatch)")
    return (not reasons, reasons)


# --------------------------------------------------------------------------- #
# Solve-based summary producer
# --------------------------------------------------------------------------- #

def _resolve_candidate(candidate, n, index):
    """Resolve a candidate factory to concrete params on a synthetic instance."""
    try:
        from benchmarks.m2 import resolve_params
        from benchmarks.synthetic_eq29 import make_matrices
    except ImportError:  # pragma: no cover - flat layout fallback
        from m2 import resolve_params  # type: ignore
        from synthetic_eq29 import make_matrices  # type: ignore
    c1, c2, c3 = make_matrices(n, index)
    return resolve_params(candidate, n, c1, c2, c3)


def _opt_target_radius(params, n):
    """The opt-phase target radius implied by a resolved param dict (or None).

    Resolution mirrors the C phase fallback (phase-specific > unprefixed): an
    explicit ``opt_branching_radius`` / ``branching_radius`` wins; else an opt /
    unprefixed ``branching_bias`` converts via r = n/(bias+2); else None (the
    candidate left the opt radius at the close() default — fidelity unchecked).
    """
    for key in ("opt_branching_radius", "branching_radius"):
        if params.get(key) is not None:
            return float(params[key])
    for key in ("opt_branching_bias", "branching_bias"):
        if params.get(key) is not None:
            bias = float(params[key])
            return n / (bias + 2.0) if (bias + 2.0) != 0 else None
    return None


def scale_invariance_summary(candidate, ns=(100, 1000), *, n_instances=3,
                             seeds=(0,), num_workers=8, M=2500, **profile_kw):
    """Solve synthetic matched-tightness instances under the candidate across
    ``ns`` and summarize cross-n radius / f(n) spread + feasibility coverage.

    Returns ``{"r_mean": cross_n_summary, "f": cross_n_summary,
    "coverage": {n: fraction reaching opt}, "target_by_n": {n: radius},
    "profiles_by_n": {...}}``. Solve-heavy (needs the C extension); the pure
    decision functions above consume only the summary.
    """
    try:
        from benchmarks.scale_invariance import radius_profile, cross_n_summary
    except ImportError:  # pragma: no cover - flat layout fallback
        from scale_invariance import radius_profile, cross_n_summary  # type: ignore
    profiles_by_n = {}
    target_by_n = {}
    for n in ns:
        profs = []
        for index in range(n_instances):
            params = _resolve_candidate(candidate, n, index)
            if index == 0:
                t = _opt_target_radius(params, n)
                if t is not None:
                    target_by_n[n] = t
            for seed in seeds:
                profs.append(radius_profile(
                    n, index=index, seed=seed, params=params,
                    num_workers=num_workers, M=M, **profile_kw))
        profiles_by_n[n] = profs
    coverage = {n: (sum(1 for p in profs if p["opt_candidates"] > 0) / len(profs)
                    if profs else 0.0)
                for n, profs in profiles_by_n.items()}
    return {
        "r_mean": cross_n_summary(profiles_by_n, "r_mean"),
        "f": cross_n_summary(profiles_by_n, "f"),
        "coverage": coverage,
        "target_by_n": target_by_n,
        "profiles_by_n": profiles_by_n,
    }


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #

def admit(candidate, *, sample_n=100, scale_ns=(100, 1000), scale_check=True,
          scale_summary=None, **scale_kw):
    """The composed NORTHSTAR §10 pre-scoring gate.

    Always runs the pure param/lever allow-list (resolving the candidate at
    ``sample_n``). When ``scale_check`` (and unless a ``scale_summary`` is
    injected), solves the scale-invariance summary over ``scale_ns`` and runs the
    cross-n indistinguishability + radius-fidelity (θ-neutrality) checks.
    ``scale_check=False`` or an injected ``scale_summary`` keeps :func:`admit`
    solve-free for unit tests and for a cheap param-only pre-filter.
    """
    reasons = []
    params = _resolve_candidate(candidate, sample_n, 0)
    ok_p, why_p = check_param_allowlist(params)
    reasons += [f"[param-allowlist] {r}" for r in why_p]

    if scale_check or scale_summary is not None:
        if scale_summary is None:
            scale_summary = scale_invariance_summary(candidate, scale_ns, **scale_kw)
        ok_s, why_s = check_scale_invariance(scale_summary)
        reasons += [f"[scale-invariance] {r}" for r in why_s]
        target_by_n = scale_summary.get("target_by_n") or {
            n: _opt_target_radius(_resolve_candidate(candidate, n, 0), n)
            for n in scale_ns}
        target_by_n = {n: t for n, t in target_by_n.items() if t is not None}
        ok_r, why_r = check_radius_realization(scale_summary, target_by_n)
        reasons += [f"[radius-fidelity] {r}" for r in why_r]

    return GateResult(ok=not reasons, reasons=reasons, params=params,
                      scale_summary=scale_summary)
