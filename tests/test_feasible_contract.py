"""bd 47j — the feasibility-flag API contract of ``Model.solve()``.

CONTRACT (CLAUDE.md §2.1 / §5 "Feasibility sign/EQUAL accounting"): the ``feasible``
flag must describe THE SOLUTION THAT IS RETURNED, not "an improvement was accepted".
Concretely, for every OPTIMIZE solve:

    result.feasible  <=>  result.solution satisfies every constraint

The pre-fix defect (bd 47j): ``mod->global_opt`` is allocated by
``manual_initial`` / ``solve()`` as ``init_state(P, assignment, n)``, and
``state.c:23`` hardcodes ``state->feasible = 0``. ``ctg`` then only ever writes
``global_opt`` inside ``if (res)`` under ``global_opt->tot_profit >
cur_sol->tot_profit`` (SearchLib.c), so a start state that is ALREADY FEASIBLE and
never strictly improved upon leaves the ``feasible=0`` sentinel in place —
``Model.solve()`` reads it at Model.pyx:938 and reports a verified-clean, optimal
solution as infeasible.

These tests are deliberately NOT about the all-zeros vector: they pin the general
invariant (returned vector vs reported flag) over both senses and both start
protocols, plus a negative control so the fix cannot be "always report True".
"""
import random

import pytest

from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE, MINIMIZE


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _knapsack(n=40, seed=3, sense=MINIMIZE):
    """n-item knapsack: min/max sum v_i x_i  s.t.  sum w_i x_i <= sum(w)//2.

    Under MINIMIZE with all-positive values the true optimum is the all-zeros
    vector, which also SATISFIES the capacity constraint (0 <= cap) — i.e. the
    cold 0^n start is feasible-and-optimal and no improvement can ever be
    accepted. That is the bd 47j repro shape.
    """
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]
    cap = sum(w) // 2
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) <= cap)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=sense)
    m.close()
    return m, w, v, cap


def _covering(n=30, seed=11):
    """UNSATISFIABLE covering instance: sum w_i x_i >= sum(w)+1 — no assignment works.

    The all-zeros start is infeasible and stays infeasible for the whole budget,
    so this is the negative control. MAXIMIZE (the Eq.29 sense) so the run does
    not tread on the bd xjs MINIMIZE+`>=` abort path.
    """
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]
    need = sum(w) + 1
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) >= need)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=MAXIMIZE)
    m.close()
    return m, w, v, need


def _cap_satisfied(solution, w, cap):
    return sum(int(w[i]) * int(solution[i]) for i in range(len(w))) <= cap


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

class TestFeasibleFlagContract:
    """result.feasible must describe result.solution."""

    def test_bd47j_repro_cold_feasible_optimum_reports_feasible(self):
        """The verbatim bd 47j repro: verified-clean optimum must not report infeasible.

        n=40 MINIMIZE knapsack, single `<=` capacity, COLD 0^n start, P=1, seed 5.
        The returned solution is all-zeros: it satisfies the constraint (0 <= cap)
        and is the true MINIMIZE optimum, and verify=True reports zero violations.
        """
        m, w, v, cap = _knapsack()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 400)
        r = m.solve()

        # Ground truth, computed here (not read from the solver):
        assert _cap_satisfied(r.solution, w, cap), "precondition: returned vector is feasible"
        assert r.verified is True
        assert list(r.violations) == []
        assert int(r.solution.sum()) == 0          # the true MINIMIZE optimum
        assert r.objective == 0

        # The contract under test.
        assert r.feasible is True, (
            "bd 47j: a verified-clean, optimal solution was reported infeasible "
            "(global_opt kept its init_state feasible=0 sentinel because no strict "
            "improvement over the feasible start was ever accepted)"
        )

    @pytest.mark.parametrize("sense", [MINIMIZE, MAXIMIZE])
    @pytest.mark.parametrize("n_workers", [1, 4])
    def test_reported_flag_matches_returned_vector(self, sense, n_workers):
        """General invariant over both senses and P: flag <=> vector satisfies constraints.

        Only the MINIMIZE cells are RED pre-fix. The MAXIMIZE cells are
        NO-REGRESSION cells: that knapsack admits improving moves, so
        ``global_opt`` is overwritten by an accepted (feasible) state and picks
        up ``feasible=1`` even on the unfixed build. They are kept because the
        fix must not break them.
        """
        m, w, v, cap = _knapsack(sense=sense)
        m.seed = 5
        m.set_param("num_workers", n_workers)
        m.set_param("M", 400)
        r = m.solve()

        truth = _cap_satisfied(r.solution, w, cap)
        assert bool(r.feasible) == truth, (
            f"reported feasible={r.feasible} but the returned vector "
            f"{'satisfies' if truth else 'violates'} the capacity constraint"
        )

    def test_final_incumbents_flag_matches_feasible_start(self):
        """Per-worker final incumbents must not claim a feasible start is infeasible.

        ``ctg`` computes ``eval_constraints`` at entry into a LOCAL ``int feasible``
        but never writes ``cur_sol->feasible``, which ``init_state`` zeroed. The
        per-worker ``(value, feasible)`` tuple in ``run_sampling`` reads that stale
        field, so ``benchmarks.metric.instance_feasible``'s empty-history fallback
        (``result.final_incumbents``) also mis-reports the run.
        """
        m, w, v, cap = _knapsack()
        m.seed = 5
        m.set_param("num_workers", 2)
        m.set_param("M", 400)
        r = m.solve()

        assert _cap_satisfied(r.solution, w, cap)
        assert r.final_incumbents, "final_incumbents must be populated"
        assert all(ok for (_value, ok) in r.final_incumbents), (
            f"a feasible start was reported infeasible per worker: {r.final_incumbents}"
        )

    def test_metric_instance_feasible_sees_the_run(self):
        """The stated bd 47j impact: metric.py must not drop the run as never-feasible."""
        from benchmarks.metric import instance_feasible

        m, w, v, cap = _knapsack()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("M", 400)
        r = m.solve()

        assert _cap_satisfied(r.solution, w, cap)
        assert instance_feasible(r) is True

    def test_negative_control_genuinely_infeasible_stays_false(self):
        """A run that never reaches a feasible point must still report feasible=False.

        Guards against "fix" by unconditionally setting the flag.
        """
        m, w, v, need = _covering()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 200)
        r = m.solve()

        covered = sum(int(w[i]) * int(r.solution[i]) for i in range(len(w)))
        assert covered < need, "precondition: the returned vector is genuinely infeasible"
        assert r.feasible is False
        assert r.verified is False
        assert r.violations, "verify=True must report the violated covering constraint"
        assert not any(ok for (_value, ok) in (r.final_incumbents or []))

    def test_warm_feasible_start_is_unchanged(self):
        """A feasible-and-improved warm start already reported feasible=True: no regression.

        NOTE this uses ``manual_initial``; the CANONICAL warm protocol
        (``general_greedy()``) is covered by
        :meth:`test_canonical_warm_general_greedy_start_is_unchanged`.
        """
        m, w, v, cap = _knapsack()
        n = len(w)
        start, tot = [0] * n, 0
        for i in range(n):
            if tot + w[i] <= cap and sum(start) < 8:
                start[i], tot = 1, tot + w[i]
        start_val = sum(v[i] * start[i] for i in range(n))
        m.manual_initial(start_val, start)
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 2000)
        r = m.solve()

        assert r.feasible is True
        assert r.verified is True
        assert _cap_satisfied(r.solution, w, cap)
        # SCOPE PIN (not a correctness claim). `history` stays the
        # ACCEPTED-IMPROVEMENT stream: every entry is a strict improvement on
        # the start, so no entry is stamped at oracle 0.
        #
        # NOTE the reason is NOT double-seeding — ``warm_repair_history``
        # already guards that (benchmarks/baselines.py:435 leaves a history
        # already stamped at oracle 0 verbatim). Emitting the start as an
        # oracle-0 incumbent is excluded from THIS commit because it changes
        # ``result.history`` and ``result.worker_histories`` — both §8-listed
        # structures — for every run with a feasible start, including runs that
        # already reported feasible=True; that needs its own frozen-table A/B.
        # Known consequence, tracked as a follow-up: with an empty history
        # ``metric.compute_primal_integral`` still scores a feasible-start,
        # never-improved run as +inf while ``result.feasible`` says True. That
        # divergence is pre-existing (it is exactly the warm
        # feasible-greedy-never-improved case ``warm_repair_history`` exists
        # for); the fix widens it to cold feasible starts.
        assert r.history, "the suboptimal warm start must be improved upon"
        assert all(oracle > 0 for (_v, oracle, *_rest) in r.history)
        assert r.objective == min(e[0] for e in r.history), (
            "the returned objective must equal the best logged incumbent"
        )

    @pytest.mark.parametrize("sense", [MINIMIZE, MAXIMIZE])
    def test_canonical_warm_general_greedy_start_is_unchanged(self, sense):
        """The CANONICAL warm protocol (bd 8an.9) must be a strict no-op.

        The whole §8 blast-radius argument rests on ``initial_state_preparation``
        (solver.c:309, :328-330) having ALREADY published the greedy start's
        ``feasible`` flag and objective into ``global_opt`` before ``ctg`` runs —
        so bd 47j's entry seed finds an incumbent it cannot supersede (no
        dominance cell fires; ``tot_profit`` compares equal) and copies nothing.
        Pin that end to end: a feasible greedy start, a run that improves on it,
        no oracle-0 history entry, and ``result.objective`` equal to the best
        logged incumbent.
        """
        m, w, v, cap = _knapsack(sense=sense)
        greedy_value, greedy_feasible = m.general_greedy()
        assert greedy_feasible is True, "precondition: the greedy construction is feasible"
        assert greedy_value is not None

        m.seed = 5
        m.set_param("num_workers", 2)
        m.set_param("verify", True)
        m.set_param("M", 800)
        r = m.solve()

        assert r.feasible is True
        assert r.verified is True
        assert list(r.violations) == []
        assert _cap_satisfied(r.solution, w, cap)
        assert all(ok for (_value, ok) in r.final_incumbents)
        # history untouched: improvements only, none backdated to oracle 0
        assert r.history, "the greedy start must be improved upon at this budget"
        assert all(oracle > 0 for (_v, oracle, *_rest) in r.history)
        best = min if sense == MINIMIZE else max
        assert r.objective == best(e[0] for e in r.history)
        # ...and every raw per-worker stream (bd o3f) is likewise unanchored
        for stream in r.worker_histories:
            assert all(oracle > 0 for (_v, oracle, *_rest) in stream)
