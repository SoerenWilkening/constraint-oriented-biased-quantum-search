"""M1 primal-integral fitness metric for the Eq.29 benchmark (bd 8an.2, NORTHSTAR §6).

The single fitness number CBQS schedules are scored on. Anytime-quality, tail-aware,
frontier-relative — a hardened primal-gap integral (NORTHSTAR §6, items 1-6). "The oracle
count is the product": this metric turns an oracle-indexed best-of-portfolio trajectory into
a comparable score, so the integral and sign conventions here are load-bearing.

Per instance ``I`` (NORTHSTAR §6):

    γ(t) = clamp( (B_I − best(t)) / D_I , −γmax, 1 )          # bounded signed gap (item 3)
    PI_I = (1/T_I) ∫₀^{T_I} γ(t) dt                          # primal integral (item 4); lower = better

where ``best(t)`` is the oracle-indexed, best-of-portfolio running-max objective trajectory
(``result.history`` — already merged feasible-only in Model.pyx:828-842), ``B_I`` is the
non-CBQS frontier objective, ``L_I`` is the CBQS-default median first-feasible objective, and
``D_I = max(B_I − L_I, ε·|B_I|)`` (item 1). ``PI_I = +∞`` on never-feasible instances (item 5).

The Eq.29 objective is MAXIMIZE, so ``best(t)`` and the anchors live in the user-facing objective
space (``global_opt.tot_profit · sense``; Model.pyx:1112/1127): higher = better, and
``best > B_I`` (over-frontier) earns a capped-negative γ.

Aggregation across instances (NORTHSTAR §6 item 5/6, §8 item 3, §13): a feasibility-tier
lexicographic comparison, a stratified signed-rank delta vs. the default schedule with a
per-``n`` noise margin, a largest-``n`` strict-improvement gate, and the §8.3 late-stage
exploration-diversity floor. Free parameters NORTHSTAR leaves unpinned are surfaced as the
named constants below (calibrated in M1, NORTHSTAR §6 item 6 / §8 item 3).

Anchors are CONSUMED from the frozen table (:func:`benchmarks.baselines.load_frozen_baselines`),
never produced here. ``L_I`` / ``default_PI`` load as ``None`` until the CBQS-default seed-bank
runs land (bd 8an.1.16); ``0.0`` is a *real* objective/PI, so a ``None`` anchor MUST fail loud,
never collapse to 0 (CLAUDE.md §2.1/§8).
"""
import math
import statistics

try:  # mirror baselines.py's dual-import idiom (works flat and as a package)
    from baselines import load_frozen_baselines  # noqa: F401  (re-exported for callers)
except ImportError:  # pragma: no cover - exercised via package import
    from benchmarks.baselines import load_frozen_baselines  # noqa: F401


# --------------------------------------------------------------------------- #
# Constants — every NORTHSTAR-unpinned tunable is a named module constant.
# --------------------------------------------------------------------------- #

#: Asymmetric clamp on the signed gap: upper bound is exactly 1, lower bound is −GAMMA_MAX.
#: NORTHSTAR §6 item 3 pins this only to one sig-fig ("γmax ≈ 0.5"); 0.5 is the default.
#: The cap stops one small-D_I over-frontier instance from dominating the aggregate.
GAMMA_MAX = 0.5

#: Division-by-zero guard in D_I = max(B_I − L_I, PI_EPS·|B_I|). NORTHSTAR §6 item 1 writes
#: "ε·scale" with no numeric ε; we take scale = |B_I| (frontier magnitude). This is a guard
#: ONLY — L_I >= B_I instances are already dropped (item 1), so the floor activates solely on
#: floating-point near-ties just above zero. On real Eq.29 (objectives ~5e6) the floor is ~5e-3,
#: negligible vs any genuine B_I − L_I (asserted in tests; CLAUDE.md §1.5 anti-silent-rescale).
PI_EPS = 1e-9

#: §8.3 floor NOISE BAND = EXPLORE_FLOOR_FRACTION · per-n default objective-space spread.
#: AMENDED (M2g, bd 8an.3.8): the floor is now TAIL-QUALITY — per instance, seed-matched, the
#: candidate's final best-of-P may not regress vs the DEFAULT's final best-of-P by more than this
#: band (mirrors the §6.6 gate-B margin semantics, in objective space). The old spread-based
#: best−median lift floor read "every worker improved" as greedy collapse (vetoing dominant
#: candidates) while PASSING the §1.3 negative control radius_uniform2 at n=40..90 where its
#: final tail regressed up to 2.5× the default spread — and was gameable by sandbagging one
#: worker. The neutral-reference sanity (default passes its own floor) is STRUCTURAL under the
#: tail definition (Δ ≡ 0 at any fraction), so this constant tunes noise tolerance only.
#: 0.25 retained from the M1 calibration scale (benchmarks/floor_calibration.csv documents the
#: default's lift/spread landscape; it no longer pins admissibility).
EXPLORE_FLOOR_FRACTION = 0.25

#: §6 item 6 noise margin: a "win" requires beating default PI by more than NOISE_MARGIN_K times
#: the per-n default spread. Multiplier unpinned by NORTHSTAR (calibrated in M1).
NOISE_MARGIN_K = 1.0

#: §6 item 6 / §8 item 3 spread statistic. IQR (robust to the heavy restart tail that best-of-P
#: harvests — std would be inflated by exactly that tail). NORTHSTAR says "measured spread" only.
SPREAD_STAT = "IQR"

#: §6 item 6 / §9 / M4: the largest-n stratum carries a hard STRICT-improvement gate.
LARGEST_N = 3000

#: Relative tolerance for the §6 item 6 deadband boundary and rank-tie grouping. PI deltas are
#: FP subtractions, so a delta whose TRUE magnitude equals the margin m (or two truly-equal
#: magnitudes) can flip across the boundary by ~1e-16; snap the boundary to a tie within REL_TOL
#: so "|δ| <= m → tie" (NORTHSTAR §6 item 6) is honored exactly. Negligible vs real Eq.29 deltas.
REL_TOL = 1e-9

#: §8 item 3 end-to-end floor (bd 8an.2.1, amended bd 8an.3.8): per stratum, the FRACTION of
#: evaluable instances whose median-over-seed tail delta (candidate best-of-P − default best-of-P)
#: must stay within the noise band for the stratum to pass. NORTHSTAR leaves it unpinned
#: (calibrated in M1, like EXPLORE_FLOOR_FRACTION / NOISE_MARGIN_K). Default 1.0 = the
#: conservative reading (no scored instance may regress its harvested tail beyond noise);
#: surfaced as a ``score_verdict`` kwarg so the M-level sweeps can relax it deliberately.
FLOOR_INSTANCE_FRACTION = 1.0

#: Relative tolerance for the ``score_verdict`` cross-check of the supplied default run-set's
#: re-scored PI against the FROZEN ``default_PI`` column (bd 8an.2.1, Q2). Looser than REL_TOL:
#: cross-machine FP and a different worker count move PI more than a subtraction residual, but a
#: stale freeze or an outright-wrong default run-set drifts further than this. Recorded by default;
#: ``strict_xcheck=True`` turns a breach into a raise.
XCHECK_REL_TOL = 1e-3


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #

def oracle_budget(n):
    """T(n) = (n/4)**2 + 1200 — the per-worker oracle budget T_I (NORTHSTAR §3/§11).

    Float division to byte-match Model.pyx:778 ``int((self.n / 4.0) ** 2 + 1200)``; integer
    ``//`` would diverge for ``n`` not divisible by 4.

    n : int  ->  int
    """
    return int((n / 4.0) ** 2 + 1200)


def require_anchor(value, name, key):
    """Return *value* as a float, or RAISE if it is ``None`` (NORTHSTAR §6 / CLAUDE.md §2.1/§8).

    The frozen table loads L_I / default_PI (and possibly B_I) as ``None`` until the CBQS-default
    seed-bank runs land (bd 8an.1.16). ``0.0`` is a *real* objective/PI, so ``None`` must never be
    coerced to 0 — fail loud. The batch driver (:func:`score_run_set`) catches the missing-anchor
    case as a recorded *skip*; the math functions here treat a ``None`` anchor as a caller bug.

    value : float|None ; name : str ; key : hashable  ->  float
    """
    if value is None:
        raise ValueError(
            f"{name} is None for {key}: anchor not yet frozen (e.g. CBQS-default seed-bank, "
            f"bd 8an.1.16). 0.0 is a real value — None must not be coerced to 0 (CLAUDE.md §2.1)."
        )
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(
            f"{name}={value!r} for {key} is non-finite; an anchor must be a real objective/PI. "
            f"NaN/inf is corrupt input — fail loud, never score it (CLAUDE.md §2.1; cf. the "
            f"non-finite drops in baselines.py:123/137)."
        )
    return v


def d_i(B_I, L_I):
    """Denominator D_I = max(B_I − L_I, PI_EPS·|B_I|) (NORTHSTAR §6 item 1).

    Caller must already have applied the drop rule (L_I >= B_I instances are non-discriminating
    and not scored). Raises ValueError on a None anchor or L_I >= B_I (a caller bug at this layer).

    B_I, L_I : float  ->  float (> 0)
    """
    B_I = require_anchor(B_I, "B_I", "d_i")
    L_I = require_anchor(L_I, "L_I", "d_i")
    if L_I >= B_I:
        raise ValueError(
            f"L_I ({L_I}) >= B_I ({B_I}): default meets/beats the frontier — instance is "
            f"non-discriminating and must be DROPPED, not scored (NORTHSTAR §6 item 1)."
        )
    return max(B_I - L_I, PI_EPS * abs(B_I))


def gamma(best, B_I, D_I):
    """Bounded signed primal gap γ = clamp((B_I − best)/D_I, −GAMMA_MAX, 1) (NORTHSTAR §6 item 3).

    1 at/below the L_I anchor, 0 at the frontier (best == B_I), negative (floored at −GAMMA_MAX)
    over-frontier (best > B_I). Caller guarantees D_I > 0 (use :func:`d_i`).

    best, B_I, D_I : float  ->  float in [−GAMMA_MAX, 1]
    """
    if D_I <= 0:
        raise ValueError(f"D_I must be > 0 (got {D_I}); use d_i() which floors it.")
    raw = (B_I - best) / D_I
    if not math.isfinite(raw):
        # max/min would silently keep the first arg on a NaN compare (min(1.0, nan) -> 1.0),
        # laundering a corrupt incumbent/anchor into a plausible finite γ. Fail loud instead.
        raise ValueError(
            f"γ gap is non-finite (best={best}, B_I={B_I}, D_I={D_I}); a NaN/inf incumbent or "
            f"anchor must fail loud, not be clamped to a finite value (CLAUDE.md §2.1)."
        )
    return max(-GAMMA_MAX, min(1.0, raw))


# --------------------------------------------------------------------------- #
# Per-instance primal integral — the core
# --------------------------------------------------------------------------- #

def compute_primal_integral(history, B_I, L_I, T_I):
    """PI_I = (1/T_I) ∫₀^{T_I} γ(t) dt over the step trajectory best(t) (NORTHSTAR §6 item 4).

    Lower = better; PI_I < 0 ⇔ best-of-portfolio beat the frontier; PI_I == 0 ⇔ best ≡ B_I over
    the whole budget; PI_I == 1 ⇔ never improved past the L_I anchor. Returns ``float('inf')``
    iff *history* is empty (never feasible — NORTHSTAR §6 item 5 sentinel).

    best(t) is the right-continuous step function:
        [0, t_1)        γ = 1                 # pre-first-feasible (no feasible incumbent yet)
        [t_k, t_{k+1})  γ = γ(v_k)            # interior steps
        [t_m, T_I]      γ = γ(v_m)            # tail: last incumbent held to budget end

    history : list[(value:float, oracle:int)]  — result.history; best-of-portfolio running-max,
              ascending oracle stamps, FEASIBLE-only (Model.pyx:828-842, SearchLib.c:213).
    B_I, L_I : float (anchors) ; T_I : int (> 0, per-worker budget).

    Raises ValueError on: None B_I/L_I; T_I <= 0; L_I >= B_I (drop rule — should not be scored);
    a negative or non-ascending oracle stamp. Oracle stamps > T_I are CLIPPED to T_I (the integral
    domain is [0, T_I]; an overshoot of one Grover round is expected, SearchLib.c:159→:173).
    """
    B_I = require_anchor(B_I, "B_I", "compute_primal_integral")
    L_I = require_anchor(L_I, "L_I", "compute_primal_integral")
    if not (isinstance(T_I, (int, float)) and T_I > 0):
        raise ValueError(f"T_I must be a positive budget (got {T_I!r}).")
    if L_I >= B_I:
        raise ValueError(
            f"L_I ({L_I}) >= B_I ({B_I}): non-discriminating instance must be DROPPED, not scored "
            f"(NORTHSTAR §6 item 1)."
        )
    if not history:
        return float("inf")  # never feasible → +∞ sentinel (NORTHSTAR §6 item 5)

    oracles = [int(o) for (_v, o) in history]
    values = [float(v) for (v, _o) in history]
    prev_o = None
    prev_v = None
    for v, o in zip(values, oracles):
        if o < 0:
            raise ValueError(f"oracle stamp {o} < 0 — ctx->oracle_count is unsigned (corrupt input).")
        if prev_o is not None and o < prev_o:
            raise ValueError(
                f"oracle stamps not ascending ({prev_o} then {o}); result.history is sorted by "
                f"construction (Model.pyx:832) — a violation means corrupt input (CLAUDE.md §1.2)."
            )
        if not math.isfinite(v):
            raise ValueError(f"history value {v} is non-finite (corrupt incumbent) — fail loud (§2.1).")
        if prev_v is not None and v < prev_v:
            # best(t) is the MAXIMIZE best-of-portfolio running-MAX (Model.pyx:837-842): values are
            # non-decreasing by construction. Guard it symmetrically with the ascending-stamp check
            # so a broken merge / non-harness caller fails loud, not produces a plausible-wrong PI.
            raise ValueError(
                f"history values not non-decreasing ({prev_v} then {v}); best(t) must be the "
                f"running-max objective trajectory (Model.pyx:837-842) — a regression means a "
                f"broken merge or non-MAXIMIZE input (CLAUDE.md §1.2/§2.1)."
            )
        prev_o = o
        prev_v = v

    D = d_i(B_I, L_I)

    def clip(t):
        return T_I if t > T_I else t

    area = 0.0
    # 1. pre-first-feasible plateau [0, t_1): γ = 1 (best ≤ L_I ⇒ raw ≥ 1 ⇒ clamp 1).
    area += 1.0 * (clip(oracles[0]) - 0.0)
    # 2. interior steps [t_k, t_{k+1}): best = v_k.
    for k in range(len(history) - 1):
        width = clip(oracles[k + 1]) - clip(oracles[k])
        if width > 0:  # zero on duplicate stamps or fully past T_I
            area += gamma(values[k], B_I, D) * width
    # 3. tail [t_m, T_I]: last incumbent held to budget end ("tail harvested", item 4).
    tail_width = T_I - clip(oracles[-1])
    if tail_width > 0:
        area += gamma(values[-1], B_I, D) * tail_width

    return area / T_I


# --------------------------------------------------------------------------- #
# Per-instance wrappers
# --------------------------------------------------------------------------- #

def instance_feasible(result):
    """True iff the run reached ANY feasible incumbent within budget (NORTHSTAR §6 item 5).

    ``bool(result.history)`` — history is feasible-only (SearchLib.c:213), so a non-empty history
    ⇔ a feasible incumbent existed. Falls back to ``result.final_incumbents`` when history is empty
    but per-worker incumbents are present.
    """
    if getattr(result, "history", None):
        return True
    return any(ok for (_v, ok) in (getattr(result, "final_incumbents", None) or []))


def score_instance(result, n, B_I, L_I, *, T_I=None):
    """PI_I + diagnostics for one Eq.29 run. T_I defaults to oracle_budget(n).

    result : OptimizeResult-like (reads .history) ; n : int ; B_I, L_I : float.
    Returns {"n","T_I","B_I","L_I","D_I","best","PI","feasible"} —
    PI == +∞ and feasible == False on never-feasible; best == history[-1][0] (None if empty).
    Raises (require_anchor) on a None anchor.
    """
    B_I = require_anchor(B_I, "B_I", (n,))
    L_I = require_anchor(L_I, "L_I", (n,))
    if T_I is None:
        T_I = oracle_budget(n)
    history = list(getattr(result, "history", []) or [])
    pi = compute_primal_integral(history, B_I, L_I, T_I)
    return {
        "n": n,
        "T_I": T_I,
        "B_I": B_I,
        "L_I": L_I,
        "D_I": d_i(B_I, L_I),
        "best": history[-1][0] if history else None,
        "PI": pi,
        "feasible": bool(history),
    }


# --------------------------------------------------------------------------- #
# §8 item 3 — late-stage exploration-diversity floor
# --------------------------------------------------------------------------- #

def exploration_floor(final_incumbents, spread_default, fraction=EXPLORE_FLOOR_FRACTION):
    """Per-portfolio DIVERSITY DIAGNOSTIC: best-of-P − median-of-P vs a fraction of the default spread.

    AMENDED (bd 8an.3.8): this spread-lift quantity is NO LONGER the §8 item 3 verdict gate — the
    verdict floor is the seed-matched TAIL-QUALITY comparison (:func:`tail_floor_delta` aggregated
    by :func:`_aggregate_floor`). Retained as the diversity diagnostic behind ``calibrate-floor``
    (benchmarks/floor_calibration.csv): the lift documents how much within-portfolio outcome
    diversity the default exhibits per n, which sets the scale of the tail floor's noise band.

    PASS iff ``best_of_P − median_of_P > fraction · spread_default`` over the FEASIBLE per-worker
    final incumbents (objective space, MAXIMIZE so higher = better).

    final_incumbents : list[(value:float, feasible:bool)]  (result.final_incumbents)
    spread_default   : float  (default schedule's per-n spread; :func:`spread`)
    Returns {"pass","best_of_P","median_of_P","lift","threshold","n_feasible"}.
    Raises ValueError if spread_default is None (spread not yet frozen — must not silently pass).
    """
    if spread_default is None:
        raise ValueError("spread_default is None: default spread not frozen — gate cannot pass silently.")
    feas = [float(v) for (v, ok) in final_incumbents if ok]
    threshold = fraction * spread_default
    if not feas:
        return {"pass": False, "best_of_P": None, "median_of_P": None,
                "lift": None, "threshold": threshold, "n_feasible": 0}
    best = max(feas)
    med = statistics.median(feas)
    lift = best - med
    return {"pass": lift > threshold, "best_of_P": best, "median_of_P": med,
            "lift": lift, "threshold": threshold, "n_feasible": len(feas)}


def tail_floor_delta(candidate_incumbents, default_incumbents):
    """§8 item 3 (amended, bd 8an.3.8) per-solve TAIL delta: candidate best-of-P − default best-of-P.

    Computed over the FEASIBLE per-worker final incumbents of one seed-matched solve pair
    (objective space, MAXIMIZE so higher = better). This is the quantity §1.3 actually protects —
    the harvested restart tail — measured directly instead of via the (gameable, both-ways-wrong)
    best−median spread proxy: a candidate that uniformly lifts every worker keeps Δ ≥ 0 and
    passes; a candidate whose portfolio retains spread but loses the tail goes Δ < 0 and fails.

    Returns:
      float  — best_c − best_d when both sides have a feasible final;
      -inf   — the default has a feasible final but the candidate has NONE (total tail collapse;
               the feasibility tier §6 item 5 also fires, but the floor must not read this as
               "no data");
      None   — the DEFAULT side has no feasible final: no reference to compare against (the
               caller skips this seed; instance-level feasibility quality is the §6 tier's job).
    """
    feas_d = [float(v) for (v, ok) in default_incumbents if ok]
    if not feas_d:
        return None
    feas_c = [float(v) for (v, ok) in candidate_incumbents if ok]
    if not feas_c:
        return float("-inf")
    return max(feas_c) - max(feas_d)


def spread(values, stat=SPREAD_STAT):
    """Per-n dispersion of a value population (NORTHSTAR §6 item 6 / §8 item 3 "measured spread").

    IQR (default) is robust to the best-of-portfolio restart tail; "std" available for comparison.
    Returns 0.0 for fewer than 2 points (no measurable spread).

    values : iterable[float] ; stat : "IQR" | "std"  ->  float (>= 0)
    """
    vals = sorted(float(v) for v in values)
    if not all(math.isfinite(v) for v in vals):
        # A +∞ never-feasible PI (or any NaN/inf) in the population would yield a non-finite spread,
        # which becomes a noise margin that silently neutralizes the §6/§8 gates. The caller must
        # exclude non-finite values; fail loud if one slips through (CLAUDE.md §2.1).
        raise ValueError("spread() population contains a non-finite value — exclude it before calling.")
    if len(vals) < 2:
        return 0.0
    if stat == "IQR":
        q1, _q2, q3 = statistics.quantiles(vals, n=4, method="inclusive")
        return q3 - q1
    if stat == "std":
        return statistics.pstdev(vals)
    raise ValueError(f"unknown spread stat {stat!r} (expected 'IQR' or 'std').")


# --------------------------------------------------------------------------- #
# §6 item 5/6 — feasibility tier + stratified aggregation
# --------------------------------------------------------------------------- #

def feasibility_dominates(feas_A, feas_B, PI_A, PI_B):
    """§6 item 5 lexicographic feasibility-tier comparison of two candidates.

    KEY 1 (feasibility-fraction, dominates PI): A wins iff feas_A is a STRICT superset of feas_B
    (feasible on a superset of instances); B wins on the mirror. A candidate that wins new
    instances but loses old ones is NOT a dominator — it falls through to KEY 2 (it would trade
    away hard-instance feasibility).
    KEY 2 (PI on the jointly-feasible set J = feas_A ∩ feas_B): lower median PI wins.

    feas_A, feas_B : set[key] feasible instances ; PI_A, PI_B : {key: PI}.
    Returns 'A' | 'B' | 'tie' | 'incomparable' (latter only when J is empty).
    """
    feas_A, feas_B = set(feas_A), set(feas_B)
    if feas_A > feas_B:
        return "A"
    if feas_B > feas_A:
        return "B"
    J = feas_A & feas_B
    if not J:
        return "incomparable"
    a = statistics.median(PI_A[k] for k in J)
    b = statistics.median(PI_B[k] for k in J)
    if a < b:
        return "A"
    if b < a:
        return "B"
    return "tie"


def _exceeds(x, thresh):
    """True iff x is strictly above thresh by more than REL_TOL (so a boundary tie reads as a tie).

    NaN-safe: a non-finite x returns False (NaN never "exceeds"). Used for the §6 item 6 deadband
    (|δ| > m) and the gate comparisons so an FP-exact boundary is treated as a tie, not a flip.
    """
    return x > thresh and not math.isclose(x, thresh, rel_tol=REL_TOL, abs_tol=0.0)


def _average_ranks(magnitudes):
    """1-based average ranks (near-equal magnitudes share their mean rank) for a list of magnitudes.

    Ties are grouped by :data:`REL_TOL`-relative closeness (not exact ``==``) so two truly-equal PI
    deltas that differ by an FP residual still share a rank (NORTHSTAR §6 item 6 magnitude-weighting).
    """
    order = sorted(range(len(magnitudes)), key=lambda i: magnitudes[i])
    ranks = [0.0] * len(magnitudes)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and math.isclose(
                magnitudes[order[j + 1]], magnitudes[order[i]], rel_tol=REL_TOL, abs_tol=0.0):
            j += 1
        avg = (i + j) / 2.0 + 1.0  # mean of ranks (i+1)..(j+1)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def default_pi_spreads(default_PI, stat=SPREAD_STAT):
    """Per-n PI spread of the default schedule — the §6 item 6 noise-margin base.

    spreads_PI = {size: spread([finite default_PI over that size])}. This is the PRODUCER for
    :func:`aggregate_stratified`'s ``spreads_PI`` argument: it excludes the +∞ never-feasible
    sentinel (those PIs are not part of the measured spread) and reuses :func:`spread`.

    NOTE — two distinct spreads (NORTHSTAR §6 item 6 vs §8 item 3): this is the spread of default
    *PIs* (PI space), used as the §6.6 win/no-regression margin. The §8.3 exploration floor uses the
    spread of default *outcome objectives* (objective space; :func:`exploration_floor`'s
    ``spread_default``), produced separately from the default per-worker final incumbents. NORTHSTAR
    §6.6 says "reuse the §8.3 spread" but the two live in different units; both producers land with
    the CBQS-default seed-bank runs (bd 8an.1.16). See the bd note on 8an.2.

    DEGENERATE STRATA ARE OMITTED (bd 1xa, mirroring :func:`default_objective_spreads`): a size
    whose finite-PI population has < 2 points (``spread()``'s own ``0.0`` sentinel) or is all-equal
    (a degenerate spread of exactly 0) has NO measurable noise margin — it is ABSENT from the
    returned dict (NOT 0.0), so :func:`aggregate_stratified`'s spread guard fires fail-loud instead
    of a zero margin silently degrading the §6.6 strict gate to "any ε improvement" and evaporating
    the REL_TOL deadband. Cannot occur on the real frozen tables (≥ 9 distinct instances per
    stratum → spread > 0); this is degenerate-input hardening (CLAUDE.md §2.1).

    default_PI : {(size,index): float|inf} ; stat : "IQR" | "std"  ->  {size: float > 0}.
    """
    by_size = {}
    for (size, _index), pi in default_PI.items():
        if math.isfinite(pi):
            by_size.setdefault(size, []).append(pi)
    out = {}
    for size, vals in by_size.items():
        s = spread(vals, stat=stat)
        if s > 0:  # unmeasurable/degenerate margin → omit (fail-loud downstream), never 0.0
            out[size] = s
    return out


def aggregate_stratified(candidate_PI, default_PI, spreads_PI, *,
                         k=NOISE_MARGIN_K, largest_n=LARGEST_N):
    """§6 item 6 aggregation — stratify by size, signed-rank delta vs. default, hard gates.

    Strata are the UNION of candidate and default sizes (so a candidate cannot dodge a gate by
    omitting a stratum the default covers). Per stratum (size):
        default_feasible / candidate_feasible = instances with a finite PI on each side.
        FEASIBILITY GATE (NORTHSTAR §6 item 5 — the dominant key, wired in here): the candidate must
            be feasible on a SUPERSET of the default's feasible instances; losing feasibility on any
            instance the default solved fails the stratum, regardless of PI on the survivors.
        Over the JOINTLY-FEASIBLE set J = default_feasible ∩ candidate_feasible:
            δ_I  = default_PI[I] − candidate_PI[I]   (> 0 ⇒ candidate better, since lower PI = better)
            m(n) = k · spreads_PI[n]                  (noise margin / deadband, |δ_I| <= m ⇒ tie)
            W    = Σ_{|δ_I|>m} sign(δ_I)·rank(|δ_I|)  (Wilcoxon-Pratt: rank over all of J, drop ties)
            worst_regression = max_{I∈J}(candidate_PI[I] − default_PI[I])
        GATE B (every stratum):  worst_regression <= m AND no feasibility regression.
        GATE A (largest_n only): W > 0 AND (median_default − median_candidate) > m AND no feasibility
            regression — a STRICT improvement on the hard, large instances (NORTHSTAR §6.6/§9).
    overall_pass = all GATE B AND (when the largest-n stratum is in the union) largest-n GATE A.

    candidate_PI, default_PI : {(size,index): float|inf} (matched-seed) ; spreads_PI : {size: float}.
    Returns {"per_size": {size: {...}}, "overall_pass": bool}.
    Raises ValueError if a needed per-n spread is None/non-finite OR <= 0 (bd 1xa: a zero spread
    yields margin m=0, degrading the §6.6 largest-n STRICT gate to "any ε>0" and evaporating the
    REL_TOL deadband — _exceeds(x, 0.0) is True for any x>0 — so an FP residual ~1e-13 would fail
    gate B / count as a win; a zero-margin stratum is unevaluable, not silently permissive).
    """
    sizes = sorted({s for (s, _i) in candidate_PI} | {s for (s, _i) in default_PI})
    per_size = {}
    overall_pass = True
    for size in sizes:
        if spreads_PI.get(size) is None:
            raise ValueError(
                f"default PI spread for n={size} is None (not frozen, or degenerate/unmeasurable and "
                f"omitted by default_pi_spreads) — cannot aggregate.")
        if spreads_PI[size] <= 0:  # NaN falls through to the non-finite margin guard below
            raise ValueError(
                f"default PI spread for n={size} is {spreads_PI[size]} (degenerate) — a zero noise "
                f"margin cannot evaluate the §6.6 strict gate / REL_TOL deadband (bd 1xa).")
        m = k * spreads_PI[size]
        if not math.isfinite(m):
            raise ValueError(f"noise margin m={m} for n={size} is non-finite (bad spread) — fail loud.")
        # Feasibility coverage (NORTHSTAR §6 item 5 dominates PI). A candidate that LOSES feasibility
        # on an instance the default solved cannot pass on the surviving instances' PI.
        default_feasible = {key for key in default_PI
                            if key[0] == size and math.isfinite(default_PI[key])}
        candidate_feasible = {key for key in candidate_PI
                              if key[0] == size and math.isfinite(candidate_PI[key])}
        lost = default_feasible - candidate_feasible
        feasibility_regressed = bool(lost)
        J = sorted(default_feasible & candidate_feasible)  # jointly feasible
        deltas = [default_PI[key] - candidate_PI[key] for key in J]  # > 0 ⇒ candidate better
        ranks = _average_ranks([abs(d) for d in deltas])
        W = sum((1.0 if d > 0 else -1.0) * ranks[idx]
                for idx, d in enumerate(deltas) if _exceeds(abs(d), m))
        median_PI = statistics.median(candidate_PI[key] for key in J) if J else float("nan")
        worst_regression = max((candidate_PI[key] - default_PI[key] for key in J), default=0.0)
        gate_B = (not _exceeds(worst_regression, m)) and (not feasibility_regressed)
        rec = {"W": W, "median_PI": median_PI, "n_jointly_feasible": len(J),
               "n_default_feasible": len(default_feasible),
               "n_candidate_feasible": len(candidate_feasible),
               "feasibility_regressed": feasibility_regressed, "lost_feasibility": sorted(lost),
               "worst_regression": worst_regression, "margin": m, "gate_B_pass": gate_B}
        if size == largest_n:
            median_default = statistics.median(default_PI[key] for key in J) if J else float("nan")
            improvement = median_default - median_PI
            gate_A = (W > 0) and _exceeds(improvement, m) and (not feasibility_regressed)
            rec["median_default_PI"] = median_default
            rec["gate_A_pass"] = gate_A
            if not gate_A:
                overall_pass = False
        if not gate_B:
            overall_pass = False
        per_size[size] = rec
    return {"per_size": per_size, "overall_pass": overall_pass}


# --------------------------------------------------------------------------- #
# Batch driver — the None-skip vs. raise boundary
# --------------------------------------------------------------------------- #

def _classify_anchor(key, baselines):
    """Resolve one instance's frozen anchors into a scoring decision (shared by the batch scorers).

    Returns ``(kind, B_I, L_I, reason)``:
      - ``("score", B_I, L_I, None)``  — both anchors present and discriminating (L_I < B_I).
      - ``("skip",  None, None, reason)`` — anchor unavailable (recorded skip, NEVER scored 0; §2.1):
            key not in baselines / B_I is None / L_I is None (seed-bank not frozen — bd 8an.1.16).
      - ``("drop",  B_I, L_I, reason)`` — L_I >= B_I: default meets/beats the frontier → DROP (§6 item 1).

    Single source of truth for the §6 anchor gate, so ``score_run_set`` and the ``score_verdict``
    banked scorer cannot drift apart (CLAUDE.md §2.5/§2.7).
    """
    entry = baselines.get(key)
    if entry is None:
        return ("skip", None, None, "key not in baselines")
    B_I = entry.get("B_I")
    L_I = entry.get("L_I")
    if B_I is None:
        return ("skip", None, None, "B_I is None")
    if L_I is None:
        return ("skip", None, None, "L_I is None (seed-bank not frozen — bd 8an.1.16)")
    if L_I >= B_I:
        return ("drop", B_I, L_I, "L_I >= B_I (non-discriminating)")
    return ("score", B_I, L_I, None)


def anchor_cap_summary(baselines):
    """Provenance of the CBQS-default anchors' classical-sample cap (bd 0o8).

    Returns ``{"cap", "approximate", "mixed", "caps"}`` over the ANCHORED rows (those with a
    non-None ``L_I`` — the ones the §6 metric actually consumes):
      - ``cap``: the single ``opt_sample_cap`` shared by all anchored rows (``None`` if none).
      - ``approximate``: ``cap > 0`` — a binding cap means the default under-finds rare improvers,
        so the anchor (and therefore the verdict) is APPROXIMATE, not faithful.
      - ``mixed``: more than one distinct cap among anchored rows — a corrupt table (candidates
        would be scored against a mix of faithful and approximate anchors). :func:`score_run_set`
        fails loud on this; the freeze (:func:`benchmarks.baselines.freeze_default_anchors`) refuses
        to write it.
    A legacy table without the ``default_cap`` column loads as cap 0 (faithful), so this is a no-op
    on existing data.
    """
    caps = {int(e.get("default_cap") or 0)
            for e in baselines.values()
            if e is not None and e.get("L_I") is not None}
    return {"cap": (next(iter(caps)) if len(caps) == 1 else None),
            "approximate": any(c > 0 for c in caps),
            "mixed": len(caps) > 1,
            "caps": sorted(caps)}


def score_run_set(results_by_instance, baselines):
    """Score a full Eq.29 run-set against the frozen baseline table.

    Per instance, SKIP-WITH-REASON (recorded, not raised) when the anchor is unavailable —
        key not in baselines : instance omitted from the frontier table (non-discriminating, §6)
        B_I is None          : no non-CBQS feasible frontier row
        L_I is None          : CBQS-default seed-bank not yet frozen (the bd 8an.1.16 dependency)
        L_I >= B_I           : DROP rule — default already meets/beats the frontier (§6 item 1)
    Otherwise compute PI_I. NEVER coerces a None anchor to 0 (CLAUDE.md §2.1/§8); skips are
    explicit and reason-tagged. The math functions raise on None — this batch layer is the only
    place "anchor not yet available" is a legitimate, recorded skip.

    results_by_instance : {(size,index): OptimizeResult-like} ; baselines : load_frozen_baselines table.
    Returns {"scored","infeasible","dropped","skipped_no_anchor","feasibility_fraction_by_size"}.
    """
    # bd 0o8: refuse to score against a mixed-cap anchor table (some faithful, some approximate)
    # — that silently blends incomparable baselines. The freeze prevents writing one; this guards
    # a hand-edited / partially-frozen table at the consumer (CLAUDE.md §2.1).
    cap_info = anchor_cap_summary(baselines)
    if cap_info["mixed"]:
        raise ValueError(
            f"Mixed-cap anchor table (opt_sample_cap values {cap_info['caps']}): the CBQS-default "
            f"anchors were frozen at different classical-sample caps, so faithful and approximate "
            f"anchors would be scored together. Re-freeze ALL anchored sizes at one cap (bd 0o8)."
        )
    scored = {}
    infeasible = []
    dropped = []
    skipped_no_anchor = []
    feas_count = {}  # size -> [n_feasible, n_total]
    for key, result in results_by_instance.items():
        size, _index = key
        kind, B_I, L_I, reason = _classify_anchor(key, baselines)
        if kind == "skip":
            skipped_no_anchor.append((key, reason))
            continue
        if kind == "drop":
            dropped.append((key, reason))
            continue
        s = score_instance(result, size, B_I, L_I)
        scored[key] = s["PI"]
        cnt = feas_count.setdefault(size, [0, 0])
        cnt[1] += 1
        if s["feasible"]:
            cnt[0] += 1
        else:
            infeasible.append(key)
    feasibility_fraction_by_size = {
        s: c[0] / c[1] for s, c in feas_count.items() if c[1]
    }
    return {
        "scored": scored,
        "infeasible": infeasible,
        "dropped": dropped,
        "skipped_no_anchor": skipped_no_anchor,
        "feasibility_fraction_by_size": feasibility_fraction_by_size,
        # bd 0o8 provenance: the cap the consumed anchors were frozen at, and whether the
        # verdict is therefore APPROXIMATE (cap>0 => default under-finds rare improvers).
        "anchor_cap": cap_info["cap"],
        "anchor_approximate": cap_info["approximate"],
    }


# --------------------------------------------------------------------------- #
# §8 item 3 — objective-space default spread (the floor's normalizer)
# --------------------------------------------------------------------------- #

def default_objective_spreads(default_results, *, stat=SPREAD_STAT):
    """Per-n OBJECTIVE-space spread of the DEFAULT schedule's outcomes — the §8.3 floor base.

    Sibling of :func:`default_pi_spreads` but in OBJECTIVE units (the floor compares a candidate's
    ``best_of_P − median_of_P`` lift, which is objective-valued, to ``fraction · spread``). Built
    from the per-worker FEASIBLE final-incumbent objectives (``result.final_incumbents``), which are
    NOT in the frozen table — so the §8.3 floor needs the live default run-set even though §6.6 reads
    the frozen ``default_PI``.

    Granularity (bd 8an.2.1, Q1/Q6 + the panel's risk #4): a PER-INSTANCE IQR, then the MEDIAN across
    instances of that size — NOT a raw pool of objectives across instances. Eq.29 objectives are
    instance-specific (different ``c1``, ~5e6, differing tens-of-% across indices), so pooling raw
    objectives across instances would let inter-instance LEVEL differences dominate the IQR and
    contaminate a within-portfolio diversity threshold. The per-instance IQR isolates within-instance
    (worker+seed) dispersion; the median over instances is the stable per-``n`` scale §8.3 asks for
    ("the default schedule's measured spread at the same n"). For a single instance the two are
    identical, so this only diverges — correctly — once a size has ≥2 instances.

    Never-feasible workers (``feasible == False``) and never-feasible seeds (empty ``final_incumbents``)
    contribute NO point — they have no feasible objective, and a ``+∞`` never-feasible run must never
    enter a spread population (CLAUDE.md §2.1; mirrors :func:`default_pi_spreads`'s +∞ exclusion).
    An instance contributes a per-instance IQR ONLY when it is measurable AND positive: < 2 feasible
    objectives (no dispersion) OR a degenerate IQR of exactly 0 (≥ 2 *identical* feasible incumbents — a
    converged/greedy default portfolio) are both treated as "no measurable diversity" and contribute
    nothing. A size where NO instance has a positive IQR is ABSENT from the returned dict (NOT 0.0) — a
    deliberate departure from :func:`spread`'s own ``<2 → 0.0`` so the floor's None-guard fires
    (fail-loud) instead of a 0.0 threshold silently neutralizing the §8.3 anti-greedy gate (an IQR-0
    default would otherwise make ``_exceeds(lift, 0)`` admit any near-greedy candidate lift > 0).

    default_results : {(size,index): OptimizeResult-like | list[OptimizeResult-like]} ;
    stat : "IQR" | "std"  ->  {size: float}.
    """
    norm = _normalize_run_set(default_results, side="default")
    per_size_iqrs = {}
    for (size, _index), seed_results in norm.items():
        feas = [float(v)
                for r in seed_results
                for (v, ok) in (getattr(r, "final_incumbents", None) or [])
                if ok]
        if len(feas) >= 2:
            # spread() raises on a non-finite objective (a corrupt finite-looking incumbent fails loud).
            iqr = spread(feas, stat=stat)
            if iqr > 0:  # a 0 IQR (converged default portfolio) is not measurable diversity → drop it
                per_size_iqrs.setdefault(size, []).append(iqr)
    return {size: float(statistics.median(iqrs)) for size, iqrs in per_size_iqrs.items()}


# --------------------------------------------------------------------------- #
# bd 8an.2.1 — end-to-end run-set verdict driver (NORTHSTAR §6/§8/§13)
# --------------------------------------------------------------------------- #

def _normalize_run_set(run_set, *, side):
    """Coerce ``{key: OptimizeResult}`` or ``{key: [OptimizeResult, ...]}`` into ``{key: list}``.

    A bare result is 1-element-wrapped (a 1-seed smoke run scores correctly; the seed-bank size is
    surfaced so a 1-seed comparison is visible, not silent). RAISES on an empty run-set or an empty
    seed bank for a key (nothing to score — fail loud, §2.1).
    """
    if not run_set:
        raise ValueError(f"{side} run-set is empty — nothing to score (NORTHSTAR §6).")
    out = {}
    for key, v in run_set.items():
        lst = list(v) if isinstance(v, list) else [v]
        if not lst:
            raise ValueError(f"{side} run-set has an empty seed bank for {key} — fail loud (§2.1).")
        out[key] = lst
    return out


def _reduce_seed_bank_pi(seed_results, n, B_I, L_I):
    """Median PI over a seed bank for one instance — byte-identical to the frozen default_PI recipe.

    Mirrors :func:`benchmarks.baselines.default_instance_anchors` (median over the per-seed primal
    integral). A never-feasible seed contributes ``+∞`` (§6 item 5); with the canonical odd 7-seed
    bank the median lands on a single middle value, so an instance feasible on ≤ half its seeds
    reduces to ``+∞`` = "not reliably feasible" (→ a feasibility regression in
    :func:`aggregate_stratified` — the correct anti-greedy hard-instance behavior).

    seed_results : list[OptimizeResult-like] ; n,B_I,L_I as in :func:`score_instance`  ->  float|inf.
    """
    pis = [score_instance(r, n, B_I, L_I)["PI"] for r in seed_results]
    return float(statistics.median(pis))


def _check_matched_seeds(candidate_results, default_results):
    """Enforce matched seeds across the two run-sets (NORTHSTAR §13); returns the bank-size audit.

    For every JOINTLY-present instance: if BOTH sides' results carry a non-None ``.seed`` (the master
    seed; ``OptimizeResult.seed``), the seed MULTISETS must be equal — else RAISE (a §13 pairing
    violation is silent corruption, and the only thing that catches seed cherry-picking). MULTISET,
    not set: a candidate that pads a favorable seed (``[0,0,1]`` vs ``[0,1,1]``) re-weights the
    median-over-seeds PI while keeping the same seed *set*, so set-equality would wave it through.
    Within-bank duplicate seeds are rejected outright (a repeated master seed is zero-diversity
    padding, not a real bank entry). If ``.seed`` is absent on either side (e.g. a bare stub), fall
    back to a bank-SIZE equality check. RAISES on a mismatch.
    """
    audit = {"candidate": {k: len(v) for k, v in candidate_results.items()},
             "default": {k: len(v) for k, v in default_results.items()}}
    for key in sorted(set(candidate_results) & set(default_results)):
        c, d = candidate_results[key], default_results[key]
        c_seeds = [getattr(r, "seed", None) for r in c]
        d_seeds = [getattr(r, "seed", None) for r in d]
        if all(s is not None for s in c_seeds) and all(s is not None for s in d_seeds):
            for label, seeds in (("candidate", c_seeds), ("default", d_seeds)):
                if len(set(seeds)) != len(seeds):
                    raise ValueError(
                        f"duplicate master seed in the {label} bank at {key} (seeds {sorted(seeds)}): a "
                        f"repeated seed is zero-diversity padding that re-weights the median-over-seeds "
                        f"PI — a paired comparison needs DISTINCT matched seeds (NORTHSTAR §13)."
                    )
            if sorted(c_seeds) != sorted(d_seeds):
                raise ValueError(
                    f"matched-seed violation at {key}: candidate seeds {sorted(c_seeds)} != default "
                    f"seeds {sorted(d_seeds)} (NORTHSTAR §13 — the paired comparison requires the SAME "
                    f"seed bank on both sides; cherry-picked or re-weighted seeds are inadmissible)."
                )
        elif len(c) != len(d):
            raise ValueError(
                f"seed-bank size mismatch at {key}: candidate {len(c)} vs default {len(d)} runs, and "
                f".seed is absent so multiset-identity is unverifiable — match the banks (NORTHSTAR §13)."
            )
    return audit


def _instance_median_lift(seed_results):
    """Median over a seed bank of the per-portfolio spread lift (best − median of FEASIBLE finals).

    The same quantity :func:`exploration_floor` computes per solve, collapsed with a per-instance
    median (bd 8an.2.1). AMENDED (bd 8an.3.8): no longer part of the verdict floor — retained as
    the diversity diagnostic behind ``calibrate-floor`` (benchmarks/floor_calibration.csv).
    ``None`` when no seed had a feasible final.
    """
    lifts = []
    for r in seed_results:
        feas = [float(v) for (v, ok) in (getattr(r, "final_incumbents", None) or []) if ok]
        if feas:
            lifts.append(max(feas) - statistics.median(feas))
    return float(statistics.median(lifts)) if lifts else None


def _pair_by_seed(cand_seed_results, def_seed_results):
    """Pair one instance's candidate/default seed banks for the §8.3 tail comparison.

    Matched by ``result.seed`` when every result on both sides carries one (the production path —
    ``_check_matched_seeds`` has already enforced equal multisets); positional otherwise (unit-test
    stubs). Returns list[(cand_result, def_result|None)] — None when the default bank has no
    counterpart for that seed (the pair is then unevaluable and the caller records a None delta).
    """
    cand = list(cand_seed_results)
    deflt = list(def_seed_results)
    if (all(getattr(r, "seed", None) is not None for r in cand)
            and all(getattr(r, "seed", None) is not None for r in deflt)):
        by_seed = {r.seed: r for r in deflt}
        return [(rc, by_seed.get(rc.seed)) for rc in cand]
    return [(rc, deflt[i] if i < len(deflt) else None) for i, rc in enumerate(cand)]


def _aggregate_floor(candidate_results, default_results, spreads_obj, *,
                     fraction=EXPLORE_FLOOR_FRACTION,
                     floor_instance_fraction=FLOOR_INSTANCE_FRACTION, default_sizes=()):
    """§8 item 3 TAIL-QUALITY floor, aggregated over a matched seed bank (amended bd 8an.3.8).

    The floor protects what §1.3 actually scores — the harvested best-of-portfolio tail — by
    comparing it DIRECTLY against the seed-matched default instead of via the old within-portfolio
    best−median spread proxy. The M2 data showed the spread proxy was wrong in both directions
    (vetoed radius_g2e_early at strata where its final tail did NOT regress; PASSED the §1.3
    negative control radius_uniform2 at n=40..90 where its worst-instance tail regression reached
    2.5× the default spread) and gameable (sandbagging one worker manufactures lift without
    touching best-of-P PI).

    Two-level, anti-conflation, noise-tolerant:
      LEVEL 1 — per (instance, seed), seed-matched: ``Δ_{i,s} = best_of_P(candidate) −
        best_of_P(default)`` over each portfolio's feasible final incumbents
        (:func:`tail_floor_delta`). NEVER pool workers across seeds. A seed where the DEFAULT has
        no feasible final yields no reference (Δ None, excluded); a seed where only the CANDIDATE
        has none is a total tail collapse (Δ −inf, counted).
      LEVEL 2a — collapse seeds per instance with the MEDIAN Δ (stable over the small bank).
        ``instance_pass`` iff the median regression does NOT exceed the noise band:
        ``not _exceeds(−Δ_med, fraction · spread_obj[n])`` — mirroring the §6.6 gate-B margin
        semantics in objective space. A size the default portfolio CONVERGES on (``spreads_obj``
        omits it — per-instance IQR 0) uses a ZERO band: the reference is sharp, so any
        beyond-REL_TOL regression fails (this replaces the bd 7zx stratum skip — the tail floor
        is evaluable against a converged reference; the old spread floor was not).
        An instance with no Δ reference in ANY seed (default never feasible there) is SKIPPED —
        feasibility quality is the §6 item 5 tier's job. An instance the default run-set does not
        cover at all is likewise skipped (no reference; mirrors the §6.6 no-anchor skip).
      LEVEL 2b — per stratum: pass iff the FRACTION of evaluable instances passing ≥
        ``floor_instance_fraction`` (one easy instance cannot mask a collapsed one). A stratum
        with NO evaluable instance is recorded as an explicit skip (``stratum_pass`` None) —
        never a silent pass. A size the default covers but the candidate OMITS fails (anti-dodge;
        mirrors :func:`aggregate_stratified`'s size union).

    NEUTRAL-REFERENCE SANITY (structural): default-vs-default gives Δ ≡ 0 on every seed → the
    floor passes at ANY fraction ≥ 0 with no calibration machinery (the M1 evaluability-by-
    reference rule and the floor_calibration admissibility pin are obsolete for gating; the
    calibration artifact remains a diversity diagnostic).

    RAISES if NO candidate solve in a default-covered stratum emitted ``final_incumbents`` at all
    (the M0e harness dependency — never a silent pass).

    candidate_results : {(size,index): list[OptimizeResult-like]} (normalized) ;
    default_results   : {(size,index): list[OptimizeResult-like]} (normalized, the reference) ;
    spreads_obj : {size: float} (:func:`default_objective_spreads`) ; default_sizes : iterable[size].
    Returns {"overall_pass": bool, "per_size": {size: {...}}, "skipped_sizes": [size]}.
    """
    cand_sizes = {s for (s, _i) in candidate_results}
    all_sizes = sorted(cand_sizes | set(default_sizes))
    per_size = {}
    skipped_sizes = []
    overall_pass = True
    for size in all_sizes:
        keys = [k for k in candidate_results if k[0] == size]
        spread_obj = spreads_obj.get(size)
        if not keys:
            # default covers this stratum, candidate omits it entirely → fail (anti-dodge).
            per_size[size] = {"n_instances": 0, "n_instances_passing": 0, "instance_pass_fraction": 0.0,
                              "instance_deltas": {}, "per_seed_delta": {}, "band": None,
                              "spread_obj": spread_obj, "stratum_pass": False,
                              "reason": "candidate omits a default-covered stratum"}
            overall_pass = False
            continue
        any_produced = any((getattr(r, "final_incumbents", None) or [])
                           for k in keys for r in candidate_results[k])
        if not any_produced:
            raise ValueError(
                f"§8.3 floor: no per-worker final_incumbents for any candidate solve at n={size} — the "
                f"M0e harness must emit result.final_incumbents (NORTHSTAR §11); cannot pass silently."
            )
        # Converged-default stratum: sharp reference → zero noise band (see docstring).
        band = (fraction * spread_obj) if spread_obj is not None else 0.0
        instance_deltas = {}
        per_seed_delta = {}
        skipped_instances = []
        n_pass = 0
        n_evaluable = 0
        for k in keys:
            def_bank = default_results.get(k)
            if not def_bank:
                # no default reference run for this instance — nothing to regress against.
                skipped_instances.append(k)
                continue
            deltas = []
            for rc, rd in _pair_by_seed(candidate_results[k], def_bank):
                if rd is None:
                    deltas.append(None)
                    continue
                deltas.append(tail_floor_delta(
                    getattr(rc, "final_incumbents", None) or [],
                    getattr(rd, "final_incumbents", None) or []))
            per_seed_delta[k] = deltas
            present = [d for d in deltas if d is not None]
            if not present:
                # default never feasible on this instance → no tail reference (feasibility
                # quality is the §6 item 5 tier's job, not the floor's).
                skipped_instances.append(k)
                continue
            n_evaluable += 1
            dmed = float(statistics.median(present))
            instance_deltas[k] = dmed
            if not _exceeds(-dmed, band):
                n_pass += 1
        n_inst = len(keys)
        if n_evaluable == 0:
            per_size[size] = {"n_instances": n_inst, "n_instances_evaluable": 0,
                              "n_instances_passing": 0, "instance_pass_fraction": None,
                              "instance_deltas": {}, "per_seed_delta": per_seed_delta,
                              "band": band, "spread_obj": spread_obj, "stratum_pass": None,
                              "skipped": True, "skipped_instances": skipped_instances,
                              "reason": ("no instance with a feasible default tail reference at "
                                         "this size — floor unevaluable")}
            skipped_sizes.append(size)
            continue
        frac_pass = n_pass / n_evaluable
        stratum_pass = frac_pass >= floor_instance_fraction
        per_size[size] = {"n_instances": n_inst, "n_instances_evaluable": n_evaluable,
                          "n_instances_passing": n_pass,
                          "instance_pass_fraction": frac_pass, "instance_deltas": instance_deltas,
                          "per_seed_delta": per_seed_delta, "band": band,
                          "spread_obj": spread_obj, "stratum_pass": stratum_pass,
                          "skipped_instances": skipped_instances}
        if not stratum_pass:
            overall_pass = False
    return {"overall_pass": overall_pass, "per_size": per_size, "skipped_sizes": skipped_sizes}


def score_verdict(candidate_results, default_results, baselines, *, k=NOISE_MARGIN_K,
                  fraction=EXPLORE_FLOOR_FRACTION, floor_instance_fraction=FLOOR_INSTANCE_FRACTION,
                  largest_n=LARGEST_N, stat=SPREAD_STAT, require_largest_n=True, strict_xcheck=False):
    """End-to-end M1 verdict: does the candidate schedule BEAT the CBQS-default? (NORTHSTAR §6/§8).

    Pure composition over already-solved run-sets and the frozen anchor table — NO solving. Wires:
      candidate PI  : matched-seed MEDIAN over the seed bank, vs frozen B_I/L_I (:func:`_reduce_seed_bank_pi`);
      default PI    : the FROZEN ``default_PI`` column is AUTHORITATIVE for the gate (§6.1 froze it);
      §6.6 (L2)     : :func:`aggregate_stratified` over PI deltas, margin = ``k · default_pi_spreads`` (PI space);
      §8.3 (L3)     : :func:`_aggregate_floor` — the TAIL-QUALITY floor (amended bd 8an.3.8):
                      candidate best-of-P vs seed-matched default best-of-P, noise band
                      ``fraction ·`` :func:`default_objective_spreads` (objective space);
    and ANDs the two into one ``overall_pass`` (lexicographic: feasibility tier — folded inside
    :func:`aggregate_stratified` — ⊳ §6.6 PI ⊳ §8.3 floor; the floor can veto but never revive a §6.6
    failure). The supplied default run-set is needed regardless (the floor compares against its
    ``final_incumbents``, which are not frozen); it is ALSO re-scored and cross-checked against the
    frozen ``default_PI`` (recorded in ``default_xcheck_failures``; a breach raises iff ``strict_xcheck``).

    RAISES on: an empty candidate or default run-set; a matched-seed violation; an unevaluable
    largest-``n`` gate when ``require_largest_n`` (today the frozen table's n=3000 ``default_PI`` is
    empty — pending bd 0o8 — so a TRUE end-to-end verdict needs the large-``n`` freeze; pass
    ``require_largest_n=False`` for an inspectable partial verdict during development); a §8.3 stratum
    with no ``final_incumbents`` anywhere. NEVER coerces a None/non-finite anchor to 0 (recorded in
    ``default_pi_missing`` / the candidate ``skipped_no_anchor`` channel).

    candidate_results, default_results : {(size,index): OptimizeResult-like | list[...]} (matched bank) ;
    baselines : :func:`benchmarks.baselines.load_frozen_baselines` table.
    Returns the verdict dict documented in bd 8an.2.1 (overall_pass + the §6.6 / §8.3 sub-results +
    full bookkeeping for calibration/audit).
    """
    candidate = _normalize_run_set(candidate_results, side="candidate")
    default = _normalize_run_set(default_results, side="default")
    seed_bank = _check_matched_seeds(candidate, default)

    # --- default PI: the FROZEN column is authoritative (Q2). Resolved FIRST so the candidate side can
    #     skip instances with no default anchor to compare against — otherwise aggregate_stratified is
    #     asked to gate a size with no default spread and RAISES mid-verdict, defeating the documented
    #     partial-verdict path (a real freeze state: baselines status=='default_unreliable' writes L_I
    #     but withholds default_PI). The run-set is re-scored further below only for the cross-check. ---
    run_keys = set(candidate) | set(default)
    default_PI = {}
    default_pi_missing = []
    for key in run_keys:
        entry = baselines.get(key)
        dpi = entry.get("default_PI") if entry else None
        if dpi is None or not math.isfinite(float(dpi)):
            default_pi_missing.append(key)
        else:
            default_PI[key] = float(dpi)
    default_pi_missing_set = set(default_pi_missing)

    # --- candidate PI (median over the matched seed bank) + score_run_set-style bookkeeping ------
    cand_book = {"scored": {}, "infeasible": [], "dropped": [], "skipped_no_anchor": [],
                 "feasibility_fraction_by_size": {}}
    cand_feas = {}
    candidate_PI = {}
    for key, seed_results in candidate.items():
        size, _i = key
        kind, B_I, L_I, reason = _classify_anchor(key, baselines)
        if kind == "skip":
            cand_book["skipped_no_anchor"].append((key, reason))
            continue
        if kind == "drop":
            cand_book["dropped"].append((key, reason))
            continue
        if key in default_pi_missing_set:
            # Scoreable (B_I/L_I present) but no frozen default_PI to compare against — recorded in the
            # top-level default_pi_missing and EXCLUDED from the §6.6 comparison (cannot compute δ_I).
            cand_book["skipped_no_anchor"].append(
                (key, "no frozen default_PI to compare (recorded in default_pi_missing)"))
            continue
        pi = _reduce_seed_bank_pi(seed_results, size, B_I, L_I)
        candidate_PI[key] = pi
        cand_book["scored"][key] = pi
        cnt = cand_feas.setdefault(size, [0, 0])
        cnt[1] += 1
        if math.isfinite(pi):
            cnt[0] += 1
        else:
            cand_book["infeasible"].append(key)
    cand_book["feasibility_fraction_by_size"] = {s: c[0] / c[1] for s, c in cand_feas.items() if c[1]}

    default_book = {"scored": {}, "infeasible": [], "dropped": [], "skipped_no_anchor": [],
                    "feasibility_fraction_by_size": {}}
    default_feas = {}
    default_rescored = {}
    for key, seed_results in default.items():
        size, _i = key
        kind, B_I, L_I, reason = _classify_anchor(key, baselines)
        if kind == "skip":
            default_book["skipped_no_anchor"].append((key, reason))
            continue
        if kind == "drop":
            default_book["dropped"].append((key, reason))
            continue
        pi = _reduce_seed_bank_pi(seed_results, size, B_I, L_I)
        default_rescored[key] = pi
        default_book["scored"][key] = pi
        cnt = default_feas.setdefault(size, [0, 0])
        cnt[1] += 1
        if math.isfinite(pi):
            cnt[0] += 1
        else:
            default_book["infeasible"].append(key)
    default_book["feasibility_fraction_by_size"] = {
        s: c[0] / c[1] for s, c in default_feas.items() if c[1]}

    default_xcheck_failures = []
    for key in set(default_rescored) & set(default_PI):
        rs, fr = default_rescored[key], default_PI[key]
        if math.isfinite(rs) != math.isfinite(fr):
            # Categorical drift: the freeze claims feasibility (finite default_PI) but the live default
            # run-set does not reach it (rs = +∞), or vice versa. This is the LARGEST possible divergence
            # and the strongest stale-freeze / wrong-run-set signal — record it unconditionally with
            # rel=+∞ (the finite-vs-finite REL_TOL band would never catch it). CLAUDE.md §2.1.
            default_xcheck_failures.append((key, rs, fr, float("inf")))
        elif math.isfinite(rs) and math.isfinite(fr):
            rel = abs(rs - fr) / max(abs(fr), PI_EPS)
            if rel > XCHECK_REL_TOL:
                default_xcheck_failures.append((key, rs, fr, rel))
    if strict_xcheck and default_xcheck_failures:
        raise ValueError(
            f"strict_xcheck: the supplied default run-set re-scores away from the frozen default_PI "
            f"beyond XCHECK_REL_TOL={XCHECK_REL_TOL} on {len(default_xcheck_failures)} instance(s) "
            f"(e.g. {default_xcheck_failures[0]}) — stale freeze or a wrong default run-set."
        )

    # --- the two spread bases: §6.6 PI-space margin vs §8.3 objective-space floor -----------------
    spreads_PI = default_pi_spreads(default_PI, stat=stat)
    spreads_obj = default_objective_spreads(default, stat=stat)

    if require_largest_n and not any(s == largest_n for (s, _i) in default_PI):
        raise ValueError(
            f"require_largest_n: no frozen default_PI at the largest-n stratum (n={largest_n}) — the §6.6 "
            f"hard-instance strict-improvement gate is unevaluable. The large-n freeze is pending "
            f"(bd 0o8); pass require_largest_n=False for an inspectable partial verdict, or freeze n={largest_n}."
        )

    aggregation = aggregate_stratified(candidate_PI, default_PI, spreads_PI, k=k, largest_n=largest_n)
    # §8.3 tail-quality floor (amended bd 8an.3.8): candidate best-of-P vs the seed-matched
    # default best-of-P, noise band = fraction · spread_obj — see _aggregate_floor's docstring.
    floor = _aggregate_floor(candidate, default, spreads_obj, fraction=fraction,
                             floor_instance_fraction=floor_instance_fraction,
                             default_sizes={s for (s, _i) in default})

    overall_pass = aggregation["overall_pass"] and floor["overall_pass"]

    # Fail-loud internal invariant: §6.6 passing must imply NO feasibility regression in any stratum
    # (the feasibility tier is the dominant key — if aggregate_stratified ever decouples them, catch it).
    if aggregation["overall_pass"] and any(
            rec.get("feasibility_regressed") for rec in aggregation["per_size"].values()):
        raise AssertionError(
            "invariant violated: aggregate_stratified reports overall_pass while a stratum has "
            "feasibility_regressed — the §6 item 5 feasibility tier must dominate PI (CLAUDE.md §2.1/§2.5)."
        )

    return {
        "overall_pass": overall_pass,
        "aggregation": aggregation,
        "floor": floor,
        "candidate_scoring": cand_book,
        "default_scoring": default_book,
        "candidate_PI": candidate_PI,
        "default_PI": default_PI,
        "spreads_PI": spreads_PI,
        "spreads_obj": spreads_obj,
        "feasibility_fraction_by_size": {
            "candidate": cand_book["feasibility_fraction_by_size"],
            "default": default_book["feasibility_fraction_by_size"],
        },
        "default_xcheck_failures": default_xcheck_failures,
        "default_pi_missing": sorted(default_pi_missing),
        "candidate_only_instances": sorted(set(candidate) - set(default)),
        "default_only_instances": sorted(set(default) - set(candidate)),
        "seed_bank": seed_bank,
        "params": {"k": k, "fraction": fraction, "floor_instance_fraction": floor_instance_fraction,
                   "largest_n": largest_n, "stat": stat, "require_largest_n": require_largest_n,
                   "strict_xcheck": strict_xcheck},
    }
