"""Regression test for bd ta2 — module-global ``python_callback`` race.

``cbqs/SearchLib.pyx`` used to stash the user callback in a module-global
``cdef object python_callback`` that *every* joblib threading worker overwrote
right before its ``nogil`` run.  Under ``num_workers > 1`` with **distinct**
direct user callbacks (the ``track_history=False`` path, which does NOT go
through the per-thread ``_solve_states`` dispatch), last-writer-wins on that
global could route one worker's C callback to another solve's Python callable.

The history path dodges the race because ``_history_callback_fn`` re-dispatches
by ``threading.get_ident()``; the *direct* callback path does not, so it is the
exposed surface.  This test drives two concurrent ``solve()`` calls — each with
its own direct callback and ``track_history=False`` — and asserts that no
worker thread ever invoked more than one solve's callback.

Detector validity (per the bd ta2 verification panel):

* **Overlap** — a ``Barrier`` aligns the two solves' starts and they run in
  separate outer threads, each spawning its OWN joblib pool, so their worker
  threads are alive simultaneously and OS idents are distinct per solve (no
  recycling within a round).  Under the global race a single worker thread
  records BOTH tags (it ran its own solve's callback *and*, after a neighbour
  overwrote the global, the neighbour's callback) -> the cross-routing assert
  fires.  With per-thread dispatch each ident carries exactly one tag.
* **Non-vacuity** — the C callback only fires on a *strictly* improving
  ``global_opt`` (``SearchLib.c`` opt-gate), so a solve that never beats its
  start could fire zero callbacks and silently pass even on a buggy build.  To
  keep every round a real detector we (a) start from the all-zeros incumbent
  (no ``general_greedy`` warm start) so the optimizer reliably climbs through
  many incumbents, and (b) assert BOTH tags actually fired each round — a
  zero-callback solve fails honestly instead of passing for free.
"""
import threading

import pytest

from cbqs import Model, MAXIMIZE


def _build_model():
    """Knapsack sized so the optimizer reliably finds several improving
    incumbents per worker (so the direct callback fires every round) while
    running long enough to overlap a concurrent solve.  No ``general_greedy``:
    starting from all-zeros guarantees an improving climb (empirically >=14
    fires/solve at n=32, vs frequent zero-fire rounds at n=24 with greedy)."""
    m = Model()
    n = 32
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    weights = [(2 + (i * 7) % 11) for i in range(n)]
    values = [(3 + (i * 5) % 13) for i in range(n)]
    cap = sum(weights) // 2
    m.add_constraint(sum(weights[i] * x[i] for i in range(n)) <= cap)
    m.set_objective(sum(values[i] * x[i] for i in range(n)), sense=MAXIMIZE)
    m.close()
    return m


@pytest.mark.parametrize("round_idx", range(10))
def test_direct_callbacks_do_not_cross_route(round_idx):
    """Two concurrent direct-callback solves must not share a worker thread's
    callback dispatch (bd ta2).

    Parametrized into independent rounds so each resets its observation map
    (ident recycling across rounds is harmless; within a round the two
    overlapping solves keep their threads alive and thus distinct)."""
    lock = threading.Lock()
    tags_by_ident: dict[int, set] = {}
    start_barrier = threading.Barrier(2)

    def run_solve(tag, seed):
        def cb():
            tid = threading.get_ident()
            with lock:
                tags_by_ident.setdefault(tid, set()).add(tag)

        m = _build_model()
        m.seed = seed
        m.set_param('num_workers', 4)
        m.set_param('track_history', False)   # exposes the direct-callback path
        m.set_param('callback', cb)
        # Align the two solves so their worker pools overlap in time.
        start_barrier.wait(timeout=30)
        return m.solve()

    threads = []
    errors = []

    def worker(tag, seed):
        try:
            run_solve(tag, seed)
        except Exception as exc:  # surface barrier timeouts / solver errors
            errors.append(exc)

    for tag, seed in (("A", 11), ("B", 22)):
        t = threading.Thread(target=worker, args=(tag, seed))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"solve raised: {errors}"
    assert all(not t.is_alive() for t in threads), "a solve thread hung"

    # Non-vacuity: both solves must have fired their callback, else this round
    # had no detection power and must not pass for free (bd ta2 panel finding).
    fired = set().union(*tags_by_ident.values()) if tags_by_ident else set()
    assert fired == {"A", "B"}, (
        f"round had no detection power: only tags {fired} fired (expected both "
        "A and B) — the solver produced no strict improvements"
    )

    # Core invariant: no worker thread dispatched more than one solve's callback.
    cross = {tid: tags for tid, tags in tags_by_ident.items() if len(tags) > 1}
    assert not cross, (
        "callback cross-routing detected (bd ta2): worker thread(s) invoked "
        f"more than one solve's callback: {cross}"
    )
