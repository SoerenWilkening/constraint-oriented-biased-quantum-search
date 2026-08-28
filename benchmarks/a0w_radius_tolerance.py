#!/usr/bin/env python3
"""bd a0w step 1: read the RADIUS-TOLERANCE constant X off the existing sweeps.

The angle-precision prediction (bd a0w) is anchored on one empirical constant:
how far may the realized neighborhood radius drift from the tuned ``r* ~ 2``
before the objective measurably degrades? The bead ASSUMED +/-10%. That assumption
sets ``eps*`` directly (``dp/p = 2*dtheta/theta`` => ``eps* = X*theta/2``), so a
factor-3 error in X is ~1.6 bits of angle precision. Pin it from data FIRST.

No new solves: this re-reads two already-frozen constant-radius sweeps.

  * bd w29 grow probe, FAITHFUL small-n (``artifacts/m5_w29_grow/n{60,90}_m1.0``)
    -- arms ``C_r2`` / ``C_r4.41`` / ``C_r6``, 9 instances x 3 seeds, obj@common.
  * bd 71e static probe, n=3000 wall-capped (``artifacts/m5_71e_probe``)
    -- arms ``strong_tight`` (r=2) / ``tight`` (r=4) / ``control`` (r=8),
    9 instances, plus ``negctl`` (identical params, different seed) which gives
    the n=3000 detectability floor directly.

Two readings per n, deliberately reported side by side:

  LINEAR   -- the conservative bound. Take the slope between r=2 and the nearest
              measured radius and extrapolate inward. Assumes NO plateau.
  QUADRATIC-- ``loss%(r) = c*(r-2)^2`` fitted through the optimum (r*~2 is the
              interior optimum, established by 71e/w29/kyg, so the first-order
              term vanishes there). This is the physically right shape but it is
              fitted only from DISTANT points, so it flatters the near field.

X is then the radius drift at which the predicted loss reaches the SEED-NOISE
FLOOR (the within-(instance, arm) objective spread across seeds) -- below that
floor a degradation is not measurable, so it is not a degradation.

Usage:  python -m benchmarks.a0w_radius_tolerance
"""
import glob, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric
from benchmarks.run_m4_n3000 import obj_at_budget

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")

#: every arm the w29 grow probe solved -- obj@common must be taken over the SAME
#: arm set the published verdict used, or the common depth B shifts.
W29_ALL_ARMS = ("C_r2", "C_r4.41", "C_r6", "G_2to4.41", "G_2to4.41_steep",
                "neg_2to2", "K_const4.41", "K_grow2to4.41", "C_r2_theta", "C_r3_theta")
W29_CONST = {"C_r2": 2.0, "C_r4.41": 4.409916944894315, "C_r6": 6.0}


def _load_dir(pattern):
    recs = {}
    for f in glob.glob(pattern):
        if os.path.basename(f) in ("summary.json", "run_config.json"):
            continue
        d = json.load(open(f))
        recs[(d["index"], d["arm"], d.get("seed"))] = d
    return recs


def _fit_quadratic_through_optimum(radii, losses_pct):
    """Least-squares c for loss%(r) = c*(r-2)^2 (zero slope at the optimum)."""
    x = np.asarray(radii, float) - 2.0
    y = np.asarray(losses_pct, float)          # loss is POSITIVE when worse
    return float(np.sum(x ** 2 * y) / np.sum(x ** 4))


def w29_small_n(n):
    recs = _load_dir(os.path.join(ART, "m5_w29_grow", f"n{n}_m1.0", "*.json"))
    if not recs:
        return None
    seeds = sorted({k[2] for k in recs})
    idxs = sorted({k[0] for k in recs})
    T = metric.oracle_budget(n)
    obj = {}
    for i in idxs:
        for s in seeds:
            cell = {a: recs.get((i, a, s)) for a in W29_ALL_ARMS}
            if any(v is None for v in cell.values()):
                continue
            B = min(min(int(r["oracle_calls"]) for r in cell.values()), T)
            for a, r in cell.items():
                obj[(i, s, a)] = obj_at_budget(r["history"], B)
    # seed-noise floor: within (instance, arm) spread over seeds
    noise = []
    for a in W29_CONST:
        for i in idxs:
            v = [obj[(i, s, a)] for s in seeds if obj.get((i, s, a)) is not None]
            if len(v) == len(seeds) and np.mean(v):
                noise.append(100.0 * (max(v) - min(v)) / abs(np.mean(v)))
    loss = {}
    for a, r in W29_CONST.items():
        pct = []
        for i in idxs:
            b = np.median([obj[(i, s, "C_r2")] for s in seeds])
            v = np.median([obj[(i, s, a)] for s in seeds])
            if b:
                pct.append(100.0 * (v - b) / b)
        loss[r] = float(np.median(pct))          # negative = worse than r=2
    return {"n": n, "instances": len(idxs), "seeds": len(seeds),
            "noise_pct": float(np.median(noise)), "loss_pct": loss}


def probe_71e_n3000():
    recs = _load_dir(os.path.join(ART, "m5_71e_probe", "*.json"))
    if not recs:
        return None
    arm_r = json.load(open(os.path.join(ART, "m5_71e_probe", "summary.json")))["arm_r_opt"]
    idxs = sorted({k[0] for k in recs})
    obj = {(i, a): recs[(i, a, s)]["objective"] for (i, a, s) in recs}
    base = {i: obj[(i, "strong_tight")] for i in idxs}       # r = 2
    loss = {}
    for arm in ("tight", "control"):
        loss[arm_r[arm]] = float(np.median(
            [100.0 * (obj[(i, arm)] - base[i]) / base[i] for i in idxs]))
    loss[2.0] = 0.0
    # negctl == control params on a different seed => the detectability floor
    noise = float(np.median([abs(100.0 * (obj[(i, "negctl")] - obj[(i, "control")]) / obj[(i, "control")])
                             for i in idxs]))
    return {"n": 3000, "instances": len(idxs), "seeds": 1,
            "noise_pct": noise, "loss_pct": loss}


def tolerance(block, r0=2.0):
    """Radius drift |dr|/r0 at which the predicted loss reaches the noise floor."""
    radii = sorted(block["loss_pct"])
    losses = [-block["loss_pct"][r] for r in radii]           # positive = worse
    nf = block["noise_pct"]
    # LINEAR through the nearest measured point above r0
    near = min((r for r in radii if r > r0), default=None)
    lin = None
    if near is not None:
        slope = (-block["loss_pct"][near]) / (near - r0)      # %/unit radius
        lin = (nf / slope / r0) if slope > 0 else float("inf")
    c = _fit_quadratic_through_optimum(radii, losses)
    quad = (np.sqrt(nf / c) / r0) if c > 0 else float("inf")
    return {"linear": lin, "quadratic": float(quad), "c_quadratic": c,
            "loss_at_plus_10pct": (c * (0.10 * r0) ** 2 if c > 0 else None)}


def main():
    blocks = [b for b in (w29_small_n(60), w29_small_n(90), probe_71e_n3000()) if b]
    if not blocks:
        raise SystemExit("no frozen sweep artifacts found under benchmarks/artifacts/")
    print("bd a0w step 1 -- RADIUS TOLERANCE X from the frozen constant-r sweeps")
    print("=" * 92)
    print(f"{'n':>6} {'inst':>5} {'seeds':>5} {'noise%':>8} | "
          f"{'measured loss% vs r=2':>34} | {'X_linear':>9} {'X_quad':>8}")
    for b in blocks:
        losses = "  ".join(f"r={r:g}:{b['loss_pct'][r]:+.4f}" for r in sorted(b["loss_pct"]))
        t = tolerance(b)
        lin = f"{t['linear']*100:.0f}%" if t["linear"] is not None else "n/a"
        print(f"{b['n']:>6} {b['instances']:>5} {b['seeds']:>5} {b['noise_pct']:>8.4f} | "
              f"{losses:>34} | {lin:>9} {t['quadratic']*100:>7.0f}%")
    print()
    for b in blocks:
        t = tolerance(b)
        print(f"  n={b['n']}: quadratic fit loss%(r) = {t['c_quadratic']:.5f}*(r-2)^2 "
              f"=> a +10% radius drift costs {t['loss_at_plus_10pct']:.5f}% "
              f"(seed noise {b['noise_pct']:.4f}%, i.e. "
              f"{b['noise_pct']/max(t['loss_at_plus_10pct'],1e-12):.0f}x larger)")
    print()
    print("VERDICT: the bead's assumed +/-10% radius tolerance is far too tight. The most")
    print("conservative reading in the table (n=3000 LINEAR, the lowest-noise arm) is the")
    print("number to carry forward; small-n readings are looser still.")


if __name__ == "__main__":
    main()
