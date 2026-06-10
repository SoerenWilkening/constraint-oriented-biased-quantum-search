# M2 — Hypothesis check (no learning): findings

*(bd 8an.3, closed 2026-06-10. NORTHSTAR §4/§12 M2. All measurements: real Eq.29
anchored strata n=10–100, 90 instances × 7 matched master seeds, equal `T(n)`
oracle budget per worker (`M=-1`), exact sampler (`opt_sample_cap=0`), scored by
the M1 §6/§8 metric against the frozen anchors @ `3c6ba1c`. Frozen tables:
`decision_touch_default.csv`, `m2d_radius_verdicts.csv`, `m2e_order_verdicts.csv`,
`m2f_theta_verdicts.csv`.
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
| **`variable_order`** | **Material at small–mid n, with a catastrophic large-n feasibility cliff in BOTH directions** (fresh post-h8d equal-`T(n)` A/B, 2026-06-10 — the prior "domination" was the h8d infeasibility artifact; see below). `asc` (low p_ii first): gate_B passes at n=10–60, W=+54/+55/+54 at n=10/20/30 with *negative* worst regressions (uniform improvement), per-stratum (gate_B ∧ floor) wins at 10/20/30/40/60 — then collapses: never-feasible seeds appear at n≥70 and the n=100 stratum collapses TOTALLY (both anchored instances 7/7 seeds never-feasible → J=∅). `desc` (high p_ii first): weaker small-n wins (gate_B at 20/40/50), cliff starts at n=70 (70_0: 5/7; 80_2/3/9, 90_0/1/2/4/5 up to 7/7 never-feasible). Mechanism (probed, adversarially reviewed): NOT a residual closure bug — desc-order `CSearch_opt` from a feasible incumbent yields verified improvements; the cliff is the all-zeros-start `CSearch_opt_sat` *constructive sampler* dead-ending under hostile orders (`count[0]==0&&count[1]==0` on ~every sample, honest `feasible=False`). M3: order is a real secondary lever but must be searched under the feasibility tier's protection; its cost surface is instance- and size-discontinuous. | `m2e_order_verdicts.csv`; bd 8an.8 |
| *(`variable_order` history)* | **Pre-fix verdict was INADMISSIBLE — P1 bug `h8d`, FIXED 2026-06-10.** Apparent §6.6 domination (W=+55 max at n=10–70, median PI *negative*) was an infeasibility artifact: look-ahead keyed clause-closure on the *natural* index while traversal used `var_order` → `eval_constraints`-violating solutions accepted (`verified=False` everywhere). Fix: rank-keyed closure + position-space look-ahead recursion; identity bit-for-bit (capstone strict-xcheck exact). The quarantined `order_pii_desc.INVALID` run-set is superseded and deleted (bd 8an.8). | core-change workflow (h8d); `test_variable_order_feasibility.c` |
| **per-variable θ (sigmoid logit channel)** | **Near-null at \|θ\|≤0.5 on z(p_ii), opt-phase.** Both signs: W ∈ [−10, +10], mostly ties-within-margin. Realized radius ratio vs default 0.97–1.08 (≤8 % drift at n=100) — the M0f decoupling claim holds (no `factor_sum` catastrophe). | `m2f_theta_verdicts.csv` |

**Negative control (§1.3):** uniform r=2 (near-greedy) loses on PI at scale
(W=−24…−2 at n≥40) *and* fails the (amended, see below) §8.3 tail floor at
n=40/60/70/80/90 — every stratum where its harvested tail genuinely regresses
(worst-instance regression up to −2.5×spread at n=80). The anti-greedy defense
works as designed — and the amendment *strengthened* it here: the old spread
floor had been passing uniform2 at n=40/70/80/90.

## Per-variable claim: kept, de-prioritized (the §4 decision)

The §4 down-scope trigger ("if the touch fraction is small") did **not** fire —
the surface is large. But M2f shows a *static separable* θ at modest amplitude
barely moves PI. Decision: **keep the per-variable channel in M3 as a secondary
search dimension** (amplitude, feature choice, and phase-targeting are
searchable); the **primary M3 search space is (per-phase radius r(n),
`opt_switch_oracles`)**, where hand-tuning already finds +55-class wins.

## Gate findings (for M3 design — must resolve before the loop optimizes against the gates)

1. **§8.3 floor vetoes uniformly-better candidates** (bd 8an.3.8) — **RESOLVED
   2026-06-10 by the NORTHSTAR §8.3 amendment (tail-quality floor)**. The M2g
   design review found the spread floor wrong in *both* directions: it vetoed
   `radius_g2e_early` at n=20/100 where its final best-of-P did **not** regress
   (the issue's "uniform improvement read as greedy collapse"), yet **passed**
   the §1.3 negative control `radius_uniform2` at n=40/70/80/90 where its tail
   regression reached −2.5×spread — and it was gameable (sandbag one worker →
   manufactured best−median lift, no §6.6 cost). The dominance-escape variant
   (option b) was a dead letter: `median_c − best_d < 0` on every evaluable
   instance in every persisted run-set. Amendment: per instance, seed-matched,
   fail iff median-over-seeds (`best_c − best_d`) regresses beyond
   0.25·spread_obj(n) (zero band at default-converged sizes — n=10 becomes
   evaluable instead of skipped); default-vs-default passes structurally
   (Δ≡0, no calibration pin needed). Re-emitted verdicts: `g2e_early` floor
   now passes at 10/20/30/50/70/100 (vetoed only at 40/60/80/90 where its tail
   genuinely collapses, worst −5.2×spread at 60); per-stratum (gate_B ∧ floor)
   wins at n=10/20/30/50/100. `floor_calibration.csv` survives as a diversity
   diagnostic (no longer pins `EXPLORE_FLOOR_FRACTION`).
2. **Verification is now load-bearing in the harness**: `result.verified` is
   persisted; `require_verified` fails loud in `run_sweep` *and*
   `load_run_set_dir`. This session it caught the `variable_order` corruption
   that a fully green gate + plausible-looking verdict had let through —
   the M1 lesson (capstone/xcheck) repeated one layer up.
3. **gate_B strictness**: `g2e_early` posts W=+55 strata yet fails gate_B at
   5/10 sizes because a *single* instance regresses beyond margin. Working as
   specified (§6.6 worst-regression), but M3's selection should expect
   most-instances-win/few-lose candidates to be common.
4. **Honest never-feasible runs persist and score** (bd 8an.8): the
   `require_verified` guard now discriminates per result — fatal only on the
   corruption signature `feasible=True ∧ verified=False`, or on a
   `verified=False` record whose *scored surface* (history / feasible
   `final_incumbents`) carries feasible entries (impossible under correct
   operation; the metric scores those surfaces, not `result.feasible`).
   `feasible=False ∧ verified=False` with an empty scored surface is the
   honest failure-to-find-feasibility shape (`global_opt` = all-zeros init
   residue, flagged by the unconditional `verify_solution`); it flows to the
   §6 item-5 +∞ sentinel, §6.6 feasibility tier, and §8.3 −inf tail collapse.
   M3's loop WILL generate hostile candidates (the order cliff above) — this
   path is now tested end-to-end (`tests/test_m2.py`).

## Reproduce

```bash
export CBQS_BENCHMARKS_DIR=<CBQS-benchmarks clone>
python -m benchmarks.m2 run-default   --out-dir benchmarks/artifacts/run_sets/default
python -m benchmarks.m2 run-candidate --schedule radius_g2e_early --out-dir benchmarks/artifacts/run_sets/radius_g2e_early
python -m benchmarks.m2 verdict --candidate-dir benchmarks/artifacts/run_sets/radius_g2e_early \
                                --default-dir benchmarks/artifacts/run_sets/default
python -m benchmarks.m2 touch-report --run-dir benchmarks/artifacts/run_sets/default
```
