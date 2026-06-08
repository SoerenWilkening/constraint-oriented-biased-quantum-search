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

#: §8 item 3 exploration floor: best-of-P must exceed median-of-P by EXPLORE_FLOOR_FRACTION of
#: the default schedule's per-n spread. NORTHSTAR leaves the fraction unpinned (calibrated in M1).
EXPLORE_FLOOR_FRACTION = 0.5

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
    """§8 item 3 hard gate: best-of-P must exceed median-of-P by a fraction of the default spread.

    PASS iff ``best_of_P − median_of_P > fraction · spread_default`` over the candidate's FEASIBLE
    per-worker final incumbents (objective space, MAXIMIZE so higher = better). Gates on OUTCOME
    lift, not per-decision entropy; the early greedy stage is exempt automatically (these are
    *final* incumbents). Feasibility tier (§6 item 5) handles the all-infeasible case first.

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

    default_PI : {(size,index): float|inf} ; stat : "IQR" | "std"  ->  {size: float}.
    """
    by_size = {}
    for (size, _index), pi in default_PI.items():
        if math.isfinite(pi):
            by_size.setdefault(size, []).append(pi)
    return {size: spread(vals, stat=stat) for size, vals in by_size.items()}


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
    Raises ValueError if a needed per-n spread is None/non-finite (must not silently pass the gate).
    """
    sizes = sorted({s for (s, _i) in candidate_PI} | {s for (s, _i) in default_PI})
    per_size = {}
    overall_pass = True
    for size in sizes:
        if spreads_PI.get(size) is None:
            raise ValueError(f"default PI spread for n={size} is None (not frozen) — cannot aggregate.")
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
    scored = {}
    infeasible = []
    dropped = []
    skipped_no_anchor = []
    feas_count = {}  # size -> [n_feasible, n_total]
    for key, result in results_by_instance.items():
        size, _index = key
        entry = baselines.get(key)
        if entry is None:
            skipped_no_anchor.append((key, "key not in baselines"))
            continue
        B_I = entry.get("B_I")
        L_I = entry.get("L_I")
        if B_I is None:
            skipped_no_anchor.append((key, "B_I is None"))
            continue
        if L_I is None:
            skipped_no_anchor.append((key, "L_I is None (seed-bank not frozen — bd 8an.1.16)"))
            continue
        if L_I >= B_I:
            dropped.append((key, "L_I >= B_I (non-discriminating)"))
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
    }
