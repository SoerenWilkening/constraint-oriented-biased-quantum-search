"""Frozen baseline tables for the Eq.29 (arXiv:2512.08384) benchmark (M0b).

Freezes the per-instance reference objective ``B_I`` from the *committed* classical-
solver results in the CBQS-benchmarks repo. Per NORTHSTAR §6/§11:

    B_I = best-known FEASIBLE objective over the NON-CBQS solvers
          {gurobi, hexaly, simanneal}, per (size, index).

This is the frontier the agent-discovered schedule is scored against (matching the
default is neutral, not a win — so CBQS's own ``iqs`` rows are excluded). The Eq.29
objective is MAXIMIZE, so B_I = max obj over the qualifying rows.

``L_I`` (CBQS-default median first-feasible) and default-``PI`` (median PI over the seed
bank) come from our OWN oracle-indexed CBQS-default runs and are produced by
:func:`freeze_default_anchors` (bd 8an.1.16), which runs the default schedule over a fixed
seed bank and scores each run with the M1 metric (``benchmarks.metric``). They depend on the
M0c/d/e oracle harness; §1.2/§6 forbid substituting wall-clock, so they are NEVER frozen at a
capped ``M`` — the run uses the real per-worker budget ``T(n)``. Until that freeze runs the
columns stay empty, and the M1 metric guards a still-empty ``L_I``/``default_PI`` against being
read as ``0`` (``metric.require_anchor`` raises; ``metric.score_run_set`` skips-with-reason).

Sources (git-LFS; set ``CBQS_BENCHMARKS_DIR`` or pass ``bench_root=``):
    <root>/Paper_general_constraints/plots/classical_comparison.csv  (gurobi,hexaly,iqs; n=500..3000)
    <root>/Paper_general_constraints/plots/res.csv                   (gurobi,hexaly,simanneal,iqs; n=10..1000)
both with schema ``size,index,obj,time,oracles,preprocess-time,method`` (anytime rows;
several per (size,index,method)). Scoped pull (the full repo is ~38 GiB):
    git lfs pull --include="Paper_general_constraints/plots/classical_comparison.csv" \
                 --include="Paper_general_constraints/plots/res.csv"

One-command freeze (with a clone available):
    CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.baselines freeze
"""
import csv
import math
import os
import statistics

try:  # reuse the CBQS_BENCHMARKS_DIR resolver in both import contexts
    from eq29_loader import default_bench_root          # flat (tests put benchmarks/ on sys.path)
except ImportError:  # pragma: no cover - exercised via `python -m benchmarks.baselines`
    from benchmarks.eq29_loader import default_bench_root  # package import

#: Non-CBQS solvers whose best feasible objective defines the frontier B_I (§6/§11).
#: ``iqs`` is CBQS (excluded — matching it is neutral); ``*-bound`` rows are dual
#: optimality bounds (not feasible primal); ``*-modeling-time`` rows are timing, not
#: objectives. All three are filtered by :func:`_is_bi_row`.
BI_METHODS = ("gurobi", "hexaly", "simanneal")

#: Suffixes marking rows that are NOT a feasible primal objective.
_NON_PRIMAL_SUFFIXES = ("-bound", "-modeling-time")

PLOTS_SUBDIR = os.path.join("Paper_general_constraints", "plots")
RESULT_CSVS = ("classical_comparison.csv", "res.csv")

#: Columns of the frozen baseline table. L_I / default_PI are emitted empty (pending
#: the oracle-indexed CBQS-default runs — M0c/d/e — and the §6 metric, M1).
FROZEN_COLUMNS = ("size", "index", "B_I", "B_I_method", "L_I", "default_PI")


def _csv_paths(bench_root=None):
    """Absolute paths to the two committed result CSVs in a CBQS-benchmarks clone."""
    root = bench_root or default_bench_root()
    if not root:
        raise RuntimeError(
            "Set CBQS_BENCHMARKS_DIR (or pass bench_root=) to a CBQS-benchmarks clone."
        )
    return [os.path.join(root, PLOTS_SUBDIR, name) for name in RESULT_CSVS]


def read_solver_results(paths):
    """Read solver-result CSV(s) into a list of row dicts.

    Each row dict: ``{"size": int, "index": int, "obj": float, "method": str}``.
    Rows are 'anytime' incumbents — there may be several per (size, index, method).
    Missing files are skipped (the two CSVs cover overlapping size ranges; the
    aggregate fail-loud guard lives in :func:`freeze_baselines`).

    Rows the benchmark maintainer commented out with a leading ``#`` (``res.csv``
    has ~2042, e.g. ``# 1000,0,...``) are skipped — ``csv`` does not treat ``#`` as
    a comment, so without this they would crash ``int()`` on ``"# 1000"``.
    """
    rows = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                size_field = (r.get("size") or "").strip()
                if not size_field or size_field.startswith("#"):
                    continue  # commented-out / blank anytime row
                rows.append({
                    "size": int(size_field),
                    "index": int(r["index"]),
                    "obj": float(r["obj"]),
                    "method": r["method"].strip().lower(),
                })
    return rows


def _is_bi_row(method):
    """True iff *method* is a feasible primal objective from a non-CBQS solver.

    Excludes ``iqs`` (CBQS), ``*-bound`` (dual bounds), ``*-modeling-time`` (timing).
    Requires an EXACT match against :data:`BI_METHODS` (after stripping those
    suffixes) so any other method — including the CBQS-family quantum solvers
    present in the real data (e.g. ``qbnb``, ``nested-qs``) or a future variant —
    is excluded rather than silently counted toward the non-CBQS frontier.
    """
    m = method.strip().lower()
    if any(m.endswith(suf) for suf in _NON_PRIMAL_SUFFIXES):
        return False
    return m in BI_METHODS


def compute_b_i(rows):
    """B_I per (size, index) = max feasible obj over {gurobi, hexaly, simanneal}.

    Returns ``{(size, index): (b_i: float, method: str)}`` where *method* is the
    solver that achieved B_I (provenance). Instances with no qualifying non-CBQS
    feasible row are OMITTED — B_I is undefined there, so they cannot anchor the
    scored set (§6 drops non-discriminating instances).
    """
    best = {}
    for r in rows:
        if not _is_bi_row(r["method"]):
            continue
        if not math.isfinite(r["obj"]):
            continue  # -inf/nan = failed/missing-anneal sentinel, not a feasible primal (§6)
        key = (r["size"], r["index"])
        if key not in best or r["obj"] > best[key][0]:
            best[key] = (r["obj"], r["method"])
    return best


def _fmt_num(v):
    """CSV-format a numeric: drop the trailing ``.0`` for integral values.

    The Eq.29 objective is integer-valued and within 2**53 even at n=3000, so float
    parsing is exact; we store integral B_I as a clean integer for diffability.
    """
    if not math.isfinite(v):  # backstop; compute_b_i already drops non-finite rows
        raise ValueError(f"non-finite B_I {v!r} cannot be frozen (not a feasible objective)")
    iv = int(round(v))
    return str(iv) if float(iv) == v else repr(v)


def freeze_baselines(bench_root=None, out_path=None, require_all=True):
    """Compute B_I from the committed CSVs and write the frozen baseline table.

    ``L_I`` / ``default_PI`` are written EMPTY (pending the oracle-indexed CBQS
    harness, M0c/d/e, and the §6 metric, M1). Rows are sorted by (size, index) for
    a stable, reviewable diff. Returns the path written.

    Fail-loud (§2.1): raises if no source CSV is found (wrong path / un-pulled LFS),
    if ``require_all`` (default) and any expected CSV is missing — a partial pull
    silently drops a whole size stratum, and the large-n (1100..3000) stratum the
    §6.6 gate runs on lives ONLY in ``classical_comparison.csv`` — or if zero B_I
    instances result. Unit tests that intentionally use one synthetic CSV pass
    ``require_all=False``.
    """
    paths = _csv_paths(bench_root)
    present = [p for p in paths if os.path.isfile(p)]
    missing = [p for p in paths if not os.path.isfile(p)]
    if not present:
        raise FileNotFoundError(
            f"No result CSVs found (looked for {paths}). Set CBQS_BENCHMARKS_DIR to a "
            f"CBQS-benchmarks clone with git-lfs pulled (plots/{{classical_comparison,res}}.csv)."
        )
    if require_all and missing:
        raise FileNotFoundError(
            f"Partial benchmark data — missing {missing}. A partial LFS pull silently "
            f"drops a whole size stratum (large-n lives only in classical_comparison.csv). "
            f"Pull both CSVs, or pass require_all=False to freeze from what is present."
        )
    rows = read_solver_results(present)
    b_i = compute_b_i(rows)
    if not b_i:
        raise ValueError(
            f"Read {len(rows)} rows from {present} but computed 0 B_I instances — no "
            f"feasible non-CBQS {list(BI_METHODS)} rows (LFS stub / wrong schema?)."
        )
    if out_path is None:
        out_path = os.path.join(os.path.dirname(__file__), "baselines_frozen.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")  # LF, not the csv default CRLF
        w.writerow(FROZEN_COLUMNS)
        for size, index in sorted(b_i):
            val, method = b_i[(size, index)]
            w.writerow([size, index, _fmt_num(val), method, "", ""])
    return out_path


def load_frozen_baselines(path):
    """Load a frozen baseline table into ``{(size, index): {col: value}}``.

    ``B_I`` is returned as float; empty ``L_I`` / ``default_PI`` cells load as ``None``.
    This is the accessor the §6 metric (M1) consumes.
    """
    table = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            key = (int(r["size"]), int(r["index"]))
            table[key] = {
                "B_I": float(r["B_I"]) if r["B_I"] != "" else None,
                "B_I_method": r["B_I_method"] or None,
                "L_I": float(r["L_I"]) if r["L_I"] != "" else None,
                "default_PI": float(r["default_PI"]) if r["default_PI"] != "" else None,
            }
    return table


# --------------------------------------------------------------------------- #
# L_I / default-PI anchors from CBQS-default seed-bank runs (bd 8an.1.16, NORTHSTAR §6)
# --------------------------------------------------------------------------- #

#: Fixed bank of default master seeds for the L_I / default-PI anchors (NORTHSTAR §6 item 1:
#: "median over a fixed bank of default seeds"). Odd count so the per-instance median is a single
#: middle value — no even-length averaging that could land the default-PI on the +∞ never-feasible
#: sentinel. Each seed is one best-of-portfolio default solve.
DEFAULT_SEED_BANK = (0, 1, 2, 3, 4, 5, 6)


def first_feasible_objective(result):
    """First feasible best-of-portfolio objective of one default run, or None if never feasible.

    ``result.history`` is feasible-only and oracle-ascending (SearchLib.c:213, Model.pyx:828-842),
    so ``history[0]`` is the earliest feasible incumbent across the portfolio; its value is the
    run's first-feasible objective (NORTHSTAR §6 item 1). ``None`` when the run never reached
    feasibility (empty history).
    """
    history = getattr(result, "history", None) or []
    return float(history[0][0]) if history else None


def default_instance_anchors(results, B_I, n, T_I=None):
    """L_I + default-PI for one Eq.29 instance from a seed bank of CBQS-default runs (NORTHSTAR §6).

    ``L_I`` = MEDIAN first-feasible objective over the runs that reached feasibility (§6 item 1).
    ``default_PI`` = MEDIAN PI over the WHOLE seed bank — a never-feasible run contributes ``+∞``
    (§6 item 5) — each run scored against the frozen ``L_I`` with the M1 metric. ``B_I`` is the
    frozen non-CBQS frontier objective; ``T_I`` defaults to ``oracle_budget(n)``.

    Returns a status-tagged dict ``{status, L_I, default_PI, n_runs, n_feasible_runs,
    per_run_first_feasible, per_run_PI}``; ``default_PI`` is ``None`` unless ``status == "ok"``:
      - ``"never_feasible"``    no run reached feasibility (``L_I`` undefined — cannot anchor).
      - ``"dropped_L_ge_B"``    ``L_I >= B_I`` (default meets/beats the frontier → drop, §6 item 1).
      - ``"default_unreliable"````L_I < B_I`` but the median PI is non-finite (default feasible on
                                ≤ half the seeds); ``default_PI`` withheld rather than writing ``+∞``.
      - ``"ok"``                ``L_I`` and a finite ``default_PI`` both set.

    §1.2/§6: the runs MUST be at the real per-worker budget ``T(n)`` — never a capped ``M``.
    """
    try:  # lazy: break the metric<->baselines import cycle (metric imports load_frozen_baselines)
        from metric import compute_primal_integral, oracle_budget
    except ImportError:  # pragma: no cover - package import
        from benchmarks.metric import compute_primal_integral, oracle_budget
    if T_I is None:
        T_I = oracle_budget(n)
    first_feas = [first_feasible_objective(r) for r in results]
    feasible = [f for f in first_feas if f is not None]
    base = {"n_runs": len(results), "n_feasible_runs": len(feasible),
            "per_run_first_feasible": first_feas, "L_I": None, "default_PI": None,
            "per_run_PI": None}
    if not feasible:
        return {**base, "status": "never_feasible"}
    L_I = float(statistics.median(feasible))
    if L_I >= B_I:
        return {**base, "L_I": L_I, "status": "dropped_L_ge_B"}
    per_run_PI = [compute_primal_integral(getattr(r, "history", None) or [], B_I, L_I, T_I)
                  for r in results]
    default_PI = float(statistics.median(per_run_PI))
    if not math.isfinite(default_PI):  # default feasible on ≤ half the seeds → withhold, don't write +∞
        return {**base, "L_I": L_I, "per_run_PI": per_run_PI, "status": "default_unreliable"}
    return {**base, "L_I": L_I, "default_PI": default_PI, "per_run_PI": per_run_PI, "status": "ok"}


def run_default_seed_bank(n, index, seeds, *, bench_root=None, M=-1, num_workers=None, verify=True):
    """Run the CBQS-DEFAULT schedule on one Eq.29 instance once per master seed (NORTHSTAR §6/§11).

    Default schedule = ``build_model`` + ``close()`` (auto ``branching_bias = n/4``) with NO custom
    phase params. ``M=-1`` uses the real per-worker budget ``T(n)`` — do NOT freeze anchors at a
    capped ``M`` (§1.2/§6). Returns one ``OptimizeResult`` per seed. Requires cbqs built + the Eq.29
    instances (``CBQS_BENCHMARKS_DIR`` or ``bench_root``).
    """
    try:  # lazy: pulls in cbqs (the C extension) only when an actual solve is requested
        from eq29_loader import load_eq29, build_model
    except ImportError:  # pragma: no cover - package import
        from benchmarks.eq29_loader import load_eq29, build_model
    c1, c2, c3 = load_eq29(n, index, bench_root)
    results = []
    for seed in seeds:
        m = build_model(c1, c2, c3)
        m.seed = int(seed)
        m.set_param("M", M)
        if num_workers is not None:
            m.set_param("num_workers", num_workers)
        m.set_param("verify", verify)
        results.append(m.solve())
    return results


def freeze_default_anchors(*, seeds=DEFAULT_SEED_BANK, bench_root=None, frozen_path=None,
                           out_path=None, sizes=None, run_fn=None, M=-1, num_workers=None,
                           log=None):
    """Fill L_I + default-PI in the frozen baseline table from CBQS-default seed-bank runs (bd 8an.1.16).

    Loads the frozen B_I table (*frozen_path*, default the committed ``baselines_frozen.csv``), runs
    the default schedule over *seeds* per instance, writes ``L_I`` + ``default_PI``, DROPS instances
    with ``L_I >= B_I`` (non-discriminating, §6 item 1), and writes the updated table to *out_path*
    (default: in place). *sizes* restricts which strata to (re)compute — unlisted sizes keep their
    existing row verbatim, so a partial freeze never wipes already-frozen anchors. ``run_fn(n, index,
    seeds) -> list[OptimizeResult]`` is injectable (real ``run_default_seed_bank`` by default; a mock
    in tests). A never-feasible-default or unreliable-default instance keeps its row with EMPTY
    anchors (the M1 guard then skips it — never reads empty as 0). Returns a summary dict.

    Fail-loud (§2.1): raises if the frozen table is missing/empty (run ``freeze`` first).
    """
    _log = log or (lambda *_a, **_k: None)
    frozen_path = frozen_path or os.path.join(os.path.dirname(__file__), "baselines_frozen.csv")
    if not os.path.isfile(frozen_path):
        raise FileNotFoundError(
            f"Frozen B_I table not found at {frozen_path}; run `freeze` first (B_I is the anchor "
            f"L_I/default-PI are scored against)."
        )
    table = load_frozen_baselines(frozen_path)
    if not table:
        raise ValueError(f"Frozen table {frozen_path} has no instances — nothing to anchor.")
    if run_fn is None:
        def run_fn(n, index, _seeds):
            return run_default_seed_bank(n, index, _seeds, bench_root=bench_root,
                                         M=M, num_workers=num_workers)

    out_rows = []
    summary = {"ok": [], "dropped": [], "never_feasible": [], "default_unreliable": [],
               "skipped": [], "n_processed": 0}
    for (size, index) in sorted(table):
        row = table[(size, index)]
        B_I, method = row["B_I"], row["B_I_method"]
        if (sizes is not None and size not in sizes) or B_I is None:
            # Keep verbatim: a stratum we are not (re)computing, or one with no frontier B_I.
            out_rows.append((size, index, B_I, method, row["L_I"], row["default_PI"]))
            if B_I is None:
                summary["skipped"].append((size, index, "B_I None"))
            continue
        summary["n_processed"] += 1
        results = run_fn(size, index, seeds)
        a = default_instance_anchors(results, B_I, size)
        status = a["status"]
        if status == "dropped_L_ge_B":
            summary["dropped"].append((size, index, a["L_I"]))
            _log(f"drop  {size}_{index}: L_I={a['L_I']} >= B_I={B_I} (non-discriminating)")
            continue  # OMIT from the table (§6 item 1)
        if status == "never_feasible":
            summary["never_feasible"].append((size, index))
            out_rows.append((size, index, B_I, method, None, None))
            _log(f"empty {size}_{index}: default never feasible over {len(seeds)} seeds")
            continue
        if status == "default_unreliable":
            summary["default_unreliable"].append((size, index, a["L_I"]))
            out_rows.append((size, index, B_I, method, a["L_I"], None))
            _log(f"warn  {size}_{index}: L_I={a['L_I']} but median PI non-finite — default_PI withheld")
            continue
        out_rows.append((size, index, B_I, method, a["L_I"], a["default_PI"]))
        summary["ok"].append((size, index))
        _log(f"ok    {size}_{index}: L_I={a['L_I']} default_PI={a['default_PI']:.6f}")

    out_path = out_path or frozen_path
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(FROZEN_COLUMNS)
        for (size, index, B_I, method, L_I, default_PI) in out_rows:
            w.writerow([size, index,
                        _fmt_num(B_I) if B_I is not None else "",
                        method or "",
                        _fmt_num(L_I) if L_I is not None else "",
                        _fmt_num(default_PI) if default_PI is not None else ""])
    summary["out_path"] = out_path
    return summary


def _main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="Freeze the Eq.29 baseline table (B_I; L_I/default-PI).")
    p.add_argument("command", choices=["freeze", "freeze-default"],
                   help="'freeze' = B_I from committed CSVs; 'freeze-default' = L_I/default-PI from "
                        "CBQS-default seed-bank runs (bd 8an.1.16, needs cbqs + CBQS_BENCHMARKS_DIR).")
    p.add_argument("--bench-root", default=None,
                   help="CBQS-benchmarks clone root (else CBQS_BENCHMARKS_DIR).")
    p.add_argument("--out", default=None, help="output CSV path")
    p.add_argument("--allow-partial", action="store_true",
                   help="freeze from whichever CSVs are present (default: require both).")
    p.add_argument("--frozen", default=None, help="frozen B_I table to read (freeze-default).")
    p.add_argument("--sizes", default=None,
                   help="freeze-default: comma-separated n's to (re)compute (else all).")
    p.add_argument("--seeds", default=None,
                   help="freeze-default: comma-separated master seed bank (else DEFAULT_SEED_BANK).")
    p.add_argument("--num-workers", type=int, default=None,
                   help="freeze-default: portfolio workers per solve (else solver default).")
    args = p.parse_args(argv)
    if args.command == "freeze":
        out = freeze_baselines(bench_root=args.bench_root, out_path=args.out,
                               require_all=not args.allow_partial)
        table = load_frozen_baselines(out)
        print(f"Froze B_I for {len(table)} instances -> {out}")
    elif args.command == "freeze-default":
        sizes = ([int(s) for s in args.sizes.split(",")] if args.sizes else None)
        seeds = (tuple(int(s) for s in args.seeds.split(",")) if args.seeds else DEFAULT_SEED_BANK)
        summary = freeze_default_anchors(seeds=seeds, bench_root=args.bench_root,
                                         frozen_path=args.frozen, out_path=args.out, sizes=sizes,
                                         num_workers=args.num_workers, log=print)
        print(f"freeze-default: {len(summary['ok'])} ok, {len(summary['dropped'])} dropped, "
              f"{len(summary['never_feasible'])} never-feasible, "
              f"{len(summary['default_unreliable'])} unreliable -> {summary['out_path']}")


if __name__ == "__main__":
    _main()
