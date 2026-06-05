"""Scale-invariance characterization + variance characterization (bd 8an.1.7, M0g).

Two deliverables of NORTHSTAR §9 / §11, run as an on-demand report (NOT a CI
gate — it solves n=3000):

A. **Scale-invariance profile** across the full n∈{10,100,1000,3000}: realized
   Hamming-radius (mean+var) and free-decision fraction f(n) for the radius
   lever, so the n≥100 invariance and the n=10 small-n compression are both
   documented with numbers.

B. **Variance characterization** (NORTHSTAR §11 / §6.6): per-size outcome
   variance → the instances×seeds needed for a target selection standard error,
   the noise margin used by the §6 win rule, and an inner-loop vs. validation
   size split.

   The §6 fitness metric (PI) requires the frozen B_I/L_I anchors from M1
   (8an.2) / M0b-2 (8an.1.16); until those land we characterize variance on the
   **best-of-portfolio objective** (and the §8.3 best-of-P vs median-of-P lift),
   which is the same per-solve random quantity PI integrates. ``pi_variance`` is
   left as an explicit hook so M1 can drop the PI trajectory in without
   restructuring this report (see ``_PI_HOOK``).

Run: ``python -m benchmarks.scale_invariance_characterization`` (writes
``benchmarks/artifacts/scale_invariance_report.json`` and prints a summary).
"""
import json
import math
import os
import statistics

from benchmarks.scale_invariance import collect_profiles, cross_n_summary

_PI_HOOK = (
    "PI variance is deferred to M1 (8an.2) + M0b-2 (8an.1.16): it needs the "
    "frozen B_I/L_I anchors. This report characterizes the best-of-portfolio "
    "objective variance as the available proxy; swap in the PI trajectory here "
    "once freeze_baselines populates L_I/default-PI."
)


def _objective_stats(profiles):
    """Mean / std / CV of the best-of-portfolio objective over solves that
    reached the opt phase, plus the best-of-P vs median-of-P lift (§8.3)."""
    objs = [p["objective"] for p in profiles
            if p["opt_candidates"] > 0 and p["objective"] is not None]
    lifts = []
    for p in profiles:
        feas = [v for (v, f) in (p.get("final_incumbents") or []) if f]
        if len(feas) >= 2:
            # best-of-P minus median-of-P, in the maximize direction.
            lifts.append(max(feas) - statistics.median(feas))
    if not objs:
        return {"n_solves": 0}
    mean = statistics.mean(objs)
    std = statistics.pstdev(objs) if len(objs) > 1 else 0.0
    cv = (std / abs(mean)) if mean else float("inf")
    return {
        "n_solves": len(objs),
        "obj_mean": mean,
        "obj_std": std,
        "obj_cv": cv,
        "portfolio_lift_median": statistics.median(lifts) if lifts else None,
        "portfolio_lift_max": max(lifts) if lifts else None,
    }


def _recommend_instances_x_seeds(cv, target_rel_se=0.02):
    """Replicates needed so the mean estimate's relative standard error ≤
    target_rel_se: SE = cv/√N ≤ target ⇒ N ≥ (cv/target)². Returns the per-size
    instances×seeds budget (rounded up, floored at 1)."""
    if cv is None or not math.isfinite(cv):
        return None
    return max(1, math.ceil((cv / target_rel_se) ** 2))


def characterize(sizes=(10, 100, 1000, 3000), n_instances=3, seeds=(0, 1),
                 radius=8.0, num_workers=8, M=2500, target_rel_se=0.02):
    """Run the full sweep and return the report dict (also serializable)."""
    profiles = collect_profiles(list(sizes), n_instances=n_instances, seeds=seeds,
                                radius=radius, num_workers=num_workers, M=M)

    # A. scale-invariance profile (median per n of f, radius mean+var)
    f_sum = cross_n_summary(profiles, "f")
    rmean_sum = cross_n_summary(profiles, "r_mean")
    rvar_sum = cross_n_summary(profiles, "r_var")

    per_size = {}
    for n in sizes:
        ostat = _objective_stats(profiles[n])
        n_feasible = sum(1 for p in profiles[n] if p["feasible"])
        n_reached_opt = sum(1 for p in profiles[n] if p["opt_candidates"] > 0)
        per_size[n] = {
            "f": f_sum["per_n_median"].get(n),
            "radius_mean": rmean_sum["per_n_median"].get(n),
            "radius_var": rvar_sum["per_n_median"].get(n),
            "n_feasible": n_feasible,
            "n_reached_opt": n_reached_opt,
            "n_total": len(profiles[n]),
            **ostat,
            "recommended_instances_x_seeds": _recommend_instances_x_seeds(
                ostat.get("obj_cv"), target_rel_se),
            # §6.6 noise margin proxy: a candidate must beat default by more than
            # this (the default's own outcome spread at this n) to count as a win.
            "noise_margin_proxy": ostat.get("obj_std"),
        }

    # B. invariance regime (n≥100 scale-stable; n=10 = small-n compression).
    big = [n for n in sizes if n >= 100]
    invariance = {
        "scale_stable_sizes": big,
        "f_rel_spread_big": cross_n_summary(
            {n: profiles[n] for n in big}, "f")["rel_spread"] if len(big) >= 2 else None,
        "radius_mean_rel_spread_big": cross_n_summary(
            {n: profiles[n] for n in big}, "r_mean")["rel_spread"] if len(big) >= 2 else None,
        "small_n_note": (
            "n=10 sits in the small-n compression regime (NORTHSTAR §4: "
            "38–56% compression); it is a drift control, not an asserted-"
            "invariant size. See tests/test_scale_invariance.py."
        ),
    }

    # Inner-loop vs validation size split (NORTHSTAR §9 splits / §11).
    # Inner loop = the cheap, scale-stable sizes the population search iterates on;
    # validation = the near-target large sizes scored less often.
    split = {
        "inner_loop_sizes": [n for n in big if n <= 1000],
        "validation_sizes": [n for n in sizes if n >= 1000],
        "rationale": (
            "Iterate on n≥100 sizes up to 1000 (scale-stable, cheap enough for "
            "many candidates); validate on the near-target large sizes "
            "(1000+, incl. the n=3000 calibration subset, §9). n=10 excluded "
            "from selection (small-n compression regime)."
        ),
    }

    return {
        "config": {
            "sizes": list(sizes), "n_instances": n_instances,
            "seeds": list(seeds), "radius": radius,
            "num_workers": num_workers, "M": M, "target_rel_se": target_rel_se,
        },
        "per_size": {str(k): v for k, v in per_size.items()},
        "invariance": invariance,
        "size_split": split,
        "pi_variance": None,
        "pi_variance_note": _PI_HOOK,
    }


def _artifact_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "artifacts", "scale_invariance_report.json")


def write_report(report, path=None):
    path = path or _artifact_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    return path


def _print_summary(report):
    print("=" * 72)
    print("Scale-invariance + variance characterization (bd 8an.1.7, M0g)")
    print("=" * 72)
    print(f"{'n':>6} {'feas/opt/tot':>13} {'f(n)':>8} {'r_mean':>8} {'r_var':>8} "
          f"{'obj_cv':>8} {'rec_NxS':>8} {'noise_marg':>11}")
    def fmt(v, p=3):
        return f"{v:.{p}f}" if isinstance(v, (int, float)) else "NA"
    for n, s in report["per_size"].items():
        ratio = "{}/{}/{}".format(s["n_feasible"], s["n_reached_opt"], s["n_total"])
        print(f"{n:>6} {ratio:>13} "
              f"{fmt(s.get('f'), 4):>8} {fmt(s.get('radius_mean'), 2):>8} "
              f"{fmt(s.get('radius_var'), 2):>8} {fmt(s.get('obj_cv'), 4):>8} "
              f"{str(s.get('recommended_instances_x_seeds')):>8} "
              f"{fmt(s.get('noise_margin_proxy'), 1):>11}")
    inv = report["invariance"]
    print(f"\nn≥100 invariance: f rel-spread="
          f"{inv['f_rel_spread_big']}, radius rel-spread={inv['radius_mean_rel_spread_big']}")
    print(f"size split: inner-loop={report['size_split']['inner_loop_sizes']}, "
          f"validation={report['size_split']['validation_sizes']}")
    print(f"\nPI variance: {report['pi_variance_note']}")


if __name__ == "__main__":
    rep = characterize()
    p = write_report(rep)
    _print_summary(rep)
    print(f"\nwrote {p}")
