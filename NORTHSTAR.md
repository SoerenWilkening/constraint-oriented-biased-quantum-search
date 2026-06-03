# Northstar — Agent-Discovered Bias Schedules for Quantum-Faithful Constrained Search

> Status: **v3 (2026-06-03)** — after two adversarial review rounds. v1→v2 closed the metric/faithfulness
> design blockers; v2→v3 fixes metric-spec precision (aggregation, anchor noise, over-frontier bound,
> feasibility composition), the per-variable-channel reparameterization, the radius scale-law, and three
> M0 infrastructure corrections (oracle-budget accumulator, per-worker counter/incumbents, seed plumbing).
> Owner: Sören Wilkening. Replaces the missing `PRD.md` (CLAUDE.md updated). **One open dependency: the
> Eq.29 benchmark data + baselines are not in this repo — see §11/§14.**

## 1. Mission

An autonomous (Claude Code) agent discovers, from a **training set**, a **generalizable, size-aware,
multi-stage static-angle bias schedule** that improves the CBQS solver's **anytime** performance on the
quadratically-constrained class of arXiv:2512.08384, transferring to the larger real benchmark (n→3000).

CBQS is the **faithful classical stand-in** whose **oracle count is the quantum cost**. The advantage
claim is an **equal-oracle-budget A/B test** (baseline schedule vs. discovered schedule at the same
`T(n)`), never "free ⇒ advantage": biasing the angles *redistributes* `total_prob` (where the
amplitude-amplification budget lands), and the A/B test at fixed `T(n)` prices that redistribution. Every
lever (scalar-bias trajectory, `variable_order`, per-variable bias) is **priced by the A/B test** — none
is "waved through" as cost-free (see §5 on `variable_order`).

## 2. Greedy is a stage, not the enemy

Prior fixed ML (removed `19870df`) collapsed to greedy because it optimized `np.mean(objectives)` over
short repeats while deployment is **best-of-portfolio** (max over workers): the mean rewards low-variance
greedy and discards the heavy tail restarts harvest (Gomes–Selman, Luby). The lesson is not "avoid
greedy" — greedy reaches good feasible solutions fast (goal b). We forbid only **uniform** collapse. The
agent discovers a **schedule**: greedy/high-bias early (fast incumbent), exploratory/low-bias late
(best-at-budget + beat the classical frontier, goal a).

## 3. Target problem (arXiv:2512.08384, Eq. 29)

```
max   Σ_i Σ_{j≥i} p_ij · x_i x_j                      (quadratic objective)
s.t.  Σ_i Σ_{j≥i} w1_ij · x_i x_j ≤ c1                (quadratic "capacity",  ≤)
      Σ_i Σ_{j≥i} w2_ij · x_i x_j ≥ c2                (quadratic "covering",  ≥)
      x ∈ {0,1}^n
```

Binary; quadratic objective + two quadratic constraints (≤ and ≥). n = 10…3000, 10 instances/size.
Per-run oracle budget **T(n) = (n/4)² + 1200**. Baselines Gurobi / Hexaly / Simanneal; **no proven
optimum** (≥~50 % gap). The `≥ c2` covering constraint makes many constructions **infeasible** — a
first-class concern (§6 feasibility tier; feasibility-first switch).

## 4. The lever — a multi-stage static-angle schedule

A **piecewise (per-phase) schedule** of static angles — *not* a continuous trajectory; the solver has
three phases (`sat`/`opt_sat`/`opt`) with independent `branching_stats`, so a schedule is a small number
of static settings plus one learned switch point. All global and size-aware (one schedule, parameterized
by `n` and structural features), applied to every instance.

- **Primary knob — scalar bias, parameterized by target *radius*.** Expected flips from the incumbent =
  `n/(bias+2)`. To make the neighborhood **exactly scale-stable**, the schedule emits a **target radius
  `r` per stage** and the harness sets `bias = n/r − 2` (so radius = `r` at *every* n; `bias = n/d`
  alone is only ~`d` flips for n≫d and is compressed 38–56 % at small n — do not use it directly).
  Greedy stage = small `r`; exploratory stage = larger `r`.
- **Learned switch point.** Feasibility-first is hard-gated (existing `opt_sat→opt` feasibility
  transition). The exploit→explore switch *within* optimization is a **learned parameter**
  `opt_switch_oracles ∈ [0, α·T(n)]` (α small, e.g. ≤0.25), **in oracle units**, plumbed into `ctg` to
  replace the current hardcoded `counter>10` heuristic. The agent searches it; we don't hand-pick it,
  and we don't wait for convergence.
- **Refinement — `variable_order` + per-variable bias (phase-aware), both priced by the A/B test.**
  - `variable_order`: a size-aware ordering priority. **Not** a cost-free relabel (see §5) — priced.
  - **Per-variable bias is re-parameterized as an additive logit through a sigmoid:**
    `value = σ(logit(assignment_bias) + θ_i)`, where `θ_i = g(features)` is a **bounded** per-variable
    offset. This (a) keeps `value ∈ (0,1)` by construction, (b) **decouples** the per-variable channel
    from the scalar bias (the current convex blend shares `factor_sum`, so enabling raw `branching_weights`
    silently blows the radius from ~4 to ~n/2 at n=3000), and (c) recovers the baseline exactly at
    `θ_i = 0`. **This requires a small C edit to `BranchingFunction` (add the sigmoid + clamp)** — so,
    correcting v2: only the **scalar-bias schedule and `variable_order` are pure runtime data**; the
    per-variable logit channel needs that one-time C change before it is usable (it is *not* per-candidate
    recompilation — the function form is fixed once; the agent then only sets data).

**Phase-1 expressiveness is a hypothesis, not a given.** A static per-variable bias is a *separable*
(product-state) prior — it cannot represent the pairwise `p_ij` terms, and in `opt` it is consulted only
where the look-ahead leaves both values feasible (`solver.c:353-359`); in `opt_sat` it is also consulted
on both-infeasible choices (`solver.c:481`). **M2 instruments the fraction of decisions the bias touches,
split by phase and by both-feasible/both-infeasible, across sizes.** If small, we down-scope the
per-variable claim and lean on the scalar-bias radius schedule and `variable_order`. Interaction-aware
bias is **Phase 2** (dynamic/marginal, conditional rotations), **charged its extra oracle cost**.

## 5. Quantum-faithfulness invariant (non-negotiable)

Admissible **iff** the QTG can implement the bias within the oracle-cost model, **priced by the equal-
`T(n)` A/B test**. Static per-qubit angles add zero *gate* cost; the `2j+1` oracle charge is
bias-independent, so biasing only redistributes the budget — the A/B test measures the redistribution.

- **`variable_order` is a priced search lever, not a free relabel.** The feasibility look-ahead keys
  clause-closure on the *natural* variable index while traversal uses `var_order`, so reordering changes
  the realized feasible set / forced-vs-free classification / `total_prob`. **Confirmed by the author:
  variable ordering genuinely affects performance** — so it is a first-class static lever whose gain is
  *priced by the equal-`T(n)` A/B test* (never assumed neutral). The QTG prepares qubits in the chosen
  order at the same per-round oracle cost; (optional, later) making the look-ahead *prefix-consistent*
  with `var_order` would give cleaner permutation semantics.
- **Feature rule (Decision C):** Phase-1 angle-setting features = exactly **{`p_ii`, objective &
  constraint row-sums, raw interaction-graph degree, nnz counts}** — each a single O(nnz) pass.
  **Banned in Phase 1:** LP/SDP/optimization-derived features *and* any iterative/spectral graph
  statistic (eigenvector/PageRank/k-core/betweenness). They would smuggle uncharged classical
  optimization into a comparison against classical solvers. (Revisit later only with a mandatory ablation
  proving the QTG, not the precompute, earns the win.) The O(n log n) argsort for `variable_order` is
  disclosed bounded preprocessing.

## 6. Objective / fitness

**Anytime quality, tail-aware, frontier-relative — a hardened primal-gap integral.** *Computable only
under the §11 oracle-budget fix; portfolio cost convention = each worker capped at `T(n)`, scored on the
best-of-portfolio running-max trajectory.* Per instance `I`:

1. **Anchors (frozen, robust — not single draws).** `L_I` and the default schedule's `PI` are frozen as
   the **median over a fixed bank of default seeds** and stored in the reference table (§11). `L_I` =
   default's median first-feasible objective (re-anchored to a trivial-feasible lower bound if needed).
   `B_I` = best-known **feasible** objective = max over the **non-CBQS** references {Gurobi, Hexaly,
   Simanneal} (CBQS-default excluded — matching the default is neutral, not a win). Denominator uses
   `D_I = max(B_I − L_I, ε·scale)`; instances where the default already meets/beats the frontier
   (`L_I ≥ B_I`) are **dropped from the scored set** (non-discriminating).
2. Run with `P` **decorrelated** workers (§11) to `T_I`; build the **best-of-portfolio, oracle-indexed**
   running-max trajectory `best(t)` (M0).
3. **Bounded signed gap** `γ(t) = clamp( (B_I − best(t)) / D_I , −γmax, 1 )` with `γmax ≈ 0.5`: 1 at the
   anchor, 0 at the frontier, **negative (capped) when `best > B_I`** — over-frontier is rewarded but
   one instance can't dominate (fixes the small-`D_I` blow-up).
4. **Primal integral** `PI_I = (1/T_I) ∫₀^{T_I} γ(t) dt` (lower = better; negative = beat the frontier).
   Rewards fast gap-closing (goal b) **and** a good/over-frontier finish (goal a), on best-of-portfolio
   (tail harvested, never the mean). Because greedy is an allowed stage, greedy-early-then-explore
   dominates pure-greedy here — but the integral is **not** self-sufficiently ungameable; the §8.3 floor
   and the §6.6 hard-instance gate close the residual modes (e.g. fast-feasible-then-idle).
5. **Feasibility tier (lexicographic, dominates PI):** within a stratum, candidate A dominates B only if
   A is feasible on a **superset** of instances (or ties feasibility with better PI on the common feasible
   set). `PI_I = +∞` (excluded) on never-feasible instances; win-rate (below) is computed **only over
   jointly-feasible** instances; **feasibility-fraction is reported and is the first lexicographic key**.
6. **Aggregation (not a flat mean, not bare win-rate):** **stratify by size**; primary =
   **signed-`PI`-delta rank-sum vs. default** (magnitude-weighted, so tiny easy wins can't outvote a flat
   hard tail) + stratum-median `PI`. A "win" requires beating default `PI` by **more than the noise
   margin** estimated from the default spread at that `n` (reuse the §8.3 spread); matched seeds; ties
   (within margin) are non-wins (consistent with the §13 Wilcoxon zero-handling). **The largest-n
   stratum carries a hard *strict-improvement* threshold** (not mere no-regression) — the project's value
   is on the hard, large instances, so the gate requires improvement there, and worst-case `PI` per
   stratum must not regress.

## 7. (Reserved — Phase-2 oracle-cost model for conditional rotations; see §14.)

## 8. Anti-greedy defenses (for the schedule)

1. **The metric** (§6): frontier-relative bounded integral + hard largest-n improvement gate makes a
   *uniform* greedy plateau strictly inferior, while *permitting* greedy as the opening stage.
2. **Bounded decisions (M1/M2 deliverable):** the sigmoid reparameterization (§4) keeps `value ∈ (ε,1−ε)`
   in the exploratory stage by construction — clamp enforced and unit-tested in `BranchingFunction`. (v2
   claimed this was already enforced; it is not — it is a deliverable.)
3. **Late-stage exploration floor (hard gate, relative to baseline):** in the *exploratory* stage the
   portfolio must retain real **outcome** diversity — `best-of-P` must exceed `median-of-P` by a fraction
   of the **default** schedule's measured spread at the same `n`. **Requires per-worker final incumbents
   (M0 deliverable; only global-best is logged today) and decorrelated workers (M0 seed fix).** Gating on
   outcome lift (not per-decision entropy) closes the loophole that a greedy-outcome rule with noisy
   decisions could pass. The early greedy stage is exempt.

## 9. Generalization contract

- **Scale-invariance enforced by an end-to-end test** (not a single-bit ΔP check): on synthetic instances
  spanning n∈{10,100,1000,3000} with **matched constraint-tightness** (`c1/Σw1`, `c2/Σw2` fixed), the
  realized **Hamming-radius distribution (mean+variance)** and the **free-decision fraction `f(n)`** must
  be statistically indistinguishable across n. `f(n)` drift is a rejection criterion.
- **Features:** within-instance **percentile/rank** transform (distribution-robust) **plus a signal-
  stationarity check**: reject a feature whose rank-correlation with realized per-variable objective
  contribution decays with n (dense-Eq.29 row-sums concentrate as ~1/√n, so their rank becomes noise at
  n=3000 even though the percentile stays uniform). Prefer intrinsic-O(1)-spread features (`p_ii` relative
  to row-sum; normalized degree in a thresholded interaction graph).
- **Splits:** train small→mid; **validation includes near-target sizes** (n∈{1000,2000} + a 3000
  calibration subset); a never-touched **n=3000 test** scored once. Validation gate = monotone-
  extrapolation (no degradation in `n`) **and** the largest-n strict-improvement threshold (§6.6) — the
  monotone gate alone can be fooled by the radius now being *more* exploratory at large n.
- **Instance sample:** reuse the paper's instances (§11); generate more per size if M0's variance
  characterization shows 10 is too few. Two disjoint validation folds; promote only on improvement in both.
- **One problem type first** (Eq. 29). Cross-type generalization is later.

## 10. Agent architecture

- **FunSearch / AlphaEvolve-style** population search over: scalar-bias **radius** schedule, per-stage
  `variable_order`/per-variable-logit function, and the `opt_switch_oracles` switch point (encoded as a
  fraction in [0,α] of `T(n)`). LLM mutates from high-scoring exemplars + observed anytime curves; the
  evaluator scores via §6; the population preserves diversity.
- **Candidate gate (pre-scoring):** static-angle realizable · A/B-priced (no free-relabel claims) ·
  scale-invariance end-to-end test passes · `value` clamp holds · late-stage exploration floor · feature
  allow-list (§5) · (Phase-3 only) compiles + prob∈[0,1] + fast.
- **No per-candidate recompilation:** the schedule/`variable_order`/per-variable-logit are runtime data
  (`set_predicted_params`/`_propagate_phase_params`); the one-time C edits (sigmoid+clamp §4, switch hook
  §4, oracle accounting §11) are infrastructure, not per-candidate. Phase-3 `BranchingFunction` rewrites
  (if ever) run subprocess-isolated with compile+import time charged, for rare promoted candidates only.
- **Selection on validation** (held-out larger sizes), never training score; multiplicity-controlled (§13).

## 11. Evaluation harness (M0 deliverables)

- **Oracle-budget enforcement (corrected):** `mod->M` is reset to 0 on every improvement
  (`SearchLib.c:221`), so it bounds work *between* improvements — setting `mod->M = T(n)` does **not** cap
  cumulative oracles. Add a **separate never-reset accumulator** `total_oracles += 2j+1` in `ctg`, gate
  termination on `total_oracles < T(n)`, and disable the wall-clock stop. Test: total oracle count at
  return == `T(n)` (±one round) regardless of improvement frequency.
- **Per-worker oracle counter:** the shared `mod->qtg_applications` (`model.h:28`) is incremented
  unlocked by all threading workers (`SearchLib.c:179`) — racy and conflated. Add `size_t oracle_count`
  to `solver_ctx_t` (one ctx per worker), increment in `ctg`, return per worker; define portfolio cost =
  each worker capped at `T(n)`, scored best-of-P. Stop reporting the shared counter.
- **Oracle-indexed, per-worker incumbent logging:** the callback is `void(void)` and logs
  `(value, wall_clock)` (`SearchLib.pyx:168`); change it to record `(value, ctx->oracle_count)` per
  worker, and **return each worker's final incumbent** (currently `incumb=[]`, `SearchLib.pyx:393`) so
  §8.3 can compute median-of-P. Rebuild best-of-portfolio in Python as a running-max merge over per-worker
  `(oracle, value)` streams. Update `test_concurrent_history.py` / `test_diagnostics_py.py` to the new
  `(value, oracle:int)` schema.
- **Per-worker stream decorrelation:** `solver_ctx_init_prng` hardcodes `prng_seed_thread(master, 0)`
  (`solver_ctx.c:535`) → all P workers identical under a fixed seed. Plumb a worker index from the
  `solve()` loop (`Model.pyx:781`) through `run_sampling` and seed `prng_seed_thread(master, worker_id)`
  (jump-decorrelated). **Hard M0 gate + test:** two workers, fixed master seed, distinct trajectories.
- **Reference & instance data (Decision D — RESOLVED for instances).** Eq.29 **instances** live in
  `github.com/SoerenWilkening/CBQS-benchmarks` → `Paper_general_constraints/instances/{n}_{idx}/{c1,c2,c3}.npy`
  (git-LFS; n=10…3000, 10/size). Scoped pull: `GIT_LFS_SKIP_SMUDGE=1 git clone … && git lfs pull
  --include="Paper_general_constraints/instances/**"` (the full repo is ~38 GiB — never a plain clone).
  **The cbqs `Model` API already expresses Eq.29 as-is (verified against `run_quantum.py`)** — objective =
  `c1` (`Σ_{i≥j} c1·x_i x_j`, MAXIMIZE), `≤` = `2·c3` vs `Σ_{i≥j} c3`, `≥` = `2·c2` vs `Σ_{i≥j} c2`
  (**gotcha:** `≤` uses **c3**, `≥` uses **c2**); `read_instance` efficiency-sorts + lower-triangularizes.
  Use the **vectorized bilinear build path for n≥1000** (the O(n²) Python loop is ~4.5M terms at n=3000).
  **Baselines ARE committed and importable** (the earlier "not committed" was a broken-clone false
  negative): `plots/classical_comparison.csv` (gurobi/hexaly/iqs, sizes 500–3000) + `plots/res.csv`
  (gurobi/hexaly/simanneal/iqs, 10–1000), schema `size,index,obj,time,oracles,preprocess-time,method`.
  M0b **imports** these — no regeneration, no Hexaly license. `B_I` = max obj over non-CBQS
  {gurobi,hexaly,simanneal} per (size,index) (exclude `iqs`/`*-bound`/`*-modeling-time`). `L_I` and
  default-`PI` still come from our own oracle-indexed CBQS-default runs.
- **Variance characterization:** measure per-solve cost and `PI` variance per size → set
  instances×seeds for the selection standard error, the noise margin (§6.6), and the inner-loop vs.
  validation size split.

## 12. Milestones

- **M0 — Infrastructure & truth.** Oracle-budget accumulator + test; per-worker oracle counter; oracle-
  indexed + per-worker incumbent logging (+ test updates); per-worker seed fix (+ two-worker test);
  sigmoid+clamp in `BranchingFunction`; `opt_switch_oracles` hook in `ctg`; scale-invariance end-to-end
  test; **resolve the Decision-D data dependency**; variance characterization. *Exit:* baseline schedule
  scored reproducibly under §6 on real (or generated) Eq.29 data; all tests green.
- **M1 — Metric & baseline.** Implement §6 (bounded anchored integral, feasibility composition,
  rank-sum + hard largest-n gate) + §8.3 floor relative to baseline spread. *Exit:* default `PI`,
  per-size noise margin, and floor calibrated.
- **M2 — Hypothesis check (no learning).** Instrument decision-touch fraction (per phase, both-feasible
  vs both-infeasible); hand-inject a radius schedule (greedy→explore) + one structural
  `variable_order`/logit; measure vs baseline. *Exit:* a hand-designed schedule moves the metric, and
  each lever's real leverage is known.
- **M3 — Agent loop (Phase 1).** Population search; cross-validated, multiplicity-controlled selection.
  *Exit:* validated improvement on near-target sizes within all gates.
- **M4 — Generalization to n=3000.** Monotone-extrapolation + largest-n improvement validation; score
  once on the untouched test with fresh seeds (Wilcoxon, matched seeds, effect size+CI); negative control.
- **M5 (later) — Phase 2** (dynamic/marginal angles, oracle-cost charged) and/or cross-type.

## 13. Statistics, reproducibility, process

- **Statistics:** unit = per-instance paired difference (candidate vs. default) at **matched seeds**;
  **Wilcoxon signed-rank** + effect size + CI; ties within the noise margin (§6.6) handled as zeros. The
  population search is a multiple-comparisons machine → the **final** rule is re-scored **once** on the
  untouched test with **new** seeds; that single number is reported. **Negative control:** the same loop
  on baseline-equivalent candidates must not yield a "significant" win.
- **Reproducibility/audit:** serialize the schedule as explicit code + normalization statistics + feature
  list + phase targeting + radius-per-stage + `opt_switch_oracles`; store frozen `B_I`/`L_I`/default-`PI`
  tables and per-worker seed bank; one-command replay of the reported test score.
- **Process:** M0–M5 filed as beads (epic `…-8an`, `bd` mandated by AGENTS.md). CLAUDE.md repointed to
  this file (done).

## 14. Open / deferred

- **Baselines (M0b) — RESOLVED:** committed at `Paper_general_constraints/plots/{classical_comparison,res}.csv`
  (gurobi/hexaly/simanneal/iqs across n=10–3000); M0b imports them — no regeneration, no Hexaly license.
  `L_I`/default-`PI` come from our own CBQS-default runs under the new oracle-indexed harness.
- **`variable_order`** — confirmed by the author as a real performance lever; treated as a priced
  (equal-`T(n)` A/B) static lever (§5). Optional later: make the look-ahead prefix-consistent with the
  order for cleaner permutation semantics.
- Phase-2 QTG cost model for conditional rotations (§7).
- Compute budget for the agent loop — set from M0's measured per-solve cost (inner loop small/mid n;
  large n only at the validation gate and the M4 test-once).
