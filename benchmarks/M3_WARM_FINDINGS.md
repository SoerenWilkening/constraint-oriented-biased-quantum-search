# M3-WARM — re-scoping + re-running M3 for the warm-started algorithm (bd 8an.10)

**Status:** **COMPLETE.** Warm M3 machinery landed + adversarially reviewed; the FINAL
full-genome, full-88-instance run against the **frozen warm anchors** (bd 8an.9) is done.
**Protocol:** WARM (`general_greedy()`), the published CBQS (`iqs`) protocol — **not** the cold
`0^n` start the original M3 (bd 884) optimized against. **Mode:** FINAL/publishable — candidates
scored against the COMMITTED frozen warm `default_PI` (8an.9), cold `L_I` shared.

## TL;DR (the headline FINAL verdict)

0. **FINAL cross-stratum §13 verdict: NO warm schedule beats the warm default on n≤90 under the
   Holm-controlled §13 — 0 survivors of 41 candidates** (incl. the cold-M3 winners cand_16/cand_23
   seeded directly + 30 evolved). The warm default is **unbeaten** on the anchored n≤90 strata.
   The warm advantage of cand_16 is **real but n=90-concentrated**: cross-stratum it falls to
   `pi_rank=+0.198` (cand_16) / `+0.212` (cand_23) — *positive on average but CV-fail* (does not
   clear BOTH the n=10–50 train and n=60–90 validate folds). Best evolved candidate `pi_rank=+0.422`,
   still CV-fail. This is the deliverable's reframed outcome ("squeeze the small/mid-n warm headroom"
   — and at small-n the headroom is too thin for a *cross-stratum* win). Run:
   `benchmarks/artifacts/m3_run_warm_8an10_final/` (gitignored; key numbers in §8 below).
1. **Improved warm strategies DO exist at n=90 (targeted)** — the schedule with a **broad `opt_sat`
   radius + early switch** (the full cand_16 genome) beats the warm default at n=90 by **§13 W=+9 /
   +23 % mean-PI** (targeted single-stratum analysis; `logs/m3_n90_warm/*.png`, `plot_m3_n90 --warm`).
   §8's cross-stratum FINAL verdict shows this n=90 win does **not** generalize to the full n≤90 fold.
2. **The task's "KEY INSIGHT" is empirically FALSE at n≤90.** The premise was that a warm
   (feasible-from-oracle-0) start makes `opt_sat`/`switch` inert, leaving a warm-live space
   `{r_opt, θ}`. But the **greedy start is frequently INFEASIBLE** — 4/9 n=90 instances
   (90_2/6/7/8), and 10_0/20_1/40_0/60_0 — so the solver **does** run `opt_sat`, and
   `opt_sat_branching_radius` + `alpha_switch` are **not inert; they are the DOMINANT drivers**
   of the warm win.
3. **My first re-scope was therefore wrong.** A search over `{r_opt, θ}` only (dropping the
   dominant levers) finds **no winner** (tie / −3 %). The driver now searches the **FULL 5-gene
   genome** by default; `--warm-live-only` keeps the reduced space (valid only where the greedy
   start is always feasible — not n≤90).

## 1. Why a warm re-run

The cold M3 (bd 884, winner `cand_16`) optimized against a `0^n` cold start; `iqs` **warm-starts**
via `general_greedy()` (bd 8an.9). Warm headroom in *objective* terms is largest at small/mid-`n`
(n=90 ≈28 %), but at n=3000 there is still a real, schedule-driven advantage **at a fixed oracle
budget** (M3 +0.12 % within `T(n)`; see §6) — it is small relative to the ~2.27e10 objective
*magnitude* but real relative to the *headroom*. An earlier "n=3000 ≈0 %, all tie" reading was an
artifact of comparing wall-bound final objectives (corrected in §6).

## 2. Genome scope — the corrected lever analysis

The collapse-to-`{r_opt, θ}` argument only holds **when the greedy start is feasible** (then the
solver jumps to stage-3 opt and `opt_sat` never runs). Empirically that is **not** the n≤90 regime:

```
warm-greedy feasibility at n=90 (M=1 probe):  90_0 ✓  90_1 ✓  90_2 ✗  90_4 ✓
                                              90_5 ✓  90_6 ✗  90_7 ✗  90_8 ✗  90_9 ✓
                                              => 4/9 INFEASIBLE
```

On those 4 infeasible-greedy instances the solver runs `opt_sat`, where cand_16's broad
`opt_sat_branching_radius=8` + early `opt_switch_oracles` reach feasibility/optimize — and these
are exactly the instances with the largest plot wins (90_7: PI 0.127→0.085). So the warm search
must keep `opt_sat_radius` + `switch`. The reduced `WARM_SPEC` (`{r_opt, θ}`,
`warm_genome_to_factory`) is retained only as an option for an all-feasible-greedy regime.

A **scheduled / convergence-aware** opt radius is still not searched (needs a new oracle-indexed C
lever = a core change) — deferred to **bd 71e** (M5).

## 3. Scoring a warm candidate (the harness) — FINAL vs EXPLORATORY

`score_verdict` reads `default_PI` from the frozen **table** as the §6.6 gate reference. Since
**8an.9 re-FROZE the warm `default_PI`** into `baselines_frozen.csv` (`protocol==warm`), the driver
(`run_m3_warm.py`) now AUTO-selects between two modes:

* **FINAL (default when the frozen table is warm)** — score candidates against the **committed
  frozen warm `default_PI`** directly. The default-vs-default capstone becomes a real
  **reproducibility gate**: a freshly-solved warm default must re-score to the frozen warm anchor
  within `metric.XCHECK_REL_TOL=1e-3` — verified **bit-for-bit** (rel_drift = 0.0; the warm solve is
  deterministic at the 7-seed bank). This is the publishable path the §8 verdict uses.
* **EXPLORATORY (`--exploratory`, or AUTO on a still-cold table)** — replace the cold frozen
  `default_PI` in an in-memory table with THIS run's warm default median PI
  (`baselines.synthesize_warm_default_pi`); the capstone is then self-consistency and the anchor
  floats per run (not reproducible). This was the only path available before 8an.9.

In BOTH modes the cold `L_I` is the shared normalizer (kept in the warm freeze too — both arms
cancel it in the paired δ) and `B_I` is the protocol-independent frontier. Both A/B arms are warm;
the negative control (`{}` solved warm) is byte-identical to the warm default → no survivor.

### Warm trajectory repair (`warm_repair_history`)
A warm worker feasible at the greedy value from oracle 0 logs only *improvements*, so a
greedy-**optimal**-never-improved run has an *empty* history → `compute_primal_integral` reads
`+∞` (never-feasible), spuriously scoring it as a feasibility loss (found at `10_2`). Repair (the
only case touched): empty history + a feasible final → `history = [(max feasible final, 0)]`
(provably exact — an empty history can only come from a feasible greedy no worker improved on). A
non-empty warm history is left **verbatim**: the review confirmed the greedy start is often
*infeasible*, where `history[0]` is the genuine first-feasible incumbent and `[0, first_stamp)` is a
legitimate `γ=1` plateau that must survive (an earlier backfill wrongly erased it).

## 4. Faithfulness / what is and isn't claimed

* §1.4 allow-list, §1.6 legal-lever-only, scale-invariance + θ radius-neutrality gates: enforced
  (the FINAL run gated out 1/41 candidates on the §1.5 radius-fidelity check — θ coupling into the
  realized radius — the gate working). Equal-`T(n)` A/B (both arms `M=-1`, exact sampler, matched
  7-seed bank).
* **FINAL / publishable** (this run): warm `default_PI` from the **frozen** 8an.9 anchors; cold
  `L_I`/`B_I` shared (by design — `L_I` is the cancel-in-δ normalizer, kept cold in the warm freeze
  too; `B_I` is protocol-independent). The capstone proves the fresh warm default reproduces the
  frozen warm anchor. This is no longer an exploratory gap — 8an.9 (re-frozen warm anchors +
  `default := warm` governance + warm capstone) is **done**, and 8an.10 scores against it.

## 5. Adversarial review outcome (bd 8an.10 review workflow)

4 dimensions × independent reviewers → adversarial verify. 21 findings, **4 confirmed**, all the
`warm_repair_history` non-empty **backfill** — it over-credited `[0, first_stamp)` and **erased the
legitimate `γ=1` plateau when the greedy start is infeasible** (confirmed empirically on 60_0:
`[(897,4),…]` → wrongly `[(897,0),(897,4),…]`). **Fixed** by dropping the non-empty backfill (the
empty-history repair is provably exact). The review's infeasible-greedy finding is the same fact
that, followed through, overturned the re-scope premise (§2). 11 other findings were affirmative
"verified clean"; 1 low-severity doc comment added.

## 6. Exploratory run + targeted results

**Reduced warm-live run** (gens 3, pop 6, `--max-per-size 4` → 36 instances; the *old* `{r_opt,θ}`
scope): 18 candidates, 15 admitted (3 gated by **radius-fidelity** — θ at tiny `r_opt` couples into
the realized radius, the gate working), **0 survivors**. This is the expected result of searching
the *wrong* (lever-dropped) space.

**Targeted §13 at n=90** (full 9 instances, warm default reused), comparing the cold winner's full
genome vs the warm-live subset vs the isolated `opt_sat` levers:

| schedule (warm) | §13 signed-rank W (n=90) | mean-PI vs warm default |
|---|---|---|
| **FULL cand_16** (opt_sat r=8 + switch + r_opt=4.41 + θ=pii_z) | **+9.0 (wins)** | **+23 %** |
| warm-live r_opt=4.41 + θ (opt_sat/switch dropped) | 0.0 (tie) | −3 % |
| opt_sat r=8 + switch only (θ off) | 0.0 (tie) | +25 % |

**Per-instance n=90 mean-PI** (`plot_m3_n90 --warm`, with the faithful repair): m3_winner **+22.9 %**,
m3_parsimonious **+22.7 %** vs warm default — wins concentrated on the infeasible-greedy instances
(90_7 0.127→0.085, 90_6 0.072→0.051, 90_2 0.062→0.045, 90_9 0.042→0.024).

**Interpretation.** The dominant warm lever at n≤90 is the **broad `opt_sat` radius + early switch**
(reaching feasibility faster on the ~44 % of instances whose greedy start is infeasible), exactly
cand_16's cold strengths — so the cold-selected schedule *also* wins warm at n=90, and the warm
search must keep those levers. The signed-rank `W=+9` shows a real n=90 win; whether the FULL
genome clears the *cross-stratum* §13 selection (both folds, incl small-n where headroom is thinner)
was the open question for a full run — **now answered in §8: it does NOT** (the n=90 win does not
generalize across n≤90; cross-stratum cand_16 falls to `pi_rank=+0.198`, CV-fail).

**Caveats (resolved by §8):** (1) the reduced run searched the wrong space and was underpowered —
the **§8 FINAL run** is full-genome, full-88-instance, and definitive; (2) the §8 run scores against
the **FROZEN warm anchors** (8an.9), not exploratory cold-`default_PI` ones; (3) the faithful warm
history (true greedy value at oracle 0, gated on greedy feasibility) landed in 8an.9.

### n=3000 — M3 WINS at the faithful oracle budget (corrected 2026-06-19)

Warm A/B on a single n=3000 instance (3000_0), 15-min wall cap per arm, 4 workers, exact sampler
(`logs/m4_spot/compare_n3000_warm_history.py`, with oracle-indexed history). **Two corrections to an
earlier wrong reading of this run:**

1. The warm greedy start at 3000_0 is **INFEASIBLE** (−63 M violation; an `M=1` probe returns it
   infeasible on all 4 workers). It is *not* feasible-from-oracle-0 — feasibility is reached only at
   oracle ~40–76, then the objective climbs. So `opt_sat` DOES run; the mechanism is the SAME as the
   n≤90 infeasible-greedy instances, not an exception.
2. The wall-bound "tie on final objective" was an **artifact of the cost axis, not a real tie.** Read
   at a FIXED oracle budget — which is the project's actual cost metric ("the oracle count is the
   product") — the M3 schedules clearly WIN:

   | at T(3000)=9989 oracles | objective | vs default |
   |---|---|---|
   | default | 22,694,940,349 (stalled) | — |
   | m3_winner (cand_16) | 22,719,890,812 | **+24.95 M (+0.110 %)** |
   | m3_parsimonious (cand_23) | 22,722,395,203 | **+27.45 M (+0.121 %)** |

   The M3 arms **converge by ~5–6 K oracles**; the default does not improve past 2.2695e10 until
   oracle **43,448,066** — its catch-up is at **~4300× the faithful budget**, inside the over-budget
   region (`compare_n3000_warm_budget.png`). The default's huge 90.9 M `oracle_calls` is the
   **big-M giant-round artifact** (M=1e8 removes the `j`-clamp → one stuck worker commits a single
   runaway Grover round charging `2j+1 ≈ 90 M`, faithfully counted but with its sim deadline-truncated;
   it cannot happen under the faithful `M=T(n)=9989`). So the "tie" only appears if the default is
   allowed to spend 4300× the budget; at any budget ≤ ~4.3e7 oracles, M3 leads by ~+0.12 % / ~27 M.

**The relative deltas look tiny only because the objective is ~2.27e10** — the *absolute* within-budget
gain is ~25–27 M, and the right denominator is the headroom (per the primal-gap metric), not the
objective magnitude. So n=3000 is NOT "~0 % headroom": at the faithful budget there is a real,
schedule-driven advantage; it was hidden by (a) the magnitude-relative %, and (b) comparing final
objectives in a wall-bound run that let the default run 4300× over budget.

**Caveat:** single instance + single seed. The at-budget M3 lead (M3 converges within budget, default
stalls) is the robust signal and matches the n≤90 mechanism (broad `opt_sat` radius on an
infeasible-greedy start); a multi-instance / multi-seed run at the faithful `M=T(n)` is needed to
confirm it generalizes. (Figures: `compare_n3000_warm_budget.png`, `*_history_logx.png`.)

## 7. Reproduce

```bash
# THE FINAL run (publishable): full-genome, full-88-instance, scored vs the FROZEN warm anchors
# (8an.9), with the cold-M3 winners cand_16/cand_23 seeded into the population. ~3.2 h.
CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.run_m3_warm \
    --out-dir benchmarks/artifacts/m3_run_warm_8an10_final --seed 20260620 \
    --generations 5 --pop-size 8 --n-offspring 6 --n-init-random 8 --seed-cold-winners
#   FINAL mode is auto-selected (the frozen table is warm); --exploratory forces the old
#   in-memory synthesize path; --max-per-size N for a fast subset pass (needs >=2/stratum for the
#   per-stratum PI spread the §6.6 aggregate requires).

# n=90 competitors-vs-default figures (full cand_16 / cand_23 warm; single-stratum, targeted):
CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.plot_m3_n90 --warm        # -> logs/m3_n90_warm/*.png
```

## 8. FINAL cross-stratum §13 verdict (bd 8an.10, 2026-06-20)

The publishable run: `run_m3_warm --seed-cold-winners` (FINAL mode, frozen warm anchors 8an.9),
seed 20260620, 5 generations, full 5-gene genome, all **88 anchored n≤90 instances**, 7-seed bank.
Artifacts at `benchmarks/artifacts/m3_run_warm_8an10_final/` (gitignored; numbers preserved here).

**RESULT: 0 survivors of 41 candidates** (40 admitted, 1 §1.5-gated). No warm schedule passes the
cross-stratum §13 (CV over BOTH folds train{10–50}/validate{60–90} **AND** Holm FWER ≤ 0.05).
**The warm default is unbeaten on the anchored n≤90 strata.** Negative control passed (no warm
baseline-equivalent survivor). The full-scale FINAL capstone passed bit-for-bit (a fresh warm
default re-scored to the frozen warm `default_PI` on all 88 instances).

| candidate | genome | `pi_rank` (n≤90) | gate | CV (both folds) |
|---|---|---|---|---|
| **seed_cand_16** (cold winner) | r_opt_sat=8, r_opt=4.41, α=0.012, θ=pii_z | **+0.198** | ✗ | ✗ |
| **seed_cand_23** (cold winner) | r_opt_sat=5.16, r_opt=4.43, α=0, θ off | **+0.212** | ✗ | ✗ |
| cand_23 (best evolved) | r_opt_sat=2.71, r_opt=3.63, α=0.003, θ_amp=0.46 off | **+0.422** | ✗ | ✗ |
| cand_16 / cand_28 / cand_25 (evolved) | (broad-opt / small-r variants) | +0.41 / +0.41 / +0.39 | ✗ | ✗ |

**Interpretation.** Every top candidate is *better-on-average* warm (positive `pi_rank`, negative =
better `pi_median` ≈ −0.07..−0.09) but **none clears the §6.6 gate or the cross-stratum CV**. The
cold-M3 winner's big n=90 edge (W=+9 / +23 %, §6/§1 targeted) **does not generalize**: scored across
all of n≤90 it collapses to `pi_rank ≈ +0.20` and CV-fails because the small-n (n=10–50) warm
headroom is too thin for consistent significance across both folds. Cf. the COLD M3 (bd 884) where
cand_16 scored `pi_rank=+0.875`, gate=True — the gap (+0.875 cold → +0.198 warm) is exactly the
"warm start already captures most of the small-n headroom" effect.

**This is the deliverable's reframed conclusion** (per the task: warm headroom is small/mid-n only,
n=90 ≈28 %, n=3000 ≈0 %; "squeeze the small/mid-n warm headroom"): a *cross-stratum* warm schedule
that beats the warm default under the full §13 does **not** exist in the searched space — the warm
advantage is **real but n=90-concentrated** (see §6 targeted n=90 and the §6 n=3000 at-budget lead).
A scheduled / convergence-aware opt radius (a new oracle-indexed C lever, not in this genome) is the
remaining untested avenue — deferred to **bd 71e** (M5).

## 9. Large-n anchoring: the B_I-PI metric is DEGENERATE at n≥1000 (bd 8an.4.8, 2026-06-21)

A spot-check during the large-n anchor freeze (8an.4.8, extending warm anchors past n=500) found the
**primal-gap-to-`B_I` metric breaks down at n≥1000** — a *fundamental* limit, not a compute one. The
M1–M3 metric normalizes progress by `(B_I − L_I)`: from a first-feasible floor `L_I` *up to* the
classical frontier `B_I`. But warm CBQS reaches feasibility **at or above `B_I`** at scale:

| n | greedy feasible? | first-feasible vs `B_I` | metric |
|---|---|---|---|
| ≤90 | often infeasible | `< B_I` (real headroom; default_PI > 0) | works |
| 500 | mixed | mostly `< B_I`, but **2/8 default_PI < 0** (500_3, 500_6 — warm already beats `B_I`) | works (onset) |
| 1000 | 2/9 feasible **== `B_I` exactly** (1000_0/1, gurobi); 7/9 infeasible | `≥ B_I` | **degenerate** |
| 3000 | 9/9 infeasible | first-feasible(3000_0) `> B_I` (22.688e9 vs 22.656e9), final beats hexaly, `verify=True` | **degenerate** |

At n≥1000, `L_I ≥ B_I` → `(B_I − L_I) ≤ 0` → every instance drops as `L_ge_B`; the primal integral
toward `B_I` is ill-defined once the solver meets/beats `B_I`. **NOTABLE — likely the headline at
scale: warm-started CBQS appears to BEAT classical SOTA (gurobi/hexaly) at n≥1000** (verified-feasible
objectives above the best-known frontier). Also: a faithful warm n=3000 solve is **~32 min** (~33 h /
9-instance stratum); n=1000 is fast (114 s, full `T(1000)=2176`).

**Decision (user, 2026-06-21): freeze tops out at n=500.** `baselines_frozen.csv` is warm-anchored
through **n=500** (8/9; 500_8 has no cold `L_I`); n≥1000 is **NOT** PI-anchorable and is documented as
degenerate (do not freeze). **M4 (n=3000 generalization) is reframed off the B_I-PI verdict** to a
**direct objective A/B** (warm candidate vs warm default, objective-at-budget, paired Wilcoxon + neg
control — the §6 n=3000 method) → tracked as a new bead. M3's "largest-n strict gate_A" exit inherits
the same reframe. See memory `largen-warm-beats-bi-metric-degenerate` and bd 8an.4.8.
