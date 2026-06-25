# NORTHSTAR Capstone — Mission delivered (M0 → M4)

**Status: the committed NORTHSTAR mission arc (M0–M4) is COMPLETE. The n=3000 generalization is
CONFIRMED.** Closed 2026-06-25 (bd `8an.5` / `8an.11`). M5 (Phase 2) is the deferred next frontier (§7).

This document is the single-page wrap-up of the program defined in `NORTHSTAR.md`. It is a *synthesis*,
not a new source of truth: every number here traces to a frozen artifact, a `bd` close reason, or a
findings doc, cited inline. Where this doc and `NORTHSTAR.md` disagree on the spec, NORTHSTAR wins; where
either disagrees with a file:line fact, the source wins.

---

## 1. Headline result

**An autonomous agent, searching only on small training strata (n ≤ 90), discovered a size-aware static
bias schedule that beats the production CBQS default at the n=3000 target scale — under a full
multiplicity-controlled statistical protocol with a clean negative control.**

Scored **once** on the 9 untouched n=3000 instances (`3000_0..8`), fresh seed `20260624` (disjoint from
all selection banks), exact sampler, `M=M_BIG` + 900 s wall cap, 4 workers. Two agent-discovered
schedules — **cand_16** (the M3 winner) and **cand_23** (a parsimonious variant) — vs. the **warm
default**, plus a baseline-equivalent **negative control**, at two budgets:

| arm | **PRIMARY** — obj @ designed `T(n)=9989` | **CORROBORATION** — obj @ equal-oracle budget |
|---|---|---|
| **cand_16** | **9/9 win**, median Δ **+19.60 M (+0.0864 %)**, Wilcoxon p=0.00195, **Holm-reject** (thr 0.025), CI95 [+14.32 M, +31.32 M] | 8/9 win, +10.00 M (+0.0441 %), p=0.0195, **Holm-reject**, CI95 [+7.93 M, +18.04 M] |
| **cand_23** | **9/9 win**, median Δ **+19.32 M (+0.0851 %)**, p=0.00195, **Holm-reject** (thr 0.05), CI95 [+14.64 M, +32.64 M] | 8/9 win, +11.71 M (+0.0516 %), p=0.0059, **Holm-reject**, CI95 [+10.13 M, +20.61 M] |
| negative control | **9/9 Δ ≡ 0** (clean) | — |

All four arms are feasible-at-`T` on all 9 instances. Both candidates Holm-reject at FWER ≤ 0.05 at the
**designed** budget *and* hold a positive Holm-significant median at the **assumption-free equal-oracle**
budget — so the win is not a wall-time or oracle-count artifact. Bootstrap CI95 of the median Δ excludes 0
on both budgets for both candidates. (Source: `benchmarks/artifacts/m4_n3000/summary.json`,
`benchmarks/M3_WARM_FINDINGS.md §11`.)

**Mechanism.** The warm default **stalls at its first-feasible incumbent** (the warm `general_greedy`
start already sits on the classical frontier; e.g. on `3000_0` its history is a single entry at oracle 55,
`oracle_calls=995`, and it never improves). The discovered schedules **start ~6 M below** that incumbent
but **cross it by oracle ~176–214 and pull away** (cand_16 on `3000_0`: 128 history steps climbing
22.6835 e9 @ oracle 98 → 22.7086 e9 @ oracle 2096). The edge is **headroom-gated** — null where the warm
start is already near-optimal (small n), real where the default stalls and leaves headroom (n=90 targeted,
n=3000).

**Companion finding (independently audited, bd `8an.11` §10).** Warm CBQS beats the best *classical*
solver (`B_I` = gurobi/hexaly/simanneal) on **11/12 n≥1000 instances** (n=1000 8/9, +4.2..6.1 M; n=3000
3/3, +28.8 M / +55.9 M / +59.2 M = +0.13..0.26 %), **every** solution feasibility-audited from the raw
`c1/c2/c3` (not the solver's own `verify` flag), 12/12 audit == solver. This is *why* the gap-to-`B_I`
metric is degenerate at scale (§3, M4) — CBQS warm lives above the classical frontier.

---

## 2. The mission and the faithfulness contract

CBQS is a **faithful classical stand-in** for a biased quantum search solver: **its oracle count *is* the
quantum cost, and the oracle count is the product.** The advantage claim is therefore always an
**equal-oracle-budget A/B test** (baseline schedule vs. discovered schedule at the same `T(n)`), never
"free ⇒ advantage": biasing the QTG angles *redistributes* where the amplitude-amplification budget lands,
and the A/B at fixed `T(n)` prices that redistribution. (`NORTHSTAR.md §1`, §5.)

The target class is the quadratically-constrained (Eq.29) family of arXiv:2512.08384. `T(n) = (n/32)² + 1200`
oracles (lowered from the original `(n/4)²` in M3, bd `8an.4.9`); `T(3000) = 9989`.

---

## 3. The milestone arc

| M | bd | Exit criterion (NORTHSTAR §12) | Delivered |
|---|---|---|---|
| **M0** | `8an.1` ✓ | Baseline scored reproducibly under §6; all tests green; the §11 infra deliverables. | Oracle accounting made **sacred**: retired the racy unlocked shared `mod->qtg_applications`, added a per-worker `ctx->oracle_count` and a **never-reset** total-oracle accumulator gating termination at `T(n)`; fixed the budget-overshoot/​int-overflow bug (`8an.1.17`, per-round `2j+1` grew ~1.2^rounds, overshot up to 26000×); migrated history to **oracle-indexed** `(value, oracle:int)` with per-worker incumbents + best-of-portfolio merge; fixed **portfolio collapse** (per-worker seed decorrelation, was hardcoded thread 0); landed the one-time `BranchingFunction` **sigmoid+clamp** reparam + `branching_radius` lever (`bias = n/r − 2`) + the `opt_switch_oracles` hook. Adversarially verified **0/8 refuted**; full gate green incl. ASan+TSan. |
| **M1** | `8an.2` ✓ | §6 metric (bounded anchored primal-gap integral, feasibility composition, rank-sum + largest-n gate) + §8.3 floor; default PI, noise margin, floor calibrated. | §6 implemented and verified on **real Eq.29 data**. The **default-vs-default strict-xcheck capstone** caught two P1 reproducibility bugs the green suite missed (`4uf` callback gating, `cjz` entropy seed), then passed with **0 failures + exact replay** after re-freeze (commit `3c6ba1c`). Per-size noise margins positive on all 10 strata; floor calibrated (`EXPLORE_FLOOR_FRACTION=0.25`, evaluability-by-reference). |
| **M2** | `8an.3` ✓ | A hand-designed schedule moves the metric; each lever's leverage is known. | Hand schedules swing the metric the full range (**Wilcoxon W +55 ↔ −55** per stratum). Leverage frozen: **`opt_switch_oracles` is dominant** (earlier explore better everywhere; default 0.1·M is left of optimal); scalar radius `r` material but size-dependent; `variable_order` material at small/mid-n but a **catastrophic large-n feasibility cliff** (n=100 collapse) — and a P1 bug (`h8d`) that accepted infeasible solutions had to be fixed first; per-variable θ near-null. The uniform-greedy negative control loses on PI **and** fails the §8.3 tail floor. |
| **M3** | `8an.4` ✓* | Validated improvement on near-target sizes within all gates (population search; CV + multiplicity control). | FunSearch/AlphaEvolve-style population search with a **§1.4 allow-list-by-construction firewall** (AST/provenance check on generated code) and §13 CV+Holm selection. **Cold** run (bd `884`): 12/30 candidates cleared both CV folds + Holm FWER ≤ 0.05; winner **cand_16** Holm `p_adj=1.5e-12`; holdout favors the winner 4/4. **Warm** rescope (bd `8an.10`, after warm became canonical in `8an.9`): the warm default is unbeaten cross-stratum on n ≤ 90 (the warm start captures small-n headroom) — but the **n=90 win is real and targeted** (W +9), setting up M4. Lowered `T(n)` to `(n/32)²+1200` (`8an.4.9`). |
| **M4** | `8an.5` ✓ | Score the discovered schedule **once** on untouched n=3000 with fresh seeds (paired Wilcoxon, effect size + CI); negative control. | The B_I-PI metric is **degenerate at n ≥ 1000** (`8an.11`): warm CBQS reaches feasibility **at/above** `B_I`, so `(B_I − L_I) ≤ 0` (onset at n=500). M4 was reframed to a **direct objective A/B** — see §1. **Generalization CONFIRMED.** |

\* **M3 node bookkeeping:** `8an.4` showed `in_progress` at close time, but all its children (`884`,
`8an.4.1`–`8an.4.10`), the warm rescope `8an.10`, and the large-n freeze `8an.4.8` are closed, and M4
(which depends on it) is delivered. It is closed as part of this consolidation — open node, not missing
work.

---

## 4. Faithfulness invariants the n=3000 claim rests on

The headline survives because the load-bearing `NORTHSTAR §1` gates hold (verified across M0–M4):

- **§1.2 Oracle accounting is sacred.** The per-worker never-reset accumulator is the denominator of the
  whole claim; the equal-oracle **corroboration** budget (`obj @ per-instance min(oracle_calls)`) is only
  meaningful because that count is correct.
- **§1.1 Equal-`T(n)` A/B pricing.** The advantage is an equal-budget A/B (cand vs. warm default at the
  same `T(n)=9989`) plus the assumption-free equal-oracle-cost corroboration; both arms share the budget
  and the 900 s wall cap. (Per the RUN POLICY the wall cap waives oracle-indexed primal-integral
  faithfulness *for the run*; the equal-oracle corroboration restores an equal-cost comparison and the
  oracle counter stays correct.)
- **§1.3 No uniform-greedy collapse / best-of-portfolio.** The schedule wins by climbing **past** the
  default's stalled first-feasible incumbent on the best-of-portfolio trajectory — never scored on the
  mean.
- **§1.4 Phase-1 feature allow-list.** The discovered θ channel (`pii_z`) and all features come only from
  `{p_ii, obj & constraint row-sums, raw degree, nnz}`, enforced by construction — no LP/SDP or spectral
  statistics smuggle uncharged classical optimization into the comparison.
- **§1.5 Scale-invariance.** Levers are parameterized by target radius `r` (`bias = n/r − 2`), so the
  cand_16/cand_23 radii transfer from the n ≤ 90 selection strata to n=3000; the final warm run gated out
  1/41 candidates on the radius-fidelity check (the gate working).
- **§1.7 Bounded decisions.** The sigmoid+clamp reparam keeps the per-variable value in `(0,1)` by
  construction, so the θ schedule cannot silently force an assignment or inflate the radius.

---

## 5. Reproduce

**Verify the verdict from saved artifacts (no clone, no solve — seconds):**

```bash
python -u -m benchmarks.run_m4_n3000 --report-only
# regenerates benchmarks/artifacts/m4_n3000/summary.json byte-for-byte
# (md5 93af457a6cc7e3151fa3055dd11035c3); the --report-only path loads only the
# 36 saved per-arm JSONs and re-runs the sign test / Wilcoxon / Holm / medians.
```

The verdict artifacts (`summary.json` + the 36 `3000_{idx}__{arm}.json`) are **committed** under
`benchmarks/artifacts/m4_n3000/` (force-added past `.gitignore` to preserve the headline in git).

**Full re-run of the headline A/B (needs the external benchmark clone + a build):**

```bash
python setup.py build_ext --inplace                       # 1. build the C extension (Model must be non-None)
export CBQS_BENCHMARKS_DIR=<CBQS-benchmarks clone>         # 2. real Eq.29 n=3000 instances (NOT vendored here)
python -u -m benchmarks.run_m4_n3000 \
  --seed 20260624 --wall 900 --workers 4                  # 3. the A/B; ~15-min wall × 9 inst × 4 arms
```

The discovered genomes are **committed constants** (`benchmarks/plot_m3_n90.py:62-65`), routed through the
pure-Python, allow-list-faithful `m3_proposer.genome_to_factory`:

- `cand_16` = `GENOME_WINNER = [8.0, 4.409916944894315, 0.012044790907040026, 0.28884412462871306, 1.0]`
- `cand_23` = `GENOME_PARSIMONIOUS = [5.164074159795587, 4.428165071164998, 0.0, 0.34053296197047567, 0.0]`
- genome layout: `[r_opt_sat, r_opt, alpha_switch, theta_amp, theta_feature_index]` (`pii_z` == index 1)

**Reproducibility boundary (honest).** The *method* and the discovered genomes are fully committed, so a
third party can re-run the A/B and recover the verdict (sign, significance, clean negctl). Two hard
prerequisites remain: (1) the real Eq.29 instances live in an **external** `CBQS-benchmarks` clone, not in
this repo; (2) the original **M3 selection** artifacts are not committed, so the *discovery* of
cand_16/cand_23 is a fresh stochastic search, not an exact replay. Net: **re-runnable and verdict-stable
given the clone + a build; not a byte-for-byte replay of the discovery.**

---

## 6. Caveats (honest)

- **Single fresh seed**, pairing over the 9 n=3000 instances (a multi-seed run would add within-instance
  power). The matched-arm, seeded design means the A/B **sign** should hold across hardware.
- The run is **wall-bound** (RUN POLICY waives oracle-faithfulness *for the run*); the equal-oracle
  corroboration is what removes the cost-axis confound.
- The edge is **headroom-gated**: null across small-n warm cross-stratum (n=10–50 near-optimal), real only
  where the default stalls (n=90 targeted, n=3000). This is a feature-of-the-regime, not a universal win.

---

## 7. What's next — M5 (Phase 2), deferred

The committed mission is delivered; the following are the deferred Phase-2 / cleanup track:

- **`71e` (M5)** — *convergence-aware / scheduled opt-radius lever.* The most direct follow-on to the M4
  mechanism (default stalls; a radius schedule that tightens as the warm search converges polishes the
  near-optimal point). Needs a **new oracle-indexed radius lever in C** (runtime data, §1.6) priced by the
  equal-`T(n)` A/B — a core change. Lowest-risk advance.
- **`8an.6` (M5)** — *Phase 2 dynamic/marginal angles.* Pairwise-`p_ij` dynamic disturbance inside
  `BranchingFunction`. **Gated** on an open question: does the QTG admit conditional/controlled rotations,
  and can their extra oracle cost be charged in fitness? If not, inadmissible under §1.1. Higher ceiling,
  higher risk.
- **`ayo` (P2)** — *T(n) constant trim* `1200 → 300` (keep the `(n/32)²` quadratic). A faithful small-n
  wall cut; re-freezes the §8 goldens via the core-change workflow. Independent of M5, **awaiting user
  approval**.

---

## 8. Provenance

- **Frozen verdict:** `benchmarks/artifacts/m4_n3000/summary.json` (committed); narrative in
  `benchmarks/M3_WARM_FINDINGS.md §9` (metric degeneracy), `§10` (beats-classical audit), `§11` (M4 verdict).
- **Drivers:** `benchmarks/run_m4_n3000.py` (M4 A/B), `benchmarks/verify_largen_beats_classical.py`
  (independent Eq.29 feasibility audit), `benchmarks/run_m3_warm.py` / `run_m3.py` (M3),
  `benchmarks/m3_proposer.py` + `m3_codegen.py` + `m3_select.py` (proposer + firewall + selection).
- **Anchors:** `benchmarks/baselines_frozen.csv` (warm, anchored through n=500), `floor_calibration.csv`,
  with `*_cold.csv` archives.
- **bd issues:** epic `8an`; milestones `8an.1` (M0), `8an.2` (M1), `8an.3` (M2), `8an.4` (M3), `8an.5` (M4),
  reframe `8an.11`; protocol shifts `8an.9` (warm canonical), `8an.10` (warm M3).
- **Goldens (do not silently change):** `BranchingFunction(i,0,0,0) == 6/7` at `bias=5`; Eq.29 RHS
  (`100_0`) `le_rhs==5032863` (c3), `ge_rhs==5040079` (c2); `T(n)=(n/32)²+1200`. (`CLAUDE.md §8`.)
