#!/usr/bin/env python3
"""Resumable single-solve anchor + floor re-freeze driver (bd 8an.4.8 / 0o8).

The two CLI commands ``freeze-default`` (L_I + default_PI -> ``baselines_frozen.csv``) and
``calibrate-floor`` (spread_obj/lift -> ``floor_calibration.csv``) both run the CBQS-default
seed bank over the same instances at the same budget (M=-1 -> T(n), opt_sample_cap=0). Run
separately they solve every instance TWICE -- a ~2x cost the large-n strata cannot absorb
(n>=1000 is hours/stratum). This driver runs each instance's seed bank ONCE and feeds the
SAME ``OptimizeResult`` objects to BOTH blessed functions via their injectable ``run_fn``
seam, halving the large-n wall-time. No solver/anchor logic is reimplemented here.

Per size, in order: (1) ``freeze_default_anchors`` writes the anchor table (populating the
run cache), (2) ``calibrate_floor`` consumes the cache (zero re-solve) and its row is merged
into the master floor CSV (calibrate_floor is not partial-safe -- it rewrites only the sizes
it is given -- so we merge per size to preserve the already-frozen 10..100 rows), (3) a
done-marker is written. Resumable: a size with a marker is skipped; each size persists before
the next, so a crash at n=2500 keeps every earlier stratum. Faithful by construction: cap=0
(exact), M=-1 (T(n)), DEFAULT_SEED_BANK=(1..7) -- identical to the verified small-n re-freeze.

Usage:
    CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.refreeze_largen 150,500,1000,1500,2000,2500,3000
    # bd 8an.9 WARM re-freeze (the published iqs protocol, now the project default):
    CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.refreeze_largen --warm 10,20,30,40,50,60,70,80,90,100,150,500
"""
import csv
import os
import sys
import time

try:  # match baselines.py dual-mode import
    from baselines import (DEFAULT_SEED_BANK, FLOOR_CALIBRATION_CSV, FROZEN_COLUMNS, _fmt_num,
                           calibrate_floor, freeze_default_anchors, load_frozen_baselines,
                           run_default_seed_bank)
except ImportError:  # pragma: no cover
    from benchmarks.baselines import (DEFAULT_SEED_BANK, FLOOR_CALIBRATION_CSV, FROZEN_COLUMNS,
                                      _fmt_num, calibrate_floor, freeze_default_anchors,
                                      load_frozen_baselines, run_default_seed_bank)

MARKER_DIR = os.path.join(os.path.dirname(__file__), "..", "logs", "refreeze")
#: bd 8an.9: warm anchors are built in a SEPARATE skeleton so the per-size single-protocol guard
#: never sees a transient warm+cold mix (pending sizes are anchor-cleared B_I-only). A final swap
#: (done by hand / the close step) makes these canonical: cp baselines_frozen.csv ..._cold.csv;
#: mv baselines_frozen_warm.csv baselines_frozen.csv (likewise the floor).
WARM_FROZEN_CSV = os.path.join(os.path.dirname(__file__), "baselines_frozen_warm.csv")
WARM_FLOOR_CSV = os.path.join(os.path.dirname(__file__), "floor_calibration_warm.csv")


def _seed_warm_skeleton(dst_path, src_path=None):
    """Create the warm anchor skeleton at *dst_path* (idempotent — leave it if it exists, to resume).

    Copies the cold ``baselines_frozen.csv`` KEEPING B_I + the cold ``L_I`` (bd 8an.9 keeps the cold
    L_I as the shared normalizer) and ``default_cap``, but BLANKS ``default_PI`` + ``protocol`` on
    EVERY row. The warm re-freeze then fills the warm ``default_PI`` size-by-size against the kept
    cold L_I. Because the single-protocol guard keys on ``default_PI`` (not L_I), a not-yet-filled
    row (cold L_I, no default_PI) is NOT protocol-anchored — so each per-size fill writes a table
    whose SCORED rows are uniformly warm, never a warm+cold mix, while staying resumable per size.
    """
    if os.path.exists(dst_path):
        return
    src = src_path or os.path.join(os.path.dirname(__file__), "baselines_frozen.csv")
    table = load_frozen_baselines(src)
    with open(dst_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(FROZEN_COLUMNS)
        for (size, index) in sorted(table):
            row = table[(size, index)]
            w.writerow([size, index,
                        _fmt_num(row["B_I"]) if row["B_I"] is not None else "",
                        row["B_I_method"] or "",
                        _fmt_num(row["L_I"]) if row["L_I"] is not None else "",
                        "",                          # default_PI blanked — filled warm per size
                        row["default_cap"] or "",
                        ""])                         # protocol blanked — set warm per size


def _make_memo(seeds, bench_root, warm=False):
    """A run_fn that solves each (n, index) seed bank once and caches the results."""
    cache = {}

    def run(n, index, _seeds):
        key = (n, index)
        if key not in cache:
            cache[key] = run_default_seed_bank(n, index, _seeds, bench_root=bench_root,
                                               M=-1, opt_sample_cap=0, vectorized=True, warm=warm)
        return cache[key]

    return run, cache


def _merge_floor_size(n, run_fn, seeds, bench_root, master_path, warm=False):
    """Compute the floor row(s) for size n (reusing run_fn's cache) and merge into master_path.

    calibrate_floor rewrites its whole out_path with only the sizes passed; we direct it to a
    temp file, then splice its row into the master so the existing 10..100 rows survive. ``warm``
    is informational here — run_fn already determines the start, so the cached (already-warm)
    results drive the floor; passing it keeps calibrate_floor's own provenance consistent.
    """
    tmp = master_path + f".tmp_{n}"
    calibrate_floor(sizes=[n], seeds=seeds, bench_root=bench_root, run_fn=run_fn,
                    warm=warm, out_path=tmp, log=print)
    cols, new_rows = None, {}
    with open(tmp) as f:
        r = csv.DictReader(f)
        cols = r.fieldnames
        for row in r:
            new_rows[int(row["size"])] = row
    os.remove(tmp)

    master = {}
    if os.path.exists(master_path):
        with open(master_path) as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or cols
            for row in r:
                master[int(row["size"])] = row
    master.update(new_rows)  # n added or replaced; all other sizes preserved verbatim
    with open(master_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for s in sorted(master):
            w.writerow(master[s])
    return new_rows.get(n)


def main(argv):
    argv = list(argv)
    warm = "--warm" in argv
    argv = [a for a in argv if a != "--warm"]
    if not argv:
        print("usage: python -m benchmarks.refreeze_largen [--warm] <comma-separated sizes>",
              file=sys.stderr)
        return 2
    sizes = [int(s) for s in argv[0].split(",")]
    seeds = DEFAULT_SEED_BANK
    bench_root = os.environ.get("CBQS_BENCHMARKS_DIR")
    if not bench_root:
        print("FATAL: CBQS_BENCHMARKS_DIR not set (need the Eq.29 instance clone).", file=sys.stderr)
        return 2
    os.makedirs(MARKER_DIR, exist_ok=True)

    # bd 8an.9: warm builds a SEPARATE skeleton (anchors cleared for these sizes) so the per-size
    # single-protocol guard never sees a transient warm+cold mix; cold writes in place as before.
    protocol = "warm" if warm else "cold"
    frozen_path = WARM_FROZEN_CSV if warm else None  # None -> freeze_default_anchors default (cold table)
    floor_path = WARM_FLOOR_CSV if warm else FLOOR_CALIBRATION_CSV
    marker_suffix = "_warm" if warm else ""
    if warm:
        _seed_warm_skeleton(WARM_FROZEN_CSV)
        print(f"[warm] anchors -> {WARM_FROZEN_CSV} (cold L_I kept; default_PI re-frozen warm); "
              f"floor -> {WARM_FLOOR_CSV}. After ALL sizes done, swap to canonical (archive cold, "
              f"mv warm -> baselines_frozen.csv/floor).", flush=True)

    print(f"=== refreeze_largen START {time.strftime('%Y-%m-%d %H:%M:%S')} protocol={protocol} "
          f"sizes={sizes} bench_root={bench_root} ===", flush=True)
    for n in sizes:
        marker = os.path.join(MARKER_DIR, f"done_{n}{marker_suffix}.marker")
        if os.path.exists(marker):
            print(f"[skip] size {n}: marker present ({marker})", flush=True)
            continue
        t0 = time.time()
        print(f"----- size {n} START {time.strftime('%H:%M:%S')} ({protocol}) -----", flush=True)
        run_fn, cache = _make_memo(seeds, bench_root, warm=warm)
        fsum = freeze_default_anchors(sizes=[n], seeds=seeds, run_fn=run_fn, warm=warm,
                                      frozen_path=frozen_path, M=-1, opt_sample_cap=0, log=print)
        floor_row = _merge_floor_size(n, run_fn, seeds, bench_root, floor_path, warm=warm)
        n_cached = len(cache)
        cache.clear()
        dt = time.time() - t0
        with open(marker, "w") as f:
            f.write(f"size={n} protocol={protocol} dt={dt:.1f}s solved_instances={n_cached} "
                    f"ok={len(fsum['ok'])} never_feasible={len(fsum['never_feasible'])} "
                    f"dropped={len(fsum['dropped'])} floor={floor_row.get('status') if floor_row else 'none'}\n")
        print(f"----- size {n} END {time.strftime('%H:%M:%S')} wall={dt:.1f}s "
              f"ok={len(fsum['ok'])} nf={len(fsum['never_feasible'])} dropped={len(fsum['dropped'])} "
              f"floor={floor_row.get('status') if floor_row else 'none'} (solved {n_cached} instances once) -----",
              flush=True)
    print(f"=== refreeze_largen END {time.strftime('%Y-%m-%d %H:%M:%S')} protocol={protocol} ===",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
