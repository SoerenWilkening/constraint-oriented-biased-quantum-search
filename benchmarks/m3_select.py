"""M3 cross-validation + multiplicity-controlled selection (bd 8an.4.5, NORTHSTAR §9/§13).

The population search (:func:`benchmarks.m3.evolve`) is a **multiple-comparisons
machine**: it scores many candidate schedules against the CBQS default, so the
fittest is selected *because* it is extreme — exactly the regime that manufactures
spurious "winners". This module is the §13 statistical discipline that turns a
fit candidate into a *defensible* one:

* **Cross-validation** (:func:`cross_validate`) — two DISJOINT instance folds over
  the anchored ``n=10..90`` strata. The authoritative bd-8an.4 decision
  (2026-06-11) is TRAIN ``n∈{10,20,30,40,50}`` → VALIDATE ``n∈{60,70,80,90}``;
  a candidate is promoted only if it clears EVERY §6/§8 gate on BOTH folds
  (NORTHSTAR §9 "promote only on improvement in both"). The largest-n strict gate
  (gate_A) stays DORMANT (``require_largest_n=False``) — n=3000 generalization is M4.

  This split DELIBERATELY OVERRIDES, for the M3 inner instance-CV, the bd-4zg
  contract pinned by :func:`benchmarks.scale_invariance.selection_sizes` /
  ``tests/test_selection_sizes.py`` (which excludes n<100 from M3 selection because
  the radius lever is scale-compressed below n=100). The newer bd-8an.4 decision
  supersedes it HERE because the only frozen-anchored strata with enough instances
  for a paired comparison are n=10..90 (~10 each); n=100 has 2, and n≥500
  ``default_PI`` is pending bd 0o8. The n≥100 ``selection_sizes`` split stays the
  authority for the M4 generalization-to-n=3000 gate (the largest-n strict gate is
  DORMANT here). The compression risk is bounded another way: the §10 pre-scoring
  gate (:func:`benchmarks.candidate_gate.admit`) still checks scale-invariance at
  n≥100, so a lever that only works in the compressed small-n regime is rejected
  before it is ever scored on these folds.

* **Multiplicity control** (:func:`select_significant`) — the §13 unit is the
  per-instance paired difference at matched seeds. Per candidate that survives CV,
  a one-sided Wilcoxon signed-rank p-value over its PI deltas (ties within the §6.6
  noise margin → zeros, exactly the gate's deadband); then **Holm–Bonferroni**
  family-wise correction across the surviving population at level ``ALPHA``. A
  survivor must pass CV *and* be Holm-rejected.

* **Final rescore** (:func:`rescore_once`) — the §13 "the final rule is re-scored
  ONCE on the untouched test with NEW seeds; that single number is reported."
  Leakage guards (new seeds disjoint from the selection bank, holdout instances
  disjoint from the folds) fire BEFORE solving.

* **Negative control** (:func:`negative_control`) — the same pipeline on
  baseline-equivalent candidates (:func:`benchmarks.m3_proposer.baseline_equivalent_factory`)
  solved at the default's matched seed bank must yield NO significant win
  (the §13 type-I / FWER check).

Pure composition over the existing metric machinery (CLAUDE.md §2.7 DON'T
DUPLICATE): the p-value is DERIVED from the same ``score_verdict`` dict the gate
reads, so the Wilcoxon and the §6.6 ``W`` see the identical jointly-feasible set
by construction. No solving here except behind the injected ``*_solve`` callables;
tests drive the loop with stubs (no C extension).
"""
import math

try:  # package import (pytest / installed) vs flat script import
    from benchmarks import metric
    from benchmarks.baselines import DEFAULT_SEED_BANK
except ImportError:  # pragma: no cover - flat layout fallback
    import metric  # type: ignore
    from baselines import DEFAULT_SEED_BANK  # type: ignore


#: Authoritative bd-8an.4 (2026-06-11) CV split over the anchored n=10..90 strata.
#: Disjoint by construction (disjoint size sets ⇒ disjoint (n,index) keys).
FOLDS = {
    "train": frozenset({10, 20, 30, 40, 50}),
    "validate": frozenset({60, 70, 80, 90}),
}

#: Family-wise error rate for the §13 multiplicity correction.
ALPHA = 0.05


# --------------------------------------------------------------------------- #
# Folds
# --------------------------------------------------------------------------- #

def restrict_run_set(run_set, fold_sizes):
    """Subset a ``{(n, index): result|list}`` run-set to the instances of one fold.

    RAISES on an empty restriction (fail loud, §2.1): an empty fold is an
    unverifiable promotion — never a silent pass.
    """
    sizes = set(fold_sizes)
    sub = {k: v for k, v in run_set.items() if k[0] in sizes}
    if not sub:
        raise ValueError(
            f"fold restriction to sizes {sorted(sizes)} is empty over run-set keys "
            f"{sorted(run_set)} — an empty fold cannot verify a promotion (NORTHSTAR §9).")
    return sub


def score_fold(candidate_results, default_results, baselines, fold_sizes, *,
               require_largest_n=False, strict_xcheck=True, score_kwargs=None):
    """Restrict BOTH run-sets to ``fold_sizes`` and score the §6/§8 verdict.

    Thin wrapper over :func:`benchmarks.metric.score_verdict`. ``require_largest_n``
    stays False (gate_A DORMANT, no fold holds n=3000); ``strict_xcheck`` is True
    for selection (the supplied default re-scores at the SAME frozen seeds, so a
    drift from the frozen ``default_PI`` is a stale-freeze bug — the M1 capstone
    lesson). A ``score_verdict`` raise PROPAGATES (corrupt input ≠ "candidate
    lost", landmine #2).
    """
    cand = restrict_run_set(candidate_results, fold_sizes)
    deflt = restrict_run_set(default_results, fold_sizes)
    return metric.score_verdict(cand, deflt, baselines, require_largest_n=require_largest_n,
                                strict_xcheck=strict_xcheck, **(score_kwargs or {}))


class CVResult:
    """Outcome of :func:`cross_validate`: ``passed`` (the AND of every fold's
    ``overall_pass``), the per-fold verdicts, and the fold size sets used."""

    __slots__ = ("passed", "per_fold", "fold_sizes")

    def __init__(self, passed, per_fold, fold_sizes):
        self.passed = bool(passed)
        self.per_fold = dict(per_fold)
        self.fold_sizes = {k: set(v) for k, v in fold_sizes.items()}

    def __repr__(self):
        return (f"CVResult(passed={self.passed}, "
                f"folds={ {k: v['overall_pass'] for k, v in self.per_fold.items()} })")


def cross_validate(candidate_results, default_results, baselines, *, folds=FOLDS,
                   strict_xcheck=True, score_kwargs=None):
    """AND the §6/§8 ``overall_pass`` across BOTH folds (NORTHSTAR §9/§13).

    A candidate is promotable only if it clears every gate on the train fold AND
    the validate fold — improvement on near-target *and* small sizes, not a single
    fold the search could overfit. ``require_largest_n=False`` on every fold.

    Fail loud (§2.1) rather than pass vacuously: an empty ``folds`` (``all([])``
    is True) or a fold that scored NO anchored instance (empty ``default_PI`` —
    ``aggregate_stratified`` over no strata returns ``overall_pass=True`` on
    nothing) is an unverifiable promotion, not a pass.
    """
    if not folds:
        raise ValueError("cross_validate requires at least one fold (NORTHSTAR §9).")
    per_fold = {}
    for name, sizes in folds.items():
        verdict = score_fold(candidate_results, default_results, baselines, sizes,
                             strict_xcheck=strict_xcheck, score_kwargs=score_kwargs)
        if not verdict["default_PI"]:
            raise ValueError(
                f"fold {name!r} (sizes {sorted(sizes)}) scored no anchored instance "
                f"(empty default_PI) — a fold with no frozen reference cannot verify a "
                f"promotion; overall_pass would be vacuously True (§2.1).")
        per_fold[name] = verdict
    passed = all(v["overall_pass"] for v in per_fold.values())
    return CVResult(passed, per_fold, folds)


# --------------------------------------------------------------------------- #
# The §13 Wilcoxon unit — DERIVED from the score_verdict dict
# --------------------------------------------------------------------------- #

class WilcoxonStat:
    """Per-candidate paired-test result: the one-sided p-value plus the bookkeeping
    the §13 audit log needs (effective sample, zeroed ties, non-finite exclusions)."""

    __slots__ = ("p_value", "statistic", "n_effective", "n_zeros",
                 "n_excluded_nonfinite", "all_zero")

    def __init__(self, p_value, statistic, n_effective, n_zeros,
                 n_excluded_nonfinite, all_zero):
        self.p_value = float(p_value)
        self.statistic = float(statistic)
        self.n_effective = int(n_effective)
        self.n_zeros = int(n_zeros)
        self.n_excluded_nonfinite = int(n_excluded_nonfinite)
        self.all_zero = bool(all_zero)

    def __repr__(self):
        return (f"WilcoxonStat(p={self.p_value:.4g}, n_eff={self.n_effective}, "
                f"n_zeros={self.n_zeros}, n_excl={self.n_excluded_nonfinite})")


def candidate_pvalue(verdict, *, alternative="greater"):
    """One-sided Wilcoxon signed-rank p-value DERIVED from a ``score_verdict`` dict.

    The §13 unit is the per-instance paired PI difference at matched seeds. Reading
    the verdict (rather than re-pairing) makes the test agree with the §6.6 ``W``
    gate BY CONSTRUCTION — same jointly-present keys, same sign, same deadband:

    * ``J`` = keys present in BOTH ``verdict['candidate_PI']`` and
      ``verdict['default_PI']``; a non-finite PI on EITHER side is EXCLUDED and
      counted (a +∞ never-feasible candidate PI is a feasibility regression that
      scipy would silently mis-rank as an ordinary loss — landmine; the AND with
      :meth:`CVResult.passed` in :func:`select_significant` is what actually sinks
      it via the §6 item-5 tier).
    * ``δ_I = default_PI[I] − candidate_PI[I]`` (> 0 ⇒ candidate better — the
      ``aggregate_stratified`` sign).
    * **tie-as-zero**: ``|δ_I| ≤ m(n)`` (``m = k · spreads_PI[n]``, REL_TOL-snapped
      via :func:`metric._exceeds`) maps ``δ_I → 0`` — the §6.6 / §13 deadband. A
      jointly-feasible size MUST have a spread (``aggregate_stratified`` already
      raised in ``score_verdict`` otherwise — metric.py:523); a missing spread here
      is a corrupt/hand-built verdict and RAISES rather than silently using margin 0
      (which would evaporate the deadband and diverge from the gate — §2.1).

    Degenerate guard (scipy 1.15.2 emits a NaN + warning on these): **no nonzero
    delta** ⇒ deterministic ``p = 1.0`` (``all_zero``), short-circuited BEFORE
    scipy. One nonzero delta yields scipy's ``p = 0.5`` (no rejection possible),
    which is harmless and left to scipy.
    """
    from scipy.stats import wilcoxon

    cand_PI = verdict["candidate_PI"]
    def_PI = verdict["default_PI"]
    spreads = verdict["spreads_PI"]
    k = verdict["params"]["k"]

    deltas = []
    n_zeros = 0
    n_excl = 0
    for key in sorted(set(cand_PI) & set(def_PI)):
        cp = cand_PI[key]
        dp = def_PI[key]
        if not (math.isfinite(cp) and math.isfinite(dp)):
            n_excl += 1
            continue
        delta = float(dp) - float(cp)
        n = key[0]
        if n not in spreads:
            raise ValueError(
                f"jointly-feasible size n={n} has no default PI spread in the verdict — "
                f"score_verdict's aggregate_stratified raises on this (metric.py:523), so a "
                f"verdict reaching here with a missing spread is corrupt (§2.1); the §13 "
                f"Wilcoxon deadband must agree with the §6.6 gate, never fall back to margin 0.")
        margin = k * spreads[n]
        if not metric._exceeds(abs(delta), margin):
            delta = 0.0
            n_zeros += 1
        deltas.append(delta)

    n_nonzero = sum(1 for d in deltas if d != 0.0)
    if n_nonzero < 1:
        return WilcoxonStat(p_value=1.0, statistic=0.0, n_effective=0, n_zeros=n_zeros,
                            n_excluded_nonfinite=n_excl, all_zero=True)

    res = wilcoxon(deltas, zero_method="wilcox", alternative=alternative, method="auto")
    return WilcoxonStat(p_value=float(res.pvalue), statistic=float(res.statistic),
                        n_effective=n_nonzero, n_zeros=n_zeros,
                        n_excluded_nonfinite=n_excl, all_zero=False)


# --------------------------------------------------------------------------- #
# Family-wise multiplicity control
# --------------------------------------------------------------------------- #

class HolmDecision:
    """One candidate's Holm verdict: raw p, the step-down adjusted p, and reject."""

    __slots__ = ("p_raw", "p_adjusted", "reject")

    def __init__(self, p_raw, p_adjusted, reject):
        self.p_raw = float(p_raw)
        self.p_adjusted = float(p_adjusted)
        self.reject = bool(reject)

    def __repr__(self):
        return (f"HolmDecision(p_raw={self.p_raw:.4g}, "
                f"p_adj={self.p_adjusted:.4g}, reject={self.reject})")


def holm_bonferroni(pvalues_by_id, *, alpha=ALPHA):
    """Holm–Bonferroni step-down FWER control across the candidate population.

    Sort the ``m`` raw p-values ascending (ties broken by id for determinism). The
    ``i``-th (0-based) is rejected iff ``p_(i) ≤ alpha/(m−i)`` AND every earlier
    one was rejected (the step-down stops at the first non-rejection). The adjusted
    p is the running-max of ``(m−i)·p_(i)`` clamped to ≤ 1 (monotone). Controls
    FWER ≤ ``alpha`` under arbitrary dependence (Holm 1979). Empty family → ``{}``.
    """
    items = sorted(pvalues_by_id.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(items)
    out = {}
    prev_adj = 0.0
    stopped = False
    for i, (cid, p) in enumerate(items):
        adj = max(prev_adj, min(1.0, (m - i) * p))
        prev_adj = adj
        if not stopped and p <= alpha / (m - i):
            reject = True
        else:
            reject = False
            stopped = True
        out[cid] = HolmDecision(p_raw=p, p_adjusted=adj, reject=reject)
    return out


class SelectionResult:
    """Outcome of :func:`select_significant`: the ``survivors`` (ids passing CV AND
    Holm), a per-candidate audit record, and the full ``holm`` table."""

    __slots__ = ("survivors", "per_candidate", "holm")

    def __init__(self, survivors, per_candidate, holm):
        self.survivors = list(survivors)
        self.per_candidate = dict(per_candidate)
        self.holm = dict(holm)

    def __repr__(self):
        return (f"SelectionResult(survivors={self.survivors}, "
                f"n_candidates={len(self.per_candidate)})")


def select_significant(candidate_results_by_id, default_results, baselines, *,
                       folds=FOLDS, alpha=ALPHA, strict_xcheck=True, score_kwargs=None):
    """Compose CV + multiplicity control over a candidate POPULATION (§13).

    For each candidate: (1) :func:`cross_validate` over BOTH folds; (2) for those
    that pass CV, a pooled :func:`candidate_pvalue` over the union of fold sizes
    (one verdict on train∪validate — the §13 per-instance unit, more powerful than
    a single fold); (3) :func:`holm_bonferroni` across the CV-passing family ONLY
    (a candidate that fails CV is never tested, so it spends no α — a deliberate,
    documented choice). A survivor passes CV AND is Holm-rejected.
    """
    union_sizes = frozenset().union(*folds.values())
    per_candidate = {}
    pvals = {}
    cv_pass_ids = []
    for cid, cand_results in candidate_results_by_id.items():
        cv = cross_validate(cand_results, default_results, baselines, folds=folds,
                            strict_xcheck=strict_xcheck, score_kwargs=score_kwargs)
        rec = {"cross_val": cv.passed, "p_value": None, "p_adjusted": None,
               "reject": False}
        if cv.passed:
            verdict = score_fold(cand_results, default_results, baselines, union_sizes,
                                 strict_xcheck=strict_xcheck, score_kwargs=score_kwargs)
            stat = candidate_pvalue(verdict)
            rec["p_value"] = stat.p_value
            pvals[cid] = stat.p_value
            cv_pass_ids.append(cid)
        per_candidate[cid] = rec

    holm = holm_bonferroni(pvals, alpha=alpha)
    survivors = []
    for cid in cv_pass_ids:
        dec = holm[cid]
        per_candidate[cid]["p_adjusted"] = dec.p_adjusted
        per_candidate[cid]["reject"] = dec.reject
        if dec.reject:
            survivors.append(cid)
    return SelectionResult(survivors=sorted(survivors), per_candidate=per_candidate, holm=holm)


# --------------------------------------------------------------------------- #
# Final rescore (§13 "re-scored ONCE on an untouched held-out with NEW seeds")
# --------------------------------------------------------------------------- #

class FinalVerdict:
    """The §13 single reported number: the held-out verdict, its pass flag, and the
    (uncorrected — a single pre-registered test) p-value."""

    __slots__ = ("verdict", "passed", "p_value", "holdout_instances", "new_seeds")

    def __init__(self, verdict, passed, p_value, holdout_instances, new_seeds):
        self.verdict = verdict
        self.passed = bool(passed)
        self.p_value = float(p_value)
        self.holdout_instances = list(holdout_instances)
        self.new_seeds = tuple(new_seeds)

    def __repr__(self):
        return (f"FinalVerdict(passed={self.passed}, p={self.p_value:.4g}, "
                f"n_holdout={len(self.holdout_instances)})")


def rescore_once(winner_factory, baselines, *, holdout_instances, new_seeds,
                 default_solve, candidate_solve, selection_keys,
                 selection_seeds=DEFAULT_SEED_BANK, score_kwargs=None):
    """Re-score the selected rule ONCE on an untouched held-out set with NEW seeds (§13).

    ``default_solve(instances, seeds) -> run_set`` and
    ``candidate_solve(factory, instances, seeds) -> run_set`` are INJECTED (real
    path: :func:`benchmarks.m2.run_sweep` + ``load_run_set_dir``; tests pass stubs,
    no C solve). Leakage guards fire BEFORE solving (a reused seed or instance
    voids the "untouched test with new seeds" guarantee and silently inflates the
    reported significance):

    * ``new_seeds`` disjoint from ``selection_seeds`` (NEW seeds) and all ≥ 1 (bd cjz);
    * ``holdout_instances`` disjoint from ``selection_keys`` (untouched).

    ``selection_keys`` is REQUIRED (no default): the §13 untouched-holdout guarantee
    must not be silently bypassable by omitting it — an empty set RAISES, mirroring
    the seed guard's non-bypassable posture (§2.1).

    Scored with ``strict_xcheck=False`` (a correct NEW-seed default run legitimately
    re-scores away from the frozen ``default_PI``, which was frozen at the selection
    seeds — strict_xcheck=True would wrongly RAISE; the asymmetry vs selection's
    strict_xcheck=True is deliberate). Reports the single number; no FWER (one
    pre-registered test). Keep OUT of the selection loop.
    """
    new_seeds = tuple(int(s) for s in new_seeds)
    sel_seeds = set(int(s) for s in selection_seeds)
    if any(s <= 0 for s in new_seeds):
        raise ValueError(f"holdout seeds must be >= 1 (bd cjz), got {new_seeds}")
    if not set(new_seeds).isdisjoint(sel_seeds):
        raise ValueError(
            f"§13 leakage: holdout seeds {sorted(set(new_seeds) & sel_seeds)} overlap the "
            f"selection seed bank {sorted(sel_seeds)} — the held-out test needs NEW seeds.")
    holdout = [tuple(k) for k in holdout_instances]
    sel_keys = {tuple(k) for k in selection_keys}
    if not sel_keys:
        raise ValueError(
            "§13: selection_keys is required and must be non-empty — the untouched-holdout "
            "disjointness guarantee cannot be verified against an empty selection set.")
    overlap = set(holdout) & sel_keys
    if overlap:
        raise ValueError(
            f"§13 leakage: holdout instances {sorted(overlap)} overlap the selection set — "
            f"the held-out test must be untouched.")

    default_rs = default_solve(holdout, new_seeds)
    candidate_rs = candidate_solve(winner_factory, holdout, new_seeds)
    verdict = metric.score_verdict(candidate_rs, default_rs, baselines,
                                   require_largest_n=False, strict_xcheck=False,
                                   **(score_kwargs or {}))
    stat = candidate_pvalue(verdict)
    return FinalVerdict(verdict=verdict, passed=verdict["overall_pass"],
                        p_value=stat.p_value, holdout_instances=holdout, new_seeds=new_seeds)


# --------------------------------------------------------------------------- #
# Negative control (§13 / §1.3 type-I check)
# --------------------------------------------------------------------------- #

class NegControlResult:
    """Outcome of :func:`negative_control`: ``any_significant`` (MUST be False — a
    True is a FWER leak), the per-candidate audit, the Holm table, and the raw
    :class:`SelectionResult`."""

    __slots__ = ("any_significant", "per_candidate", "holm", "selection")

    def __init__(self, any_significant, per_candidate, holm, selection):
        self.any_significant = bool(any_significant)
        self.per_candidate = dict(per_candidate)
        self.holm = dict(holm)
        self.selection = selection

    def __repr__(self):
        return (f"NegControlResult(any_significant={self.any_significant}, "
                f"survivors={self.selection.survivors})")


def negative_control(baseline_equiv_factories_by_id, default_results, baselines, *,
                     candidate_solve, candidate_instances, candidate_seeds,
                     folds=FOLDS, alpha=ALPHA, strict_xcheck=True, score_kwargs=None):
    """Run the IDENTICAL selection pipeline on baseline-equivalent candidates (§13).

    Each baseline-equivalent factory (e.g.
    :func:`benchmarks.m3_proposer.baseline_equivalent_factory`) is solved via the
    injected ``candidate_solve(factory, instances, seeds)`` at the SAME
    ``candidate_seeds`` as the default reference, so its PI deltas are pure seed
    noise (a real type-I check, not trivially-zero). A correctly-calibrated
    machine yields NO survivor → ``any_significant`` False. The driver should treat
    a True as a fail-loud FWER-leak bug.
    """
    candidate_results_by_id = {
        cid: candidate_solve(factory, candidate_instances, candidate_seeds)
        for cid, factory in baseline_equiv_factories_by_id.items()}
    sel = select_significant(candidate_results_by_id, default_results, baselines,
                             folds=folds, alpha=alpha, strict_xcheck=strict_xcheck,
                             score_kwargs=score_kwargs)
    return NegControlResult(any_significant=bool(sel.survivors),
                            per_candidate=sel.per_candidate, holm=sel.holm, selection=sel)
