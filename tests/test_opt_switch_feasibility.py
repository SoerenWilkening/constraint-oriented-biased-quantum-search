"""bd xjs: the exploit->explore switch must never see an infeasible ``cur_sol``.

ctg's switch site carries an unconditional fail-loud guard (CLAUDE.md §2.1,
§5 phase-machine coupling) that ``abort()``s the *process* if ``stage=3`` is
reached while ``cur_sol->feasible == 0``.  The guard is correct; what used to
be wrong is the state handed to it: ``CSearch_opt_sat``'s stage-2
("tighten the slack", ``direction == -1``) accept stamped ``feasible = 0`` on a
candidate it had just proven feasible.

Because the failure is an ``abort()``, it cannot be observed in-process -- each
case runs in a subprocess and the assertion is on the exit status plus stderr.

The configuration matrix is the one recorded on bd xjs: only MINIMIZE + a
``>=`` covering constraint + a cold ``0^n`` start reaches the corrupting
accept, so the other three combinations are negative controls that must keep
passing.

The general trigger is broader than "cold", and measured: MINIMIZE + ANY
infeasible start (a warm ``general_greedy()`` start that comes out infeasible
reproduces it identically). MAXIMIZE is immune because the objective is stored
negated, so at the first-feasible handoff ``cur_sol->tot_profit < 0 <=
total_violation`` and the corrupting stage-2 accept can never fire; a ``<=``
capacity model is immune because ``0^n`` is feasible and ctg enters stage 3
without ever running opt_sat.
"""

import os
import subprocess
import sys
import textwrap

import pytest

import cbqs

# A silently-degraded build (optional deps / extension missing) reports
# Model is None; that is a hard failure here, not a skip (CLAUDE.md §7).
assert cbqs.Model is not None, "cbqs extension not built -- build before running tests"

ABORT_MESSAGE = "opt-switch reached with infeasible"

# n=40 knapsack, seed 5: the exact bd xjs repro. M is pinned to T(40) =
# (40/32)^2 + 1200 = 1201 so the trajectory (and hence the auto-derived
# opt_switch_oracles = int(0.1*M) = 120) is the production one regardless of
# the conftest budget cap, which does not reach a subprocess anyway.
_CHILD = textwrap.dedent(
    """
    import random, sys
    from cbqs import Model, MINIMIZE, MAXIMIZE

    sense_name, con_sense = sys.argv[1], sys.argv[2]
    sense = MINIMIZE if sense_name == "min" else MAXIMIZE

    n, rng = 40, random.Random(3)
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]

    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    lhs = sum(w[i] * x[i] for i in range(n))
    if con_sense == "ge":
        m.add_constraint(lhs >= sum(w) // 2)
    else:
        m.add_constraint(lhs <= sum(w) // 2)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=sense)
    m.close()
    m.seed = 5
    m.set_param("num_workers", 1)
    m.set_param("verify", True)
    m.set_param("M", 1201)          # == T(40); cold 0^n start (no general_greedy)
    r = m.solve()

    # Independently re-check the reported solution against the constraint --
    # a feasible verdict must survive recomputation (CLAUDE.md §2.1).
    load = sum(w[i] * int(r.solution[i]) for i in range(n))
    ok = load >= sum(w) // 2 if con_sense == "ge" else load <= sum(w) // 2
    print("RESULT", sense_name, con_sense, r.objective, r.feasible, ok, r.oracle_calls)
    if r.feasible and not ok:
        sys.exit("reported feasible but the solution violates the constraint")
    """
)


def _run_case(sense_name, con_sense):
    """Run one (sense, constraint-sense) cold solve in a subprocess.

    PYTHONPATH is pinned to the package root of the *imported* cbqs so the
    child exercises the same build as this test process (a bare script picks
    up whatever editable install is on the default path instead).
    """
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(cbqs.__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (pkg_root, env.get("PYTHONPATH", "")) if p
    )
    return subprocess.run(
        [sys.executable, "-c", _CHILD, sense_name, con_sense],
        capture_output=True, text=True, timeout=600, env=env,
    )


@pytest.mark.parametrize(
    "sense_name,con_sense",
    [("min", "ge"), ("min", "le"), ("max", "ge"), ("max", "le")],
)
def test_cold_start_never_switches_on_infeasible_cur_sol(sense_name, con_sense):
    proc = _run_case(sense_name, con_sense)
    assert ABORT_MESSAGE not in proc.stderr, (
        f"{sense_name}/{con_sense} cold solve tripped ctg's phase-machine guard:\n"
        f"{proc.stderr}"
    )
    assert proc.returncode == 0, (
        f"{sense_name}/{con_sense} cold solve exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "RESULT" in proc.stdout, proc.stdout


def test_min_ge_cold_start_reports_a_verifiable_solution():
    """The bd xjs case specifically: it must finish AND stay self-consistent."""
    proc = _run_case("min", "ge")
    assert proc.returncode == 0, proc.stderr
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT")][0]
    _, _, _, _objective, feasible, recheck_ok, _oracles = line.split()
    # `recheck_ok` is the independent recomputation of the covering constraint
    # on the returned solution vector; it may only disagree with the reported
    # feasibility when nothing feasible was reported.
    if feasible == "True":
        assert recheck_ok == "True", line


# The general trigger is "MINIMIZE + an infeasible start", not "cold": a warm
# general_greedy() start that comes out infeasible reproduces the same abort.
# Two constraints (a tight capacity + a demanding covering) make the greedy
# construction end infeasible, so opt_sat runs and reaches stage 2.
_WARM_CHILD = textwrap.dedent(
    """
    import random, sys
    from cbqs import Model, MINIMIZE, MAXIMIZE

    sense = MINIMIZE if sys.argv[1] == "min" else MAXIMIZE
    n, rng = 30, random.Random(0)
    w = [rng.randint(1, 9) for _ in range(n)]
    u = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]

    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) <= int(sum(w) * 0.35))
    m.add_constraint(sum(u[i] * x[i] for i in range(n)) >= int(sum(u) * 0.45))
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=sense)
    m.close()
    m.seed = 5
    m.set_param("num_workers", 1)
    m.set_param("M", 900)
    _value, greedy_feasible = m.general_greedy()
    # The premise of this test: the WARM start must be infeasible, else the run
    # goes straight to stage 3 and never exercises opt_sat at all.
    assert not greedy_feasible, "greedy start is feasible -- test premise broken"
    m.solve()
    print("RESULT warm-infeasible ok")
    """
)


@pytest.mark.parametrize("sense_name", ["min", "max"])
def test_warm_infeasible_start_never_switches_on_infeasible_cur_sol(sense_name):
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(cbqs.__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (pkg_root, env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [sys.executable, "-c", _WARM_CHILD, sense_name],
        capture_output=True, text=True, timeout=600, env=env,
    )
    assert ABORT_MESSAGE not in proc.stderr, (
        f"{sense_name} warm-infeasible solve tripped ctg's phase-machine guard:\n"
        f"{proc.stderr}"
    )
    assert proc.returncode == 0, (
        f"{sense_name} warm-infeasible solve exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "RESULT" in proc.stdout, proc.stdout


# `ignore_constraint_search` starts ctg in stage 3 / CSearch_opt / stats_opt even
# from an infeasible point. Its first accept used to trip the "first found
# feasible solution" handoff, which set stage=2 + active_stats=opt_sat WITHOUT
# moving search_function -- CSearch_opt running on the opt_sat bias (NORTHSTAR
# §5). The flag had NO end-to-end coverage; this is the smoke test for it.
_ICS_CHILD = textwrap.dedent(
    """
    import random, sys
    from cbqs import Model, MAXIMIZE

    n, rng = 25, random.Random(4)
    w = [rng.randint(1, 9) for _ in range(n)]
    v = [rng.randint(1, 9) for _ in range(n)]

    m = Model()
    xs = m.add_variables(n)
    x = [xs[i] for i in range(n)]
    # `>=` covering: the 0^n start is INFEASIBLE, so stage 3 is entered from an
    # infeasible point -- the configuration that desynced.
    m.add_constraint(sum(w[i] * x[i] for i in range(n)) >= sum(w) // 2)
    m.set_objective(sum(v[i] * x[i] for i in range(n)), sense=MAXIMIZE)
    m.close()
    m.seed = 5
    m.set_param("num_workers", 1)
    m.set_param("M", 600)
    m.set_param("ignore_constraint_search", True)
    r = m.solve()
    load = sum(w[i] * int(r.solution[i]) for i in range(n))
    print("RESULT ics", r.objective, r.feasible, load >= sum(w) // 2)
    """
)


def test_ignore_constraint_search_keeps_the_phase_machine_coupled():
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(cbqs.__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (pkg_root, env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [sys.executable, "-c", _ICS_CHILD],
        capture_output=True, text=True, timeout=600, env=env,
    )
    assert "phase-machine desync" not in proc.stderr, proc.stderr
    assert ABORT_MESSAGE not in proc.stderr, proc.stderr
    assert proc.returncode == 0, (
        f"ignore_constraint_search solve exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT")][0]
    _, _, _objective, feasible, recheck_ok = line.split()
    if feasible == "True":
        assert recheck_ok == "True", line
