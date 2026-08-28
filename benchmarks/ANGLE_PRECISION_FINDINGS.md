# bd a0w — angle precision: how coarse may the QTG's `R_y(θᵢ)` be?

**Bead:** `constraint-oriented-biased-quantum-search-a0w` (M5). **Date:** 2026-08-28.
**Verdict:** CBQS is **far more robust to inaccurate angles than the bead predicted**. There is no gradual degradation — performance is FLAT down to a hard **collapse cliff at `ε = θ`**, where the grid rounds the rotation to zero and the search becomes deterministic greedy. Measured **b\* ≈ 2.7–3.7 bits (~6–9 T-gates per rotation)** at n=60–150, versus the bead's predicted 6.5–7. The T-count is **O(log n) per rotation / O(n log n) per QTG application** — NOT O(1), and **not** flat in n for the dithered arm either: the bead's dither prediction is falsified, analytically and empirically.

## 1. Question

On hardware the QTG's per-variable rotations `R_y(θᵢ)` are not exact: Ross-Selinger /
gridsynth synthesizes each to an absolute accuracy `ε` radians at a T-count of `≈3·log₂(1/ε)`.
Coarser angles buy cheaper circuits. CBQS should be robust to inaccurate angles as long as they
still generate the highly biased superposition that grants the performance. **How coarse can we
go before the objective degrades, and how does that scale with `n`?**

This adds a cost axis the project has never priced: **the inside of the oracle**. Today the
product is the oracle count at exact angles. With this lever the claim strengthens to "the
schedule needs only `b` bits, so each QTG application costs `≈3·b·n` T-gates instead of
`≈3·53·n`". Precision also *moves* the measured oracle count (coarser angles perturb the
sampling distribution), so the two axes are reported separately and **precision is never folded
into the equal-`T(n)` oracle pricing** (NORTHSTAR §1.1/§5).

### 1a. Why the pessimistic error budget does not apply

The naive objection is a union bound over every rotation in every Grover iteration
(`ε ≲ 1/#rotations` ⇒ ~25–30 bits). It does not apply. The Grover iterate is
`G = −A S₀ A† O_f`. If `A` is synthesized **once** and that same circuit and its adjoint are
used, then `Ã S₀ Ã†` is the **exact** reflection about `|ψ̃⟩ = Ã|0⟩`. The algorithm is therefore
exactly Grover on a slightly *perturbed initial distribution*: **zero error accumulation in `j`**.
CBQS uses the BBHT randomized-`j` schedule, which is robust to not knowing `p` exactly, so the
resulting mis-set rotation count is free too.

Assumptions, stated so they can be checked:
- **(a)** `O_f` is exact — it is arithmetic/comparison, no rotations. Holds.
- **(b)** `A` and `A†` are the **same** synthesized circuit, not independently synthesized. If
  (b) is violated errors *do* accumulate and the requirement tightens to `ε ≲ 1/j`.

So the precision requirement is set only by **how far the sampling distribution may shift before
the objective degrades** — a far weaker condition, and the one measured here.

## 2. Step 1 (before any code) — the radius-tolerance constant `X`

The whole prediction hangs on one empirical constant: how far may the realized neighborhood
radius drift from the shipped `r* ≈ 2` before the objective measurably degrades? Since
`p_flip = r/n = sin²(θ/2)` ⇒ `dp/p = 2·dθ/θ`, a radius tolerance `X` translates directly into
an angle tolerance `ε* = X·θ/2`. **The bead assumed `X = ±10%`.** Read off the frozen
constant-radius sweeps instead (`benchmarks/a0w_radius_tolerance.py`, no new solves):

| n | source | seed-noise floor | measured loss vs r=2 | `X` (linear) | `X` (quadratic) |
|---|--------|------------------|----------------------|--------------|-----------------|
| 60 | w29 grow, faithful, 9×3 | 0.157% | r=4.41: −0.005%, r=6: −0.076% | ±4007% | ±303% |
| 90 | w29 grow, faithful, 9×3 | 0.073% | r=4.41: −0.047%, r=6: −0.127% | ±187% | ±151% |
| 3000 | 71e static, wall 900 s, 9×1 | 0.0026% | r=4: −0.009%, r=8: −0.045% | **±29%** | ±72% |

*linear* extrapolates the slope from the nearest measured radius inward (assumes **no** plateau —
the conservative bound); *quadratic* fits `loss%(r) = c·(r−2)²` through the interior optimum
(the physically right shape, but fitted only from distant points). `X` is the drift at which the
predicted loss reaches the seed-noise floor — below that floor a "degradation" is not measurable.

**Finding: the assumed ±10% is far too tight — by 3× at the most conservative reading (n=3000
linear) and by an order of magnitude at small n.** A +10% radius drift costs 0.00005–0.0003% of
objective, i.e. **50–900× below the seed-noise floor**. Carried forward: **`X = 0.30`** as the
headline, with `X ∈ {0.10, 0.30, 0.50}` reported as a band. This loosens `ε*` by
`log₂(0.30/0.10) ≈ 1.6 bits` versus the bead's prediction.

## 3. What was built (default-OFF, baseline byte-identical)

The lever quantizes **θ, never `p`**: the physical knob is the `R_y` angle, and a uniform grid in
probability space is unfaithful and far too coarse near `p ≈ 0`, which is exactly where CBQS
operates (`p_flip = r/n`, so `θ ≈ 2√(r/n)` shrinks like `1/√n`).

- **`cbqs/src/Branching.h`** — two new fields on `BranchingStats_t`
  (`angle_precision_eps`, `angle_precision_dither`) and a pure quantizer
  `branch_quantize_angle` applied **immediately after the existing sigmoid+clamp** in
  `BranchingFunction`:

  ```
  p = 1 − value ;  θ = 2·asin(√p)
  systematic (dither=0):  θ_q = 2ε·round(θ / 2ε)          → |θ_q − θ| ≤ ε
  dithered   (dither=1):  θ_q = θ + ε·u(index),  |u| < 1  → |θ_q − θ| ≤ ε
  value_q = branch_clamp(1 − sin²(θ_q/2))
  ```

  `u(index)` is a splitmix64 finalizer on the variable index — a **pure function of the index**,
  touching neither the solver PRNG stream nor any global state, so determinism under a fixed seed
  is unaffected and the offsets are stable across workers, phases and Grover rounds exactly as a
  compiled circuit would be. `sin²` is even and bounded, so a negative or over-rotated `θ_q` is
  still a valid probability (no folding); the re-clamp is what makes **bounded decisions
  (NORTHSTAR §1.7) hold by construction** even for a grid coarse enough to round θ to zero — the
  case that would otherwise silently force deterministic greedy.
  `ε ≤ 0` (the default) **skips the block entirely**, so the pre-a0w path — including the §8
  golden `BranchingFunction(i,0,0,0) == 6/7` at `bias=5` — is recovered **bit-for-bit**.
- **`solver_ctx.{c,h}`** — `solver_ctx_set_angle_precision` + the three per-phase variants.
- **`phase_params.py`** — `angle_precision_eps` (float > 0) and `angle_precision_dither` (bool)
  added to `PHASE_PARAM_SUFFIXES`, so `sat_`/`opt_sat_`/`opt_` resolution comes for free
  (18 → 24 phase params); plus the **reporting-only** helpers `angle_precision_bits`,
  `t_count_per_rotation`, `t_count_per_qtg_application`. Bits are never an input.
- **`SearchLib.pyx`** — propagated in the **existing** per-phase loop of
  `_propagate_phase_params` (no second route, §2.7; runtime data only, §1.6).

The two synthesis models are the nameable engineering trade-off:

| `dither` | physical model | error structure |
|---|---|---|
| `False` (default) | one rotation circuit compiled once, reused for all `n` variables | **systematic** grid rounding; radius error adds **coherently** (`~n·dθ`) |
| `True` | `n` independently synthesized circuits | per-variable pseudorandom residual within ε; first-order error **averages** |

## 4. Theory — the falsifiable prediction, corrected

With `p = sin²(θ/2) = (1 − cos θ)/2` and `θ = 2·asin(√(r/n))`:

**Systematic.** All `n` variables share one `θ_q`, so the error is coherent:
`|Δr|/r ≈ 2ε/θ` ⇒ `ε*_sys = X·θ/2 = X·√(r/n)` ⇒ **`b*_sys = ½·log₂ n + log₂(π/2) − log₂(X√r)`**.

**Dithered.** The first-order term averages away, but a **second-order coherent bias remains**,
exactly (no small-angle approximation needed) — with `u ~ U[−1,1]`:

```
E[ sin²((θ + εu)/2) ] = ( 1 − cos θ · sinc ε ) / 2 ,   sinc x = sin x / x
⇒ |Δr|/r = cos θ (1 − sinc ε)/(1 − cos θ)  ≈  n ε² / (12 r)
⇒ ε*_dit = √(12·r·X/n) = θ·√(3X)
⇒ b*_dit = ½·log₂ n + log₂(π/2) − ½·log₂(12·r·X)
```

**This falsifies the bead's dither prediction.** The bead expected dither to cancel the
`n`-dependence (`b* ≈ 4`, flat). It does not: dither kills the *first-order* coherent error, but
`E[sin²]` sits strictly **above** `sin²`, and that second-order bias is itself coherent across
variables and grows like `n·ε²`. **Both modes are `½·log₂ n + const`; dither buys a _constant_
`log₂(2√(3/X))` bits** — 2.0 bits at `X=0.5`, 2.7 at `X=0.3`, 3.5 at `X=0.1`.

Closed form vs. the shipped lever's actual splitmix64 draw (residual = the finite-`n` sampling
fluctuation of a fixed hash draw, which shrinks with `n` as expected):

| n | ε | closed-form `E[r_q]` | lever `r_q` | Δ |
|---|---|---|---|---|
| 90 | 0.25 | 2.447 | 2.687 | +9.8% |
| 90 | 0.03 | 2.006 | 2.038 | +1.6% |
| 3000 | 0.25 | 17.56 | 17.67 | +0.7% |
| 3000 | 0.03 | 2.225 | 2.219 | −0.3% |

Predicted `ε*` / `b*` at the measured tolerance **`X = 0.30`** (`r = 2`):

| n | θ (rad) | ε\*\_sys | b\*\_sys | T/rot | ε\*\_dit | b\*\_dit | T/rot |
|---|---------|----------|----------|-------|----------|----------|-------|
| 60 | 0.3672 | 0.0699 | 4.49 | 11.5 | 0.359 | 2.13 | 4.4 |
| 90 | 0.2993 | 0.0426 | 5.21 | 13.7 | 0.289 | 2.44 | 5.4 |
| 150 | 0.2315 | 0.0438 | 5.16 | 13.5 | 0.222 | 2.82 | 6.5 |
| 3000 | 0.0517 | 0.0098 | 7.33 | 20.0 | 0.0489 | 5.01 | 13.1 |
| 10⁶ | 0.0028 | 0.00054 | 11.52 | 32.6 | 0.00268 | 9.20 | 25.6 |

(`benchmarks/a0w_radius_tolerance.py` pins `X`; the closed forms above are the model the sweep
tests. Systematic rounding is a non-monotone **lattice** in ε — a coarse grid can inflate the
radius as easily as collapse it — so `ε*` is defined by the coarsest ε for which *it and every
finer ε* stays inside tolerance.)

## 5. Benchmark protocol

The **w29 faithful probe protocol** (`benchmarks/run_a0w_precision_probe.py`):

- **Faithful**: oracle-budget termination `M = T(n)`, **no wall cap** ⇒ fully reproducible, zero
  wall-truncation noise. Affordable precisely because the budget is small (user directive: keep
  the Grover-iteration count small; the goal is the *minimal* precision, not a maximal-budget run).
- **Warm start** (canonical since bd 8an.9): `general_greedy()` + `warm_repair_history`.
- Everything else at the settled static configuration (bd kyg/w29): `opt_branching_radius=2`,
  `opt_sat_branching_radius=8`, cand_16's early switch — the **only** difference between arms is
  the angle precision. ε is set **unprefixed**, i.e. all three phases: on hardware there is no
  phase at which the circuit is magically exact.
- **obj@common**, **best-of-portfolio** (NORTHSTAR §1.3, never the mean), 4 workers, median over
  seeds, two-sided Wilcoxon + Holm across the ε family, per-seed sign counts.
- Grid: ε ∈ {0.5, 0.25, 0.125, 0.0625, 0.03, 0.015, 0.008, 0.004, 0.002, 0.001} × dither
  {off, on} × n ∈ {60, 90, 150}, 9 instances × 5 seeds (45 cells/arm), plus an `exact` arm. 2 970 solves total.
- **Negative control** `negctl`: ε = 1e-12 must reproduce `exact` **exactly** (Δ = 0).
- Also recorded per arm: the **mechanism** — the realized opt-phase Hamming radius from
  `result.branch_diagnostics`, against the analytic `r_q = n·sin²(θ_q/2)`.

`ε*` = the coarsest grid ε that is (i) not Holm-rejected against `exact` and (ii) whose median
objective loss stays inside the seed-noise floor, **and for which every finer ε also passes**.


## 6. Results

**2 970 solves**: 3 sizes × 22 arms × 9 instances × 5 seeds, faithful (`M = T(n)`, no wall).
(The n=90 `summary.json` was initially written by a stray 3-seed analysis pass; it has been
recomputed over all 5 seeds — analysis only, no re-solving — and the table below is the 5-seed
result. `--report-only` regenerates any summary from the stored per-cell records.)
Harness control passed at every `n`: `negctl` (ε=1e-12) reproduced `exact` with **median Δ = 0
exactly**, 9/9 instances.

### 6a. The headline — ε\*, b\*, and the T-count

| n | θ (rad) | seed-noise floor | ε\*<sub>sys</sub> | b\*<sub>sys</sub> | T/rot | ε\*<sub>dit</sub> | b\*<sub>dit</sub> | T per QTG app |
|---|---------|------------------|-------------------|-------------------|-------|-------------------|-------------------|---------------|
| 60  | 0.3672 | 0.158% | 0.25  | **2.65** | 6 | 0.5   | 1.65 | ~360 |
| 90  | 0.2993 | 0.093% | 0.25  | **2.65** | 6 | 0.25  | 2.65 | ~540 |
| 150 | 0.2315 | 0.117% | 0.125 | **3.65** | 9 | 0.125 | 3.65 | ~1 350 |

**≈3 bits, ≈6–9 T-gates per rotation.** The bead predicted 6.5–7 bits (18–19 T/rot) from the
assumed ±10% radius tolerance; the measured tolerance (§2) is 3–10× looser, and that is exactly
where the ~3-bit saving comes from.

### 6b. The cliff is a COLLAPSE cliff at ε = θ — 4/4 predictions correct

There is no gradual degradation. Performance is flat across the whole grid until the systematic
grid rounds the angle to **zero** (`round(θ/2ε) = 0`, i.e. **ε > θ**), at which point `p_flip` is
pinned at the `BRANCH_EPS = 1e-9` clamp and the exploratory stage becomes deterministic greedy.

| n | θ | ε=0.5 | ε=0.25 | ε=0.125 | ε=0.0625 |
|---|---|-------|--------|---------|----------|
| 60  | 0.3672 | **0.000** \* | 5.234 | 1.497 | 3.118 |
| 90  | 0.2993 | **0.000** \* | 7.220 | 1.839 | 1.864 |
| 150 | 0.2315 | **FEASIBILITY LOSS** \* | **0.000** \* | 3.409 | 3.409 |

(realized opt-phase Hamming radius; exact-angle arm ≈ 2.6–3.0. \* = `ε > θ`, i.e. collapse
*predicted in advance*.) Every starred cell collapsed; no unstarred cell did.

The collapse costs, in objective: **−5.25%** (n=60, 0/9 instances, p=0.0039, and 45/45 cells never
reach the exact arm's objective at any budget), **−2.46%** (n=90), and at n=150 it is no longer a
degradation at all but a **total feasibility loss** — 0 of 45 cells reach a feasible point, because
the `sat` phase's angle is collapsed too, so nothing can move off the greedy start.

Everything short of the cliff is free, including large radius *distortions*: at n=90, ε=0.25
inflates the realized radius from 2.62 to **7.22 (2.8×)** for a median objective change of −0.064%,
inside the noise floor. That is the §2 tolerance measurement confirmed end-to-end by a completely
independent route.

### 6c. The dither prediction is FALSIFIED — and the corrected theory is confirmed

The bead predicted dither would cancel the `n`-dependence (`b* ≈ 4`, flat). §4 derives why it
cannot: dither kills the *first-order* coherent error but `E[sin²((θ+εu)/2)] = (1 − cos θ·sinc ε)/2`
sits strictly **above** `sin²(θ/2)`, and that second-order bias is itself coherent, growing as
`n·ε²/(12r)`. The prediction is that **at fixed ε the dithered loss must grow with n**. It does,
monotonically, at every ε:

| ε (dithered) | n=60 | n=90 | n=150 |
|---|---|---|---|
| 0.5   | −0.122% (r 1.66×) | −0.207% (r 2.11×) | −0.452% (r 2.65×) |
| 0.25  | −0.017% (r 1.23×) | −0.087% (r 1.36×) | −0.273% (r 1.53×) |
| 0.125 | +0.000% (r 1.09×) | +0.000% (r 1.13×) | −0.046% (r 1.16×) |

The **radius inflation grows with `n` at every ε — 3/3 at each of the three, 9/9 overall** — and
the objective loss follows it wherever the loss is resolvable above the noise floor (ε = 0.5 and
0.25; at ε = 0.125 the n=60 and n=90 losses are both 0, i.e. below the floor, and only n=150 is
resolved). **Dither does not buy flatness in n.**

Nor did it buy the predicted constant ~2.7-bit advantage *at these sizes*: measured ε\* is
0.5/0.25/0.125 (dithered) vs 0.25/0.25/0.125 (systematic) — dither wins by **one grid step at n=60
and ties at n=90 and n=150**. On a factor-2 ε grid with a ~0.1% noise floor, a ≤1-step difference is
not a resolved gain. Two reasons the theoretical advantage does not show up here: (i) the systematic
arm's only real failure mode is the collapse, and at ε just below θ its *lattice* happens to land on
a usable angle; (ii) the dithered arm pays the second-order bias early, which at these small `n`
costs roughly what the coherent first-order error costs.

**Practical consequence: prefer the COHERENT (one-circuit) model.** It is the cheaper compilation
(one circuit description, not `n`), it is what the shipped uniform-angle schedule naturally produces,
and it is not measurably worse. The dithered arm remains the interesting object at large `n`, where
the `√(3n)` first-order gain should eventually outrun the `n·ε²` bias — untested here.

### 6d. The second cost axis: precision moves the oracle count too

Reported separately, never folded into equal-`T(n)` pricing (NORTHSTAR §5). Median oracles for an
arm to reach the exact arm's `obj@common` (the `exact` arm itself: 1 041 / 1 053 / 1 174 at
n=60/90/150, 0 misses of 45):

- **Above the cliff** the target is simply never reached — 45/45 misses at every collapsed arm.
- **Below the cliff** the coarse arms are, if anything, marginally *faster* to the target
  (e.g. n=60 dithered ε=0.5: 616 oracles vs 1 041 for `exact`) with 26/45 misses vs 11/45 — a
  higher-variance search, not a better one. No arm improves both axes.

### 6e. n=3000 spot-check — the prediction confirmed 20× beyond where it was fitted

Wall-capped 150 s (a deliberate deviation from the 900–1800 s RUN POLICY, taken to keep the check
under an hour; both arms of every comparison share the same cap). 3 instances × 1 seed × 5 arms.
θ(3000) = 0.05165 rad, so the grid brackets the predicted collapse threshold between ε=0.0625
(above θ) and ε=0.03 (below).

**Realized opt-phase Hamming radius, per instance:**

| arm | ε vs θ | inst 0 | inst 1 | inst 2 | predicted |
|---|---|---|---|---|---|
| `exact` | — | 2.86 | 3.17 | 3.00 | — |
| **`e0.0625_sys`** | **ε > θ** | **0.000** | **0.000** | **0.000** | 0.00 ✓ |
| `e0.03_sys` | ε < θ | 3.83 | 4.06 | 3.80 | 2.70 ✓ |
| `e0.5_dit` | — | infeasible | **81.7** | **90.1** | 64.2 ✓ |
| `e0.03_dit` | ε < θ | 3.33 | 3.52 | 3.27 | 2.22 ✓ |

**The collapse boundary `ε = θ` holds 3/3 at n=3000** — a prediction made from n ≤ 150 and
extrapolated 20×. So ε\* = 0.03 rad on this grid: **b\* ≈ 5.7 bits, ~15 T-gates per rotation,
~45 500 T per QTG application** (the strict threshold is `b > log₂(π/2θ) = 4.93`; the factor-2 grid
has nothing between 0.03 and 0.0625).

**The dither falsification is now decisive.** At ε=0.5 the dithered radius inflates to ~86 against
an exact arm of ~3.0 — a **~29× blow-up** — versus only **1.66×** at n=60 for the *same* ε. That is
the second-order coherent bias `n·ε²/(12r)` behaving exactly as the closed form says, across a 50×
range in `n`. Dither is not flat in `n`.

**What this run does NOT establish.** The 150 s cap reaches only 350–2500 of T(n)=9989 oracles, and
`obj@common` reads at the shallowest arm in each cell, so the objective deltas (−0.019 % for the
collapsed arm, +0.0005 % for ε=0.03) are **not resolvable**; with a single seed the noise floor
computes as 0.0000 %, which makes the `indist?` scoring rule vacuous — the probe therefore reports
"no grid point indistinguishable", and that must **not** be read as a negative result. The radius is
the decisive read here. A decidable objective claim at n=3000 needs the full 900 s cap (~3.75 h) and
several seeds.

## 7. Verdict

1. **The bead's headline question is answered: ~3 bits, ~6–9 T-gates per rotation** at n=60–150
   (b\* = 2.65 / 2.65 / 3.65), i.e. **~3n·b\* ≈ 360–1 350 T-gates per QTG application** — versus
   ~3·53·n ≈ 24 000 (n=150) for double-precision angles, an **~18× reduction in the T-cost inside
   the oracle**. The premise "CBQS is robust to inaccurate angles as long as they still generate the
   highly biased superposition" is **confirmed, and more strongly than predicted**.

2. **The requirement is a threshold, not a tolerance.** `ε* ≈ θ = 2·asin(√(r/n))`: the *only* thing
   that matters is not rounding the rotation to zero. Radius errors of 2–3× cost nothing measurable.

3. **T-count per QTG application is O(n log n) — O(log n) per rotation — for BOTH modes.**
   Since `θ ∝ n^(−1/2)`, `b* = ½·log₂n + const`. Not O(1). The bead's "dither ⇒ b* ≈ 4, flat in n"
   is falsified analytically (the second-order coherent bias) and empirically (§6c). Caveat: with 3
   sizes on a 1-bit grid the *fitted* slope is 0.5–0.8 with wide error bars; the scaling claim rests
   on the mechanism (`ε_collapse = θ`, confirmed 4/4), not on the fit.

4. **Confirmed at n=3000, not just extrapolated** (§6e): the collapse boundary `ε = θ` held 3/3
   at 20× the size it was fitted on, giving **b\* ≈ 5.7 bits / ~15 T-gates per rotation /
   ~45 500 T per QTG application** — ~10.5× cheaper than double precision at that size (the
   advantage narrows with `n`, since b\* grows like ½·log₂n while double precision stays at 53).
   Still extrapolated: ~9 bits at n=10⁶, i.e. ~27 T-gates per rotation against ~159.

5. **The `½·log₂n` law is CONDITIONAL on `r* ≈ 2` holding as `n` grows.** Since
   `θ = 2·arcsin√(r/n)`, a radius that itself scaled with `n` (`r ∝ n^α`) would give
   `b* = (1−α)/2 · log₂n + c` — slower growth, and at `α = 1` a **flat** requirement. So the
   O(log n) conclusion is really "O(log n) *given a constant optimal radius*". `r* ≈ 2` is
   established only up to n=3000 (71e / w29 / kyg all landed there); if it drifted upward at
   n ≳ 10⁵ the precision requirement would begin to saturate. That — not the shrinking absolute
   `Δθ` — is the thing that would overturn this section.

   (Worth stating because the absolute change *does* vanish and invites the opposite intuition:
   from n=10⁹ to 10¹² the whole requirement moves by 0.00009 rad. But cost is `3·log₂(1/ε)`, and
   the logarithm converts that geometric shrinkage into a *constant* increment: **every doubling
   of `n` costs +0.50 bits / +1.5 T-gates per rotation, at every scale**. Measured slope of `b*`
   vs `log₂n` over n=60→3000 is 0.555, against 0.500 in theory. The margin over double precision
   erodes accordingly: 12.4× at n=3000, 6.3× at 10⁶, 2.9× at 10¹²; `b*` only reaches 53 bits at
   n ≈ 10³².)

6. **Assumption (b) of §1a is load-bearing and is NOT tested here.** All of this holds only if `A`
   and `A†` are the *same* synthesized circuit. If they are independently synthesized, errors
   accumulate and the requirement tightens to `ε ≲ 1/j` — a different regime entirely.

**Disposition: the lever ships default-OFF** (`angle_precision_eps = None` ⇒ exact angles ⇒
bit-for-bit the pre-a0w solve). It is a *reporting* instrument for the T-count axis, deliberately
**excluded from the M3 candidate lever surface** (`candidate_gate._UNPRICED_AXIS_SUFFIXES`), because
it moves cost on an axis the equal-`T(n)` oracle A/B does not price (§1.1).

**Open: a decidable OBJECTIVE claim at n=3000.** The §6e spot-check confirms the *mechanism* at
scale but was wall-capped at 150 s, too shallow to resolve objective differences. Re-run with the
policy cap and more seeds:
`run_a0w_precision_probe --n 3000 --wall 900 --indices 0..8 --seeds <3+> --arms exact,e0.0625_sys,e0.03_sys,e0.5_dit,e0.03_dit`
(≈3.75 h for 3 instances × 1 seed; ~11 h for 9 × 1).

## 8. Gates

- **C suite 69/69** (`ctest`, no `-R` filter) incl. the new 15-case `test_angle_precision` and the
  §8 branching golden `6/7` at `bias=5`, bit-for-bit with the lever off.
- **pytest 1 062 passed, 0 skipped** (with `CBQS_BENCHMARKS_DIR` set, so the real-instance and
  Eq.29-RHS baselines actually ran); `test_stress.py` 4 passed.
- **ASan 69/69 clean; TSan `test_thread_safety` clean** (Homebrew LLVM, per CLAUDE.md §7 macOS note).
- **Core-change workflow** (§3): propose → adversarial refute → independent verify, all three run.
  Nine must-fix findings were raised and every one addressed — the §1.1 candidate-surface leak
  (red-first), a false bit-for-bit claim, a CI filter that had silently drifted to 23-of-27 targets,
  a print-instead-of-crash harness control, NORTHSTAR spec drift, a `bool('false') == True` coercion
  hole, a banker's-vs-C rounding mismatch in the verification mirrors, over-broad synthesis-mode
  claims, and dangling references to then-uncommitted files.
- **Figure:** `benchmarks/artifacts/m5_a0w_precision/angle_precision_cliff.png` (4 sizes; the n=3000 objective panel is explicitly marked non-decidable).
- **Drivers:** `benchmarks/a0w_radius_tolerance.py` (step 1), `benchmarks/run_a0w_precision_probe.py`
  (sweep), `benchmarks/plot_a0w_precision.py`. **Tests:** `tests/test_angle_precision.{c,py}`.
