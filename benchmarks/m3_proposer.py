"""M3 parametric / evolutionary proposer (bd 8an.4.6, NORTHSTAR §10).

The first concrete ``proposer`` behind the :func:`benchmarks.m3.evolve` seam
(``proposer(population, rng) -> list[Candidate]``). Parametric-first and
pluggable: the LLM-FunSearch proposer (bd 8an.4.7) plugs into the SAME seam
unchanged — :func:`genome_to_factory`'s closed key/feature enumeration is the
shared faithfulness firewall for both.

Search space (M2 collapsed it to ~3 productive dims, ``benchmarks/M2_FINDINGS.md``):

* **per-phase scalar radius** ``r_opt_sat`` / ``r_opt`` — the §1.5 scale-stable
  lever (``bias = n/r − 2`` at every ``n``; emitted as ``branching_radius`` so
  the C path converts and :func:`benchmarks.candidate_gate.check_radius_realization`
  aligns). Radius is *material, size-dependent* (M2d).
* **switch fraction** ``alpha_switch`` ∈ [0, 0.25] — the exploit→explore switch
  encoded as a fraction of ``T(n)`` (NORTHSTAR §4 ``α ≤ 0.25``); emitted as
  ``opt_switch_oracles = round(alpha · T(n))`` PER INSTANCE. M2 found this lever
  **dominant** (same radii: switch swings W from +55 to −55).
* **per-variable θ** ``theta_amp`` × an **allow-listed** feature — the M0f sigmoid
  logit channel (``opt_branching_weights``), opt-phase only (mirrors
  ``m2.theta_pii_pos``). M2f found it **near-null** at |θ|≤0.5 on z(p_ii), so it is
  a *secondary* dimension; kept searchable (amplitude + which feature).

**Held out:** ``variable_order`` (``opt_variable_priorities``) is a legal lever
but has a catastrophic large-n feasibility cliff in BOTH directions (bd 8an.8,
M2_FINDINGS) — it is NOT a genome axis here; the feasibility tier (§6 item 5,
inside :func:`benchmarks.metric.score_verdict`) is what would protect a future
order search, and until that is wired the order lever stays gated.

**Faithfulness by construction (CLAUDE.md §1.4/§1.6/§5):** :data:`FEATURES` is a
CLOSED registry containing EXACTLY the NORTHSTAR §1.4 allow-list
(``p_ii``, objective/constraint row-sums, raw interaction-graph degree). There is
no code path to a banned (LP/SDP/spectral/iterative) feature.
:func:`genome_to_factory` emits ONLY keys in
:data:`benchmarks.candidate_gate.LEGAL_LEVER_PARAMS` and never a
budget/cost/termination override.

Pure Python; no C extension import (tests drive the loop with the stub evaluator
from ``tests/test_m3.py``). All stochasticity flows through the passed numpy
``Generator`` so the population trajectory is reproducible (bd 8an.4.4).
"""
import math

import numpy as np

try:  # package import (pytest / installed) vs flat script import
    from benchmarks import m2, metric
    from benchmarks.m3 import Candidate
except ImportError:  # pragma: no cover - flat layout fallback
    import m2  # type: ignore
    import metric  # type: ignore
    from m3 import Candidate  # type: ignore


# --------------------------------------------------------------------------- #
# Allow-listed per-variable features (NORTHSTAR §1.4) — the CLOSED registry.
# Each is one O(nnz) pass over the (lower-triangular int64) Eq.29 matrices,
# mean-centered + z-scored + clipped to [−1, 1] so the emitted weight stays
# bounded (|weight| <= theta_amp <= 0.5, §1.7). 'none' turns the θ channel OFF.
# --------------------------------------------------------------------------- #

def _zclip(vec):
    """z-score then clip to [−1, 1] (mirror ``m2._pii_z_clipped``; bounded feature)."""
    v = np.asarray(vec, dtype=float)
    sd = v.std()
    z = (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)
    return np.clip(z, -1.0, 1.0)


def _sym_rowsum(mat):
    """Per-variable symmetric weight of a lower-triangular interaction matrix.

    The Eq.29 matrices store ``Σ_{i≥j}`` couplings in the lower triangle, so
    variable ``i``'s total coupling is its row-sum (j ≤ i) plus its column-sum
    (k ≥ i) minus the doubly-counted diagonal. One O(nnz) reduction.
    """
    m = np.asarray(mat)
    return m.sum(axis=1) + m.sum(axis=0) - np.diag(m)


def _sym_degree(mat):
    """Raw off-diagonal interaction-graph degree per variable (nnz count, §1.4)."""
    m = np.asarray(mat) != 0
    deg = m.sum(axis=1) + m.sum(axis=0) - np.diag(m)
    return deg - np.diag(m).astype(deg.dtype)  # drop the self-loop (diagonal nnz)


#: CLOSED feature registry == EXACTLY the NORTHSTAR §1.4 allow-list. Index 0 is
#: the OFF switch. A future feature must be added here (and is then auto-covered
#: by the allow-list / fuzz tests); there is intentionally NO dynamic feature path.
FEATURES = (
    ("none", lambda n, c1, c2, c3: None),
    ("pii_z", lambda n, c1, c2, c3: m2._pii_z_clipped(c1)),                 # diag(c1) = p_ii
    ("obj_rowsum_z", lambda n, c1, c2, c3: _zclip(_sym_rowsum(c1))),        # objective row-sums
    ("cons_rowsum_z", lambda n, c1, c2, c3: _zclip(_sym_rowsum(np.asarray(c2) + np.asarray(c3)))),
    ("degree_z", lambda n, c1, c2, c3: _zclip(_sym_degree(c1))),           # interaction-graph degree
)

#: Genome layout (fixed order, a float64 vector). The loop mutates this vector
#: and uses it as the diversity axis (``m3.Candidate.genome``).
GENES = ("r_opt_sat", "r_opt", "alpha_switch", "theta_amp", "theta_feature")

#: Per-gene bounds. Radius ∈ [1.5, 8]: ``bias = n/r − 2 > −1`` for every anchored
#: ``n ≥ 10`` (n=10, r=8 → bias=−0.75 > −1; phase_params.py:67 guard) and
#: ``r < n`` (so :func:`cbqs.phase_params.radius_to_bias` stays in domain), while
#: bracketing the M2d band r=2..6. ``alpha_switch`` ∈ [0, 0.25] is the §4 ceiling.
#: ``theta_amp`` ∈ [0, 0.5] is the M2f radius-neutral band. ``theta_feature`` ∈
#: [0, len(FEATURES)−ε] so ``floor()`` indexes a valid feature (never over-indexes).
GENE_BOUNDS = {
    "r_opt_sat": (1.5, 8.0),
    "r_opt": (1.5, 8.0),
    "alpha_switch": (0.0, 0.25),
    "theta_amp": (0.0, 0.5),
    "theta_feature": (0.0, len(FEATURES) - 1e-9),
}

#: Default per-gene mutation step, as a FRACTION of each gene's range (so a single
#: σ is comparable across the heterogeneous axes). NORTHSTAR leaves it unpinned.
GENE_SIGMA = 0.1

#: A near-default seed anchor for ``evolve``'s initial population: r=4 gives a
#: scale-invariant realized radius ~4 (close to the default's n/4-bias radius
#: ~3.3–3.7), switch at the default 0.1·T(n), θ off. NOT relied on for the §13
#: negative control — that uses :func:`baseline_equivalent_factory` (emits {},
#: the byte-identical default path), which needs no n-dependent radius round-trip.
BASELINE_GENOME = np.array([4.0, 4.0, 0.1, 0.0, 0.0], dtype=float)


def clamp_genome(genome):
    """Project a genome onto :data:`GENE_BOUNDS` (the single, idempotent bounds
    enforcement point). Raises on a wrong-length genome (fail loud, §2.1)."""
    g = np.array([float(x) for x in genome], dtype=float)
    if g.shape != (len(GENES),):
        raise ValueError(
            f"genome must have {len(GENES)} genes {GENES}, got shape {g.shape}")
    for i, name in enumerate(GENES):
        lo, hi = GENE_BOUNDS[name]
        g[i] = min(max(g[i], lo), hi)
    return g


def random_genome(rng):
    """A uniform-random in-bounds genome (rng-driven; reproducible)."""
    return np.array([rng.uniform(*GENE_BOUNDS[name]) for name in GENES], dtype=float)


def mutate(genome, rng, *, sigma=GENE_SIGMA):
    """Gaussian per-gene step (σ scaled to each gene's range), then clamp.

    All randomness comes from ``rng`` (a numpy ``Generator``) so an identical
    call sequence reproduces the trajectory (bd 8an.4.4).
    """
    g = clamp_genome(genome)
    steps = np.array([rng.normal(0.0, sigma * (GENE_BOUNDS[name][1] - GENE_BOUNDS[name][0]))
                      for name in GENES], dtype=float)
    return clamp_genome(g + steps)


def crossover(g_a, g_b, rng):
    """Per-gene uniform-coin recombination of two genomes, then clamp."""
    a = clamp_genome(g_a)
    b = clamp_genome(g_b)
    mask = rng.random(len(GENES)) < 0.5
    return clamp_genome(np.where(mask, a, b))


def genome_to_factory(genome):
    """Decode a genome into a schedule factory ``f(n, c1, c2, c3) -> {param: value}``.

    The factory emits ONLY keys in
    :data:`benchmarks.candidate_gate.LEGAL_LEVER_PARAMS` — the §1.4/§1.6 allow-list
    holds BY CONSTRUCTION:

    * ``opt_sat_branching_radius`` / ``opt_branching_radius`` — the per-phase
      scalar radius (scale-stable lever; C converts r → bias = n/r − 2).
    * ``opt_switch_oracles`` — ``round(alpha · T(n))`` per instance (the
      [0, α·T(n)] encoding; ``solve()`` re-clamps to [0, 0.25·M] as the backstop).
      NEVER an ``M`` / budget override.
    * ``opt_branching_weights`` (only when θ is active) — ``theta_amp`` times an
      allow-listed, bounded, z-clipped feature vector (opt-phase only).
    """
    g = clamp_genome(genome)
    r_opt_sat, r_opt, alpha_switch, theta_amp, theta_feat = (float(x) for x in g)
    feat_name, feat_fn = FEATURES[int(math.floor(theta_feat))]

    def factory(n, c1, c2, c3):
        # r < n keeps radius_to_bias (phase_params.py:38) in domain (bias > −1);
        # never fires for r ≤ 8 < n ≥ 10, but assert it rather than silently
        # corrupt the lever at a hypothetical tiny n (fail loud, §2.1).
        if not (r_opt_sat < n and r_opt < n):
            raise ValueError(
                f"radius must be < n for a valid bias (r_opt_sat={r_opt_sat}, "
                f"r_opt={r_opt}, n={n}) — bias = n/r − 2 would breach > −1.")
        params = {
            "opt_sat_branching_radius": r_opt_sat,
            "opt_branching_radius": r_opt,
            "opt_switch_oracles": int(round(alpha_switch * metric.oracle_budget(n))),
        }
        if theta_amp > 0.0 and feat_name != "none":
            vec = feat_fn(n, c1, c2, c3)
            params["opt_branching_weights"] = theta_amp * np.asarray(vec, dtype=float)
        return params

    return factory


def baseline_equivalent_factory():
    """A factory emitting ``{}`` — the EXACT CBQS-default path (``close()`` auto-sets
    bias = n/4, ``opt_switch_oracles`` = 0.1·M). The robust §13 negative-control
    candidate: solved at the default's matched seed bank its PI deltas are pure
    seed noise, so a correctly-calibrated multiplicity machine rejects it."""
    def factory(n, c1, c2, c3):
        return {}
    return factory


class ParametricProposer:
    """Evolutionary ``proposer(population, rng) -> list[Candidate]`` over the genome.

    Each call: take the fittest ``ceil(len/2)`` parents (by :class:`m3.Fitness`),
    produce ``n_offspring`` children by mutation (optionally crossover at
    ``crossover_rate``), and wrap each child genome in a :class:`m3.Candidate`
    carrying its decoded factory, the genome tuple (the loop's diversity axis),
    and §13 provenance (``meta``). ``meta['id']`` is REQUIRED — both
    :func:`m3.evaluate_candidate` (run-set subdir) and the m3_select population
    keying read it. Stateless apart from a per-instance id counter, so a fresh
    proposer + fresh ``rng`` reproduces the trajectory.
    """

    def __init__(self, *, n_offspring=8, sigma=GENE_SIGMA, crossover_rate=0.0,
                 id_prefix="cand"):
        if n_offspring < 1:
            raise ValueError(f"n_offspring must be >= 1, got {n_offspring}")
        self.n_offspring = int(n_offspring)
        self.sigma = float(sigma)
        self.crossover_rate = float(crossover_rate)
        self.id_prefix = str(id_prefix)
        self._next_id = 0

    def _make_id(self):
        cid = f"{self.id_prefix}_{self._next_id}"
        self._next_id += 1
        return cid

    def __call__(self, population, rng):
        if not population:
            raise ValueError(
                "ParametricProposer needs a non-empty population to mutate from "
                "(evolve guarantees this — a bare modulo-by-zero would be the silent "
                "alternative, §2.1).")
        parents = sorted(population, key=lambda ind: ind.fitness, reverse=True)
        n_parents = max(1, -(-len(parents) // 2))  # ceil(len/2)
        parents = parents[:n_parents] or list(population)
        out = []
        for i in range(self.n_offspring):
            parent = parents[i % len(parents)]
            child = np.asarray(parent.candidate.genome, dtype=float)
            op = "mutate"
            if (self.crossover_rate > 0.0 and len(parents) > 1
                    and float(rng.random()) < self.crossover_rate):
                mate = parents[int(rng.integers(len(parents)))]
                child = crossover(child, np.asarray(mate.candidate.genome, dtype=float), rng)
                op = "crossover"
            child = mutate(child, rng, sigma=self.sigma)
            out.append(Candidate(
                factory=genome_to_factory(child),
                genome=tuple(float(x) for x in child),
                meta={"id": self._make_id(), "op": op,
                      "parent": tuple(float(x) for x in parent.candidate.genome)}))
        return out
