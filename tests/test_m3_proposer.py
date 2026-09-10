"""Tests for the M3 parametric/evolutionary proposer (benchmarks/m3_proposer.py, bd 8an.4.6).

Stub-based — no C extension, no real solves (mirrors tests/test_m3.py). The
proposer is pure runtime data: a genome -> factory decode plus rng-driven
mutation behind the m3.evolve seam. The faithfulness firewall (§1.4 feature
allow-list, §1.6 legal-lever-only output) is the central thing under test.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import m3, m3_proposer as P  # noqa: E402
from benchmarks.candidate_gate import LEGAL_LEVER_PARAMS, _FAITHFULNESS_BREACH_PARAMS  # noqa: E402
from benchmarks.synthetic_eq29 import make_matrices  # noqa: E402
from benchmarks.m3 import Candidate, Fitness  # noqa: E402


# --------------------------------------------------------------------------- #
# §1.4 feature allow-list — the CLOSED registry holds by construction.
# --------------------------------------------------------------------------- #

def test_features_are_exactly_the_northstar_allowlist():
    # NORTHSTAR §1.4: {p_ii, objective & constraint row-sums, raw interaction-graph
    # degree, nnz}. The registry must be EXACTLY these (+ the 'none' off switch);
    # a future spectral/LP feature must not be able to slip in unnoticed.
    names = [name for name, _ in P.FEATURES]
    assert names == ["none", "pii_z", "obj_rowsum_z", "cons_rowsum_z", "degree_z"]
    # no banned-feature vocabulary anywhere in the registry names
    banned = ("eigen", "pagerank", "kcore", "k_core", "betweenness", "spectral",
              "lp", "sdp", "centrality")
    blob = " ".join(names).lower()
    assert not any(b in blob for b in banned)


def test_genome_to_factory_emits_only_legal_levers_for_fuzzed_population():
    # The firewall (§1.6): EVERY decoded candidate, at EVERY size, sets only keys
    # in LEGAL_LEVER_PARAMS — never a budget/cost/termination override.
    rng = np.random.default_rng(0)
    seen_keys = set()
    for _ in range(300):
        factory = P.genome_to_factory(P.random_genome(rng))
        for n in (10, 40, 90, 100, 1000):
            c1, c2, c3 = make_matrices(n, 0)
            params = factory(n, c1, c2, c3)
            seen_keys |= set(params)
            assert set(params) <= set(LEGAL_LEVER_PARAMS)
            assert set(params).isdisjoint(_FAITHFULNESS_BREACH_PARAMS)
            assert "opt_variable_priorities" not in params  # order lever HELD OUT
    # the radius + switch keys are always emitted; weights only sometimes
    assert {"opt_sat_branching_radius", "opt_branching_radius",
            "opt_switch_oracles"} <= seen_keys


def test_variable_order_is_never_a_genome_axis():
    # bd 8an.8 / M2_FINDINGS: variable_order has a large-n feasibility cliff — it is
    # held out of the search entirely, not merely defaulted off.
    assert "variable_priorities" not in " ".join(P.GENES)
    assert all("priorit" not in g for g in P.GENES)


# --------------------------------------------------------------------------- #
# Switch encoding (§4 alpha<=0.25 as a fraction of T(n), per instance).
# --------------------------------------------------------------------------- #

def test_switch_is_a_fraction_of_T_n_per_instance():
    from benchmarks.metric import oracle_budget
    # alpha at the ceiling 0.25 -> opt_switch_oracles ~ 0.25*T(n), scaling with n.
    g = P.clamp_genome([4.0, 6.0, 0.25, 0.0, 0.0])
    factory = P.genome_to_factory(g)
    vals = {}
    for n in (10, 100, 1000):
        c1, c2, c3 = make_matrices(n, 0)
        sw = factory(n, c1, c2, c3)["opt_switch_oracles"]
        vals[n] = sw
        assert sw == int(round(0.25 * oracle_budget(n)))
        assert sw <= int(round(0.25 * oracle_budget(n)))  # never exceeds the §4 ceiling
    assert vals[1000] > vals[100] > vals[10]  # scales with T(n)


def test_alpha_zero_switches_immediately():
    g = P.clamp_genome([4.0, 6.0, 0.0, 0.0, 0.0])
    c1, c2, c3 = make_matrices(40, 0)
    assert P.genome_to_factory(g)(40, c1, c2, c3)["opt_switch_oracles"] == 0


# --------------------------------------------------------------------------- #
# Theta channel: bounded, opt-phase only, off when amp=0 or feature='none'.
# --------------------------------------------------------------------------- #

def test_theta_weights_bounded_and_opt_phase_only():
    g = P.clamp_genome([4.0, 6.0, 0.1, 0.5, 1.0])  # theta_amp=0.5, feature=pii_z
    c1, c2, c3 = make_matrices(50, 0)
    params = P.genome_to_factory(g)(50, c1, c2, c3)
    w = params["opt_branching_weights"]
    assert len(w) == 50
    assert float(np.max(np.abs(w))) <= 0.5 + 1e-12        # |w| <= theta_amp <= 0.5
    # opt-phase ONLY (no sat_/opt_sat_ weights), mirroring m2.theta_pii_pos
    assert not any(k.endswith("branching_weights") and k != "opt_branching_weights"
                   for k in params)


def test_theta_off_emits_no_weights():
    c1, c2, c3 = make_matrices(40, 0)
    # amp 0 -> off
    off_amp = P.genome_to_factory(P.clamp_genome([4.0, 6.0, 0.1, 0.0, 1.0]))
    assert "opt_branching_weights" not in off_amp(40, c1, c2, c3)
    # feature 'none' (index 0) -> off even with amp>0
    off_feat = P.genome_to_factory(P.clamp_genome([4.0, 6.0, 0.1, 0.5, 0.0]))
    assert "opt_branching_weights" not in off_feat(40, c1, c2, c3)


def test_every_feature_is_bounded_and_length_n():
    rng = np.random.default_rng(3)
    for idx in range(1, len(P.FEATURES)):  # skip 'none'
        g = P.clamp_genome([4.0, 6.0, 0.1, 0.5, idx + 0.5])
        for n in (20, 80):
            c1, c2, c3 = make_matrices(n, int(rng.integers(5)))
            w = P.genome_to_factory(g)(n, c1, c2, c3)["opt_branching_weights"]
            assert len(w) == n
            assert np.all(np.isfinite(w))
            assert float(np.max(np.abs(w))) <= 0.5 + 1e-12


def test_theta_feature_index_never_over_indexes_at_upper_bound():
    # theta_feature at its bound floors to the LAST feature, not out of range.
    hi = P.GENE_BOUNDS["theta_feature"][1]
    g = P.clamp_genome([4.0, 6.0, 0.1, 0.5, hi])
    assert int(math.floor(g[4])) == len(P.FEATURES) - 1
    c1, c2, c3 = make_matrices(30, 0)
    P.genome_to_factory(g)(30, c1, c2, c3)  # must not IndexError


# --------------------------------------------------------------------------- #
# Bounds / clamping / mutation.
# --------------------------------------------------------------------------- #

def test_clamp_projects_onto_bounds():
    g = P.clamp_genome([100.0, -5.0, 9.0, 99.0, -1.0])
    assert g[0] == P.GENE_BOUNDS["r_opt_sat"][1]      # 8.0
    assert g[1] == P.GENE_BOUNDS["r_opt"][0]          # 1.5
    assert g[2] == P.GENE_BOUNDS["alpha_switch"][1]   # 0.25
    assert g[3] == P.GENE_BOUNDS["theta_amp"][1]      # 0.5
    assert g[4] == P.GENE_BOUNDS["theta_feature"][0]  # 0.0


def test_clamp_rejects_wrong_length():
    with pytest.raises(ValueError):
        P.clamp_genome([1.0, 2.0, 3.0])


def test_random_genome_in_bounds():
    rng = np.random.default_rng(9)
    for _ in range(100):
        g = P.random_genome(rng)
        for i, name in enumerate(P.GENES):
            lo, hi = P.GENE_BOUNDS[name]
            assert lo <= g[i] <= hi


def test_mutate_and_crossover_stay_in_bounds():
    rng = np.random.default_rng(2)
    g = P.random_genome(rng)
    for _ in range(200):
        g = P.mutate(g, rng, sigma=2.0)  # big sigma to push against bounds
        for i, name in enumerate(P.GENES):
            lo, hi = P.GENE_BOUNDS[name]
            assert lo <= g[i] <= hi
    child = P.crossover(P.random_genome(rng), P.random_genome(rng), rng)
    for i, name in enumerate(P.GENES):
        lo, hi = P.GENE_BOUNDS[name]
        assert lo <= child[i] <= hi


def test_mutate_is_deterministic_under_fixed_rng():
    g0 = np.array([4.0, 6.0, 0.1, 0.2, 1.0])
    a = P.mutate(g0, np.random.default_rng(7))
    b = P.mutate(g0, np.random.default_rng(7))
    assert np.allclose(a, b)
    c = P.mutate(g0, np.random.default_rng(8))
    assert not np.allclose(a, c)


def test_genome_to_factory_fails_loud_when_radius_not_below_n():
    # r < n is the bias-domain invariant; never fires in-bounds (r<=8<n>=10) but
    # must fail loud at a hypothetical tiny n (§2.1), not silently corrupt the lever.
    factory = P.genome_to_factory(P.clamp_genome([8.0, 8.0, 0.1, 0.0, 0.0]))
    c1, c2, c3 = make_matrices(8, 0)  # n=8 < r=8
    with pytest.raises(ValueError):
        factory(8, c1, c2, c3)


def test_baseline_equivalent_factory_emits_empty_default_path():
    c1, c2, c3 = make_matrices(40, 0)
    assert P.baseline_equivalent_factory()(40, c1, c2, c3) == {}


# --------------------------------------------------------------------------- #
# ParametricProposer behind the m3.evolve seam.
# --------------------------------------------------------------------------- #

def test_proposer_returns_candidates_with_unique_ids_and_genomes():
    prop = P.ParametricProposer(n_offspring=6)
    seed_pop = [m3.Individual(candidate=Candidate(P.genome_to_factory(P.BASELINE_GENOME),
                                                  genome=tuple(P.BASELINE_GENOME)),
                              fitness=Fitness(True, 0, 0.0, -0.3, 1.0))]
    offspring = prop(seed_pop, np.random.default_rng(0))
    assert len(offspring) == 6
    ids = [c.meta["id"] for c in offspring]
    assert len(set(ids)) == 6                      # unique ids (population keying)
    for c in offspring:
        assert len(c.genome) == len(P.GENES)
        assert callable(c.factory)
        assert "parent" in c.meta and "op" in c.meta


def test_proposer_raises_loud_on_empty_population():
    # fail loud (§2.1), not a bare ZeroDivisionError from the parent modulo.
    with pytest.raises(ValueError):
        P.ParametricProposer(n_offspring=2)([], np.random.default_rng(0))


#: A genome-space toy landscape (no solve): fitness rises toward the M2-optimal
#: corner (r_opt~6, switch~0). Maps a genome to a real Fitness (the loop sort key).
_OPT = np.array([2.0, 6.0, 0.0])


def _fit_from_genome(genome):
    g = np.asarray(genome, dtype=float)[:3]
    dist = float(np.linalg.norm(g - _OPT))
    return Fitness(passes_gate=dist < 1.0, lost_feasibility_total=0,
                   pi_rank=-dist, pi_median=-0.3, floor_fraction=1.0)


def _fake_evaluator(candidate, **_kw):
    return m3.Individual(candidate=candidate, fitness=_fit_from_genome(candidate.genome),
                         verdict=None, gate=None, gated_out=False)


def _seed_population():
    genomes = [P.BASELINE_GENOME,
               np.array([6.0, 2.0, 0.2, 0.0, 0.0]),
               np.array([3.0, 4.0, 0.1, 0.3, 1.0])]
    return [Candidate(P.genome_to_factory(g), genome=tuple(g), meta={"id": f"seed{i}"})
            for i, g in enumerate(genomes)]


def test_proposer_drives_evolve_toward_the_optimum():
    res = m3.evolve(P.ParametricProposer(n_offspring=6, sigma=0.2),
                    rng=np.random.default_rng(0), generations=12, pop_size=6,
                    init_population=_seed_population(), evaluator=_fake_evaluator)
    # the search should improve on the seed population's best pi_rank
    seed_best = max(_fit_from_genome(c.genome) for c in _seed_population())
    assert res.best.fitness.pi_rank > seed_best.pi_rank
    # monotone best-so-far (elitism, inherited from evolve)
    for a, b in zip(res.history, res.history[1:]):
        assert b >= a


def test_proposer_evolve_is_deterministic_under_fixed_seed():
    def run():
        r = m3.evolve(P.ParametricProposer(n_offspring=5), rng=np.random.default_rng(42),
                      generations=6, pop_size=5, init_population=_seed_population(),
                      evaluator=_fake_evaluator)
        return [tuple(round(x, 9) for x in ind.candidate.genome) for ind in r.population]
    assert run() == run()
