# bd kyg — optimize ON TOP of the r≈2 baseline (re-anchored search vs r=2, not the default)

**Bead:** `constraint-oriented-biased-quantum-search-kyg` (labels: 71e, M5). **Date:** 2026-07-01.
**Verdict:** **WON'T-DO by direct measurement.** No lever — fine opt radius, opt_sat radius, switch α,
per-variable θ (all four allow-listed features), or variable_order — **systematically beats the constant
`r≈2` / `opt_sat≈8` baseline** when re-anchored at r=2 and scored vs r=2 (not the weak default). The one
lever with an apparent small-n signal (the opt_sat radius) is a **seed-variance basin lottery** that
**dissolves by n=500**. `r≈2` (opt) + `opt_sat≈8` is the ceiling — the same disposition as bd w29, now
established for the *re-anchored* search the bead asked for. Driver `benchmarks/run_kyg_probe.py`,
conditional analysis `benchmarks/kyg_conditional.py`, tests `tests/test_kyg_probe.py`.

## 1. Question

bd w29 (`W29_FINDINGS.md` §7b): a plain constant opt radius `r≈2` (no θ, no schedule) BEATS the M4
"winner" cand_16 (r=4.41 + θ) at n=3000, 8/9 instances. cand_16 only ever beat the *default* (bias=n/4);
`r≈2` beats cand_16. Every prior M3 search anchored broad (r~4–8) and scored vs the *default*, so it
optimized over the weak default. kyg asks: **can any OTHER lever, re-anchored at r=2 and scored vs the
r=2 baseline, improve on the `r≈2` ceiling?** PRIOR (from the bead): r≈2 has resisted every lever →
modest expected upside; either find a real gain or cleanly establish r≈2 as the ceiling.

## 2. Method

**Baseline `C_r2`** = constant opt radius 2, opt_sat radius 8, cand_16's early switch — exactly W29 §7b's
"bare r=2". **Every arm scores vs C_r2** (not the default). All levers are runtime data (set_param /
`m3_proposer.genome_to_factory` allow-listed path) — **no C change**, faithful by construction (§1.4/§1.6).
Arms: `neg_r2_genome` (harness zero-check), fine radius {1.5..3}, opt_sat radius {2,3,4,5,5.5,6,6.5,7},
switch α {0,½,2×,0.1·T}, θ {pii,obj,cons,degree}_z, variable_order {asc,desc}. Read: `obj@common`
best-of-portfolio, median-over-seeds Δ vs C_r2, Wilcoxon(greater)+Holm, per-seed sign. FAITHFUL small-n =
oracle-budget `M=mult·T(n)`, no wall (reproducible; `neg==C_r2` exactly).

**Analysis hardened after an adversarial review** (workflow `wf_51d87237`) — two defects that would have
manufactured a false ceiling were fixed + unit-tested: (1) **read_budget** reads at `min(mult·T, oracle)`
so a constant lever's headroom band `[T, mult·T]` is actually inspected (reading at `T` is `M`-invariant →
inert); (2) **per-pair common budget** `B=min(oracle[arm], oracle[baseline], read_budget)` so a stalled
third arm can't collapse `B` and force a spurious NULL. Plus a feasibility-parity guard, exact-per-cell
neg check, and symmetric p-gated HURTS. The harness reproduces W29 §7a's `C_r2_theta`=−3,557 at n=60
byte-for-byte (independent validation).

## 3. The opt (explore) phase: `r≈2` is the ceiling

At n=60/90/150, **every opt-phase lever is null vs C_r2**: fine radius (1.5–3.0), θ (pii/obj/cons/degree_z),
switch α. Fine radius `r=1.5` is null at n=90 and **hurts** at n=150 (−12k, 1+/8−); `r=3` and the late
switch `0.1·T` clearly hurt. Nothing systematically beats the tight opt radius `r≈2`. Confirms M2/w29/8an.10
— the re-anchoring did not crack it.

## 4. The opt_sat (feasibility-push) radius: a genuine but conditional lever

The only lever with structure. `opt_sat_branching_radius` (fixed at 8 by cand_16 and every prior search,
never tuned) is **mechanically conditional**: it is *exactly* inert (Δ≡0 vs C_r2) on greedy-**feasible**
instances (the phase machine skips opt_sat when the warm start is already feasible) and acts only on
greedy-**infeasible** ones. So the all-instance median dilutes the signal with exact zeros; the correct
read conditions on greedy-infeasible instances (`kyg_conditional.py`).

**It is a real lever, not portfolio-diversity:** on n=90 instance 8, C_r2 at 4/8/12 workers gives the
*identical* result (a 3× portfolio cannot escape the opt_sat=8 basin) while optsat6 at 4 workers gains
+483k. The gap opens right after first-feasible (opt_sat=8 funnels the search into a worse feasible basin).
Conditioned on where it runs, opt_sat≈4–6 beats the default 8 on a **majority** of hard-feasibility
instances (sign-consistent 13/14 across n=90+150), while opt_sat=7 (≈8) is null/negative.

## 5. …but it does NOT generalize — the apparent win is a seed-variance basin lottery

The effect is **dominated by seed variance** (which feasible basin a run lands in), and it **dissolves
with scale**:

| opt_sat vs default 8 (infeasible-greedy) | n=60 | n=90 (5-seed) | n=150 (3-seed) | n=500 (3-seed) |
|---|---|---|---|---|
| best-behaved arm | optsat2 (tight) | optsat6 (5/5) | optsat6 (8/9) | **coin-flip** |
| optsat6 median Δ | (worst) | +2,323 | +7,810 | +414 (4+/4−) |
| per-run swing | — | ±500k | — | **±2.7M** |

- **Seed variance swamps the effect.** n=90 instance 8, optsat6 vs C_r2 across 5 seeds: +483k, **−472k**,
  +513k, +422k, −32k. The "5/5 positive" was a median artifact; the 3-seed +6,875 dropped to +2,323 at
  5 seeds (the +525k instance-7 win was a seed-630 outlier).
- **Direction is not stable in n**: optsat2 best at n=60, optsat6 best at n=90/150, coin-flip at n=500.
- **It vanishes by n=500**: every opt_sat arm is a 4/8-ish sign split; the large positive *means*
  (optsat4 +89k) are a handful of ±2.7M basin-lottery outlier cells, not a systematic direction.

## 6. Headroom probe: no hidden lever

Faithful mult=4 at n=90 (read in the `[T, 4T]` opt-phase-headroom band, the fixed read from §2). With 4×
the opt-phase oracles, **no lever pulls ahead of r=2** — all arms median Δ=0, no Holm survivor
(harness `neg` clean, max|cellΔ|=0). optsat2's faint 4+/0− (p=0.063) is the only flicker, not significant.
Closes the last "headroom-gated lever" loophole.

## 7. Verdict

**WON'T-DO.** No lever, re-anchored at r=2 and scored vs the r=2 baseline, systematically beats it.
`r≈2` (opt) + `opt_sat≈8` is the ceiling. The one lever with structure (opt_sat radius) is a genuine but
weak, seed-variance-dominated basin effect on hard-feasibility instances that **strengthens n=90→150 then
dissolves n=150→500** — it does *not* trend toward the n=3000 regime. An n=3000 A/B is **not warranted**:
the faithful small-n runs already cannot resolve the effect, and a wall-capped n=3000 A/B is strictly
noisier (RUN POLICY machine-dependence on top of the ±millions seed variance). This is the "cleanly
establish r≈2 as the ceiling" outcome the bead anticipated.

**What was learned (beyond the null):** (a) the opt_sat radius is a previously-unnoticed *conditional*
lever — inert on greedy-feasible instances, active only on greedy-infeasible ones (feasibility phase);
(b) the large per-instance deltas on hard instances are a *seed-driven feasible-basin lottery* (individual
runs swing by millions), not stalling and not portfolio-substitutable at fixed seed; (c) the analysis
hardening (per-pair budget, headroom read) is reusable for any future re-anchored screen.

**Data:** `benchmarks/artifacts/m5_kyg/{n60,n90,n150,n500}_*`, `n90_optsat_5seed`, `n90_m4.0` (headroom).
**Method note:** faithful oracle-budget small-n + greedy-feasibility-conditioned scoring is the cheap,
reproducible discriminator; multi-seed is mandatory (single-seed n=500 gave a spurious reversal — the
seed variance is ±millions on hard-feasibility instances).
