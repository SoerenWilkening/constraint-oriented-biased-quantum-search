#!/usr/bin/env python3
"""bd kyg — optimize ON TOP of the r≈2 baseline (re-anchored search vs r=2, NOT the default).

Motivation (bd w29, W29_FINDINGS §7b): a PLAIN constant opt radius r≈2 (no θ, no switch tuning,
no schedule) BEATS the M4 "winner" cand_16 (r=4.41 + θ) at n=3000 — 8/9 instances. cand_16 only ever
beat the DEFAULT (bias=n/4); r≈2 beats cand_16. So r≈2 is the NEW best-known lever. Every prior M3
search (m3_proposer, bd 884) scored candidates vs the DEFAULT and anchored broad (r~4-8), so it found
improvements over the WEAK default, not over the current best.

This probe RE-ANCHORS at r=2 and scores EVERY arm vs the C_r2 BASELINE (constant opt r=2, opt_sat=8,
cand_16's early switch — the established ceiling), sweeping the levers cand_16 never tuned around 2:

  FINE RADIUS   near 2 (1.5 .. 3.0)                — is r=2 exactly optimal, or is 1.8 / 2.3 better?
  OPT_SAT r     {2,4,6} vs the fixed 8             — does the feasibility-push radius matter at r_opt=2?
  SWITCH α      {0, half, 2×, default 0.1}         — earlier/later exploit→explore switch at r=2?
  θ FEATURE     obj_rowsum_z / cons_rowsum_z /     — only pii_z was tried (NULL in w29); the OTHER
                degree_z  (allow-listed, §1.4)       allow-listed features are untried on top of r=2.
  ORDER         opt_variable_priorities asc/desc   — priced relabel (§1.1); 8an.8 cliff n≥70, verify=True.

FAITHFULNESS: no C changes. Every override is runtime data through set_param / genome_to_factory;
θ features are the CLOSED §1.4 allow-list (m3_proposer.FEATURES); radius is bias=n/r−2 (§1.5); the
n=3000 validation obeys the RUN POLICY wall cap. neg_r2_genome MUST tie C_r2 exactly (harness check).

Methodology mirrors run_w29_grow_probe (proven, reproducible):
  FAITHFUL small-n : M = budget_mult·T(n), NO wall  → zero wall-noise, neg==baseline exactly.
  WALL     n≥1000  : M = T(n) (NOT M_BIG — the schedule/keying fix a996fc0) + wall-clock cap; obj@common.
  obj@common best-of-portfolio, median-over-seeds Δ vs C_r2, Wilcoxon(greater)+Holm over the arm family,
  per-seed sign robustness.

CAVEAT (task kyg): small-n headroom is THIN (M2 θ null; 8an.10 0/41; w29 θ/decay/grow null small-n but
action at n=3000). A small-n NULL does NOT rule out an n=3000 win (headroom-gated). SCREEN small (prune
what clearly HURTS + worsens with headroom), DECIDE large (carry survivors + neutral-plausible to n=3000).

Usage:
  CBQS_BENCHMARKS_DIR=<clone> python -u -m benchmarks.run_kyg_probe \
      --n 90 [--budget-mult 1.0] [--indices 0..8] [--seeds ...] [--workers 4] [--arms sub,set] \
      [--wall 900]  [--report-only]
"""
import argparse, json, os, sys, time
import numpy as np
import scipy.stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import metric, baselines
from benchmarks.eq29_loader import load_eq29, build_model
from benchmarks.m3_proposer import genome_to_factory
from benchmarks.m2 import _pii as m2_pii
from benchmarks.run_m4_n3000 import obj_at_budget, _holm, _boot_ci_median  # proven stats core (§2.7)

# --- cand_16 (M4 winner) constants — the shared base every r=2 arm inherits (opt_sat + early switch) ---
R_OPT_SAT = 8.0
ALPHA = 0.012044790907040026     # cand_16 early switch fraction of T(n)
THETA_AMP = 0.28884412462871306  # cand_16 θ amplitude (the amp that "won" at n=3000, θ-coupled to r=4.41)
DEFAULT_INDICES = tuple(range(9))
DEFAULT_SEEDS = (20260630, 20260701, 20260702)

# θ-feature index in m3_proposer.FEATURES: 1=pii_z, 2=obj_rowsum_z, 3=cons_rowsum_z, 4=degree_z.
_FEAT = {"pii": 1, "obj": 2, "cons": 3, "deg": 4}

# All arms. C_r2 is the BASELINE (everything scores against it). Grouped by lever under test.
BASELINE = "C_r2"
ARMS = [
    "C_r2",                                   # BASELINE: const opt r=2, opt_sat=8, cand_16 early switch
    "neg_r2_genome",                          # HARNESS: r=2 emitted via genome path — MUST tie C_r2 (Δ=0)
    # fine radius near 2 (untried #1)
    "C_r1.5", "C_r1.75", "C_r2.25", "C_r2.5", "C_r3",
    # opt_sat radius (untried #2) — opt held at 2; finer sweep for the greedy-conditional analysis
    "optsat2", "optsat3", "optsat4", "optsat5", "optsat5.5", "optsat6", "optsat6.5", "optsat7",
    # switch α (untried #3) — opt held at 2
    "sw0", "sw_half", "sw_2x", "sw_default",
    # θ at r=2 with each allow-listed feature (untried #4; pii_z incl for direct w29 cross-check)
    "theta_pii", "theta_obj", "theta_cons", "theta_deg",
    # variable_order (untried #5; 8an.8 cliff, verify=True catches infeasibility)
    "order_asc", "order_desc",
    # CBQS default (bias=n/4) — reference only (NOT in the family; context/figure)
    "default",
]
# arms excluded from the Holm family (baseline, harness, reference)
_NON_FAMILY = {"C_r2", "neg_r2_genome", "default"}


def _base(n):
    """Shared base for every r=2 arm: cand_16's opt_sat radius + early switch (matches w29 _base)."""
    return {"opt_sat_branching_radius": R_OPT_SAT,
            "opt_switch_oracles": int(round(ALPHA * metric.oracle_budget(n)))}


def _theta_arm(n, c1, c2, c3, feat_key, amp=THETA_AMP):
    """r=2 + θ (amp·feature) via the genome path (allow-listed FEATURES only, §1.4)."""
    feat_idx = _FEAT[feat_key] + 0.5           # +0.5 so floor() lands on the intended feature index
    return dict(genome_to_factory((R_OPT_SAT, 2.0, ALPHA, amp, feat_idx))(n, c1, c2, c3))


def arm_params(arm, n, c1, c2, c3):
    if arm == "default":          return {}    # CBQS default: close() auto-sets bias=n/4, switch=0.1·M
    if arm == "C_r2":             return {**_base(n), "opt_branching_radius": 2.0}
    if arm == "neg_r2_genome":    return dict(genome_to_factory((R_OPT_SAT, 2.0, ALPHA, 0.0, 0.0))(n, c1, c2, c3))
    # fine radius
    if arm == "C_r1.5":           return {**_base(n), "opt_branching_radius": 1.5}
    if arm == "C_r1.75":          return {**_base(n), "opt_branching_radius": 1.75}
    if arm == "C_r2.25":          return {**_base(n), "opt_branching_radius": 2.25}
    if arm == "C_r2.5":           return {**_base(n), "opt_branching_radius": 2.5}
    if arm == "C_r3":             return {**_base(n), "opt_branching_radius": 3.0}
    # opt_sat radius (opt fixed at 2). optsatN sets opt_sat radius = N; baseline C_r2 uses 8.
    if arm.startswith("optsat"):
        rs = float(arm[len("optsat"):])
        return {**_base(n), "opt_branching_radius": 2.0, "opt_sat_branching_radius": rs}
    # switch α (opt fixed at 2)
    if arm == "sw0":
        return {**_base(n), "opt_branching_radius": 2.0, "opt_switch_oracles": 0}
    if arm == "sw_half":
        return {**_base(n), "opt_branching_radius": 2.0,
                "opt_switch_oracles": int(round(0.5 * ALPHA * metric.oracle_budget(n)))}
    if arm == "sw_2x":
        return {**_base(n), "opt_branching_radius": 2.0,
                "opt_switch_oracles": int(round(2.0 * ALPHA * metric.oracle_budget(n)))}
    if arm == "sw_default":
        return {**_base(n), "opt_branching_radius": 2.0,
                "opt_switch_oracles": int(round(0.1 * metric.oracle_budget(n)))}  # the C default 0.1·M
    # θ features at r=2
    if arm == "theta_pii":        return _theta_arm(n, c1, c2, c3, "pii")
    if arm == "theta_obj":        return _theta_arm(n, c1, c2, c3, "obj")
    if arm == "theta_cons":       return _theta_arm(n, c1, c2, c3, "cons")
    if arm == "theta_deg":        return _theta_arm(n, c1, c2, c3, "deg")
    # variable_order (priced relabel §1.1; asc = -p_ii won n=10-60 in 8an.8; desc = +p_ii)
    if arm == "order_asc":
        return {**_base(n), "opt_branching_radius": 2.0, "opt_variable_priorities": -m2_pii(c1)}
    if arm == "order_desc":
        return {**_base(n), "opt_branching_radius": 2.0, "opt_variable_priorities": m2_pii(c1)}
    raise ValueError(arm)


def solve_arm(arm, n, idx, seed, budget_mult, workers, bench_root, wall=None):
    c1, c2, c3 = load_eq29(n, idx, bench_root)
    resolved = arm_params(arm, n, c1, c2, c3)
    m = build_model(c1, c2, c3, vectorized=True)
    greedy_value, greedy_feasible = m.general_greedy()
    m.seed = int(seed)
    if wall and wall > 0:
        # WALL mode (n>=1000 RUN POLICY): M=T(n) (NOT M_BIG) so any schedule keys correctly on
        # total_oracles/mod->M; the wall cap interrupts giant O(n*j^2) rounds; obj@common is the read.
        m.set_param("M", int(metric.oracle_budget(n)))
        m.set_param("stopping_time", float(wall))
    else:
        # FAITHFUL mode (small-n): oracle-budget termination, reproducible (no wall noise).
        m.set_param("M", int(round(budget_mult * metric.oracle_budget(n))))
        m.set_param("stopping_time", -1.0)
    m.set_param("num_workers", workers)
    m.set_param("verify", True)
    m.set_param("opt_sample_cap", 0)
    m.set_param("track_history", True)
    for k, v in resolved.items():
        m.set_param(k, v)
    r = m.solve()
    baselines.warm_repair_history(r, greedy_value=greedy_value, greedy_feasible=greedy_feasible)
    hist = [[float(v), int(o)] for (v, o) in (r.history or [])]
    rps = {k: (float(v) if np.isscalar(v) else f"<vec[{len(v)}]>") for k, v in resolved.items()}
    return {"arm": arm, "n": n, "index": idx, "seed": int(seed), "params": rps,
            "objective": int(r.objective) if r.objective is not None else None,
            "feasible": bool(r.feasible), "oracle_calls": int(r.oracle_calls), "history": hist}


# --------------------------- analysis (generic over ARMS) --------------------------- #
#
# Two review-hardened choices vs the run_m4_n3000 template (bd kyg review, wf_51d87237):
#  (1) PER-PAIR common budget. B is min(oracle_calls[arm], oracle_calls[baseline], read_budget) —
#      NOT a global min over every arm. A global min lets a stall-prone arm (the bias=n/4 `default`
#      or an order arm past the 8an.8 cliff) that halts at ~200 oracles in WALL mode collapse B for
#      EVERY comparison, truncating each pair to the pre-divergence region → a spurious NULL ("r=2 is
#      the ceiling"). Per-pair B also makes each Δ independent of which other arms are in --arms.
#  (2) read_budget = the ACTUAL run budget, not T. Every kyg arm is a CONSTANT lever, so its history
#      up to T=oracle_budget(n) is M-independent (M only sets where the solve stops). Reading at T
#      therefore gives byte-identical deltas at budget_mult 1 and 4 — the headroom probe would be
#      INERT. Headroom for a constant lever = reading at a DEEPER oracle depth, so faithful mode reads
#      at min(mult·T, oracle_calls); wall mode reads at T (the faithful cost axis — history past T is
#      the sim-truncated over-budget artifact, per the m4/w29 lesson).


def _read_budget(T, budget_mult, wall):
    """Deepest oracle depth at which to read obj@common (see note (2) above)."""
    if wall and wall > 0:
        return int(T)                        # wall (n>=1000): the faithful cost axis
    return int(round(budget_mult * T))       # faithful: the actual budget (enters the headroom region)


def _cmp(recs, indices, seeds, arm, baseline, read_budget):
    """median-over-seeds Δ(arm−baseline) per instance at the PER-PAIR common budget; Wilcoxon(greater)
    over instance medians; per-seed sign; per-cell exact-zero tracking; feasibility-loss accounting."""
    perseed, pairs = {}, []
    max_abs = 0; nonzero_cells = 0
    arm_feas_loss = base_feas_loss = 0        # cells where one side is feasible-at-B and the other is not
    for idx in indices:
        ds = []
        for s in seeds:
            ra, rb = recs.get((idx, arm, s)), recs.get((idx, baseline, s))
            if ra is None or rb is None:
                ds = None; break
            B = min(int(ra["oracle_calls"]), int(rb["oracle_calls"]), read_budget)  # PER-PAIR budget
            a = obj_at_budget(ra["history"], B); b = obj_at_budget(rb["history"], B)
            if a is None and b is None:
                ds = None; break              # neither feasible by B — nothing to compare
            if a is None:                     # arm lost feasibility where baseline held it
                arm_feas_loss += 1; ds = None; break
            if b is None:                     # baseline lost feasibility where arm held it
                base_feas_loss += 1; ds = None; break
            d = a - b
            ds.append(d)
            max_abs = max(max_abs, abs(d)); nonzero_cells += (1 if d != 0 else 0)
        if ds is None:
            continue
        perseed[idx] = ds
        pairs.append((idx, float(np.median(ds))))
    med = [d for _i, d in pairs]
    p = 1.0; W = None
    if any(x != 0 for x in med):
        try:
            W, p = ss.wilcoxon(med, alternative="greater", zero_method="wilcox"); W, p = float(W), float(p)
        except ValueError:
            p = 1.0
    allpos = sum(1 for i in perseed if all(x > 0 for x in perseed[i]))
    allneg = sum(1 for i in perseed if all(x < 0 for x in perseed[i]))
    return {"arm": arm, "baseline": baseline, "n_pairs": len(pairs),
            "n_pos": sum(1 for d in med if d > 0), "n_neg": sum(1 for d in med if d < 0),
            "median_delta": (float(np.median(med)) if med else None),
            "ci95": (_boot_ci_median(med) if len(med) >= 3 else None),
            "wilcoxon_W": W, "p_value": p, "all_seeds_pos": allpos, "all_seeds_neg": allneg,
            "max_abs_cell_delta": int(max_abs), "nonzero_cells": nonzero_cells,
            "arm_feas_loss": arm_feas_loss, "base_feas_loss": base_feas_loss,
            "per_instance": [{"index": i, "median_delta": d, "per_seed": perseed[i]} for i, d in pairs]}


def _classify(cmp_):
    """SCREEN verdict for one arm vs C_r2. HELPS/HURTS/NEUTRAL (pre-Holm; Holm applied at family level).
    Both sides require the SAME evidence bar (seed-robust sign + p<=0.05) so HURTS cannot fire more
    readily than HELPS under noise (a HURTS must never prematurely prune a headroom-gated arm — task
    caveat). An arm that SHEDS feasibility vs the baseline can never be HELPS (it is not a free win)."""
    md = cmp_["median_delta"]
    if md is None:
        return "NO_DATA"
    n = cmp_["n_pairs"]
    bar = max(2, n // 2)
    if cmp_["arm_feas_loss"] > 0:              # lost feasibility somewhere the baseline held it
        return "HURTS" if md < 0 else "NEUTRAL"
    if md > 0 and cmp_["all_seeds_pos"] >= bar and cmp_["p_value"] <= 0.05:
        return "HELPS"
    # HURTS mirrors HELPS: seed-robust negative sign AND a one-sided (arm<baseline) Wilcoxon p<=0.05.
    if md < 0 and cmp_["all_seeds_neg"] >= bar and _neg_pvalue(cmp_) <= 0.05:
        return "HURTS"
    return "NEUTRAL"


def _neg_pvalue(cmp_):
    """One-sided Wilcoxon p for arm<baseline (mirror of the greater test on the flipped medians)."""
    med = [pi["median_delta"] for pi in cmp_["per_instance"]]
    if not any(x != 0 for x in med):
        return 1.0
    try:
        _W, p = ss.wilcoxon(med, alternative="less", zero_method="wilcox")
        return float(p)
    except ValueError:
        return 1.0


def _verdict(n, recs, indices, seeds, read_budget, arms, T):
    feas = {arm: sum(1 for idx in indices for s in seeds
                     if (recs.get((idx, arm, s)) is not None
                         and obj_at_budget(recs[(idx, arm, s)]["history"], read_budget) is not None))
            for arm in arms}
    cmps = {arm: _cmp(recs, indices, seeds, arm, BASELINE, read_budget)
            for arm in arms if arm != BASELINE}
    fam = {a: cmps[a]["p_value"] for a in cmps if a not in _NON_FAMILY}
    holm = _holm(fam, alpha=0.05) if fam else {}
    classes = {a: _classify(cmps[a]) for a in cmps}
    # a screen "winner" = HELPS AND Holm-reject AND no feasibility shed vs baseline (multiplicity-safe)
    winners = [a for a in fam if holm.get(a, {}).get("reject")
               and classes.get(a) == "HELPS" and cmps[a]["arm_feas_loss"] == 0]
    neg = cmps.get("neg_r2_genome")
    # harness: neg_r2_genome must tie C_r2 in EVERY cell (per-cell exact zero, m4-style — not just median)
    neg_clean = bool(neg and neg["max_abs_cell_delta"] == 0 and neg["nonzero_cells"] == 0
                     and neg["n_pairs"] == len(indices))
    return {"bead": "constraint-oriented-biased-quantum-search-kyg", "N": n, "T": T,
            "read_budget": int(read_budget), "seeds": list(seeds), "indices": list(indices),
            "arms": list(arms), "feasible_cells": feas, "cmp_vs_C_r2": cmps, "holm": holm,
            "classes": classes, "winners": winners, "neg_harness_clean": neg_clean}


def run(*, n, out_dir, seeds, budget_mult, workers, indices, bench_root, wall=None,
        report_only=False, arms=None, log=print):
    arms = list(arms) if arms else list(ARMS)
    os.makedirs(out_dir, exist_ok=True)
    T = metric.oracle_budget(n)
    mode = "wall" if (wall and wall > 0) else "faithful"
    cfg = {"N": n, "seeds": list(seeds), "budget_mult": budget_mult, "workers": int(workers),
           "indices": list(indices), "arms": arms, "mode": mode,
           "wall_s": (float(wall) if wall else None)}
    cfg_path = os.path.join(out_dir, "run_config.json")
    if os.path.exists(cfg_path):
        prev = json.load(open(cfg_path))
        for k in ("N", "workers", "mode"):
            if prev.get(k) != cfg[k]:
                raise SystemExit(f"[kyg] CONFIG MISMATCH on {k}: {prev.get(k)} != {cfg[k]} — fresh --out-dir.")
        if mode == "wall" and prev.get("wall_s") != cfg["wall_s"]:
            raise SystemExit("[kyg] CONFIG MISMATCH on wall_s — fresh --out-dir.")
        if mode == "faithful" and prev.get("budget_mult") != cfg["budget_mult"]:
            raise SystemExit("[kyg] CONFIG MISMATCH on budget_mult — fresh --out-dir.")
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
                        log(f"[kyg] ({done}/{total}) skip {n}_{idx} {arm} s={s}"); continue
                    t0 = time.time()
                    rec = solve_arm(arm, n, idx, s, budget_mult, workers, bench_root, wall=wall)
                    json.dump(rec, open(rp, "w"))
                    log(f"[kyg] ({done}/{total}) {n}_{idx} {arm} s={s}: "
                        f"obj@T={obj_at_budget(rec['history'], T)} feas={rec['feasible']} "
                        f"oracles={rec['oracle_calls']} {time.time()-t0:.1f}s")

    recs = {}
    for idx in indices:
        for s in seeds:
            for arm in arms:
                rp = os.path.join(out_dir, f"{n}_{idx}__{arm}__s{s}.json")
                if os.path.exists(rp):
                    recs[(idx, arm, s)] = json.load(open(rp))
    read_budget = _read_budget(T, budget_mult, wall)
    summary = _verdict(n, recs, indices, seeds, read_budget, arms, T)
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=2)
    _report(log, summary)
    return summary


def _report(log, s):
    log("\n" + "=" * 88)
    log(f"bd kyg — n={s['N']}: does ANY lever, re-anchored at r=2, beat the constant r=2 BASELINE?")
    log("=" * 88)
    log(f"N={s['N']} T(n)={s['T']} read_budget={s.get('read_budget')} "
        f"instances={s['indices']} seeds={s['seeds']}")
    cells = len(s['indices']) * len(s['seeds'])
    log(f"feasible cells per arm @read_budget (of {cells}): {s['feasible_cells']}")
    neg = s["cmp_vs_C_r2"].get("neg_r2_genome")
    log(f"\nHARNESS neg_r2_genome vs C_r2: clean={s['neg_harness_clean']} "
        f"(max|cellΔ|={neg['max_abs_cell_delta'] if neg else 'NA'}, must be 0 in every cell)")
    order = ["C_r1.5", "C_r1.75", "C_r2.25", "C_r2.5", "C_r3",
             "optsat2", "optsat3", "optsat4", "optsat5", "optsat6", "optsat7",
             "sw0", "sw_half", "sw_2x", "sw_default",
             "theta_pii", "theta_obj", "theta_cons", "theta_deg", "order_asc", "order_desc", "default"]
    log(f"\n--- Δ vs C_r2 [obj@common per-pair @read_budget, median-over-seeds] "
        f"(positive = beats the r=2 ceiling) ---")
    for a in order:
        c = s["cmp_vs_C_r2"].get(a)
        if not c or c["median_delta"] is None:
            continue
        h = s["holm"].get(a, {})
        rej = "  <==HOLM-REJECT" if h.get("reject") else ""
        cls = s["classes"].get(a, "")
        floss = (f" feas_loss={c['arm_feas_loss']}" if c.get("arm_feas_loss") else "")
        log(f"  {a:>14}: Δ={c['median_delta']:+,.0f} (+{c['n_pos']}/-{c['n_neg']} of {c['n_pairs']}) "
            f"allseed +{c['all_seeds_pos']}/-{c['all_seeds_neg']}  p={c['p_value']:.3g}  [{cls}]{rej}{floss}")
    log("")
    if s["winners"]:
        log(f"kyg SCREEN VERDICT (n={s['N']}): SIGNAL — {s['winners']} beat r=2 (HELPS + Holm-reject). "
            f"Carry to n=3000 wall validation.")
    else:
        helps = [a for a, c in s["classes"].items() if c == "HELPS"]
        neutral = [a for a, c in s["classes"].items() if c == "NEUTRAL"]
        log(f"kyg SCREEN VERDICT (n={s['N']}): NO Holm-surviving winner. "
            f"HELPS(pre-Holm)={helps or 'none'}; NEUTRAL={len(neutral)} arms (carry neutral-plausible "
            f"to n=3000 — headroom-gated per task caveat); the rest HURT/prune.")
    log("=" * 88)


def main(argv=None):
    p = argparse.ArgumentParser(description="bd kyg re-anchored (vs r=2) lever probe.")
    p.add_argument("--n", type=int, default=90)
    p.add_argument("--budget-mult", type=float, default=1.0)
    p.add_argument("--wall", type=float, default=None,
                   help="WALL mode (n>=1000): M=T(n) + this wall-clock cap (s); obj@common read. "
                        "Omit for FAITHFUL small-n mode (M=budget_mult*T(n), no wall).")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--bench-root", default=os.environ.get("CBQS_BENCHMARKS_DIR"))
    p.add_argument("--seeds", default=",".join(str(x) for x in DEFAULT_SEEDS))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--indices", default=None)
    p.add_argument("--arms", default=None,
                   help="comma-separated subset of arms to SOLVE+score (default all). Baseline C_r2 is "
                        "force-included (scoring needs it).")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    if not args.bench_root:
        raise SystemExit("CBQS_BENCHMARKS_DIR (or --bench-root) is required.")
    arms = None
    if args.arms:
        sub = [a.strip() for a in args.arms.split(",")]
        unknown = [a for a in sub if a not in ARMS]
        if unknown:
            raise SystemExit(f"unknown arm(s): {unknown}; known: {ARMS}")
        if BASELINE not in sub:
            sub = [BASELINE] + sub                      # scoring needs the baseline
        arms = sub
    tag = (f"n{args.n}_wall{int(args.wall)}" if args.wall else f"n{args.n}_m{args.budget_mult}")
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "artifacts", "m5_kyg", tag)
    indices = ([int(x) for x in args.indices.split(",")] if args.indices else list(DEFAULT_INDICES))
    seeds = [int(x) for x in args.seeds.split(",")]
    run(n=args.n, out_dir=out_dir, seeds=seeds, budget_mult=args.budget_mult, workers=args.workers,
        indices=indices, bench_root=args.bench_root, wall=args.wall, report_only=args.report_only,
        arms=arms)


if __name__ == "__main__":
    main()
