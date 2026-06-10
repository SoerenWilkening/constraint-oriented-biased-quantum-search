# M2 — Hypothesis check (no learning): findings

*(bd 8an.3, closed 2026-06-10. NORTHSTAR §4/§12 M2. All measurements: real Eq.29
anchored strata n=10–100, 90 instances × 7 matched master seeds, equal `T(n)`
oracle budget per worker (`M=-1`), exact sampler (`opt_sample_cap=0`), scored by
the M1 §6/§8 metric against the frozen anchors @ `3c6ba1c`. Frozen tables:
`decision_touch_default.csv`, `m2d_radius_verdicts.csv`, `m2f_theta_verdicts.csv`.
Run-sets regenerable via `python -m benchmarks.m2`; default side strict-xcheck-guarded.)*

## Exit criteria (§12 M2) — both met

1. **A hand-designed schedule moves the metric** — overwhelmingly, in both
   directions: W swings from **+55 (max possible)** to **−55 (min possible)**
   per stratum across the schedule family.
2. **Each lever's real leverage is known** — the table below.

## Decision-touch instrumentation (M2a/M2b)

Fraction of variable decisions where `BranchingFunction` is actually consulted
(vs feasibility-forced), per phase (counters: bd 8an.3.1; measurement frozen in
`decision_touch_default.csv`):

| phase | touch fraction | trend |
|---|---|---|
| `opt` | 0.69 (n=10) → 0.83 (20) → 0.89 (30) → **0.90–0.94 (40–100)** | grows with n |
| `opt_sat` | 0.33–0.60 (free + both-infeasible both consulted) | declines with n |
| `sat` | — (0 decisions) | never runs under OPTIMIZE |

The bias lever's *surface* is large at target-relevant sizes. **But see M2f:
touched ≠ steered** — a large surface does not guarantee a static separable
prior can exploit it.

## Lever leverage (M2d/e/f)

| lever | leverage | evidence |
|---|---|---|
| **`opt_switch_oracles`** (exploit→explore switch) | **DOMINANT.** Same radii: switch=0 → W=+55 at n=10/20/50 (+53/+45/+32 elsewhere, median PI 0.123 vs 0.351 at n=100); switch=0.25·M → W=−55 at n=10–50. Earlier explore is better at every size measured; the default 0.1·M is left of optimal. | `m2d_radius_verdicts.csv` (`radius_g2e_early` vs `radius_g2e_late`) |
| **scalar radius `r` (per phase)** | **Material, size-dependent.** Uniform r=6 → W=+55 at n=10 (the small-n compression regime), mixed→negative at large n. `opt_sat` r=2 harms hard-feasibility instances regardless of everything else (instance 40_6: δPI≈+0.27 in *every* r=2 schedule; byte-identical across switch settings because feasibility arrives after both thresholds). | `m2d_radius_verdicts.csv` |
| **`variable_order`** | **INADMISSIBLE — P1 bug `h8d`.** Apparent §6.6 domination (W=+55 max at n=10–70, zero regressions, median PI *negative* = "beating" classical B_I by up to +83%) is an infeasibility artifact: the look-ahead keys clause-closure on the *natural* index while traversal uses `var_order`, so the solver accepts `eval_constraints`-violating solutions (`verified=False` on every solve). Quarantined: `run_sets/order_pii_desc.INVALID`. Re-measure after `h8d`; blocks M3 from searching this lever. | live repro in `h8d`; quarantine README |
| **per-variable θ (sigmoid logit channel)** | **Near-null at \|θ\|≤0.5 on z(p_ii), opt-phase.** Both signs: W ∈ [−10, +10], mostly ties-within-margin. Realized radius ratio vs default 0.97–1.08 (≤8 % drift at n=100) — the M0f decoupling claim holds (no `factor_sum` catastrophe). | `m2f_theta_verdicts.csv` |

**Negative control (§1.3):** uniform r=2 (near-greedy) loses on PI at scale
(W=−24…−2 at n≥40) *and* trips the §8.3 floor at n=20/50/60 — including
vetoing its own n=20 PI win. The anti-greedy defense works as designed.

## Per-variable claim: kept, de-prioritized (the §4 decision)

The §4 down-scope trigger ("if the touch fraction is small") did **not** fire —
the surface is large. But M2f shows a *static separable* θ at modest amplitude
barely moves PI. Decision: **keep the per-variable channel in M3 as a secondary
search dimension** (amplitude, feature choice, and phase-targeting are
searchable); the **primary M3 search space is (per-phase radius r(n),
`opt_switch_oracles`)**, where hand-tuning already finds +55-class wins.

## Gate findings (for M3 design — must resolve before the loop optimizes against the gates)

1. **§8.3 floor vetoes uniformly-better candidates** (bd 8an.3.8, blocks 8an.4):
   `radius_g2e_early` dominates §6.6 yet fails the floor at *every* stratum —
   improving every worker collapses the best−median portfolio lift (e.g.
   (50,0): 26.6k vs default 65.4k). The floor currently reads "uniform
   improvement" as "greedy collapse". Options under review: tail-quality floor
   (best-of-P vs default best-of-P), OR-style pass, or keep+document.
2. **Verification is now load-bearing in the harness**: `result.verified` is
   persisted; `require_verified` fails loud in `run_sweep` *and*
   `load_run_set_dir`. This session it caught the `variable_order` corruption
   that a fully green gate + plausible-looking verdict had let through —
   the M1 lesson (capstone/xcheck) repeated one layer up.
3. **gate_B strictness**: `g2e_early` posts W=+55 strata yet fails gate_B at
   5/10 sizes because a *single* instance regresses beyond margin. Working as
   specified (§6.6 worst-regression), but M3's selection should expect
   most-instances-win/few-lose candidates to be common.

## Reproduce

```bash
export CBQS_BENCHMARKS_DIR=<CBQS-benchmarks clone>
python -m benchmarks.m2 run-default   --out-dir benchmarks/artifacts/run_sets/default
python -m benchmarks.m2 run-candidate --schedule radius_g2e_early --out-dir benchmarks/artifacts/run_sets/radius_g2e_early
python -m benchmarks.m2 verdict --candidate-dir benchmarks/artifacts/run_sets/radius_g2e_early \
                                --default-dir benchmarks/artifacts/run_sets/default
python -m benchmarks.m2 touch-report --run-dir benchmarks/artifacts/run_sets/default
```
