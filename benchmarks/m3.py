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
