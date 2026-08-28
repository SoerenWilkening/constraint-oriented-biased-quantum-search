#!/usr/bin/env python3
"""bd a0w (M5): ANGLE-PRECISION probe — how coarse can the QTG's R_y(theta_i) be?

On hardware the QTG's per-variable rotations are not exact: Ross-Selinger /
gridsynth synthesizes each to an absolute accuracy `eps` radians at a T-count of
~3*log2(1/eps). Coarser angles buy cheaper circuits. This probe measures the
MINIMAL precision that still yields the full objective, and how that scales in n.

Why the pessimistic union-bound error budget does NOT apply (see the writeup):
the Grover iterate is G = -A S0 A^dag O_f, so if A is synthesized ONCE and that
same circuit and its adjoint are used, A~ S0 A~^dag is the EXACT reflection about
|psi~> = A~|0>. The algorithm is then exactly Grover on a slightly perturbed
initial distribution: ZERO error accumulation in j. The precision requirement is
set only by how far the sampling distribution may shift before the objective
degrades — the quantity measured here.

METHOD — the w29 faithful probe protocol (benchmarks/run_w29_*.py):
  * FAITHFUL: oracle-budget termination (M = mult*T(n)), NO wall cap => fully
    reproducible, no wall-truncation noise. Affordable precisely because the
    budget is small (user directive: keep the Grover iteration count small).
  * WARM start (canonical since bd 8an.9): m.general_greedy() + warm_repair_history.
  * Everything else at the settled static configuration (bd kyg/w29): opt radius
    r=2, opt_sat radius 8, cand_16's early switch — so the ONLY difference
    between arms is the angle precision.
  * obj@common, BEST-OF-PORTFOLIO (NORTHSTAR §1.3, never the mean), median over
    seeds, Wilcoxon + Holm across the eps family (§13), per-seed sign counts.

ARMS: `exact` (lever OFF) + one arm per (eps, dither-mode) + `negctl` (eps=1e-12).

  NOTE on the negative control: `eps <= 0` is the only BIT-FOR-BIT control and it
  is the `exact` arm itself (the quantizer block is skipped entirely; pinned by
  tests/test_angle_precision.{c,py}). `negctl` at eps=1e-12 is a NEAR-exact
  control: the round trip 1 - sin^2(asin(sqrt(p))) is lossy at the 1e-13 level,
  and sampling compares `random_num > value`, so a perturbation that small can
  eventually flip a decision. The bead's own spec is therefore the right bar --
  "must reproduce the exact-angle arm to WITHIN SEED NOISE, ideally Delta = 0" --
  and that is what is checked; an exact 0 is reported when it happens but is not
  required.
  dither OFF (`_sys`) = COHERENT displacement (shared grid snap). For the shipped
    uniform-angle schedule (theta_i == 0, no branching_weights -- what this probe
    runs) all n angles are IDENTICAL, so ONE circuit is synthesized and reused and
    its single residual applies to every variable: the radius error adds
    coherently (~n*dtheta). This is the HEADLINE arm.
  dither ON  (`_dit`) = INCOHERENT residuals: an independent zero-mean offset per
    variable, so the FIRST-ORDER radius error averages (~sqrt(n)*dtheta). It is
    NOT free under uniform angles -- it needs n separately synthesized circuits
    for what is the same target angle -- and it assumes the gridsynth residual is
    zero-mean and ~uniform within eps. Read it as pricing an explicit engineering
    choice, not as the default.

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_a0w_precision_probe \
      [--n 90] [--budget-mult 1.0] [--indices 0..8] [--seeds ...] [--workers 4] \
      [--wall 900] [--report-only]
"""
import argparse, json, math, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.run_m4_n3000 import obj_at_budget, _holm, _boot_ci_median  # proven stats core (§2.7)
from cbqs.phase_params import angle_precision_bits, t_count_per_rotation

# --- the settled static configuration everything else sits at (bd kyg / w29) ---
R_OPT     = 2.0                          # the ceiling constant opt radius
R_OPT_SAT = 8.0
ALPHA     = 0.012044790907040026          # cand_16's early opt switch (fraction of T(n))

#: log grid of gridsynth accuracies (radians), roughly b_equiv = 1.65 .. 10.6.
EPS_GRID = (0.5, 0.25, 0.125, 0.0625, 0.03, 0.015, 0.008, 0.004, 0.002, 0.001)
#: the near-exact negative control (see the module docstring): fine enough that
#: the quantized angle agrees with the exact one to ~1e-13, NOT bit-for-bit.
EPS_NEGCTL = 1e-12

DEFAULT_INDICES = tuple(range(9))
DEFAULT_SEEDS = (20260828, 20260829, 20260830)
M_BIG = 100_000_000


def _eps_tag(eps):
    return f"{eps:g}".replace("-", "m")


def arm_name(eps, dither):
    return f"e{_eps_tag(eps)}_{'dit' if dither else 'sys'}"


def build_arms():
    arms = ["exact", "negctl"]
    for dither in (False, True):
        for eps in EPS_GRID:
            arms.append(arm_name(eps, dither))
    return arms


ARMS = build_arms()


def parse_arm(arm):
    """arm name -> (eps, dither) or None for the exact arm."""
    if arm == "exact":
        return None
    if arm == "negctl":
        return (EPS_NEGCTL, False)
    body, mode = arm[1:].rsplit("_", 1)
    return (float(body.replace("m", "-")), mode == "dit")


def _base(n):
    return {"opt_sat_branching_radius": R_OPT_SAT,
            "opt_branching_radius": R_OPT,
            "opt_switch_oracles": int(round(ALPHA * metric.oracle_budget(n)))}


def arm_params(arm, n):
    p = dict(_base(n))
    spec = parse_arm(arm)
    if spec is not None:
        eps, dither = spec
        # Unprefixed => ALL THREE phases. On hardware every state preparation
        # uses the same synthesized rotations; there is no phase at which the
        # circuit is magically exact.
        p["angle_precision_eps"] = float(eps)
        p["angle_precision_dither"] = bool(dither)
    return p


# --------------------------------------------------------------------------- #
# predicted radius under quantization (the mechanism, computed analytically)
# --------------------------------------------------------------------------- #

def _c_round(x):
    """C99 round(): half away from zero. Python's round() is BANKER'S rounding
    (round(0.5)==0, round(2.5)==2), which diverges from the C lever on exact
    ties -- and these helpers exist precisely to mirror the C behaviour."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def theta_exact(n, r=R_OPT):
    """The R_y angle the opt phase asks for: p_flip = r/n = sin^2(theta/2)."""
    return 2.0 * math.asin(math.sqrt(r / n))


def predicted_radius(n, eps, dither, r=R_OPT, samples=None):
    """Realized radius after quantization, r_q = sum_i n*sin^2(theta_q,i / 2)/n.

    Systematic: every variable shares one theta_q (coherent). Dithered: each
    variable gets its own offset, so this averages over the actual per-index
    offsets the C lever uses (reproduced here in Python)."""
    th = theta_exact(n, r)
    if eps is None or eps <= 0:
        return float(r)
    if not dither:
        thq = 2.0 * eps * _c_round(th / (2.0 * eps))
        return n * math.sin(thq / 2.0) ** 2
    k = samples or n
    tot = 0.0
    for i in range(k):
        tot += math.sin((th + eps * _dither_u(i)) / 2.0) ** 2
    return n * tot / k


def _dither_u(index):
    """Mirror of branch_dither_u (cbqs/src/Branching.h): splitmix64 on the index."""
    z = (index & 0xFFFFFFFF) + 0x9E3779B97F4A7C15
    z &= 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    z = z ^ (z >> 31)
    return (z >> 11) * (2.0 / 9007199254740992.0) - 1.0


# --------------------------------------------------------------------------- #
# solve
# --------------------------------------------------------------------------- #

def solve_arm(arm, n, idx, seed, budget_mult, workers, bench_root, wall=None):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = arm_params(arm, n)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    if wall and wall > 0:
        # WALL mode (n>=1000 RUN POLICY): M=T(n) so the switch keys correctly;
        # the wall cap is the early terminator for giant O(n*j^2) rounds.
        m.set_param("M", int(metric.oracle_budget(n)))
        m.set_param("stopping_time", float(wall))
    else:
        m.set_param("M", int(round(budget_mult * metric.oracle_budget(n))))
        m.set_param("stopping_time", -1.0)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    t0 = time.time()
    r = m.solve()
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o) in (r.history or [])]
    bd = r.branch_diagnostics or {}
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed),
            "params": {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                           else v) for k, v in resolved.items()},
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls),
            "wall_s": time.time() - t0,
            # the MECHANISM: the realized opt-phase Hamming radius under quantization
            "radius_mean": bd.get("radius_mean"), "free_fraction": bd.get("free_fraction"),
            "opt_candidates": bd.get("opt_candidates"),
            "history": hist}


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #

def _obj_common(recs, indices, seeds, arms, T):
    """obj@common: best-of-portfolio running max at the min oracle depth reached
    by ANY arm in the cell (cancels differing termination depths)."""
    obj_at, depth = {}, {}
    for idx in indices:
        for s in seeds:
            cell = {a: recs.get((idx, a, s)) for a in arms}
            if any(r is None for r in cell.values()):
                continue
            B = min(min(int(r["oracle_calls"]) for r in cell.values()), T)
            depth[(idx, s)] = B
            for a, r in cell.items():
                obj_at[(idx, s, a)] = obj_at_budget(r["history"], B)
    return obj_at, depth


def _cmp(obj_at, indices, seeds, arm, baseline):
    """Paired per-instance median-over-seeds delta vs `baseline`, two-sided.

    Two-sided because the question is "is this arm DISTINGUISHABLE from exact",
    not "is it better" — systematic rounding can inflate the radius as easily as
    collapse it, and either is a departure from the exact-angle schedule."""
    pairs, perseed = [], {}
    for idx in indices:
        ds = []
        for s in seeds:
            a, b = obj_at.get((idx, s, arm)), obj_at.get((idx, s, baseline))
            if a is None or b is None:
                ds = None; break
            ds.append(a - b)
        if ds is None:
            continue
        perseed[idx] = ds
        pairs.append((idx, float(np.median(ds))))
    med = [d for _i, d in pairs]
    p = 1.0
    if any(x != 0 for x in med):
        try:
            _W, p = ss.wilcoxon(med, alternative="two-sided", zero_method="wilcox")
            p = float(p)
        except ValueError:
            p = 1.0
    base_vals = [obj_at[(i, s, baseline)] for i in indices for s in seeds
                 if obj_at.get((i, s, baseline)) is not None]
    scale = float(np.median(base_vals)) if base_vals else None
    md = float(np.median(med)) if med else None
    return {"arm": arm, "baseline": baseline, "n_pairs": len(pairs),
            "n_pos": sum(1 for d in med if d > 0), "n_neg": sum(1 for d in med if d < 0),
            "n_zero": sum(1 for d in med if d == 0),
            "median_delta": md,
            "median_pct": (100.0 * md / scale) if (md is not None and scale) else None,
            "ci95": (_boot_ci_median(med) if len(med) >= 3 else None),
            "p_value": p,
            "all_seeds_neg": sum(1 for i in perseed if all(x < 0 for x in perseed[i])),
            "per_instance": [{"index": i, "median_delta": d, "per_seed": perseed[i]}
                             for i, d in pairs]}


def _seed_noise_pct(obj_at, indices, seeds, arm="exact"):
    """Detectability floor: within-(instance, arm) spread across seeds, in % of
    the objective, read on the SAME axis as the deltas (obj@common). A |median
    delta| under this floor is not a measurable degradation -- at small n it is
    dominated by the seed basin lottery (bd kyg), not by the lever."""
    out = []
    for idx in indices:
        v = [obj_at[(idx, s, arm)] for s in seeds if obj_at.get((idx, s, arm)) is not None]
        if len(v) == len(seeds) and np.mean(v) != 0:
            out.append(100.0 * (max(v) - min(v)) / abs(np.mean(v)))
    return float(np.median(out)) if out else None


def _oracles_to_match(recs, obj_at, indices, seeds, arm, baseline="exact"):
    """The SECOND cost axis: median oracles this arm needs to reach the
    baseline's obj@common. Precision does move the measured oracle count
    (coarser angles perturb the sampling distribution); that is reported here,
    ALONGSIDE the T-count-per-oracle axis and never folded into it
    (NORTHSTAR §1.1/§5). None when a majority of cells never get there."""
    vals, misses = [], 0
    for idx in indices:
        for s in seeds:
            rec, target = recs.get((idx, arm, s)), obj_at.get((idx, s, baseline))
            if rec is None or target is None:
                continue
            hit = next((o for (v, o) in rec["history"] if v >= target), None)
            if hit is None:
                misses += 1
            else:
                vals.append(int(hit))
    return {"median_oracles": (float(np.median(vals)) if vals else None),
            "reached": len(vals), "never_reached": misses}


def _median_radius(recs, indices, seeds, arm):
    """Median realized opt-phase Hamming radius for an arm, or None if no cell
    reported one. Uses `is not None` throughout: 0.0 is a REAL measurement (the
    angle rounded to zero -> forced greedy), not a missing value."""
    vals = [recs[(i, arm, s)]["radius_mean"] for i in indices for s in seeds
            if recs.get((i, arm, s)) is not None
            and recs[(i, arm, s)].get("radius_mean") is not None]
    return float(np.median(vals)) if vals else None


def _verdict(n, recs, indices, seeds, arms, T, wall=None):
    obj_at, depth = _obj_common(recs, indices, seeds, arms, T)
    feas = {a: sum(1 for i in indices for s in seeds
                   if obj_at.get((i, s, a)) is not None) for a in arms}
    noise = _seed_noise_pct(obj_at, indices, seeds)
    neg = _cmp(obj_at, indices, seeds, "negctl", "exact") if "negctl" in arms else None

    modes = {}
    for dither in (False, True):
        key = "dithered" if dither else "systematic"
        fam = [arm_name(e, dither) for e in EPS_GRID if arm_name(e, dither) in arms]
        cmps = {a: _cmp(obj_at, indices, seeds, a, "exact") for a in fam}
        holm = _holm({a: c["p_value"] for a, c in cmps.items()}, alpha=0.05)
        # eps*: the COARSEST eps that is statistically indistinguishable from
        # exact (Holm-adjusted, two-sided) AND whose median loss stays inside
        # the seed-noise floor. Walk the grid coarse -> fine and take the first
        # eps for which that holds at this eps and every finer one.
        ordered = sorted(EPS_GRID, reverse=True)
        ok = {}
        for e in ordered:
            a = arm_name(e, dither)
            if a not in cmps:
                ok[e] = None; continue
            c = cmps[a]
            # feasibility tier first (NORTHSTAR §6): an arm that never reaches a
            # feasible point is the worst possible outcome, never "indistinguishable".
            if feas.get(a, 0) == 0:
                ok[e] = False
                continue
            within_noise = (c["median_pct"] is not None and noise is not None
                            and c["median_pct"] >= -abs(noise))
            ok[e] = bool((not holm[a]["reject"]) and within_noise)
        eps_star = None
        for e in ordered:
            finer = [f for f in ordered if f <= e]
            if all(ok.get(f) for f in finer):
                eps_star = e
                break
        modes[key] = {
            "dither": dither, "family": fam,
            "cmp": cmps, "holm": holm, "indistinguishable": ok,
            "eps_star": eps_star,
            "b_star": (angle_precision_bits(eps_star) if eps_star else None),
            "t_per_rotation": (t_count_per_rotation(eps_star) if eps_star else None),
            "predicted_radius": {arm_name(e, dither): predicted_radius(n, e, dither)
                                 for e in EPS_GRID},
            # NB `is not None`, never truthiness: a realized radius of 0.0 is
            # the COLLAPSE signal (theta rounded to zero => forced greedy), the
            # single most important reading here.
            "realized_radius": {a: _median_radius(recs, indices, seeds, a) for a in fam},
            "oracles_to_exact": {a: _oracles_to_match(recs, obj_at, indices, seeds, a)
                                 for a in fam},
        }
    exact_radius = _median_radius(recs, indices, seeds, "exact")
    exact_oracles = _oracles_to_match(recs, obj_at, indices, seeds, "exact")
    return {"bead": "constraint-oriented-biased-quantum-search-a0w", "N": n, "T": T,
            # the run mode is part of the RESULT: a wall-capped spot-check and a
            # faithful oracle-budget sweep are not interchangeable reads, and a
            # downstream figure must be able to say which it is plotting.
            "wall_s": (float(wall) if wall else None),
            "mode": ("wall" if wall else "faithful"),
            "seeds": list(seeds), "indices": list(indices), "arms": list(arms),
            "eps_grid": list(EPS_GRID), "r_opt": R_OPT,
            "theta_exact": theta_exact(n), "feasible_cells": feas,
            "common_depth": {f"{i}_{s}": d for (i, s), d in depth.items()},
            "seed_noise_pct": noise, "negctl_vs_exact": neg,
            "exact_radius_mean": exact_radius,
            "exact_oracles_to_target": exact_oracles,
            "modes": modes}


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run(*, n, out_dir, seeds, budget_mult, workers, indices, bench_root, arms=None,
        wall=None, report_only=False, log=print):
    arms = list(arms or ARMS)
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    mode = "wall" if (wall and wall > 0) else "faithful"
    cfg = {"N": n, "seeds": list(seeds), "budget_mult": budget_mult, "workers": int(workers),
           "indices": list(indices), "arms": arms, "mode": mode,
           "wall_s": (float(wall) if wall else None), "r_opt": R_OPT,
           "r_opt_sat": R_OPT_SAT, "alpha_switch": ALPHA, "eps_grid": list(EPS_GRID)}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "workers", "mode", "r_opt", "r_opt_sat"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[a0w] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — fresh --out-dir.")
        if mode == "wall" and prev.get("wall_s") != cfg["wall_s"]:
            raise SystemExit("[a0w] CONFIG MISMATCH on wall_s — fresh --out-dir.")
        if mode == "faithful" and prev.get("budget_mult") != cfg["budget_mult"]:
            raise SystemExit("[a0w] CONFIG MISMATCH on budget_mult — fresh --out-dir.")
    else:
        json.dump(cfg, open(cfg_path, "w"), indent=2)

    if not report_only:
        total = len(indices) * len(arms) * len(seeds); done = 0
        for idx in indices:
            for s in seeds:
                for arm in arms:
                    done += 1
                    rp = os.path.join(out_dir, f"{n}_{idx}__{arm}__s{s}.json")
                    if os.path.exists(rp):
                        log(f"[a0w] ({done}/{total}) skip {n}_{idx} {arm} s={s}"); continue
                    rec = solve_arm(arm, n, idx, s, budget_mult, workers, bench_root, wall=wall)
                    json.dump(rec, open(rp, "w"))
                    log(f"[a0w] ({done}/{total}) {n}_{idx} {arm} s={s}: "
                        f"obj@T={obj_at_budget(rec['history'], T)} feas={rec['feasible']} "
                        f"oracles={rec['oracle_calls']} r_real={rec['radius_mean']} "
                        f"{rec['wall_s']:.1f}s")

    recs = {}
    for idx in indices:
        for s in seeds:
            for arm in arms:
                rp = os.path.join(out_dir, f"{n}_{idx}__{arm}__s{s}.json")
                if os.path.exists(rp):
                    recs[(idx, arm, s)] = json.load(open(rp))
    summary = _verdict(n, recs, indices, seeds, arms, T, wall=wall)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=2)
    _report(log, summary)
    check_harness_controls(summary)     # CLAUDE.md §2.1: crash, never warn
    return summary


class HarnessControlFailure(AssertionError):
    """A probe harness control did not hold — the sweep is not trustworthy."""


def check_harness_controls(summary):
    """Fail LOUD if a harness control is violated (CLAUDE.md §2.1).

    A control that only prints is the warning-instead-of-crash pattern §2.1
    forbids: the summary.json would still be written and read as a result.

    Controls:
      * `negctl` (eps=1e-12, near-exact) must reproduce `exact` to WITHIN THE
        SEED-NOISE FLOOR. It is deliberately NOT required to be exactly 0 --
        the round trip 1 - sin^2(asin(sqrt(p))) is lossy at ~1e-13 and sampling
        compares `random_num > value`, so a decision can flip. Exactly 0 is
        reported when it happens; outside the noise floor is a hard failure.
      * every scored arm must have produced at least one comparable cell -- an
        arm with no pairs would otherwise "pass by absence of data".
    """
    problems = []
    c = summary.get("negctl_vs_exact")
    noise = summary.get("seed_noise_pct")
    if c is not None and c["median_delta"] is not None:
        pct = c["median_pct"] or 0.0
        if noise is not None and abs(pct) > abs(noise):
            problems.append(
                f"negctl (eps={EPS_NEGCTL:g}) vs exact: median Δ={pct:+.4f}% is OUTSIDE the "
                f"seed-noise floor ±{noise:.4f}% — the near-exact control did not reproduce "
                f"the exact-angle arm, so the sweep's zero point is not trustworthy")
    feas = summary.get("feasible_cells", {})
    for key, m in summary.get("modes", {}).items():
        for arm, cmpres in m["cmp"].items():
            if cmpres["n_pairs"] > 0:
                continue
            if feas.get(arm, 0) == 0:
                # NOT a harness failure: an arm so coarse that it never reaches a
                # feasible point is the STRONGEST negative result there is (the §6
                # metric scores never-feasible as +inf). It is reported as a
                # FEASIBILITY LOSS by _report and can never be `indistinguishable`.
                continue
            problems.append(
                f"{key} arm {arm!r}: {feas.get(arm, 0)} feasible cells but 0 comparable "
                f"pairs — no data, not a pass")
    if problems:
        raise HarnessControlFailure(
            "bd a0w probe harness controls FAILED:\n  - " + "\n  - ".join(problems))


def _fmt_oracles(ot):
    if not ot or ot.get("median_oracles") is None:
        return "n/a"
    return f"{ot['median_oracles']:.0f}"


def _report(log, s):
    n = s["N"]
    log("\n" + "=" * 100)
    log(f"bd a0w ANGLE-PRECISION probe — n={n}: how coarse may R_y(theta_i) be before the objective moves?")
    log("=" * 100)
    log(f"N={n}  T(n)={s['T']}  instances={s['indices']}  seeds={s['seeds']}")
    log(f"exact opt angle theta = 2*asin(sqrt(r/n)) = {s['theta_exact']:.5f} rad at r={s['r_opt']}"
        f"   (realized radius {s['exact_radius_mean']:.4f})"
        if s["exact_radius_mean"] is not None else "")
    log(f"seed-noise floor (within-instance spread of `exact` over seeds): "
        f"{s['seed_noise_pct']:.4f}%" if s["seed_noise_pct"] is not None else "seed-noise floor: n/a")
    eo = s.get("exact_oracles_to_target")
    if eo:
        log(f"reference: the `exact` arm reaches its own obj@common at a median of "
            f"{_fmt_oracles(eo)} oracles ({eo['reached']} cells, {eo['never_reached']} misses)")
    if s["negctl_vs_exact"]:
        c = s["negctl_vs_exact"]
        noise = s.get("seed_noise_pct")
        pct = c["median_pct"] or 0.0
        exact_zero = (c["median_delta"] == 0 and c["n_pos"] == 0 and c["n_neg"] == 0)
        within = noise is None or abs(pct) <= abs(noise)
        tag = ("OK (exactly 0)" if exact_zero else
               "OK (within seed noise)" if within else "*** OUTSIDE SEED NOISE ***")
        log(f"HARNESS negctl (eps={EPS_NEGCTL:g}, near-exact) vs exact: "
            f"median Δ={c['median_delta']} ({pct:+.4f}%) "
            f"(+{c['n_pos']}/-{c['n_neg']}/={c['n_zero']})  {tag}")
        log("  (the BIT-FOR-BIT control is eps<=0, i.e. the `exact` arm itself: the "
            "quantizer is skipped entirely. 1-sin²(asin(√p)) is lossy at ~1e-13.)")
    for key in ("systematic", "dithered"):
        m = s["modes"][key]
        blurb = ("INCOHERENT: n separately synthesized circuits (assumes a zero-mean residual)"
                 if m["dither"] else
                 "COHERENT: one circuit synthesized once and reused -- the HEADLINE arm")
        log(f"\n--- {key.upper()} rounding ({blurb}) [obj@common, best-of-portfolio] ---")
        log(f"{'eps':>8} {'b_eq':>6} {'T/rot':>6} {'r_pred':>8} {'r_real':>8} "
            f"{'medianΔ':>14} {'Δ%':>9} {'+/-':>7} {'p':>9} {'orc→exact':>10} {'miss':>5}  {'indist?':>8}")
        for e in sorted(EPS_GRID, reverse=True):
            a = arm_name(e, m["dither"])
            c = m["cmp"].get(a)
            if c is None:
                continue
            rr = m["realized_radius"].get(a)
            ot = m.get("oracles_to_exact", {}).get(a)
            n_cells = len(s["indices"]) * len(s["seeds"])
            feas_a = s["feasible_cells"].get(a, 0)
            if c["median_delta"] is None:
                # no comparable pair: either a FEASIBILITY LOSS (the decisive
                # negative) or genuinely missing cells — say which.
                what = (f"FEASIBILITY LOSS ({feas_a}/{n_cells} cells feasible)"
                        if feas_a == 0 else f"no pairs ({feas_a}/{n_cells} feasible)")
                log(f"{e:>8g} {angle_precision_bits(e):>6.2f} {t_count_per_rotation(e):>6.1f} "
                    f"{m['predicted_radius'][a]:>8.3f} {(f'{rr:.3f}' if rr is not None else 'n/a'):>8} "
                    f"{what:>47}  {str(m['indistinguishable'].get(e)):>8}")
                continue
            log(f"{e:>8g} {angle_precision_bits(e):>6.2f} {t_count_per_rotation(e):>6.1f} "
                f"{m['predicted_radius'][a]:>8.3f} {(f'{rr:.3f}' if rr is not None else 'n/a'):>8} "
                f"{c['median_delta']:>+14,.0f} {(c['median_pct'] or 0):>+9.4f} "
                f"{c['n_pos']:>3}/{c['n_neg']:<3} {c['p_value']:>9.4g} "
                f"{_fmt_oracles(ot):>10} {(ot['never_reached'] if ot else '-'):>5}  "
                f"{str(m['indistinguishable'].get(e)):>8}")
        if m["eps_star"]:
            log(f"  => eps* = {m['eps_star']:g} rad  (b* = {m['b_star']:.2f} bits, "
                f"~{m['t_per_rotation']:.0f} T-gates/rotation, "
                f"~{m['t_per_rotation']*n:,.0f} T per QTG application at n={n})")
        else:
            log("  => eps*: NO grid point is indistinguishable from exact (cliff is coarser than the grid)")
    log("=" * 100)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd a0w angle-precision probe (Ross-Selinger / gridsynth).")
    p.add_argument("--n", type=int, default=90)
    p.add_argument("--budget-mult", type=float, default=1.0)
    p.add_argument("--wall", type=float, default=None,
                   help="WALL mode (n>=1000 RUN POLICY): M=T(n) + this wall cap (s). "
                        "Omit for FAITHFUL small-n mode (M=budget_mult*T(n), no wall).")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None)
    p.add_argument("--arms", default=None,
                   help="comma-separated subset of arms to SOLVE+score (default all).")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    arms = ARMS
    if args.arms:
        arms = [a.strip() for a in args.arms.split(",")]
        unknown = [a for a in arms if a not in ARMS]
        if unknown:
            raise SystemExit(f"unknown arm(s): {unknown}; known: {ARMS}")
    tag = (f"n{args.n}_wall{int(args.wall)}" if args.wall else f"n{args.n}_m{args.budget_mult}")
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "artifacts", "m5_a0w_precision", tag)
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    seeds = [int(x) for x in args.seeds.split(",")]
    run(n=args.n, out_dir=out_dir, seeds=seeds, budget_mult=args.budget_mult,
        workers=args.workers, indices=indices, bench_root=args.bench_root, arms=arms,
        wall=args.wall, report_only=args.report_only)


if __name__ == "__main__":
    main()
