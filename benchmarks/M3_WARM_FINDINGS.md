# M3-WARM — re-scoping + re-running M3 for the warm-started algorithm (bd 8an.10)

**Status:** exploratory machinery landed + reviewed; exploratory run results appended below.
**Protocol:** WARM (`general_greedy()`), the published CBQS (`iqs`) protocol — **not** the cold
`0^n` start the original M3 (bd 884) optimized against.

## 1. Why a warm re-run

The cold M3 (bd 884, winner `cand_16`) optimized a configuration the published CBQS never uses:
`iqs` **warm-starts** via `general_greedy()` (bd 8an.9). The warm landscape is materially
different, and — decisively — a warm start is **feasible from oracle 0**, so the phase machine
jumps straight to stage-3 *opt* (`SearchLib.c:142`), **skipping** `opt_sat`. That collapses the
cold 5-gene genome `(r_opt_sat, r_opt, alpha_switch, theta_amp, theta_feature)`:

| cold gene        | warm status | why |
|------------------|-------------|-----|
| `r_opt_sat`      | **INERT**   | no `opt_sat` phase runs when the start is feasible |
| `alpha_switch`   | **INERT**   | no `opt_sat→opt` switch; already in `opt` from oracle 0 |
| `r_opt`          | **LIVE**    | the opt-phase radius — the dominant warm lever |
| `theta_amp/feature` | **LIVE** | per-variable θ logit channel (opt-phase only) |

These two dead genes were `cand_16`'s **dominant cold levers** (broad `opt_sat` radius 8 + early
switch). The warm n=90 ≈23 % PI win (`plot_m3_n90 --warm`) came **entirely** from `r_opt`
(~4.4 vs default ~3.7) + θ. So a naive warm re-run of the cold genome would burn the whole search
budget on two inert dimensions.

**Where it pays:** warm headroom is small/mid-`n` only — n=90 ≈28 % headroom; n=3000 ≈0 %
(greedy near-optimal, all methods tie within 0.006 %, `logs/m4_spot/compare_n3000_warm.py`). So
warm M3 targets `n≤90`; gains shrink with `n` and do **not** generalize to n=3000.

## 2. The re-scope (`WARM_SPEC`)

`benchmarks/m3_proposer.py` adds a 3-gene warm-live genome
`WARM_GENES = (r_opt, theta_amp, theta_feature)` and `warm_genome_to_factory`, which emits
**only** the live opt-phase levers and **omits** the inert `opt_sat_branching_radius` /
`opt_switch_oracles` entirely. Consequence: a warm candidate differs from the warm **default**
*purely* in `opt_branching_radius` (+ opt-phase `opt_branching_weights` when θ is active) — no
inert-dim confound, no wasted mutation budget. One `ParametricProposer` drives both searches via
a `GenomeSpec` (`COLD_SPEC` / `WARM_SPEC`); the cold 5-gene path is byte-identical.

A **scheduled / convergence-aware** opt radius (radius that tightens as the warm search polishes a
near-optimal point) is **not** searched here: it needs a new oracle-indexed C lever (outside the
§1.4 scalar/array lever surface = a core change). Deferred to **bd 71e** (M5 territory).

## 3. Scoring a warm candidate (the harness)

`score_verdict` reads `default_PI` from the frozen **table** as the authoritative §6.6 gate
reference — and that column is **cold**. To compare warm-vs-warm we hand the metric an in-memory
table from `baselines.synthesize_warm_default_pi(frozen, warm_default_runset)`:

* `default_PI` ← the **freshly-solved warm default**'s median PI (per instance);
* `B_I` (classical frontier) ← **kept** (protocol-independent);
* `L_I` (cold first-feasible floor) ← **kept** as the shared normalizer. Its warm/cold
  inconsistency is the accepted **exploratory** gap: the warm candidate and warm default both
  normalize against the *same* cold `L_I`, so a shared offset cancels in the paired δ.

The capstone still holds: the warm default re-scores to *exactly* the synthesized `default_PI`
(`strict_xcheck=True` passes — a real consistency guard). Both A/B arms are warm
(`run_sweep(warm=True)`); the negative control (`{}` solved warm) is byte-identical to the warm
default → exact-zero deltas → no survivor.

### Warm trajectory repair (`warm_repair_history`)
A warm worker is feasible at the greedy value from oracle 0, but the C callback logs only
**improvements** — so a greedy-**optimal**-and-never-improved run has an *empty* history, which
`compute_primal_integral` reads as never-feasible (`+∞`), spuriously scoring a feasible (often
optimal) warm run as a **feasibility loss** (observed at `10_2`: greedy lands exactly on `B_I`).
Repair (the only case touched): empty history + a feasible final → `history = [(max feasible
final, 0)]` — provably exact (empty history ⟹ no worker improved ⟹ every final == the greedy
value, held over `[0, T]`). A non-empty warm history is left **verbatim** (the `[0, first_stamp)`
cold `γ=1` plateau is kept) — see §5.

## 4. Faithfulness / what is and isn't claimed

* §1.4 feature allow-list, §1.6 legal-lever-only output, scale-invariance + θ radius-neutrality
  gates: **unchanged** and enforced (`candidate_gate.admit`, start-agnostic — it measures the
  lever, not the trajectory). The warm factory is allow-list-faithful by construction.
* **Equal-`T(n)`** A/B: both arms `M=-1` (real `T(n)`), exact sampler, matched 7-seed bank.
* This is **EXPLORATORY**: cold `L_I`/`B_I` anchors with a warm `default_PI`. A
  FINAL/reproducible/publishable result needs **bd 8an.9** (re-frozen *warm* `default_PI` +
  `default := warm` governance + warm capstone). 8an.10 discovers/ranks; it does not re-freeze.

## 5. Adversarial review outcome (bd 8an.10 review workflow)

4 dimensions × independent reviewers → adversarial verify. 15 findings, **4 confirmed**, all the
same root cause: the original `warm_repair_history` non-empty **backfill** (prepend
`(history[0][0], 0)` when `first_stamp>0`) (a) over-credited `[0, first_stamp)` with the
*first-improvement* value rather than the lower greedy value, and (b) was simply **wrong** when
the greedy start was infeasible (then that interval is genuinely pre-feasible). **Fix applied:**
dropped the non-empty backfill — only the empty-history case is repaired (provably exact). The
residual `γ=1` plateau over `[0, first_stamp)` is <1 % of the integral at `n≤90` and near-
symmetric across both arms (accepted exploratory gap). The faithful upgrade (seed the true greedy
value at oracle 0, gated on greedy feasibility) needs the greedy objective exposed from C →
deferred to the 8an.9 FINAL path. (11 other findings were affirmative "verified clean"; 1
low-severity doc comment added at the rescore call site.)

## 6. Exploratory run results

**Run (2026-06-18):** seed 20260618, gens 3, pop 6, n_offspring 4, n_init_random 5,
`--max-per-size 4` → 36 anchored instances over n=10..90, 7-seed bank. 18 candidates evaluated,
**15 admitted, 3 gated**, **0 survivors**, negative control PASSED. (A *reduced* pass — see
caveats; the full ~88-instance run is ~3.5 h, `run_default` ≈ 307 s/candidate.)

**Result: NO warm candidate beat the warm default** under the §13 gate (both-fold CV + signed-rank
+ Holm). Every candidate had `cross_val=False` and `pi_rank ≤ 0` (tie at best, never a positive
signed-rank). The search drifted toward small `r_opt` (best by fitness: `r_opt=3.28, θ off`,
`pi_rank=0.0`). The warm `default_PI` median is **0.062** (min 0.0 — some instances' greedy start
is already optimal) — the warm default is near-frontier, leaving little headroom.

**Gate working (faithfulness):** 3 candidates were rejected by the **radius-fidelity** check — e.g.
`r_opt=1.50, θ=0.40·pii_z` realizes radius 1.80 (|Δ|/target 0.20 > band): a per-variable θ at a
*tiny* radius couples into the realized radius (the M0f coupling the gate exists to catch). θ is
not free of the radius at small r.

**Targeted §13 check of the known-good genome.** The memory's n=90 "+23 %" came from the *cold*
`cand_16` genome (r_opt≈4.41 + θ=0.29·pii_z) evaluated warm under a **mean-PI** lens
(`plot_m3_n90 --warm`) with the *old over-crediting* history backfill. Scoring that exact genome as
a **warm-live** schedule under the §13 metric + the **faithful** history repair (reusing this run's
warm default), per stratum:

| n  | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 |
|----|----|----|----|----|----|----|----|----|----|
| signed-rank W | 0 | 0 | 0 | 0 | 0 | **−4** | 0 | 0 | 0 |
| mean-PI Δ | +3% | −1% | −0% | −2% | −3% | −6% | −11% | −0% | **+2%** |

`overall_pass = False`. It **ties** the warm default at almost every stratum (W=0 within the noise
margin), **regresses at n=60** (gate_B fails), and at **n=90 is only +2 %, not +23 %**. The +23 %
does not survive (a) restricting to warm-live levers, (b) the §13 signed-rank/CV gate vs the weaker
mean-PI lens, and (c) the faithful (non-over-crediting) `warm_repair_history`.

**Interpretation.** Warm-start brings the default near-optimal (greedy ≈ frontier), so the warm
headroom for a schedule is small and concentrated at larger `n`; under the strict cross-stratum §13
selection the warm default is **unbeaten** on n≤90 here. The cold-era warm "+23 %" was inflated by
the mean-PI lens + the over-crediting backfill. This reframes the deliverable from "M3 squeezes the
warm headroom" to **"the warm default is robust on n≤90; the warm-live levers (r_opt, θ) do not
yield a §13-significant win at the searched budget."**

**Caveats (why this is exploratory, not a final verdict):**
1. *Reduced run* — 36 instances (4/size) × 18 candidates × 3 gens is **underpowered**: limited
   Wilcoxon power and a search that did not densely probe the `r_opt≈4.4 + θ=pii_z` region. A full
   run (88 instances, more generations, population seeded near that region) is needed for a
   definitive "no winner."
2. *Exploratory anchors* — cold `L_I`/`B_I` with a warm `default_PI` (§3/§4). A final result needs
   bd 8an.9 (re-frozen warm anchors).
3. The faithful warm history (true greedy value at oracle 0, gated on greedy feasibility) is
   deferred to 8an.9; the conservative repair here keeps a small `[0, first_stamp)` γ=1 plateau.

## 7. Reproduce

```bash
CBQS_BENCHMARKS_DIR=<clone> python -m benchmarks.run_m3_warm \
    --out-dir benchmarks/artifacts/m3_run_warm_8an10 \
    --seed 20260618 --generations 5 --pop-size 8 --n-offspring 6 --n-init-random 6
```
