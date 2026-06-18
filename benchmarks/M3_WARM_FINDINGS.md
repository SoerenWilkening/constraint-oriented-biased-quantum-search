# M3-WARM — re-scoping + re-running M3 for the warm-started algorithm (bd 8an.10)

**Status:** warm M3 machinery landed + adversarially reviewed; exploratory run done.
**Protocol:** WARM (`general_greedy()`), the published CBQS (`iqs`) protocol — **not** the cold
`0^n` start the original M3 (bd 884) optimized against.

## TL;DR (the headline finding)

1. **Improved warm strategies DO exist at n=90** — the schedule with a **broad `opt_sat`
   radius + early switch** (the full cand_16 genome) beats the warm default by **§13 W=+9 /
   +23 % mean-PI**. The figures are at `logs/m3_n90_warm/*.png` (`plot_m3_n90 --warm`).
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
via `general_greedy()` (bd 8an.9). Warm headroom is small/mid-`n` only — n=90 ≈28 % headroom;
n=3000 ≈0 % (greedy near-optimal, all methods tie, `logs/m4_spot/compare_n3000_warm.py`).

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

## 3. Scoring a warm candidate (the harness)

`score_verdict` reads `default_PI` from the frozen **table** as the §6.6 gate reference — and that
column is **cold**. To compare warm-vs-warm we hand the metric an in-memory table from
`baselines.synthesize_warm_default_pi(frozen, warm_default_runset)`:

* `default_PI` ← the **freshly-solved warm default**'s median PI;
* `B_I` (frontier) ← kept (protocol-independent); `L_I` (cold first-feasible floor) ← kept as the
  shared normalizer (both arms use the *same* cold `L_I`, so the offset cancels in the paired δ —
  the accepted exploratory gap).

The capstone holds: the warm default re-scores to *exactly* the synthesized `default_PI`
(`strict_xcheck=True` passes). Both A/B arms are warm; the negative control (`{}` solved warm) is
byte-identical to the warm default → no survivor.

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

* §1.4 allow-list, §1.6 legal-lever-only, scale-invariance + θ radius-neutrality gates: enforced.
  Equal-`T(n)` A/B (both arms `M=-1`, exact sampler, matched 7-seed bank).
* **EXPLORATORY**: cold `L_I`/`B_I` with a warm `default_PI`. A FINAL/publishable result needs
  **bd 8an.9** (re-frozen *warm* anchors + `default := warm` governance + warm capstone). 8an.10
  discovers/ranks; it does not re-freeze.

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
is the open question for a full run.

**Caveats:** (1) the reduced run searched the wrong space and is underpowered — a full-genome,
full-88-instance run is needed for a definitive cross-stratum verdict; (2) exploratory anchors
(cold `L_I`/`B_I`); (3) the faithful warm history (true greedy value at oracle 0, gated on greedy
feasibility) is deferred to 8an.9.

## 7. Reproduce

```bash
# full-genome warm search (the corrected scope) — n≤90, ~3.5 h for the full instance set:
CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.run_m3_warm \
    --out-dir benchmarks/artifacts/m3_run_warm_8an10 --seed 20260618 \
    --generations 5 --pop-size 8 --n-offspring 6 --n-init-random 6        # add --max-per-size 4 for a fast pass

# n=90 competitors-vs-default figures (full cand_16 / cand_23 warm):
CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.plot_m3_n90 --warm        # -> logs/m3_n90_warm/*.png
```
