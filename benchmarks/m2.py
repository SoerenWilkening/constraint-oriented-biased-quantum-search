"""M2 hypothesis-check harness (bd 8an.3, NORTHSTAR §4 / §12 M2).

Machinery for the no-learning lever check:

* **Candidate runner** — :func:`run_candidate_seed_bank` mirrors
  :func:`benchmarks.baselines.run_default_seed_bank` (same matched seed bank,
  same ``M=-1`` real ``T(n)`` budget, same fail-loud seed validation) but
  injects a hand-designed schedule as ``Model.set_param`` phase params before
  ``solve()``. Schedules are *runtime data only* (NORTHSTAR §1.6) — radius per
  phase, ``opt_switch_oracles``, ``variable_priorities``, ``branching_weights``.
* **Run-set persistence** — :func:`save_run_set` / :func:`load_run_set_dir`
  serialize exactly what the §6 metric duck-types (``history``,
  ``final_incumbents``, ``seed``) plus the M2a ``decision_touch`` diagnostics
  and the *resolved* schedule params (NORTHSTAR §13 audit). The live default
  run-set (needed by §8.3 — ``final_incumbents`` are not frozen) is solved
  ONCE per instance set and replayed for every candidate verdict.
* **Decision-touch report** — :func:`decision_touch_report` pools the M2a
  per-phase counters across instances/seeds into per-size touch fractions
  (the NORTHSTAR §4 expressiveness-hypothesis measurement, M2b).
* **Verdict** — :func:`verdict_from_dirs` wires two persisted run-sets into
  :func:`benchmarks.metric.score_verdict` (``require_largest_n=False`` until
  the bd 0o8 large-n freeze lands).

CLI::

    python -m benchmarks.m2 run-default   --out-dir benchmarks/artifacts/run_sets/default
    python -m benchmarks.m2 run-candidate --schedule <name> --out-dir .../<name>
    python -m benchmarks.m2 touch-report  --run-dir .../default --out decision_touch.csv
    python -m benchmarks.m2 verdict       --candidate-dir .../<name> --default-dir .../default
"""

import csv
import json
import math
import os
import types

try:  # package import (pytest / installed) vs flat script import
    from benchmarks.baselines import (
        DEFAULT_SEED_BANK,
        load_frozen_baselines,
        warm_repair_history,
    )
    from benchmarks import metric
except ImportError:  # pragma: no cover - flat layout fallback
    from baselines import (  # type: ignore
        DEFAULT_SEED_BANK, load_frozen_baselines, warm_repair_history)
    import metric  # type: ignore

#: Default frozen-anchor table (M1, re-frozen post-4uf/cjz @ 3c6ba1c).
FROZEN_BASELINES_CSV = os.path.join(os.path.dirname(__file__), "baselines_frozen.csv")

#: Named hand-designed schedules (M2d/e/f register here). Each value is a
#: factory ``f(n, c1, c2, c3) -> {param_name: value}`` returning CONCRETE
#: set_param values for one instance (arrays sized to n, scalars as-is) —
#: callables keep per-instance features out of the JSON/CLI surface while the
#: registry name keeps runs reproducible (NORTHSTAR §13).
SCHEDULES = {}


def register_schedule(name, factory):
    """Register a named schedule factory; raises on duplicates (fail loud)."""
    if name in SCHEDULES:
        raise ValueError(f"schedule {name!r} already registered")
    SCHEDULES[name] = factory
    return factory


# --------------------------------------------------------------------------- #
# M2 hand-designed schedule family (NORTHSTAR §4 / §12 M2 — no learning)
# --------------------------------------------------------------------------- #
# Baseline for contrast: the CBQS default leaves phase params unset, so
# close() auto-sets bias = n/4 in EVERY phase (realized radius n/(n/4+2),
# ~3.3–3.7 over n=10..100) and opt_switch_oracles defaults to 0.1*M.
# All schedules below are pure runtime data (§1.6): per-phase target radius
# (bias = n/r − 2 at every n, the §1.5 scale-stable lever) and the
# opt_switch_oracles switch point (clamped by solve() to [0, 0.25*M] — the
# §4 alpha <= 0.25 bound). Equal-T(n) pricing comes from the runner (M=-1).

# M2d — the canonical greedy->explore radius schedule: tighten near the
# incumbent while satisfying/feasibility-tightening (r=2), then explore a
# wider neighborhood in the objective phase (r=6).
register_schedule("radius_g2e", lambda n, c1, c2, c3: {
    "opt_sat_branching_radius": 2.0,
    "opt_branching_radius": 6.0,
})

# M2d — same radii, switch timing variants: immediate explore vs the latest
# admissible switch (huge value -> clamped to 0.25*M by solve()).
register_schedule("radius_g2e_early", lambda n, c1, c2, c3: {
    "opt_sat_branching_radius": 2.0,
    "opt_branching_radius": 6.0,
    "opt_switch_oracles": 0,
})
register_schedule("radius_g2e_late", lambda n, c1, c2, c3: {
    "opt_sat_branching_radius": 2.0,
    "opt_branching_radius": 6.0,
    "opt_switch_oracles": 10 ** 9,   # -> min(., 0.25*M): latest admissible switch
})

# M2d — uniform controls: separate "it is the SCHEDULE" from "it is just a
# different radius". uniform2 is the §1.3 anti-greedy negative control (a
# near-greedy uniform tightening should fail the §8.3 floor / lose the tail).
register_schedule("radius_uniform6", lambda n, c1, c2, c3: {
    "opt_sat_branching_radius": 6.0,
    "opt_branching_radius": 6.0,
})
register_schedule("radius_uniform2", lambda n, c1, c2, c3: {
    "opt_sat_branching_radius": 2.0,
    "opt_branching_radius": 2.0,
})


def _pii(c1):
    """diag(c1) = p_ii, the objective self-weights — §1.4 allow-list, one O(n) pass."""
    import numpy as np
    return np.asarray(np.diag(np.asarray(c1)), dtype=float)


def _pii_z_clipped(c1):
    """Bounded per-variable feature: z-score of p_ii clipped to [-1, 1]."""
    import numpy as np
    d = _pii(c1)
    sd = d.std()
    z = (d - d.mean()) / sd if sd > 0 else np.zeros_like(d)
    return np.clip(z, -1.0, 1.0)


# M2e — one structural variable_order (priced relabel, §5: same T(n) budget,
# different realized feasible set / forced-vs-free split). Priorities argsort
# DESCENDING (solver_ctx_set_variable_order); propagation applies the first
# non-None priorities to ALL THREE phases. desc = high objective self-weight
# decided first; asc = exact reverse (the negative control).
register_schedule("order_pii_desc", lambda n, c1, c2, c3: {
    "opt_variable_priorities": _pii(c1),
})
register_schedule("order_pii_asc", lambda n, c1, c2, c3: {
    "opt_variable_priorities": -_pii(c1),
})

# M2f — per-variable logit offset theta_i (M0f sigmoid channel), OPT PHASE
# ONLY (branching_weights are per-phase; opt is where the bias touches >90 %
# of decisions per decision_touch_default.csv). theta = ±0.5·clip(z(p_ii), ±1):
# bounded |theta| <= 0.5, mean-centered. theta>0 makes high-p_ii variables
# STICKIER to the incumbent (BranchingFunction returns incumbent-bit
# stickiness at the production call sites: bit_T==0); theta<0 flips them more.
# MUST be radius-neutral (the M0f decoupling claim) — M2f checks realized
# radius_mean against the default before scoring.
register_schedule("theta_pii_pos", lambda n, c1, c2, c3: {
    "opt_branching_weights": 0.5 * _pii_z_clipped(c1),
})
register_schedule("theta_pii_neg", lambda n, c1, c2, c3: {
    "opt_branching_weights": -0.5 * _pii_z_clipped(c1),
})


# --------------------------------------------------------------------------- #
# Anchored instance set
# --------------------------------------------------------------------------- #

def anchored_instances(baselines):
    """Sorted [(n, index)] usable for a §6.6 comparison: finite B_I, L_I AND frozen default_PI.

    Instances without a frozen ``default_PI`` (e.g. the pending n=3000 strata,
    bd 0o8) are excluded — scoring them is a recorded skip, not a win, so
    solving them here would burn compute for no verdict signal.
    """
    keys = []
    for key, entry in baselines.items():
        if all(entry.get(k) is not None and math.isfinite(float(entry[k]))
               for k in ("B_I", "L_I", "default_PI")):
            keys.append(key)
    return sorted(keys)


# --------------------------------------------------------------------------- #
# Candidate runner
# --------------------------------------------------------------------------- #

def resolve_params(params_or_factory, n, c1, c2, c3):
    """Resolve a schedule into concrete ``set_param`` values for one instance.

    ``params_or_factory`` may be a dict (values may individually be callables
    ``f(n, c1, c2, c3)`` for per-instance arrays) or a single factory callable
    returning the whole dict. Returns a new dict of concrete values.
    """
    params = (params_or_factory(n, c1, c2, c3)
              if callable(params_or_factory) else dict(params_or_factory))
    out = {}
    for key, value in params.items():
        out[key] = value(n, c1, c2, c3) if callable(value) else value
    return out


def run_candidate_seed_bank(n, index, seeds, params_or_factory, *, bench_root=None,
                            M=-1, num_workers=None, verify=True, opt_sample_cap=0,
                            vectorized=True, warm=False):
    """Run a CANDIDATE schedule on one Eq.29 instance once per master seed.

    Mirrors :func:`benchmarks.baselines.run_default_seed_bank` (same budget
    ``M=-1`` == real ``T(n)``, same seed fail-loud, same vectorized build) and
    then injects the resolved schedule params via ``Model.set_param`` before
    each ``solve()``. Equal-``T(n)`` by construction — the §5 pricing is the
    A/B comparison at the same oracle budget, never a discount.

    ``warm`` (bd 8an.10, default False) calls ``m.general_greedy()`` before each
    ``solve()`` (greedy warm start, matching the published iqs / the warm default).
    The A/B stays matched only if the default is solved warm TOO — the warm M3 driver
    runs both arms warm; never mix a warm candidate against a cold default.

    Returns ``(results, resolved_params)`` — the resolved params are persisted
    next to the run-set for §13 audit/replay.
    """
    try:  # lazy: pulls in cbqs (the C extension) only when an actual solve is requested
        from eq29_loader import load_eq29, build_model
    except ImportError:  # pragma: no cover - package import
        from benchmarks.eq29_loader import load_eq29, build_model
    bad = [s for s in seeds if int(s) <= 0]
    if bad:
        # bd cjz: seed 0 = entropy-seeded, non-reproducible, and the result
        # still reports the requested seed — fail loud before wasting a solve.
        raise ValueError(
            f"seed bank contains {bad!r}: Model seed 0 means 'auto-generate from "
            f"entropy', which is non-reproducible — use seeds >= 1 (bd cjz).")
    c1, c2, c3 = load_eq29(n, index, bench_root)
    resolved = resolve_params(params_or_factory, n, c1, c2, c3)
    results = []
    for seed in seeds:
        m = build_model(c1, c2, c3, vectorized=vectorized)
        greedy_value = greedy_feasible = None
        if warm:
            # bd 8an.10 warm-start; bd 8an.9: capture greedy value+feasibility before solve()
            # overwrites global_opt, to seed the faithful oracle-0 incumbent below.
            greedy_value, greedy_feasible = m.general_greedy()
        m.seed = int(seed)
        m.set_param("M", M)
        if num_workers is not None:
            m.set_param("num_workers", num_workers)
        m.set_param("verify", verify)
        m.set_param("opt_sample_cap", int(opt_sample_cap))
        for key, value in resolved.items():
            m.set_param(key, value)
        r = m.solve()
        if warm:
            warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
        results.append(r)
    return results, resolved


# --------------------------------------------------------------------------- #
# Run-set persistence
# --------------------------------------------------------------------------- #

def require_verified(results, *, context):
    """FAIL LOUD if any reported-FEASIBLE result failed post-solve verification (§2.1).

    The M2e lesson (bd 8an.3.5): with ``variable_order`` set, the C look-ahead
    keys clause-closure on the NATURAL index while traversal uses var_order, so
    the solver can accept ``eval_constraints``-violating states as "feasible" —
    the run then reports inflated, frontier-beating objectives that the metric
    happily scores. ``result.verified`` is the independent ground-truth check.

    The corruption signature is ``feasible=True ∧ verified=False`` — the solver
    CLAIMED feasibility that ground truth refutes. ``feasible=False ∧
    verified=False`` is different (bd 8an.8, order_pii_desc @ 70_0): the run
    HONESTLY found no feasible point within T(n), ``global_opt`` still holds
    the all-zeros init residue, and ``verify_solution`` (which checks
    ``global_opt`` unconditionally) rightly flags it. That is a legitimate,
    scoreable lever outcome — the §6 item-5 never-feasible sentinel, the §6.6
    feasibility tier, and the §8.3 tail-collapse −inf all exist to punish it —
    so it must persist, not crash. A missing ``feasible`` attribute is treated
    as feasible (conservative: unknown provenance stays fatal).

    The honest case is additionally required to have an EMPTY scored surface:
    the metric never reads ``result.feasible`` — it scores ``history`` and
    ``final_incumbents`` — and ``result.feasible`` (from ``global_opt``) is
    coupled to those surfaces only by an implicit C invariant (every scored
    entry gates on the same ``cur_sol->feasible`` that wins ``global_opt``).
    A ``feasible=False`` result whose history is non-empty or whose
    ``final_incumbents`` carry a feasible entry is an impossible state under
    correct operation — treat it as corruption and crash, never score it.
    """
    def _scored_feasible_surface(r):
        if getattr(r, "history", None):
            return True
        return any(bool(ok) for _v, ok in (getattr(r, "final_incumbents", None) or ()))

    bad = [(i, getattr(r, "seed", None)) for i, r in enumerate(results)
           if getattr(r, "verified", None) is False
           and (getattr(r, "feasible", True) is not False
                or _scored_feasible_surface(r))]
    if bad:
        first = results[bad[0][0]]
        raise ValueError(
            f"{context}: {len(bad)}/{len(results)} solve(s) FAILED post-solve "
            f"verification (seeds {[s for _i, s in bad]}) — the solver accepted "
            f"constraint-violating solutions (violations: "
            f"{getattr(first, 'violations', None)!r}). This run-set is invalid "
            f"and will not be persisted (CLAUDE.md §2.1; bd 8an.3.5 lesson).")


def result_to_record(result):
    """Serialize the metric-relevant slice of an OptimizeResult to plain JSON types.

    Persists exactly what :mod:`benchmarks.metric` duck-types (``history``,
    ``final_incumbents``, ``seed``) plus bookkeeping (``objective``,
    ``feasible``, ``oracle_calls``, ``verified``) and ``branch_diagnostics``
    WITHOUT the bulky ``per_worker`` list (the pooled raw sums +
    ``decision_touch`` are kept and re-poolable across seeds/instances).
    """
    bd = getattr(result, "branch_diagnostics", None)
    if bd is not None:
        bd = {k: v for k, v in bd.items() if k != "per_worker"}
    verified = getattr(result, "verified", None)
    return {
        "seed": int(result.seed),
        "objective": (None if result.objective is None else float(result.objective)),
        "feasible": bool(result.feasible),
        "verified": (None if verified is None else bool(verified)),
        "oracle_calls": int(getattr(result, "oracle_calls", 0)),
        "history": [[float(v), int(o)] for (v, o) in (result.history or [])],
        "final_incumbents": [[float(v), bool(f)] for (v, f) in
                             (getattr(result, "final_incumbents", None) or [])],
        "branch_diagnostics": bd,
    }


def record_to_result(record):
    """Inverse of :func:`result_to_record` — a metric-duck-typed replay object."""
    return types.SimpleNamespace(
        seed=record["seed"],
        objective=record["objective"],
        feasible=record["feasible"],
        verified=record.get("verified"),
        oracle_calls=record.get("oracle_calls", 0),
        history=[(v, int(o)) for (v, o) in record["history"]],
        final_incumbents=[(v, bool(f)) for (v, f) in record["final_incumbents"]],
        branch_diagnostics=record.get("branch_diagnostics"),
    )


def _instance_path(out_dir, n, index):
    return os.path.join(out_dir, f"{int(n)}_{int(index)}.json")


def save_run_set(out_dir, n, index, results, *, schedule_id, resolved_params=None):
    """Persist one instance's seed-bank results to ``<out_dir>/<n>_<index>.json``."""
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "schedule_id": schedule_id,
        "n": int(n),
        "index": int(index),
        "resolved_params": _jsonable_params(resolved_params),
        "records": [result_to_record(r) for r in results],
    }
    path = _instance_path(out_dir, n, index)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)  # atomic: a killed sweep never leaves a torn file
    return path


def _jsonable_params(params):
    """Schedule params with numpy arrays coerced to lists (audit serialization)."""
    if params is None:
        return None
    out = {}
    for key, value in params.items():
        out[key] = list(map(float, value)) if hasattr(value, "__len__") and \
            not isinstance(value, str) else value
    return out


def load_run_set_dir(run_dir):
    """Load a persisted run-set directory -> ``{(n, index): [replay results]}``.

    Raises on an empty/missing directory (fail loud, §2.1) — an empty run-set
    silently scoring as "nothing to compare" is exactly the M1 lesson.
    """
    if not os.path.isdir(run_dir):
        raise FileNotFoundError(f"run-set directory not found: {run_dir}")
    out = {}
    for name in sorted(os.listdir(run_dir)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        with open(os.path.join(run_dir, name)) as fh:
            payload = json.load(fh)
        key = (int(payload["n"]), int(payload["index"]))
        results = [record_to_result(rec) for rec in payload["records"]]
        # Defense in depth vs pre-guard run-sets (records carry verified=None
        # if written before the bd 8an.3.5 fix — those pass; an explicit False
        # means a KNOWN-invalid run-set and must never reach the metric).
        require_verified(results, context=f"{run_dir} {key[0]}_{key[1]}")
        out[key] = results
    if not out:
        raise ValueError(f"run-set directory {run_dir} contains no instance files")
    return out


def run_sweep(schedule_id, params_or_factory, instances, *, out_dir,
              seeds=DEFAULT_SEED_BANK, bench_root=None, num_workers=None,
              opt_sample_cap=0, vectorized=True, resume=True, warm=False, log=print):
    """Solve a schedule over ``instances`` (list of ``(n, index)``), persisting incrementally.

    ``params_or_factory=None`` runs the CBQS default (no injected params) via
    :func:`benchmarks.baselines.run_default_seed_bank` — byte-identical to the
    anchor-freeze recipe. ``resume=True`` skips instances whose file already
    exists, so an interrupted sweep continues where it stopped.

    ``warm`` (bd 8an.10) warm-starts every solve via ``general_greedy()`` (the
    published iqs protocol). Threaded into BOTH the default and candidate paths so a
    warm M3 A/B keeps both arms matched; never mix warm and cold across the two arms.
    """
    try:
        from benchmarks.baselines import run_default_seed_bank
    except ImportError:  # pragma: no cover
        from baselines import run_default_seed_bank  # type: ignore
    os.makedirs(out_dir, exist_ok=True)
    done, skipped = [], []
    for (n, index) in instances:
        path = _instance_path(out_dir, n, index)
        if resume and os.path.exists(path):
            skipped.append((n, index))
            continue
        if params_or_factory is None:
            results = run_default_seed_bank(
                n, index, seeds, bench_root=bench_root, num_workers=num_workers,
                opt_sample_cap=opt_sample_cap, vectorized=vectorized, warm=warm)
            resolved = None
        else:
            results, resolved = run_candidate_seed_bank(
                n, index, seeds, params_or_factory, bench_root=bench_root,
                num_workers=num_workers, opt_sample_cap=opt_sample_cap,
                vectorized=vectorized, warm=warm)
        # §2.1 fail-loud: a verification failure means the solver accepted
        # constraint-violating solutions — never persist such a run-set.
        require_verified(results, context=f"{schedule_id} {n}_{index}")
        save_run_set(out_dir, n, index, results, schedule_id=schedule_id,
                     resolved_params=resolved)
        done.append((n, index))
        log(f"[m2] {schedule_id}: solved {n}_{index} "
            f"({len(done)} new, {len(skipped)} skipped)")
    manifest = {
        "schedule_id": schedule_id,
        "seeds": [int(s) for s in seeds],
        "num_workers": num_workers,
        "opt_sample_cap": int(opt_sample_cap),
        "warm": bool(warm),  # bd 8an.10 provenance: greedy warm start vs cold 0^n
        "instances_done": sorted([list(k) for k in done + skipped]),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    return {"done": done, "skipped": skipped}


# --------------------------------------------------------------------------- #
# M2b — decision-touch report
# --------------------------------------------------------------------------- #

_PHASES = ("sat", "opt_sat", "opt")
_TOUCH_KEYS = ("decisions", "free", "bothinf", "forced")


def decision_touch_report(run_sets):
    """Pool M2a decision-touch counters per (size, phase) across instances+seeds.

    run_sets : ``{(n, index): [results with .branch_diagnostics]}``.
    Returns rows ``{n, phase, decisions, free, bothinf, forced, touch_fraction,
    instances, runs}`` sorted by (n, phase order). The touch fraction is
    recomputed from the POOLED counters (not averaged over per-run fractions)
    with the per-phase consulted semantics: free everywhere + bothinf in
    opt_sat only. Runs missing ``decision_touch`` raise — measuring M2b with a
    pre-M2a binary would silently report zeros (§2.1).
    """
    pooled = {}
    seen_instances = {}
    runs = {}
    for (n, _index), results in run_sets.items():
        for r in results:
            bd = getattr(r, "branch_diagnostics", None) or {}
            dt = bd.get("decision_touch")
            if dt is None:
                raise ValueError(
                    f"run for n={n} has no decision_touch diagnostics — "
                    f"rebuilt pre-M2a binary? (bd 8an.3.1)")
            for phase in _PHASES:
                key = (n, phase)
                acc = pooled.setdefault(key, dict.fromkeys(_TOUCH_KEYS, 0))
                for k in _TOUCH_KEYS:
                    acc[k] += int(dt[phase][k])
            seen_instances.setdefault(n, set()).add(_index)
            runs[n] = runs.get(n, 0) + 1
    rows = []
    for n in sorted({k[0] for k in pooled}):
        for phase in _PHASES:
            acc = pooled[(n, phase)]
            consulted = acc["free"] + (acc["bothinf"] if phase == "opt_sat" else 0)
            rows.append({
                "n": n,
                "phase": phase,
                **acc,
                "touch_fraction": (consulted / acc["decisions"]
                                   if acc["decisions"] > 0 else None),
                "instances": len(seen_instances[n]),
                "runs": runs[n],
            })
    return rows


def write_touch_csv(rows, out_path):
    """Write :func:`decision_touch_report` rows to CSV."""
    fields = ["n", "phase", "decisions", "free", "bothinf", "forced",
              "touch_fraction", "instances", "runs"]
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return out_path


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #

def verdict_from_dirs(candidate_dir, default_dir, *, baselines_path=None,
                      require_largest_n=False, strict_xcheck=True, **kwargs):
    """Load two persisted run-sets and produce the §6/§8 verdict.

    ``strict_xcheck=True`` by default: the replayed default side MUST re-score
    to the frozen ``default_PI`` (the M1 capstone that caught the 4uf/cjz
    reproducibility bugs) — a drift means the binary/anchors diverged and the
    whole comparison is void. ``require_largest_n=False`` until bd 0o8 freezes
    the n=3000 default anchors.
    """
    baselines = load_frozen_baselines(baselines_path or FROZEN_BASELINES_CSV)
    candidate = load_run_set_dir(candidate_dir)
    default = load_run_set_dir(default_dir)
    return metric.score_verdict(candidate, default, baselines,
                                require_largest_n=require_largest_n,
                                strict_xcheck=strict_xcheck, **kwargs)


def summarize_verdict(out, log=print):
    """Human-readable verdict summary (per-size §6.6 deltas + §8.3 floor)."""
    agg = out["aggregation"]
    log(f"overall_pass: {out['overall_pass']} "
        f"(§6.6 {agg['overall_pass']} AND §8.3 {out['floor']['overall_pass']})")
    for n in sorted(agg["per_size"]):
        ps = agg["per_size"][n]
        fl = out["floor"]["per_size"].get(n, {})
        log(f"  n={n:>5}: W={ps.get('W')} median_PI={ps.get('median_PI')} "
            f"worst_regression={ps.get('worst_regression')} margin={ps.get('margin')} "
            f"gate_B={ps.get('gate_B_pass')} "
            f"feas_regressed={ps.get('feasibility_regressed')} "
            f"floor_pass={fl.get('stratum_pass')}")
    if out.get("default_xcheck_failures"):
        log(f"  !! default xcheck failures: {out['default_xcheck_failures']}")
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _main(argv=None):
    import argparse

    p = argparse.ArgumentParser(
        description="M2 hypothesis-check harness (bd 8an.3): run/persist schedule "
                    "sweeps, report decision-touch fractions, score verdicts.")
    p.add_argument("command", choices=["run-default", "run-candidate",
                                       "touch-report", "verdict"])
    p.add_argument("--bench-root", default=None,
                   help="CBQS-benchmarks clone root (else CBQS_BENCHMARKS_DIR).")
    p.add_argument("--frozen", default=None,
                   help=f"frozen anchor table (default {FROZEN_BASELINES_CSV}).")
    p.add_argument("--out-dir", default=None, help="run-set output directory.")
    p.add_argument("--schedule", default=None,
                   help="run-candidate: registered schedule name "
                        f"(known: {sorted(SCHEDULES) or '—'}).")
    p.add_argument("--params-json", default=None,
                   help="run-candidate: inline JSON dict of scalar set_param values "
                        "(alternative to --schedule for radius/switch schedules).")
    p.add_argument("--sizes", default=None,
                   help="comma-separated n filter over the anchored instance set.")
    p.add_argument("--seeds", default=None,
                   help=f"comma-separated master seed bank (default {DEFAULT_SEED_BANK}).")
    p.add_argument("--num-workers", type=int, default=None)
    p.add_argument("--opt-sample-cap", type=int, default=0,
                   help="bd 0o8 classical sample cap; 0 (default) = exact/faithful.")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="re-solve instances whose run-set files already exist.")
    p.add_argument("--run-dir", default=None, help="touch-report: run-set directory.")
    p.add_argument("--out", default=None, help="touch-report: output CSV path.")
    p.add_argument("--candidate-dir", default=None, help="verdict: candidate run-set dir.")
    p.add_argument("--default-dir", default=None, help="verdict: default run-set dir.")
    p.add_argument("--no-strict-xcheck", dest="strict_xcheck", action="store_false",
                   help="verdict: tolerate default-side drift from the frozen PI "
                        "(recorded, not raised) — for inspection only.")
    p.add_argument("--warm", dest="warm", action="store_true",
                   help="run-default/run-candidate: published warm general_greedy start (bd 8an.9) "
                        "— the DEFAULT (matches the canonical warm baselines_frozen.csv). Accepted "
                        "explicitly for scripts; equivalent to omitting it.")
    p.add_argument("--cold", dest="warm", action="store_false",
                   help="run-default/run-candidate: COLD 0^n start instead of the warm general_greedy "
                        "start. Reproduces the archived baselines_frozen_cold.csv. BOTH arms of an "
                        "A/B must share the start.")
    p.set_defaults(resume=True, strict_xcheck=True, warm=True)
    args = p.parse_args(argv)

    if args.command in ("run-default", "run-candidate"):
        if not args.out_dir:
            p.error(f"{args.command} requires --out-dir")
        baselines = load_frozen_baselines(args.frozen or FROZEN_BASELINES_CSV)
        instances = anchored_instances(baselines)
        if args.sizes:
            keep = {int(s) for s in args.sizes.split(",")}
            instances = [k for k in instances if k[0] in keep]
        seeds = (tuple(int(s) for s in args.seeds.split(","))
                 if args.seeds else DEFAULT_SEED_BANK)
        if args.command == "run-default":
            schedule_id, factory = "default", None
        else:
            if bool(args.schedule) == bool(args.params_json):
                p.error("run-candidate needs exactly one of --schedule / --params-json")
            if args.schedule:
                if args.schedule not in SCHEDULES:
                    p.error(f"unknown schedule {args.schedule!r} "
                            f"(known: {sorted(SCHEDULES)})")
                schedule_id, factory = args.schedule, SCHEDULES[args.schedule]
            else:
                schedule_id, factory = "params-json", json.loads(args.params_json)
        out = run_sweep(schedule_id, factory, instances, out_dir=args.out_dir,
                        seeds=seeds, bench_root=args.bench_root,
                        num_workers=args.num_workers,
                        opt_sample_cap=args.opt_sample_cap, resume=args.resume,
                        warm=args.warm)
        print(f"{schedule_id}: {len(out['done'])} solved, "
              f"{len(out['skipped'])} already present ({'WARM' if args.warm else 'COLD'} start) "
              f"-> {args.out_dir}")
    elif args.command == "touch-report":
        if not args.run_dir:
            p.error("touch-report requires --run-dir")
        rows = decision_touch_report(load_run_set_dir(args.run_dir))
        for row in rows:
            tf = row["touch_fraction"]
            print(f"n={row['n']:>5} {row['phase']:<8} decisions={row['decisions']:>12} "
                  f"touch={tf if tf is None else round(tf, 4)}")
        if args.out:
            print(f"wrote {write_touch_csv(rows, args.out)}")
    elif args.command == "verdict":
        if not (args.candidate_dir and args.default_dir):
            p.error("verdict requires --candidate-dir and --default-dir")
        out = verdict_from_dirs(args.candidate_dir, args.default_dir,
                                baselines_path=args.frozen,
                                strict_xcheck=args.strict_xcheck)
        summarize_verdict(out)


if __name__ == "__main__":  # pragma: no cover
    _main()
