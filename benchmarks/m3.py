"""M3 agent-loop harness (bd 8an.4, NORTHSTAR §9/§10/§12-M3/§13).

The population search that *discovers* a schedule, layered on the M2 machinery:

* **Candidate** — a schedule factory ``f(n, c1, c2, c3) -> {param: value}`` (the
  same object :mod:`benchmarks.m2` already runs), passed DIRECTLY to
  :func:`benchmarks.m2.run_sweep` — never through the ``SCHEDULES`` registry,
  which raises on duplicate names and so cannot hold a stream of generated
  candidates.
* **Evaluator** — solve the candidate over the anchored strata once per matched
  seed, then :func:`benchmarks.metric.score_verdict` against the frozen default.
  That verdict is a per-stratum dict with no single scalar; this module supplies
  the missing scalar.
* **Selection fitness** (bd 8an.4.1, this file) — :func:`fitness` collapses the
  verdict dict into a SORTABLE :class:`Fitness` (higher = better) that respects
  the NORTHSTAR §6 lexicographic order — feasibility ⊳ §6.6 (W then median PI) ⊳
  §8.3 floor — with the all-gates ``overall_pass`` as the dominant hard gate.

The fitness is PURE over the verdict dict: it does not solve, and it does not
call :func:`score_verdict`. The caller computes the verdict and **fails loud** on
its raises (a degenerate spread, a matched-seed violation, an internal invariant
breach are corrupt input, never "the candidate lost"); :func:`fitness` only ever
sees a well-formed verdict. This keeps the selection logic unit-testable with
canned dicts (no C extension, no solve) — see ``tests/test_m3.py``.
"""

import math

_GATED_OUT_LOST = 10 ** 9  #: lost-feasibility sentinel for an inadmissible candidate

#: PI is the bounded anchored integral γ∈[−γmax, 1] averaged over time, so
#: PI ∈ [−0.5, 1] (NORTHSTAR §6.3, γmax≈0.5). A non-finite median PI (an empty
#: jointly-feasible set — total feasibility collapse) is sanitized to this
#: worst finite level so the fitness stays a TOTAL order (NaN comparisons are
#: all False and would silently corrupt sorted()/max()). Feasibility has already
#: sunk such a candidate via the dominant lost-feasibility key, so the exact
#: sentinel only needs to be "no better than the worst real PI".
_PI_WORST = 1.0


def _w_normalized(rec):
    """Per-stratum signed rank-sum W rescaled to ≈[−1, 1] by its theoretical max.

    W (metric.py:545) is a Wilcoxon-Pratt signed rank-sum over the jointly-
    feasible set J, so its range is ±J(J+1)/2 — a big-J stratum would otherwise
    swamp a small-J one in any cross-stratum mean. Normalizing by W_max(J) makes
    "fraction of the maximum possible win" comparable across sizes. An empty J
    (no jointly-feasible instance) has no measurable win → worst (−1.0); the
    feasibility key dominates that case anyway.
    """
    J = int(rec.get("n_jointly_feasible", 0))
    if J <= 0:
        return -1.0
    w_max = J * (J + 1) / 2.0
    return float(rec["W"]) / w_max if w_max > 0 else 0.0


def _sanitize_pi(value):
    """A finite, lower-is-better median PI (NaN/inf → the worst finite level)."""
    v = float(value)
    return v if math.isfinite(v) else _PI_WORST


def _mean(values, default=0.0):
    vals = list(values)
    return sum(vals) / len(vals) if vals else default


class Fitness:
    """A sortable selection score for one candidate (higher sorts better).

    Ordering is lexicographic over, in priority order:

    1. ``passes_gate`` — ``verdict["overall_pass"]`` (all §6.6 gate_B [and gate_A
       when the largest-n stratum is evaluable] AND the §8.3 floor). A candidate
       that clears every gate strictly outranks any that does not — selection
       promotes only passing candidates (NORTHSTAR §10/§13), but the graded keys
       below still drive mutation pressure among the (initially mostly failing)
       population.
    2. ``-lost_feasibility_total`` — the §6 item-5 feasibility tier, the dominant
       graded key: a candidate that loses feasibility on ANY instance the default
       solved sinks below one that does not, regardless of its W.
    3. ``pi_rank`` — mean normalized §6.6 W across strata (higher = better), the
       magnitude-weighted signed-rank primary signal.
    4. ``pi_median`` — ``−`` mean (sanitized) candidate median PI (lower PI is a
       better gap, so negated to "higher = better"); the §6.6 level tiebreaker.
    5. ``floor_fraction`` — mean §8.3 per-stratum instance-pass fraction; below
       §6.6 in priority (the floor can veto an ``overall_pass`` but never revive
       a §6.6 loss), kept as a graded signal so a better tail breaks PI ties.

    All five are stored finite; the comparison key is the tuple in this order.
    Components are exposed as attributes for the §13 audit log (why a candidate
    ranked where it did).
    """

    __slots__ = ("passes_gate", "lost_feasibility_total", "pi_rank",
                 "pi_median", "floor_fraction", "_key")

    def __init__(self, passes_gate, lost_feasibility_total, pi_rank, pi_median,
                 floor_fraction):
        self.passes_gate = bool(passes_gate)
        self.lost_feasibility_total = int(lost_feasibility_total)
        self.pi_rank = float(pi_rank)
        self.pi_median = float(pi_median)
        self.floor_fraction = float(floor_fraction)
        # higher-is-better tuple: feasibility-first, §6.6 (W then median) ⊳ floor
        self._key = (
            self.passes_gate,
            -self.lost_feasibility_total,
            self.pi_rank,
            self.pi_median,
            self.floor_fraction,
        )

    def __eq__(self, other):
        return isinstance(other, Fitness) and self._key == other._key

    def __lt__(self, other):
        if not isinstance(other, Fitness):
            return NotImplemented
        return self._key < other._key

    def __le__(self, other):
        if not isinstance(other, Fitness):
            return NotImplemented
        return self._key <= other._key

    def __hash__(self):
        return hash(self._key)

    def __repr__(self):
        return (f"Fitness(gate={self.passes_gate}, "
                f"lost_feas={self.lost_feasibility_total}, "
                f"pi_rank={self.pi_rank:.4f}, pi_median={self.pi_median:.4f}, "
                f"floor={self.floor_fraction:.4f})")

    @classmethod
    def gated_out(cls):
        """A minimal Fitness for an inadmissible candidate (failed the §10 gate).

        Sorts strictly below any admitted candidate — even one that regressed
        feasibility on the whole anchored set — because an inadmissible
        (unfaithful / scale-drifting) schedule is never a valid selection, while
        an admissible-but-bad one is at least a measured data point.
        """
        return cls(passes_gate=False, lost_feasibility_total=_GATED_OUT_LOST,
                   pi_rank=-1.0, pi_median=-_PI_WORST, floor_fraction=0.0)


def fitness(verdict):
    """Collapse a :func:`benchmarks.metric.score_verdict` dict into a :class:`Fitness`.

    Pure over ``verdict``; never solves, never calls ``score_verdict``. Reads:

    * ``verdict["overall_pass"]`` — the hard gate.
    * ``verdict["aggregation"]["per_size"][n]`` — ``W``, ``median_PI``,
      ``lost_feasibility``, ``n_jointly_feasible`` (metric.py:550-566).
    * ``verdict["floor"]["per_size"][n]["instance_pass_fraction"]`` (metric.py
      ``_aggregate_floor``); a skipped stratum (``stratum_pass is None`` /
      fraction ``None``) contributes 0 to the mean (no measured tail credit).
    """
    agg = verdict["aggregation"]["per_size"]
    floor = verdict.get("floor", {}).get("per_size", {})

    lost_total = sum(len(rec.get("lost_feasibility", ())) for rec in agg.values())
    pi_rank = _mean(_w_normalized(rec) for rec in agg.values())
    # lower PI is better → negate so the comparison stays "higher = better"
    pi_median = -_mean(_sanitize_pi(rec.get("median_PI")) for rec in agg.values())
    floor_fraction = _mean(
        (rec.get("instance_pass_fraction") or 0.0) for rec in floor.values())

    return Fitness(
        passes_gate=verdict.get("overall_pass", False),
        lost_feasibility_total=lost_total,
        pi_rank=pi_rank,
        pi_median=pi_median,
        floor_fraction=floor_fraction,
    )


# --------------------------------------------------------------------------- #
# Population loop (bd 8an.4.3) — proposer-agnostic. A `proposer` is any callable
# ``proposer(population, rng) -> list[Candidate]`` (the parametric proposer is
# bd 8an.4.6, the LLM proposer bd 8an.4.7; both plug in here unchanged). The
# evaluator is a module-level seam so tests drive the loop with a fake scorer.
# --------------------------------------------------------------------------- #

class Candidate:
    """One schedule proposal: a factory + a genome descriptor + provenance.

    * ``factory`` — ``f(n, c1, c2, c3) -> {param: value}``, the object
      :mod:`benchmarks.m2` runs and :mod:`benchmarks.candidate_gate` resolves.
    * ``genome`` — a tuple/array the proposer mutates and the loop uses for
      DIVERSITY (the parametric genome is the lever vector; an LLM proposer can
      pass a code-embedding or hash). ``None`` disables distance-based diversity
      (exact-duplicate dedup only).
    * ``meta`` — free-form provenance for the §13 audit log (parent genome,
      mutation, generation, …).
    """

    __slots__ = ("factory", "genome", "meta")

    def __init__(self, factory, genome=None, meta=None):
        self.factory = factory
        self.genome = genome
        self.meta = dict(meta or {})


class Individual:
    """An evaluated :class:`Candidate`: its :class:`Fitness`, the raw verdict
    (None when gated out or stubbed), the :class:`~benchmarks.candidate_gate.GateResult`,
    and whether the §10 gate rejected it pre-scoring."""

    __slots__ = ("candidate", "fitness", "verdict", "gate", "gated_out")

    def __init__(self, candidate, fitness, verdict=None, gate=None, gated_out=False):
        self.candidate = candidate
        self.fitness = fitness
        self.verdict = verdict
        self.gate = gate
        self.gated_out = bool(gated_out)


class EvolveResult:
    """Outcome of :func:`evolve`: the surviving ``population`` (list of
    :class:`Individual`, fittest first), the best-ever ``best`` Individual
    (elitism — never lost), the ``history`` of best-so-far :class:`Fitness` (one
    entry for the initial population + one per generation), and ``generations``."""

    __slots__ = ("population", "best", "history", "generations")

    def __init__(self, population, best, history, generations):
        self.population = population
        self.best = best
        self.history = history
        self.generations = generations


def _genome_distance(a, b):
    """Euclidean distance between two genomes; ``inf`` for non-comparable / None
    (so only exact-equal genomes count as "the same" under a distance floor)."""
    if a is None or b is None:
        return 0.0 if a is b or a == b else float("inf")
    ga = [float(x) for x in a]
    gb = [float(x) for x in b]
    if len(ga) != len(gb):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(ga, gb)))


def select_survivors(individuals, k, *, min_genome_distance=0.0):
    """Diversity-preserving elitist truncation: keep the ``k`` fittest, but skip
    a candidate that sits within ``min_genome_distance`` of an already-kept one
    (NORTHSTAR §10 "the population preserves diversity"). The single best is
    always kept first (elitism). With ``min_genome_distance == 0`` this is plain
    top-``k`` truncation. Deterministic: ties break by the genome tuple.
    """
    ordered = sorted(
        individuals,
        key=lambda ind: (ind.fitness, tuple(ind.candidate.genome or ())),
        reverse=True,
    )
    kept = []
    deferred = []
    for ind in ordered:
        if len(kept) >= k:
            break
        if min_genome_distance > 0 and any(
                _genome_distance(ind.candidate.genome, s.candidate.genome)
                < min_genome_distance for s in kept):
            deferred.append(ind)
            continue
        kept.append(ind)
    # backfill with the best deferred (near-duplicate) individuals if diversity
    # pruning left us short of k — never return fewer than min(k, available).
    for ind in deferred:
        if len(kept) >= k:
            break
        kept.append(ind)
    return kept


def evaluate_candidate(candidate, *, default_results, baselines, instances, seeds,
                       out_dir, bench_root=None, num_workers=None,
                       opt_sample_cap=0, gate_scale_ns=(100, 1000),
                       scale_check=True, score_kwargs=None):
    """Gate → solve → score → :func:`fitness` for one candidate (the real evaluator).

    Module-level so the loop calls ``m3.evaluate_candidate`` by name and tests
    monkeypatch it with a stub (no solve). Steps:

    1. **§10 gate** (``candidate_gate.admit``) — an inadmissible candidate gets
       :meth:`Fitness.gated_out` and is never solved (saves the ~20 min–3.6 h).
    2. **Solve** the candidate over ``instances`` at the matched ``seeds`` and
       equal ``T(n)`` (``benchmarks.m2.run_sweep``; ``require_verified`` guards
       the run-set), persisting under ``out_dir``.
    3. **Score** vs the *live* default run-set (``score_verdict``, strict_xcheck
       ON) — the default is solved ONCE by the caller and replayed (landmine #4).
    4. **Fitness** from the verdict.

    A ``score_verdict`` raise propagates (corrupt input / invariant breach — fail
    loud, landmine #2); it is NOT swallowed as "candidate lost".
    """
    from benchmarks import candidate_gate, m2, metric

    gate = candidate_gate.admit(candidate.factory, scale_ns=gate_scale_ns,
                                scale_check=scale_check)
    if not gate.ok:
        return Individual(candidate, Fitness.gated_out(), verdict=None,
                          gate=gate, gated_out=True)

    m2.run_sweep(candidate.meta.get("id", "m3_candidate"), candidate.factory,
                 instances, out_dir=out_dir, seeds=seeds, bench_root=bench_root,
                 num_workers=num_workers, opt_sample_cap=opt_sample_cap)
    candidate_results = m2.load_run_set_dir(out_dir)
    verdict = metric.score_verdict(candidate_results, default_results, baselines,
                                   strict_xcheck=True, require_largest_n=False,
                                   **(score_kwargs or {}))
    return Individual(candidate, fitness(verdict), verdict=verdict, gate=gate,
                      gated_out=False)


def evolve(proposer, *, rng, generations, pop_size, init_population=(),
           evaluator=None, eval_kwargs=None, min_genome_distance=0.0,
           log=lambda *a: None):
    """Run the population search (NORTHSTAR §10).

    ``proposer(population, rng) -> list[Candidate]`` is the pluggable mutation
    seam; ``evaluator(candidate, **eval_kwargs) -> Individual`` defaults to the
    module-level :func:`evaluate_candidate` (resolved at call time so a
    monkeypatch takes effect). Each generation: propose offspring from the
    current population, evaluate them, then :func:`select_survivors` down to
    ``pop_size`` (diversity-preserving, elitist). ``rng`` (a numpy ``Generator``)
    makes the trajectory reproducible (bd 8an.4.4) — all stochasticity lives in
    the proposer; selection is deterministic.
    """
    eval_kwargs = dict(eval_kwargs or {})

    def _eval(cand):
        fn = evaluator if evaluator is not None else evaluate_candidate
        return fn(cand, **eval_kwargs)

    population = [_eval(c) for c in init_population]
    if not population:
        raise ValueError("evolve needs a non-empty init_population to seed the search")
    population = select_survivors(population, pop_size,
                                  min_genome_distance=min_genome_distance)
    best = max(population, key=lambda ind: ind.fitness)
    history = [best.fitness]

    for gen in range(generations):
        offspring = [_eval(c) for c in proposer(population, rng)]
        population = select_survivors(population + offspring, pop_size,
                                      min_genome_distance=min_genome_distance)
        gen_best = max(population, key=lambda ind: ind.fitness)
        if gen_best.fitness > best.fitness:
            best = gen_best
        # elitism: the best-ever individual is always retained in the population
        if best not in population:
            population = select_survivors(population + [best], pop_size,
                                          min_genome_distance=min_genome_distance)
        history.append(best.fitness)
        log(f"[m3] gen {gen + 1}/{generations}: best {best.fitness!r}")

    population = sorted(population, key=lambda ind: ind.fitness, reverse=True)
    return EvolveResult(population=population, best=best, history=history,
                        generations=generations)
