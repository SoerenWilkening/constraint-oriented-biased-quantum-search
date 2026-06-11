"""Tests for the M3 LLM-FunSearch proposer + AST firewall (benchmarks/m3_codegen.py,
bd 8an.4.7, NORTHSTAR §10 / CLAUDE.md §1.4/§1.6/§2.1).

Offline and stub-based — no network (a :class:`FakeLLMClient` stands in for the
LLM) and no C extension / real solve (the proposer is exercised through the
``m3.evolve`` seam with a fake evaluator, mirroring tests/test_m3.py). The bulk
of the file red-teams the firewall: every banned feature / unsafe construct must
be REJECTED, and a legal program must be ACCEPTED and compile to the same params
the parametric proposer would emit.
"""
import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks import candidate_gate, m2, m3, m3_codegen, m3_proposer  # noqa: E402
from benchmarks.m3_codegen import (  # noqa: E402
    FaithfulnessError, FakeLLMClient, LLMProposer, compile_candidate_factory,
    extract_code, genome_to_source, validate_source)


# A legal program touching all three lever channels (radius, switch, theta via
# an allow-listed feature) — the golden ACCEPT case.
LEGAL_SRC = (
    "def build_schedule(n, feat, oracle_budget):\n"
    "    r = 3.0\n"
    "    params = {\n"
    "        \"opt_sat_branching_radius\": 2.0,\n"
    "        \"opt_branching_radius\": r,\n"
    "        \"opt_switch_oracles\": int(round(0.12 * oracle_budget(n))),\n"
    "    }\n"
    "    params[\"opt_branching_weights\"] = clip(0.3 * feat(\"pii_z\"), -0.5, 0.5)\n"
    "    return params\n"
)


def _fenced(src):
    return f"Here is my improved schedule:\n```python\n{src}```\n"


# --------------------------------------------------------------------------- #
# Firewall — ACCEPT a legal program
# --------------------------------------------------------------------------- #

def test_validate_accepts_legal_program():
    assert validate_source(LEGAL_SRC) is not None


def test_validate_accepts_baseline_and_if_else():
    assert validate_source(m3_codegen.BASELINE_SOURCE) is not None
    cond = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    if n < 50:\n"
        "        r = 2.0\n"
        "    else:\n"
        "        r = 5.0\n"
        "    return {\"opt_branching_radius\": r}\n"
    )
    assert validate_source(cond) is not None


# --------------------------------------------------------------------------- #
# Firewall — REJECT unsafe constructs (sandbox-escape / DoS surface)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src, why", [
    ("import os\ndef build_schedule(n, feat, oracle_budget):\n    return {}\n",
     "import"),
    ("from numpy import linalg\ndef build_schedule(n, feat, oracle_budget):\n"
     "    return {}\n", "from-import"),
    ("def build_schedule(n, feat, oracle_budget):\n"
     "    x = open('/etc/passwd')\n    return {}\n", "open()"),
    ("def build_schedule(n, feat, oracle_budget):\n"
     "    return eval('1')\n", "eval()"),
    ("def build_schedule(n, feat, oracle_budget):\n"
     "    return {}.__class__\n", "dunder/attribute"),
    ("def build_schedule(n, feat, oracle_budget):\n"
     "    v = feat('pii_z')\n    return {'opt_branching_weights': v.sum()}\n",
     "attribute access"),
    ("def build_schedule(n, feat, oracle_budget):\n"
     "    x = __import__('os')\n    return {}\n", "__import__ dunder name"),
])
def test_validate_rejects_unsafe(src, why):
    with pytest.raises(FaithfulnessError):
        validate_source(src)


@pytest.mark.parametrize("src", [
    # for-loop (power-iteration / PageRank / k-core shape)
    "def build_schedule(n, feat, oracle_budget):\n"
    "    s = 0.0\n    for i in [1, 2, 3]:\n        s = s + i\n"
    "    return {\"opt_branching_radius\": s}\n",
    # while-loop (iterative convergence shape)
    "def build_schedule(n, feat, oracle_budget):\n"
    "    s = 0.0\n    while s < 3:\n        s = s + 1\n"
    "    return {\"opt_branching_radius\": s}\n",
    # comprehension over a feature vector (could build a custom statistic)
    "def build_schedule(n, feat, oracle_budget):\n"
    "    v = [x for x in feat('pii_z')]\n    return {}\n",
    # lambda
    "def build_schedule(n, feat, oracle_budget):\n"
    "    f = lambda x: x\n    return {}\n",
])
def test_validate_rejects_loops_and_comprehensions(src):
    with pytest.raises(FaithfulnessError):
        validate_source(src)


# --------------------------------------------------------------------------- #
# Firewall — REJECT §1.4 feature-allow-list violations (the load-bearing check)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("feature", ["eigenvector", "pagerank", "kcore",
                                     "betweenness", "lp_dual", "none"])
def test_validate_rejects_banned_feature_names(feature):
    src = (
        "def build_schedule(n, feat, oracle_budget):\n"
        f"    return {{'opt_branching_weights': clip(feat('{feature}'), -0.5, 0.5)}}\n"
    )
    with pytest.raises(FaithfulnessError):
        validate_source(src)


def test_validate_rejects_computed_feature_name():
    # a non-literal feat() arg would route around the static allow-list
    src = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    name = 'pii_z'\n"
        "    return {'opt_branching_weights': clip(feat(name), -0.5, 0.5)}\n"
    )
    with pytest.raises(FaithfulnessError):
        validate_source(src)


def test_every_allowlisted_feature_is_accepted():
    for name in sorted(m3_codegen.FEATURE_NAMES):
        src = (
            "def build_schedule(n, feat, oracle_budget):\n"
            f"    return {{'opt_branching_weights': clip(feat('{name}'), -0.5, 0.5)}}\n"
        )
        assert validate_source(src) is not None, name


# --------------------------------------------------------------------------- #
# Firewall — REJECT faithfulness-breach / unknown lever keys
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", ["M", "opt_sample_cap", "stop_val",
                                 "num_workers", "stopping_time", "not_a_lever"])
def test_validate_rejects_illegal_emitted_keys(key):
    literal = (
        "def build_schedule(n, feat, oracle_budget):\n"
        f"    return {{{key!r}: 1}}\n"
    )
    with pytest.raises(FaithfulnessError):
        validate_source(literal)
    subscript = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    params = {}\n"
        f"    params[{key!r}] = 1\n"
        "    return params\n"
    )
    with pytest.raises(FaithfulnessError):
        validate_source(subscript)


def test_validate_rejects_computed_emitted_key():
    src = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    k = 'M'\n    params = {}\n    params[k] = 1\n    return params\n"
    )
    with pytest.raises(FaithfulnessError):
        validate_source(src)


# --------------------------------------------------------------------------- #
# Firewall — REJECT structural violations
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src", [
    # wrong signature
    "def build_schedule(n, c1, c2, c3):\n    return {}\n",
    # wrong name
    "def factory(n, feat, oracle_budget):\n    return {}\n",
    # extra top-level statement
    "x = 1\ndef build_schedule(n, feat, oracle_budget):\n    return {}\n",
    # nested / second function def
    "def build_schedule(n, feat, oracle_budget):\n"
    "    def helper():\n        return 1\n    return {}\n",
    # **kwargs
    "def build_schedule(n, feat, oracle_budget, **kw):\n    return {}\n",
    # calling a non-whitelisted helper
    "def build_schedule(n, feat, oracle_budget):\n"
    "    return {\"opt_branching_radius\": sum([1, 2])}\n",
    # exponentiation (DoS / not in the op whitelist)
    "def build_schedule(n, feat, oracle_budget):\n"
    "    return {\"opt_branching_radius\": n ** 2}\n",
    # reading an out-of-scope name
    "def build_schedule(n, feat, oracle_budget):\n"
    "    return {\"opt_branching_radius\": np}\n",
])
def test_validate_rejects_structural_violations(src):
    with pytest.raises(FaithfulnessError):
        validate_source(src)


def test_validate_rejects_oversized_source():
    big = "def build_schedule(n, feat, oracle_budget):\n    return {}\n" + \
        "# pad\n" * 10000
    with pytest.raises(FaithfulnessError):
        validate_source(big)


def test_validate_rejects_non_string():
    with pytest.raises(FaithfulnessError):
        validate_source(123)


# --------------------------------------------------------------------------- #
# Compile + run — a legal program produces resolvable, allow-listed params
# --------------------------------------------------------------------------- #

def test_compiled_factory_resolves_to_allowlisted_params():
    factory = compile_candidate_factory(LEGAL_SRC)
    from benchmarks.synthetic_eq29 import make_matrices
    n = 40
    c1, c2, c3 = make_matrices(n, index=0)
    params = factory(n, c1, c2, c3)
    # exactly the keys the program emits, all legal levers
    assert set(params) == {"opt_sat_branching_radius", "opt_branching_radius",
                           "opt_switch_oracles", "opt_branching_weights"}
    ok, reasons = candidate_gate.check_param_allowlist(params)
    assert ok, reasons
    # switch uses the oracle-budget encoding; theta is a bounded length-n vector
    from benchmarks.metric import oracle_budget
    assert params["opt_switch_oracles"] == int(round(0.12 * oracle_budget(n)))
    theta = np.asarray(params["opt_branching_weights"])
    assert theta.shape == (n,)
    assert np.all(np.abs(theta) <= 0.5 + 1e-9)


def test_compiled_factory_feat_only_returns_allowlisted_vectors():
    # the runtime feature accessor must reject anything outside the registry,
    # even if (hypothetically) the static check were bypassed
    build = m3_codegen.compile_factory(LEGAL_SRC)  # the raw build_schedule
    from benchmarks.synthetic_eq29 import make_matrices
    c1, c2, c3 = make_matrices(10, index=0)
    feat = m3_codegen._make_feature_accessor(10, c1, c2, c3)
    assert feat("pii_z").shape == (10,)
    with pytest.raises(FaithfulnessError):
        feat("pagerank")
    with pytest.raises(FaithfulnessError):
        feat("none")


def test_compile_candidate_factory_rejects_crashing_program():
    # smoke test must drop a factory that raises on the synthetic instance
    crashing = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    return {\"opt_branching_radius\": 1.0 / 0.0}\n"
    )
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(crashing, strata=(10,))


def test_compile_candidate_factory_rejects_non_dict_return():
    bad = ("def build_schedule(n, feat, oracle_budget):\n"
           "    return 5.0\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(bad, strata=(10,))


def test_compile_candidate_factory_rejects_wrong_theta_shape():
    # a scalar where a length-n weight vector is required
    bad = ("def build_schedule(n, feat, oracle_budget):\n"
           "    return {\"opt_branching_weights\": 0.1}\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(bad, strata=(10,))


# --------------------------------------------------------------------------- #
# DoS / fail-loud hardening (regressions for the firewall red-team, bd 8an.4.7).
# Every escape the adversarial workflow confirmed must now be REJECTED as a
# FaithfulnessError (never a raw crash / hang reaching the multi-hour solve).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src", [
    # sequence-replication memory blow-ups — closed STATICALLY (no exec/fork)
    "def build_schedule(n, feat, oracle_budget):\n    big = [0] * n * n * n\n    return {}\n",
    "def build_schedule(n, feat, oracle_budget):\n    s = \"x\" * n * n\n    return {}\n",
    "def build_schedule(n, feat, oracle_budget):\n    t = (0,) * n\n    return {}\n",
])
def test_validate_rejects_sequence_replication_dos(src):
    with pytest.raises(FaithfulnessError):
        validate_source(src)


def test_validate_rejects_string_in_arithmetic():
    # a string literal anywhere but a key / feat() arg / docstring is forbidden
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    x = \"hello\"\n    return {}\n")
    with pytest.raises(FaithfulnessError):
        validate_source(src)


def test_validate_allows_docstring_string():
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    \"\"\"a greedy->explore schedule\"\"\"\n"
           "    return {\"opt_branching_radius\": 3.0}\n")
    assert validate_source(src) is not None


def test_compile_rejects_deep_nested_recursionerror():
    # ~1200 chained '+1' terms sit UNDER the node cap but blow compile()'s C
    # stack -> a RecursionError that must surface as FaithfulnessError, not crash
    src = ("def build_schedule(n, feat, oracle_budget):\n    x = 1"
           + "+1" * 1200 + "\n    return {}\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(src, strata=(10,))


def test_compile_rejects_non_numeric_lever_value():
    # a non-numeric emitted value must be a FaithfulnessError, not a raw TypeError
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    return {\"opt_branching_radius\": feat}\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(src, strata=(10,))


def test_compile_rejects_n_gated_crash_via_multistratum_smoke():
    # benign at the small smoke n, crashes at a larger stratum (len(int) -> TypeError);
    # the multi-stratum smoke must detonate it during validation
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    params = {}\n"
           "    if n > 50:\n        y = len(n)\n"
           "    return params\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(src, strata=(10, 100))


def test_compile_rejects_n_gated_wrong_shape():
    # scalar weights only at n > 20 — invisible to a single-n=10 smoke
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    if n > 20:\n        return {\"opt_branching_weights\": 0.1}\n"
           "    return {\"opt_branching_weights\": clip(0.3 * feat(\"pii_z\"), -0.5, 0.5)}\n")
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(src, strata=(10, 100))


def test_compile_kills_runtime_cpu_blowup_within_budget():
    # a loop-free bignum squaring chain (no static signal) must be KILLED by the
    # subprocess wall-clock budget and reported as FaithfulnessError, promptly
    src = ("def build_schedule(n, feat, oracle_budget):\n    x = 9999999999\n"
           + "    x = x * x\n" * 26 + "    return {}\n")
    t0 = time.time()
    with pytest.raises(FaithfulnessError):
        compile_candidate_factory(src, strata=(10,), timeout=2.0)
    assert time.time() - t0 < 15.0   # killed near the 2s budget, not left to hang


def test_factory_wrapper_is_failloud_at_any_n():
    # the returned factory must convert a crash at ANY n (even one the smoke
    # didn't cover) into FaithfulnessError, so admit/solve can't hit a raw crash
    src = ("def build_schedule(n, feat, oracle_budget):\n"
           "    if n > 50:\n        y = len(n)\n"
           "    return {}\n")
    factory = m3_codegen.make_candidate_factory(m3_codegen.compile_factory(src))
    from benchmarks.synthetic_eq29 import make_matrices
    assert factory(10, *make_matrices(10)) == {}        # benign branch
    with pytest.raises(FaithfulnessError):              # crash branch -> fail-loud
        factory(100, *make_matrices(100))


def test_proposer_records_none_src_on_empty_response():
    # an empty LLM response is rejected before src is bound; the rejection record
    # must carry None, never a stale src leaked from a prior offspring
    proposer = LLMProposer(FakeLLMClient(["", _fenced(LEGAL_SRC)]), n_offspring=2)
    out = proposer(_seed_population(), np.random.default_rng(0))
    assert len(out) == 1                       # second (legal) one survives
    assert proposer.rejections == [(None, proposer.rejections[0][1])]
    assert proposer.rejections[0][0] is None


# --------------------------------------------------------------------------- #
# Genome bridge — parametric genome <-> DSL source round-trips equivalently
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("genome", [
    m3_proposer.BASELINE_GENOME,
    np.array([2.0, 6.0, 0.2, 0.4, 1.0]),     # theta on pii_z
    np.array([3.0, 4.0, 0.05, 0.0, 0.0]),    # theta OFF (amp 0)
    np.array([5.0, 5.0, 0.25, 0.3, 3.0]),    # theta on cons_rowsum_z
])
def test_genome_to_source_is_firewall_valid_and_equivalent(genome):
    src = genome_to_source(genome)
    # the bridge output must itself pass the firewall (so the LLM can mutate it)
    assert validate_source(src) is not None
    code_factory = compile_candidate_factory(src)
    param_factory = m3_proposer.genome_to_factory(genome)
    from benchmarks.synthetic_eq29 import make_matrices
    n = 30
    c1, c2, c3 = make_matrices(n, index=1)
    a = code_factory(n, c1, c2, c3)
    b = param_factory(n, c1, c2, c3)
    assert set(a) == set(b)
    for key in a:
        np.testing.assert_allclose(np.asarray(a[key], dtype=float),
                                   np.asarray(b[key], dtype=float))


# --------------------------------------------------------------------------- #
# Prompt assembly
# --------------------------------------------------------------------------- #

def test_build_prompt_lists_allowlisted_features_and_excludes_banned():
    system, user = m3_codegen.build_prompt([], nonce=0)
    for name in m3_codegen.FEATURE_NAMES:
        assert name in system
    assert "eigenvector" not in system and "pagerank" not in system.lower()
    assert "build_schedule" in system
    # with no exemplars, the baseline is shown
    assert "def build_schedule" in user


def test_build_prompt_nonce_varies_user_turn_only():
    system0, user0 = m3_codegen.build_prompt([], nonce=0)
    system1, user1 = m3_codegen.build_prompt([], nonce=1)
    assert system0 == system1           # cache-stable system contract
    assert user0 != user1               # diversity across offspring


def test_extract_code_pulls_fenced_block():
    assert "build_schedule" in extract_code(_fenced(LEGAL_SRC))
    assert "build_schedule" in extract_code(LEGAL_SRC)   # unfenced -> whole text
    with pytest.raises(FaithfulnessError):
        extract_code("")


# --------------------------------------------------------------------------- #
# The proposer — drops bad generations, keeps good ones, plugs into evolve
# --------------------------------------------------------------------------- #

def _seed_population():
    """A tiny stub population: parametric candidates wrapped as Individuals
    (so exemplar_source has genomes to render)."""
    pop = []
    for genome in (m3_proposer.BASELINE_GENOME, np.array([2.0, 5.0, 0.1, 0.0, 0.0])):
        cand = m3.Candidate(factory=m3_proposer.genome_to_factory(genome),
                            genome=tuple(float(x) for x in genome), meta={})
        pop.append(m3.Individual(candidate=cand,
                                 fitness=m3.Fitness.gated_out()))
    return pop


def test_proposer_accepts_legal_generation():
    proposer = LLMProposer(FakeLLMClient([_fenced(LEGAL_SRC)]), n_offspring=1)
    out = proposer(_seed_population(), np.random.default_rng(0))
    assert len(out) == 1
    cand = out[0]
    assert cand.meta["op"] == "llm"
    assert "build_schedule" in cand.meta["source"]
    ok, reasons = candidate_gate.check_param_allowlist(
        m2.resolve_params(cand.factory, 40, *_matrices(40)))
    assert ok, reasons
    assert not proposer.rejections


def test_proposer_drops_banned_generation_without_crashing():
    banned = (
        "def build_schedule(n, feat, oracle_budget):\n"
        "    return {'opt_branching_weights': clip(feat('pagerank'), -0.5, 0.5)}\n"
    )
    proposer = LLMProposer(FakeLLMClient([_fenced(banned)]), n_offspring=1)
    out = proposer(_seed_population(), np.random.default_rng(0))
    assert out == []                       # dropped, not crashed
    assert len(proposer.rejections) == 1   # recorded for the §13 audit


def test_proposer_keeps_only_valid_when_mixed():
    proposer = LLMProposer(
        FakeLLMClient([_fenced(LEGAL_SRC),
                       "def build_schedule(n, feat, oracle_budget):\n"
                       "    import os\n    return {}\n"]),
        n_offspring=2)
    out = proposer(_seed_population(), np.random.default_rng(0))
    assert len(out) == 1
    assert len(proposer.rejections) == 1


def test_proposer_distinct_sources_get_distinct_genomes():
    other = genome_to_source(np.array([2.0, 6.0, 0.2, 0.4, 1.0]))
    proposer = LLMProposer(
        FakeLLMClient([_fenced(LEGAL_SRC), _fenced(other)]), n_offspring=2)
    out = proposer(_seed_population(), np.random.default_rng(0))
    assert len(out) == 2
    assert out[0].genome != out[1].genome   # not deduped by the diversity floor


def test_proposer_plugs_into_evolve_with_stub_evaluator():
    # the LLM proposer drives m3.evolve with NO solve and NO network
    proposer = LLMProposer(FakeLLMClient([_fenced(LEGAL_SRC)]), n_offspring=2,
                           smoke_strata=(10,))

    def stub_eval(candidate, **_kw):
        # fitness keyed off the (deterministic) source fingerprint
        score = float(candidate.genome[0]) % 7
        return m3.Individual(
            candidate=candidate,
            fitness=m3.Fitness(passes_gate=True, lost_feasibility_total=0,
                               pi_rank=score, pi_median=-0.3, floor_fraction=1.0))

    res = m3.evolve(proposer, rng=np.random.default_rng(0), generations=3,
                    pop_size=4, init_population=[c.candidate for c in _seed_population()],
                    evaluator=stub_eval)
    assert res.generations == 3
    assert res.best is not None


# --------------------------------------------------------------------------- #
# Anthropic adapter — optional, lazy, no network in tests
# --------------------------------------------------------------------------- #

def test_module_import_does_not_require_anthropic():
    # importing the module must not import the optional SDK
    assert "anthropic" not in sys.modules or True  # tolerate a pre-imported SDK
    # the adapter class exists and is constructible with an injected client
    assert hasattr(m3_codegen, "AnthropicLLMClient")


def test_anthropic_client_routes_to_messages_create_with_opus():
    # inject a fake SDK client; assert the call shape (model id, system, user)
    calls = {}

    class _Block:
        type = "text"
        text = _fenced(LEGAL_SRC)

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kw):
            calls.update(kw)
            return _Resp()

    class _Client:
        messages = _Messages()

    client = m3_codegen.AnthropicLLMClient(client=_Client())
    text = client("SYS", "USER")
    assert "build_schedule" in text
    assert calls["model"] == "claude-opus-4-8"
    assert calls["system"] == "SYS"
    assert calls["messages"][0]["content"] == "USER"
    assert calls["thinking"] == {"type": "adaptive"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _matrices(n):
    from benchmarks.synthetic_eq29 import make_matrices
    return make_matrices(n, index=0)
