"""
bd o3f: solve() exposes the raw per-worker incumbent streams.

Each portfolio worker already logs every feasible worker-local improvement
(bd 4uf); solve() used to merge those streams into the best-of-P ``history``
and discard them. ``result.worker_histories`` keeps them -- one stream per
worker, indexed by ``worker_id``, entries ``(value, oracle, elapsed_s)`` with
``elapsed_s`` measured from the shared solve() start -- so a user can replay
the running-max over any subset of workers post hoc (e.g. "how would P'<P
workers have done?") without re-running. The merged ``history`` schema
``(value, oracle)`` is unchanged (CLAUDE.md §8).
"""
import random

import pytest

from cbqs import Model, MAXIMIZE


N = 24
SEED = 11
WORKERS = 3


def _build_model(seed=SEED, num_workers=WORKERS, track_history=True):
    rng = random.Random(1234)
    m = Model()
    xs = m.add_variables(N)
    x = [xs[i] for i in range(N)]
    weights = [rng.randint(1, 9) for _ in range(N)]
    values = [rng.randint(1, 9) for _ in range(N)]
    m.add_constraint(sum(weights[i] * x[i] for i in range(N)) <= sum(weights) // 2)
    m.set_objective(sum(values[i] * x[i] for i in range(N)), sense=MAXIMIZE)
    m.close()
    m.seed = seed
    m.set_param('num_workers', num_workers)
    m.set_param('track_history', track_history)
    return m


def _merge(streams, is_better):
    """Reference best-of-portfolio merge over (value, oracle, *_) streams."""
    merged = sorted((e for s in streams for e in s), key=lambda e: e[1])
    out, best = [], None
    for e in merged:
        if best is None or is_better(e[0], best):
            best = e[0]
            out.append((e[0], e[1]))
    return out


@pytest.fixture(scope="module")
def result():
    return _build_model().solve()


def test_one_stream_per_worker(result):
    assert len(result.worker_histories) == WORKERS
    assert any(len(s) > 0 for s in result.worker_histories)


def test_entry_schema_and_monotonicity(result):
    for stream in result.worker_histories:
        for entry in stream:
            assert isinstance(entry, tuple) and len(entry) == 3
            value, oracle, elapsed = entry
            assert isinstance(oracle, int) and oracle >= 0
            assert isinstance(elapsed, float) and elapsed >= 0.0
        oracles = [e[1] for e in stream]
        elapsed = [e[2] for e in stream]
        values = [e[0] for e in stream]
        assert oracles == sorted(oracles)
        assert elapsed == sorted(elapsed)
        # a worker's own incumbents only improve (MAXIMIZE)
        assert all(b > a for a, b in zip(values, values[1:]))


def test_history_is_running_max_over_worker_histories(result):
    assert _merge(result.worker_histories, lambda n, b: n > b) == list(result.history)


def test_single_worker_stream_matches_p1_run(result):
    """Worker 0 of the P=3 run IS the P=1 run under the same seed (independence).

    This is the property that makes post-hoc subsetting valid: a worker's
    trajectory depends only on (master seed, worker_id), never on its peers.
    """
    p1 = _build_model(num_workers=1).solve()
    w0 = [(v, o) for (v, o, _t) in result.worker_histories[0]]
    assert w0 == list(p1.history)


def test_deterministic_under_fixed_seed():
    a = _build_model().solve().worker_histories
    b = _build_model().solve().worker_histories
    strip = lambda hs: [[(v, o) for (v, o, _t) in s] for s in hs]
    assert strip(a) == strip(b)


def test_track_history_false_gives_empty():
    r = _build_model(track_history=False).solve()
    assert r.worker_histories == []
    assert r.history == []


def test_serialization_and_summary(result):
    d = result.to_dict()
    assert d["worker_histories"] == [[list(e) for e in s] for s in result.worker_histories]
    assert "workers" in result.summary()
