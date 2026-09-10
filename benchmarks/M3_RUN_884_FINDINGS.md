# M3 agent-loop run — findings (bd 884)

**Run:** `python -m benchmarks.run_m3 --generations 4 --pop-size 6 --n-offspring 6
--n-init-random 5 --seed 20260615` (driver: `benchmarks/run_m3.py`).
Artifacts (gitignored, reproducible from the seed): `benchmarks/artifacts/m3_run_884/`
(`summary.json` = the §13 audit record). Date: 2026-06-15.

## Setup
- **Scope:** the 88 anchored Eq.29 instances with a frozen `default_PI` at `n∈{10..90}`
  (80_0 dropped — never-feasible; 90_3 has no B_I row). Seed bank = `DEFAULT_SEED_BANK` (1..7).
- **Faithfulness:** equal-`T(n)` A/B (M=-1 both sides, §1.1); exact sampler (`opt_sample_cap=0`);
  `variable_order` **held out** (8an.8 cliff); θ opt-phase only, allow-listed features by
  construction (§1.4). `stopping_time` OFF (dormant at n≤90).
- **Capstone (M1 lesson):** default-vs-default strict-xcheck **exact** on all 88 instances
  *before* any candidate was scored (the live default reproduces the frozen anchors).
- **Selection (§13):** CV folds train `{10,20,30,40,50}` → validate `{60,70,80,90}`; a survivor
  must pass **both folds** AND be Holm–Bonferroni rejected at FWER ≤ 0.05; negative control; final
  rescore on the untouched n=100/150 holdout with **new** seeds 8–10.

## Result — a schedule family BEATS the CBQS default
- 30 candidates evaluated, **all admitted** (the radius family is scale-invariant by construction,
  so the §10 gate passed every one). **12 survivors** clear CV (both folds) **and** Holm (FWER ≤ 0.05).
- **Negative control PASSED** (no baseline-equivalent survivor).
- **Winner (highest fitness): `cand_16`** — `r_opt_sat=8.0, r_opt=4.41, alpha_switch=0.012,
  theta_amp=0.29 on pii_z`. Holm `p_adj = 1.5e-12`; pi_rank 0.875, floor 1.0, no feasibility loss.
- **§13 rescore on the untouched holdout** (n=100/150, seeds 8–10): `overall_pass=True`,
  **all 4 holdout instances favor the winner** (unanimous direction). The one-sided Wilcoxon
  `p = 0.0625` is the **n=4 power floor** (2⁻⁴) — only four faithful n≥100 anchors exist, so the
  formal p cannot dip below 0.0625 even with a unanimous holdout. The §6/§8 **gate passes** on the
  holdout; the small-n caveat is the only reason p sits just above 0.05.

## What drives the win (the interpretable signal)
The survivors cluster sharply, and the cluster reproduces the **M2 leverage finding** on real data
with §13 rigor:

| lever | default | survivor cluster (median [min, max]) | direction |
|---|---|---|---|
| `alpha_switch` (×T(n)) | 0.10 | **0.019** [0.0, 0.072] | switch to **explore ~5× EARLIER** |
| `r_opt_sat` (radius) | ~3.3–3.7 realized | **7.9** [5.2, 8.0] | **broad** opt_sat neighborhood |
| `r_opt` (radius) | ~3.3–3.7 | 4.34 [2.66, 4.91] | near default |
| θ | off | mixed; **5/12 survivors θ-OFF** | **not the driver** |

- The dominant lever is **`opt_switch_oracles`**: the default switches to the explore (objective-
  maximizing) phase at 0.1·T(n); the survivors switch almost immediately (α≈0–0.05). This is exactly
  M2's "opt_switch_oracles DOMINANT; earlier-explore better everywhere n=10..100; default 0.1M left
  of optimal", now **cross-validated + Holm-controlled + holdout-confirmed**.
- **θ is incidental:** 5 of the 12 survivors (`cand_9/20/22/23/init_rand_2`) have the θ channel OFF
  (`theta_feature='none'`) and still win — e.g. `cand_23` (`r_opt_sat=5.16, r_opt=4.43, alpha=0.0`,
  θ off). This confirms M2f's "θ near-null"; the win is a **radius + switch** effect, not θ.

**Parsimonious recommendation:** a θ-OFF schedule with `alpha_switch ≈ 0` (switch to explore as soon
as a feasible point exists) and a broad opt_sat radius (`r_opt_sat ≈ 6–8`, `r_opt ≈ 4–4.5`) is the
robust, faithful improvement over the default on the anchored n≤90 strata. `cand_16` is the
single highest-fitness point but the **cluster** (not the point) is the finding.

## Caveats / scope
- Generalization to **n=3000 (M4)** is NOT established here — the largest-n strict gate (gate_A) is
  dormant and `default_PI` for n≥500 is pending (bd 0o8 / 8an.4.8). The n=100/150 holdout passes the
  gate, which is encouraging but small.
- The negative control is, by construction of the matched-seed metric, an **exact-zero** control
  (baseline-equivalent at matched seeds = byte-identical run-set → zero deltas). It proves the
  pipeline never fabricates a winner from a null schedule, but does not stress the FWER machinery
  with noise (a different-seed null would violate `score_verdict`'s matched-seed invariant).
