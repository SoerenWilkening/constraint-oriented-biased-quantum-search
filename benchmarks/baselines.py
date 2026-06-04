"""Frozen baseline tables for the Eq.29 (arXiv:2512.08384) benchmark (M0b).

Freezes the per-instance reference objective ``B_I`` from the *committed* classical-
solver results in the CBQS-benchmarks repo. Per NORTHSTAR §6/§11:

    B_I = best-known FEASIBLE objective over the NON-CBQS solvers
          {gurobi, hexaly, simanneal}, per (size, index).

This is the frontier the agent-discovered schedule is scored against (matching the
default is neutral, not a win — so CBQS's own ``iqs`` rows are excluded). The Eq.29
objective is MAXIMIZE, so B_I = max obj over the qualifying rows.

NOT produced here: ``L_I`` (CBQS-default median first-feasible) and default-``PI``
(median PI over the seed bank). Those come from our OWN oracle-indexed CBQS-default
runs, which depend on the M0c/d/e oracle harness and the §6 PI metric (M1), and
§1.2/§6 forbid substituting wall-clock. The frozen table carries empty ``L_I`` /
``default_PI`` columns as placeholders to be filled once that harness lands.

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


def _main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="Freeze the Eq.29 baseline table (B_I).")
    p.add_argument("command", choices=["freeze"])
    p.add_argument("--bench-root", default=None,
                   help="CBQS-benchmarks clone root (else CBQS_BENCHMARKS_DIR).")
    p.add_argument("--out", default=None, help="output CSV path")
    p.add_argument("--allow-partial", action="store_true",
                   help="freeze from whichever CSVs are present (default: require both).")
    args = p.parse_args(argv)
    if args.command == "freeze":
        out = freeze_baselines(bench_root=args.bench_root, out_path=args.out,
                               require_all=not args.allow_partial)
        table = load_frozen_baselines(out)
        print(f"Froze B_I for {len(table)} instances -> {out}")


if __name__ == "__main__":
    _main()
