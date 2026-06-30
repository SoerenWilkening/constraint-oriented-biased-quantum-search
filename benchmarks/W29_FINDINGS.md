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

**Drivers:** `benchmarks/run_w29_decay_probe.py` (A/B; `--budget-mult` faithful mode for small-n),
`benchmarks/run_w29_noise_audit.py` (§5 prerequisite). **Tests:** `tests/test_opt_radius_schedule.{c,py}`.
