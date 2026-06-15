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
"""
import csv
import os
import sys
import time

try:  # match baselines.py dual-mode import
    from baselines import (DEFAULT_SEED_BANK, FLOOR_CALIBRATION_CSV, calibrate_floor,
                           freeze_default_anchors, run_default_seed_bank)
except ImportError:  # pragma: no cover
    from benchmarks.baselines import (DEFAULT_SEED_BANK, FLOOR_CALIBRATION_CSV, calibrate_floor,
                                      freeze_default_anchors, run_default_seed_bank)

MARKER_DIR = os.path.join(os.path.dirname(__file__), "..", "logs", "refreeze")


def _make_memo(seeds, bench_root):
    """A run_fn that solves each (n, index) seed bank once and caches the results."""
    cache = {}

    def run(n, index, _seeds):
        key = (n, index)
        if key not in cache:
            cache[key] = run_default_seed_bank(n, index, _seeds, bench_root=bench_root,
                                               M=-1, opt_sample_cap=0, vectorized=True)
        return cache[key]

    return run, cache


def _merge_floor_size(n, run_fn, seeds, bench_root, master_path):
    """Compute the floor row(s) for size n (reusing run_fn's cache) and merge into master_path.

    calibrate_floor rewrites its whole out_path with only the sizes passed; we direct it to a
    temp file, then splice its row into the master so the existing 10..100 rows survive.
    """
    tmp = master_path + f".tmp_{n}"
    calibrate_floor(sizes=[n], seeds=seeds, bench_root=bench_root, run_fn=run_fn,
                    out_path=tmp, log=print)
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
    if not argv:
        print("usage: python -m benchmarks.refreeze_largen <comma-separated sizes>", file=sys.stderr)
        return 2
    sizes = [int(s) for s in argv[0].split(",")]
    seeds = DEFAULT_SEED_BANK
    bench_root = os.environ.get("CBQS_BENCHMARKS_DIR")
    if not bench_root:
        print("FATAL: CBQS_BENCHMARKS_DIR not set (need the Eq.29 instance clone).", file=sys.stderr)
        return 2
    os.makedirs(MARKER_DIR, exist_ok=True)

    print(f"=== refreeze_largen START {time.strftime('%Y-%m-%d %H:%M:%S')} "
          f"sizes={sizes} bench_root={bench_root} ===", flush=True)
    for n in sizes:
        marker = os.path.join(MARKER_DIR, f"done_{n}.marker")
        if os.path.exists(marker):
            print(f"[skip] size {n}: marker present ({marker})", flush=True)
            continue
        t0 = time.time()
        print(f"----- size {n} START {time.strftime('%H:%M:%S')} -----", flush=True)
        run_fn, cache = _make_memo(seeds, bench_root)
        fsum = freeze_default_anchors(sizes=[n], seeds=seeds, run_fn=run_fn,
                                      M=-1, opt_sample_cap=0, log=print)
        floor_row = _merge_floor_size(n, run_fn, seeds, bench_root, FLOOR_CALIBRATION_CSV)
        n_cached = len(cache)
        cache.clear()
        dt = time.time() - t0
        with open(marker, "w") as f:
            f.write(f"size={n} dt={dt:.1f}s solved_instances={n_cached} "
                    f"ok={len(fsum['ok'])} never_feasible={len(fsum['never_feasible'])} "
                    f"dropped={len(fsum['dropped'])} floor={floor_row.get('status') if floor_row else 'none'}\n")
        print(f"----- size {n} END {time.strftime('%H:%M:%S')} wall={dt:.1f}s "
              f"ok={len(fsum['ok'])} nf={len(fsum['never_feasible'])} dropped={len(fsum['dropped'])} "
              f"floor={floor_row.get('status') if floor_row else 'none'} (solved {n_cached} instances once) -----",
              flush=True)
    print(f"=== refreeze_largen END {time.strftime('%Y-%m-%d %H:%M:%S')} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
