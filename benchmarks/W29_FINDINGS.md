# bd w29 — continuous oracle-indexed opt-radius DECAY lever: BUILT + settled WON'T-DO by direct measurement

**Bead:** `constraint-oriented-biased-quantum-search-w29` (M5 / 71e). **Date:** 2026-06-30.
**Verdict:** the within-opt-phase decaying radius does **NOT** beat the best CONSTANT opt radius
(`r*≈2`). Confirmed **by DIRECT MEASUREMENT** of the real lever (not the 71e config-only proxy).
The lever code is **KEPT, default-OFF (inert)** for a possible future M5 Phase-2 reuse; ship `r*≈2`
via the existing static `opt_branching_radius`.

## 1. Question

bd 71e (M5 oracle-indexed opt-radius schedule) was closed WON'T-DO on **proxy inference** (a static
radius sweep + a one-step broad→tight switch-placement proxy — the phase machine cannot express a
*within-opt continuous* decay config-only). w29 re-opened it (user-directed) to settle it **by direct
measurement**: build the real continuous decay lever and measure whether a radius that tightens
*continuously with convergence* inside the opt phase beats the best constant opt radius `r*≈2`.

## 2. What was built (faithful; default-OFF)

A **between-round classical write** of the opt-phase state-prep angle. The inner sampler
(`Branching.h` / `quantum_search.c` / `approximate_state_sampler.c`) is **byte-unchanged** —
`BranchingFunction` still only READS `stats->bias`.

- `solver_ctx.{h,c}`: per-worker `opt_radius_schedule_t {enabled,r_start,r_end,gamma}` + a PURE
  evaluator `opt_radius_schedule_eval(s,ratio) = r_end + (r_start-r_end)*(1-clamp(ratio))^gamma`,
  with an **exact early-return** `r_start` when `r_start==r_end` (bit-for-bit constant degeneracy).
- `SearchLib.c`: hook at the TOP of the `ctg` between-round loop, BEFORE the `2j+1` charge, gated
  `enabled && stage==3`: `ratio = total_oracles/mod->M` (T(n)-normalized, mirrors
  `opt_switch_oracles`; the per-call per-worker accumulator, NOT the racy shared counter), writes
  `ctx->branching_stats_opt.bias = n/r - 2`. Radius held CONSTANT through the round's Grover iters.
- Propagated via the existing `_propagate_phase_params` route; Python params
  `opt_radius_schedule_{r_start,r_end,gamma}` (validated `>0`), armed iff both endpoints set.

**Gates (commit `a612204`):** C suite 68/68 (8 new w29 cases incl. ctg bit-for-bit negative control +
liveness) + branching golden 6/7; Python 974 (incl. `test_opt_radius_schedule.py` 26: validation,
bit-for-bit neg control, single-worker determinism, scheduled-lever scale-invariance n∈{100,1000});
ASan 68/68 clean; TSan thread_safety clean; core-change 3+1 panel (all code invariants OK); CORE-CHANGE
CAPSTONE warm default-vs-default strict_xcheck `overall_pass=True` (lever-OFF path byte-identical,
frozen anchors undisturbed).

## 3. PREREQUISITE — §5 oracle-axis nondeterminism audit (w29.3, PASS)

`benchmarks/run_w29_noise_audit.py`, n=1000, 4 workers, wall=60s:
- **(1) single-worker + decay armed: bit-for-bit deterministic** (identical 51-entry history).
- **(2) multi-worker wall-cap noise floor: max 0.0038%** of objective (median 0%) — ~10× below the
  71e static-radius edge (~0.04–0.05%).
- **(3) neg==static under the race: max |Δ| = 0.0** — `obj@common` reads at the matched min-oracle
  depth, which cancels the wall-truncation timing. **The obj@common axis is decidable.**

The multi-worker oracle-axis nondeterminism the 71e probes saw is the **wall-cap truncating each
worker at a timing-dependent round** (RUN POLICY's accepted machine-dependence), NOT the lever — the
hook adds no shared write (only the per-worker `ctx->branching_stats_opt.bias`).

## 4. DECISION via faithful small-n direct measurement (w29.4)

User-directed: test small problems (n ≤ 90) *first*, before the ~34h n=3000 run. **Faithful mode**
(`run_w29_decay_probe --budget-mult`): terminate on the oracle budget `M = mult·T(n)`, **no wall cap**
→ fast *and* reproducible (no wall-truncation noise). Arms share `opt_sat_radius=8` + an early switch,
so the ONLY difference is the opt-phase radius trajectory. `obj@common` best-of-portfolio (4 workers),
median-over-seeds Δ vs `A_r2` (constant `r*=2`), 9 instances × 3 seeds.

**Δ vs constant `r*=2` (negative = decay WORSE); `neg_r2` is the schedule-degenerate harness check:**

| setting        | neg vs A | D_4to2  | D_8to2   | D_8to2_steep |
|----------------|----------|---------|----------|--------------|
| n=30, 1×T(n)   | 0        | +0      | +0       | +0 (saturated) |
| n=60, 1×T(n)   | 0        | +0      | −3,810   | −6,487       |
| n=90, 1×T(n)   | 0        | −2,586  | −10,522  | −3,317       |
| n=90, 4×T(n)   | 0        | −4,832  | −41,472  | −16,507      |

- **`neg_r2 == A_r2` exactly (Δ=0) at every setting** — the schedule-degenerate arm reproduces the
  constant arm bit-for-bit at obj@common, even multi-worker. Harness sound.
- **No decay arm beats the constant at any n; none seed-robust-positive.** n=30 is saturated (the
  `T(n)=(n/32)²+1200` floor makes the budget ~1208 across small n; the warm start + tight constant
  already converge).
- **The decay loses harder with both problem size and opt-phase headroom.** The broad-early `D_8to2`
  degrades monotonically: −3.8K (n=60) → −10.5K (n=90,1×) → −41.5K (n=90,4×). This **closes the
  "small-n headroom too thin" loophole in the opposite direction**: *more* opt room makes the
  broad-early radius waste *more* oracles wandering instead of refining.

**Headroom probe `mult=8` aborted — O(n·j²) blowup (the "0o8 wall"):** at `M=8·T(90)≈9664` with
`opt_sample_cap=0`, a converged search sits in stuck rounds drawing an exponentially growing Grover
count `j` (up to ~remaining/2 ≈ 4800); one round then simulates `4j²≈90M` candidates × n ≈ billions of
ops (56 min, ~2/9 instances). The faithful no-wall mode has nothing to cap giant rounds — the n=3000
RUN POLICY avoids this via the wall cap (which interrupts a runaway round). `mult=4` was just under the
cliff and already answered the headroom question, so `mult=8` was redundant and killed.

## 5. Verdict

**Three independent lines now agree the decay does NOT beat the best constant `r*≈2`:** (a) 71e static
sweep (tight constant is the interior optimum); (b) 71e schedule proxy (broad→tight decisively worse,
−29.8M, 9/9); (c) **w29 small-n direct measurement of the real lever** (worse across sizes + headroom,
worsening monotonically). The faithful small-n direct measurement (~6 min) settles it; the ~34h
wall-capped n=3000 confirmation was **deliberately skipped** (user decision) — the trend (worse with
more headroom/size) predicts an even larger negative there.

**Disposition (user decision):** **WON'T-DO** for the decay-vs-constant question, **by direct
measurement** (not just proxy). The lever code is **KEPT, default-OFF (inert, byte-identical when
disabled)** as faithful between-round scheduling infra a future M5 Phase-2 could reuse. **Ship `r*≈2`
via the existing static `opt_branching_radius` lever** (the free win 71e already identified).

## 6. Method lessons

- **Faithful (oracle-budget, no-wall) small-n is the cheap, reproducible discriminator.** It removes the
  wall-truncation noise floor entirely (`neg==A` exactly), so a clean obj@common read costs minutes, not
  the ~34h a wall-capped n=3000 A/B needs. Test small + faithful before paying for large + wall-capped.
- **More headroom is the right loophole check, not more size.** `T(n)` is ~flat at small n (the +1200
  floor), so a size sweep alone doesn't grow opt-phase room — vary the budget multiple to test
  headroom-gating directly.
- **Faithful large-budget at small n hits the O(n·j²) Grover-sim wall** (`mult≳8`). Use `opt_sample_cap`
  or a wall cap if a large-budget faithful probe is ever needed; the n=3000 RUN POLICY already wall-caps.

## 7. Follow-up — the OPPOSITE direction: GROW tight→broad (refine-then-explore)

User hypothesis (after the decay null): with a warm start, a TIGHT radius early refines the
near-optimal warm solution, then BROADENING late escapes local optima — the inverse of the falsified
"explore-then-exploit" decay. Target endpoint = the M4 winner cand_16's opt radius r=4.41 (NB θ-coupled:
cand_16 = `r_opt=4.41 + θ=z(p_ii)·0.288`; the *bare*-radius 71e optimum is r≈2). `run_w29_grow_probe.py`,
faithful (M=T(n), no wall), n∈{60,90}, 9 instances × 3 seeds. Arms share opt_sat=8 + cand_16's early
switch; radius-only (θ off) AND cand_16-regime (θ on). `neg_2to2 == C_r2` Δ=0 everywhere (harness exact).

**Constant sweep resolves the 2-vs-4.41 tension — r≈2 is robustly the best constant:**

| vs C_r2 | C_r4.41 | C_r6 |
|---------|---------|------|
| n=60    | −4,753 (p=0.88) | −7,552 (p=0.72) |
| n=90    | −11,185 (p=1.0) | −23,901 (p=1.0) |

So cand_16's 4.41 is **not** a better bare radius (it was θ-coupled); constant r=2 beats it at n=60/90
(consistent with 71e's n=3000 r\*≈2). A 1-instance smoke fluke had suggested 4.41 > 2; the 9×3 sweep
overturns it.

**Growing tight→broad does NOT beat the best constant r=2** (the decisive test, `G_2to4.41 vs C_r2` at
n=90): Δ=0, +4/−4, **p=0.68**, not seed-robust. n=60 likewise null/negative.

**The apparent positives are artifacts of r=4.41 being a suboptimal constant**, NOT schedule wins:
`G_2to4.41 vs C_r4.41` = +10,323 (p=0.014) and `K_grow2to4.41 vs K_const4.41` (cand_16 regime, θ on) =
+6,305 (p=0.027) — but these beat only the *inferior* r=4.41 constant, because the growing path spends
its early oracles at the *better* tight radius. That re-confirms "tighter is better," not "schedule
helps." Neither clears Holm (family of 3; smallest p=0.027 > 0.05/3) nor is seed-robust (3/9 all-pos).

**Conclusion: the best constant r≈2 dominates BOTH schedule directions** — decay (broad→tight) lost and
worsened with headroom; grow (tight→broad) is null vs the best constant. The static-radius lever is the
right answer, now confirmed against both monotone schedule directions by direct measurement. (Driver:
`run_w29_grow_probe.py`; artifacts `benchmarks/artifacts/m5_w29_grow/`.)

### 7a. "But cand_16 was the best — wouldn't beating it beat all?" — decomposition (n=90)

A natural objection: cand_16 was the M4 winner, the bare best constant couldn't beat it, and
`K_grow2to4.41` beats cand_16 (+6,305) — so isn't the growing schedule the new best? Resolved by adding
the missing arm `C_r2_theta` (cand_16's exact θ=z(p_ii)·0.288 at the *bare-optimal* radius r=2):

| n=90, median Δ vs bare C_r2 | Δ | split |
|-----------------------------|------|-------|
| C_r2_theta (const r=2 + θ)  | +0     | 4+/4− |
| K_grow2to4.41 (θ + grow 2→4.41) | +2,950 | 5+/4− |
| K_const4.41 (cand_16)       | −6,390 | 3+/5− |
| C_r4.41                     | −11,185 | 1+/8− |
| C_r6                        | −23,901 | 0+/9− |

### 7b. Direct n=3000 test (user-requested): grow + θ@r=2 at scale — instance-0 tease did NOT replicate

The small-n decomposition left one thread open: does θ at the right radius (r=2), or the grow schedule,
help *at n=3000* (cand_16's home turf)? Tested directly, wall-capped 900 s (the proven 71e regime;
5-min was too short — a 20 s smoke reached only 76 oracles / 1 % of T(n), still infeasible).
`run_w29_grow_probe --n 3000 --wall 900`, 9 instances × 1 seed, 4 arms (bare r=2, r=2+θ, cand_16
r=4.41+θ, GROW r=2→4.41+θ). **All 9 instances feasible.**

**Instance 0 teased a win** (obj@common Δ vs bare r=2): GROW **+3.94M**, θ@r=2 +0.29M, cand_16 −4.78M —
so GROW looked like the best arm and θ looked scale-dependent. **The other 8 instances did NOT
replicate it** (obj@common, 9 instances):

| comparison | median Δ | sign | p (Wilcoxon) |
|---|---|---|---|
| θ@r=2 vs bare r=2 | −490,939 | 4+/5− | 0.50 |
| **GROW vs bare r=2** (decisive) | −679,486 | 4+/5− | 0.46 |
| GROW vs const r=2+θ | +21,437 | 5+/4− | 0.54 |
| cand_16 (r=4.41) vs bare r=2 | −3,650,317 | 1+/8− | 0.998 |
| GROW vs cand_16 | +2,915,149 | 9+/0− | 0.002 |

- **θ@r=2 is null at n=3000** (median −491K, 4/5) — the instance-0 +1.16M was a favorable draw; θ does
  NOT robustly help at scale either. The last residual thread is closed.
- **GROW does NOT beat the bare best constant r=2** (median −679K, 4/5, p=0.46). Per-instance GROW-vs-r=2:
  +3.94, −1.06, −0.68, −1.29, +1.66, −1.98, +0.36, +2.14, −0.74 (M). By **mean** grow/θ look marginally
  positive (+261K/+240K) but that is skewed by 2 instances (0, 7); the robust **median/sign** test says no.
- **GROW adds nothing over constant r=2+θ** (+21K, 5/4) — the schedule ≈ the constant, as at small-n.
- **cand_16 (r=4.41) robustly loses to r=2** (8/9) and **GROW beats cand_16 9/9** — the same artifact:
  growing from 2 beats sitting at the inferior 4.41 because it passes through the better tight radius.

**Verdict (n=3000, direct): the best constant r≈2 is the ceiling at scale too; neither the grow schedule
nor θ@r=2 robustly beats it, and the schedule adds nothing over the constant.** The single-instance feel
was misleading — a textbook case for why the multi-instance run was needed. Figures:
`obj_over_oracles_w29_3000_0.png` (instance 0) and `..._grid.png` (all 9). w29 WON'T-DO stands, now
confirmed by direct measurement at n=3000 as well as faithful small-n.

---

Decisive: `K_grow2to4.41 vs C_r2_theta` = **+0 (4+/4−)** — the growing *schedule* TIES the *constant*
r=2 + θ; and `C_r2_theta vs C_r2` = +0 (θ near-null at r=2, matching M2f). **The premise was wrong:
cand_16 is NOT the ceiling — bare r=2 beats it (−6,390)**, because 4.41 is too broad. `K_grow` beats
cand_16 only because growing from 2 spends its early oracles at the better tight radius; it *recovers*
cand_16's deficit and lands at ≈r=2, the schedule adding nothing beyond "be near r=2." Everything
collapses to: **the cluster {bare r=2, r=2+θ, K_grow} is statistically tied at the top** (broad configs
clearly below) → **constant r≈2 is the ceiling and no schedule exceeds it.** (At n=60 θ even slightly
hurts — C_r2_theta −3,557 vs bare r=2.) Residual open thread, distinct from w29's radius schedule:
whether **θ at the right radius (r=2)** helps *at n=3000* (neutral at n≤90) — that is the Phase-2 θ
lever (bd 8an.6), a constant, not a schedule.

**Drivers:** `benchmarks/run_w29_decay_probe.py` (decay A/B; `--budget-mult` faithful mode for small-n),
`benchmarks/run_w29_grow_probe.py` (grow direction + constant sweep), `benchmarks/run_w29_noise_audit.py`
(§5 prerequisite). **Tests:** `tests/test_opt_radius_schedule.{c,py}`.
