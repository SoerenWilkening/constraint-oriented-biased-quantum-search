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


# --------------------------------------------------------------------------- #
# The literal bd xjs / bd 47j repros, pinned end to end.
# --------------------------------------------------------------------------- #

def _xjs_model(con_sense, sense=MINIMIZE, n=40, seed=3):
    """The verbatim repro fixture from bd xjs (`>=`) and bd 47j (`<=`)."""
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]
    rhs = sum(w) // 2
    lhs = sum(w[i] * x[i] for i in range(n))
    m.add_constraint(lhs >= rhs if con_sense == "ge" else lhs <= rhs)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=sense)
    m.close()
    return m, w, v, rhs


class TestAcceptanceRepros:
    """The two repros must return a CORRECT, SELF-CONSISTENT result.

    Pre-fix, the bd xjs repro (``>=``) first ``abort()``ed the process at ctg's
    exploit->explore guard and then — once bd xjs alone made the flag truthful —
    returned the silent wrong answer ``objective=0, feasible=False,
    verified=False, solution=0^n`` while ``final_incumbents == [(104, True)]``
    and ``history == [104]``: a result that contradicted its own history.
    """

    def test_bd_xjs_repro_ge_is_self_consistent(self):
        m, w, v, rhs = _xjs_model("ge")
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("stopping_time", 900)
        # The literal repro sets no M, i.e. the real T(40) = 1201 budget.
        # `-1` opts out of the conftest default-budget cap (bd 8an.1.4).
        m.set_param("M", -1)
        r = m.solve()

        sol = [int(b) for b in r.solution]
        load = sum(w[i] * sol[i] for i in range(len(w)))

        # (1) the returned vector really satisfies the covering constraint
        assert load >= rhs, f"returned vector violates the constraint: {load} < {rhs}"
        # (2) the reported flags agree with it
        assert r.feasible is True
        assert r.verified is True
        assert list(r.violations) == []
        # (3) the objective describes the returned vector ...
        assert r.objective == sum(v[i] * sol[i] for i in range(len(w)))
        # (4) ... and is consistent with the streams that reported it
        assert r.history, "a run that reaches feasibility must log incumbents"
        assert r.objective == min(e[0] for e in r.history)
        assert r.final_incumbents == [(r.objective, True)]

    def test_bd_47j_repro_le_reports_the_feasible_optimum(self):
        m, w, v, rhs = _xjs_model("le")
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("stopping_time", 900)
        # The literal repro sets no M, i.e. the real T(40) = 1201 budget.
        # `-1` opts out of the conftest default-budget cap (bd 8an.1.4).
        m.set_param("M", -1)
        r = m.solve()

        sol = [int(b) for b in r.solution]
        load = sum(w[i] * sol[i] for i in range(len(w)))

        assert load <= rhs
        assert sum(sol) == 0, "the all-zeros vector is the MINIMIZE optimum here"
        assert r.feasible is True
        assert r.verified is True
        assert list(r.violations) == []
        assert r.objective == 0
        assert r.final_incumbents == [(0, True)]
        # The start was already optimal, so nothing ever improved on it: the
        # history is the ACCEPTED-IMPROVEMENT stream and stays empty (see the
        # scope pin on test_warm_feasible_start_is_unchanged).
        assert r.history == []


# --------------------------------------------------------------------------- #
# EQUAL constraints (the stage-1 violation predicate)
# --------------------------------------------------------------------------- #

class TestEqualityConstraintFeasibility:
    """`sum w_i x_i == R` must never report the all-zeros vector as feasible.

    ``potentials[c] == rhs[c]`` means LHS == 0, not "the equality holds"; the
    pre-fix stage-1 violation loop scored that as SATISFIED, so an `== R` model
    with R != 0 reported ``final_incumbents == [(0, True)]`` on the all-zeros
    vector (measured: seeds 2 and 3 below) with ``verified=False``.
    """

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_equality_never_reports_a_violating_point_as_feasible(self, seed):
        n, rng = 20, random.Random(7)
        w = [rng.randint(1, 9) for _ in range(n)]
        m = Model()
        xs = m.add_variables(n)
        x = [xs[i] for i in range(n)]
        m.add_constraint(sum(w[i] * x[i] for i in range(n)) == 25)
        m.set_objective(sum(x[i] for i in range(n)), sense=MINIMIZE)
        m.close()
        m.seed = seed
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 600)
        r = m.solve()

        lhs = sum(w[i] * int(r.solution[i]) for i in range(n))
        # the contract: the flag describes the vector, in BOTH directions
        assert bool(r.feasible) == (lhs == 25), (
            f"reported feasible={r.feasible} but sum w_i x_i == {lhs} (need 25)"
        )
        if r.feasible:
            assert r.verified is True
            assert list(r.violations) == []
            assert r.objective == int(r.solution.sum())
        # and no logged incumbent may be a violating point
        assert all(ok for (_value, ok) in r.final_incumbents) == bool(r.feasible)


# --------------------------------------------------------------------------- #
# ignore_constraint_search: the SAME contract, no sense-dependent exemption
# --------------------------------------------------------------------------- #

class TestIgnoreConstraintSearchContract:
    """``ignore_constraint_search`` is a search-strategy flag, not a contract opt-out.

    It skips the sat/opt_sat phases, but ``eval_constraints`` still runs at ctg
    entry and ``CSearch_opt`` still accepts only constraint-satisfying
    candidates — so ``result.feasible`` must mean the same thing there.

    Pre-fix the pre-loop ``global_opt`` seed excluded ICS while the in-loop
    publish did not, which made the flag SENSE-DEPENDENT: MINIMIZE + ICS
    returned a verify-clean feasible optimum and reported ``feasible=False``,
    MAXIMIZE reported ``True``.
    """

    @pytest.mark.parametrize("sense", [MINIMIZE, MAXIMIZE])
    @pytest.mark.parametrize("ics", [False, True])
    def test_flag_matches_vector_for_both_senses(self, sense, ics):
        m, w, v, cap = _knapsack(n=20, sense=sense)
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 400)
        m.set_param("ignore_constraint_search", ics)
        r = m.solve()

        truth = _cap_satisfied(r.solution, w, cap)
        assert truth, "precondition: this fixture's returned vector is feasible"
        assert bool(r.feasible) is True, (
            f"sense={sense} ICS={ics}: verify-clean feasible vector reported "
            f"feasible={r.feasible} (bd 47j contract, no ICS exemption)"
        )
        assert r.verified is True
        assert list(r.violations) == []

    def test_negative_control_unsatisfiable_under_ics_stays_false(self):
        """Guards against "fix by always reporting True" on the ICS path too."""
        m, w, v, need = _covering()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("verify", True)
        m.set_param("M", 200)
        m.set_param("ignore_constraint_search", True)
        r = m.solve()

        covered = sum(int(w[i]) * int(r.solution[i]) for i in range(len(w)))
        assert covered < need, "precondition: the returned vector is genuinely infeasible"
        assert r.feasible is False
        assert r.verified is False


# --------------------------------------------------------------------------- #
# stop_val (bd xjs follow-up): it had NO functional test at all
# --------------------------------------------------------------------------- #

def _covering_max(n=25, seed=4):
    rng = random.Random(seed)
    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]
    need = sum(w) // 2
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) >= need)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=MAXIMIZE)
    m.close()
    return m, w, v, need


class TestStopVal:
    """``stop_val`` is an OBJECTIVE threshold on the internal ``tot_profit``.

    MAXIMIZE stores the objective negated, so ``stop_val=-60`` means "stop once
    the objective reaches 60". Two properties are pinned: it actually stops
    early, and it is NOT silently inert under ``ignore_constraint_search`` (the
    bd xjs ``&& stage != 3`` guard blocked the sticky ``feasible`` the break is
    gated on, so the ICS arm ran the whole budget).
    """

    @pytest.mark.parametrize("ics", [False, True])
    def test_stop_val_stops_early_and_meets_the_threshold(self, ics):
        m, w, v, need = _covering_max()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("M", 600)
        m.set_param("stop_val", -60)
        m.set_param("ignore_constraint_search", ics)
        m.set_param("verify", True)
        stopped = m.solve()

        ref, w2, v2, need2 = _covering_max()
        ref.seed = 5
        ref.set_param("num_workers", 1)
        ref.set_param("M", 600)
        ref.set_param("ignore_constraint_search", ics)
        unstopped = ref.solve()

        assert stopped.feasible is True
        assert stopped.verified is True
        assert stopped.objective >= 60, (
            "the run may only stop once the threshold is met"
        )
        assert stopped.oracle_calls < unstopped.oracle_calls, (
            f"ICS={ics}: stop_val did not stop the run early "
            f"({stopped.oracle_calls} vs {unstopped.oracle_calls} oracles) — "
            "it is silently inert"
        )
        assert unstopped.oracle_calls >= 600, "the reference run must spend the budget"

    def test_stop_val_unset_spends_the_budget(self):
        """Negative control: -1 (the default) must not stop anything early."""
        m, w, v, need = _covering_max()
        m.seed = 5
        m.set_param("num_workers", 1)
        m.set_param("M", 600)
        m.set_param("stop_val", -1)
        r = m.solve()
        assert r.oracle_calls >= 600


# --------------------------------------------------------------------------- #
# manual_initial(P, assignment): the semantics of P, pinned
# --------------------------------------------------------------------------- #

class TestManualInitialProfitSemantics:
    """``P`` is ADVISORY and its role is phase-dependent — pin both halves.

    bd 47j made ctg recompute the objective at the feasible-start entry, which
    silently changed what a caller-supplied ``P`` does. The change is correct
    (that state is now stamped feasible and seeded into the shared incumbent, so
    an unvalidated ``P`` would be published as a *confidently feasible* wrong
    answer) but it is ASYMMETRIC, and
    ``test_warm_feasible_start_is_unchanged`` cannot catch it because it passes
    the true objective as ``P``.
    """

    def test_wrong_P_on_a_feasible_start_is_ignored(self):
        """FEASIBLE start: ``P`` must not reach ``result.objective`` or the history."""
        results = {}
        for P in (0, 999_999, -999_999):
            m, w, v, cap = _knapsack(n=20)
            n = len(w)
            start, tot = [0] * n, 0
            for i in range(n):
                if tot + w[i] <= cap and sum(start) < 5:
                    start[i], tot = 1, tot + w[i]
            true_start_obj = sum(v[i] * start[i] for i in range(n))
            assert true_start_obj != 0, "precondition: the start has a non-trivial objective"
            m.manual_initial(P, start)
            m.seed = 5
            m.set_param("num_workers", 1)
            m.set_param("verify", True)
            m.set_param("M", 50)
            r = m.solve()
            assert r.feasible is True and r.verified is True
            assert r.objective == sum(v[i] * int(r.solution[i]) for i in range(n)), (
                f"P={P}: result.objective does not describe result.solution"
            )
            results[P] = (r.objective, tuple(e[0] for e in r.history))

        assert len(set(results.values())) == 1, (
            f"a wrong P changed the reported answer on a FEASIBLE start: {results}"
        )

    def test_P_on_an_infeasible_start_is_honoured_as_a_violation_bound(self):
        """INFEASIBLE start: ``tot_profit`` is a VIOLATION sum, and ``P`` bounds it.

        Not a defect — phase 1 does not hold an objective in that slot, so there
        is nothing to recompute. Pinned so the asymmetry is documented rather
        than silent (CLAUDE.md §2.1), and so a future "recompute everywhere"
        change has to confront it.
        """
        objectives = {}
        for P in (0, 100_000):
            n, rng = 30, random.Random(0)
            w = [rng.randint(1, 9) for _ in range(n)]
            u = [rng.randint(1, 9) for _ in range(n)]
            v = [rng.randint(1, 9) for _ in range(n)]
            m = Model()
            xs = m.add_variables(n)
            x = [xs[i] for i in range(n)]
            m.add_constraint(sum(w[i] * x[i] for i in range(n)) <= int(sum(w) * 0.35))
            m.add_constraint(sum(u[i] * x[i] for i in range(n)) >= int(sum(u) * 0.45))
            m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=MINIMIZE)
            m.close()
            m.manual_initial(P, [0] * n)   # 0^n violates the covering constraint
            m.seed = 5
            m.set_param("num_workers", 1)
            m.set_param("verify", True)
            m.set_param("M", 300)
            r = m.solve()
            # whatever P does to the trajectory, the CONTRACT still holds
            assert bool(r.feasible) == (r.verified is not False)
            if r.feasible:
                assert r.objective == sum(v[i] * int(r.solution[i]) for i in range(n))
            objectives[P] = r.objective

        assert objectives[0] != objectives[100_000], (
            "P is documented as live on an INFEASIBLE start (the phase-1 "
            f"acceptance bound); it made no difference: {objectives}"
        )
