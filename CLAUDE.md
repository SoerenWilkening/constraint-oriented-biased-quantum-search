# CLAUDE.md — CBQS Operating Charter

Operating contract for agents working in this repository. These rules **override** default behavior.
They tell you how to work and how to *fail fast*; they do **not** restate the product spec — that lives in
`NORTHSTAR.md` (mission, fitness metric, milestones M0–M5) and is the single source of truth for the *what*.

## 0. Required reading (every session)

1. **`NORTHSTAR.md`** — the design doc. Canonical for mission (§1), the quantum-faithfulness invariant (§5),
   the fitness metric (§6), the M0 harness deliverables (§11), and the milestone plan (§12). When this
   charter and NORTHSTAR disagree on the *spec*, NORTHSTAR wins; when they disagree on a *file:line fact*,
   the **source wins** (NORTHSTAR's internal line citations are known to drift — see §5 below).
2. **`AGENTS.md`** — task tracking (`bd`/beads) and the mandatory session-completion / push protocol.
   Do **not** duplicate that protocol here; obey it.

This is a research solver. **The oracle count is the product.** CBQS is a faithful classical stand-in
whose oracle count *is* the quantum cost; everything we measure and claim rests on that number being
correct. Treat any code touching it as load-bearing.

> **⚡ RUN POLICY (overrides §1.1/§1.2 for execution — user directive 2026-06-16).** Every CBQS run sets a
> wall-clock cap `stopping_time` of **15–30 minutes** (900–1800 s; pick within the band by available time —
> more time → toward 30 min): `m.set_param('stopping_time', 900..1800)` before `solve()`. **Do not leave it
> at the `-1` default.** Faithfulness is **explicitly waived for runs** — 15–30 min is long enough that
> schedule changes have a meaningful, measurable performance impact, and wall-clock performance within that
> fixed budget is what we evaluate. This **supersedes** the "never substitute wall-clock for oracles"
> prohibition (§1.2) and the equal-`T(n)` pricing (§1.1) *for run execution*; the oracle-accounting code
> stays load-bearing (it must remain correct), but the oracle-indexed primal-integral faithfulness
> guarantees (NORTHSTAR §6) no longer hold for wall-capped runs — the accepted tradeoff. Consequences:
> n≥1000 / n=3000 (M4) become runnable on a single box (non-exact, accepted); both arms of any A/B must
> share the same cap to stay matched; the cap is checked **between** Grover rounds, so one in-progress
> large-`j` round can overshoot. `stopping_time` is a **harness/run-level** setting, not a per-candidate
> lever (`candidate_gate` keeps it in `_FAITHFULNESS_BREACH_PARAMS`, so tuned candidates cannot set it).

---

## 1. Non-negotiable invariants (reject-early gates)

These are the gates that let you **kill a bad approach before writing it**. If a proposed change or
candidate schedule violates one of these, stop and reconsider — do not "make it work."

- **§1.1 Quantum-faithfulness.** Every lever (scalar-bias/radius schedule, `variable_order`, per-variable
  bias, switch point) must be implementable by the QTG within the oracle-cost model **and priced by the
  equal-`T(n)` A/B test**. There is no "free relabel": `variable_order` is a *priced* lever, not a costless
  permutation. If a lever cannot be priced by the A/B test, it is inadmissible. (NORTHSTAR §5.)
- **§1.2 Oracle accounting is sacred.** The measured quantity is `2j+1` oracle charges accumulated per
  worker. Never substitute wall-clock for oracles, never let the accumulator be racy/under-counted, never
  reset the cumulative counter. The current shared `mod->qtg_applications` is **racy and wrong** (§5);
  fixing it (per-worker counter, never-reset accumulator) is M0, not optional polish.
  *(Exception — the RUN POLICY callout above: runs now carry a 15–30 min wall cap and faithfulness is
  waived for them. The counter must still be correct; only the "no wall-clock termination" rule is lifted.)*
- **§1.3 No uniform-greedy collapse.** Greedy is an *allowed opening stage*, never the whole schedule.
  Score on **best-of-portfolio** (running-max over workers), **never the mean** — the mean rewards
  low-variance greedy and discards the restart tail. (NORTHSTAR §2, §8.)
- **§1.4 Phase-1 feature allow-list.** Angle-setting features are **exactly** `{p_ii, objective &
  constraint row-sums, raw interaction-graph degree, nnz counts}` — each one O(nnz) pass. **Banned:**
  LP/SDP/optimization-derived features and *any* iterative/spectral graph statistic (eigenvector,
  PageRank, k-core, betweenness). They smuggle uncharged classical optimization into a comparison against
  classical solvers. (NORTHSTAR §5, Decision C.)
- **§1.5 Scale-invariance.** Levers are parameterized by a **target radius `r`**, with `bias = n/r − 2`,
  so the neighborhood is radius-`r` at *every* `n`. Do not use `bias = n/d` directly (it is compressed
  38–56% at small `n`). The realized Hamming-radius distribution and free-decision fraction `f(n)` must be
  statistically indistinguishable across `n`. **Beware:** enabling `branching_weights` silently rescales
  the radius via the shared `factor_sum` (§5) — a tuning change that flips weights on/off changes the
  neighborhood size without touching `bias`.
- **§1.6 No per-candidate recompilation.** Schedules, `variable_order`, and the per-variable logit are
  **runtime data** propagated via `_propagate_phase_params` → per-phase C setters. The handful of C edits
  (sigmoid+clamp in `BranchingFunction`, the `opt_switch_oracles` hook, oracle accounting) are **one-time
  infrastructure**, not per-candidate. Any design that recompiles C per candidate is wrong.
- **§1.7 Bounded decisions.** The exploratory stage must keep `value ∈ (ε, 1−ε)` *by construction*
  (the sigmoid+clamp reparameterization). This is a **deliverable, not a current fact** — `value` is
  unclamped today (§5).

---

## 2. Fail-fast engineering principles

Adapted to a C core + Cython bindings + Python harness. Numbered for reference in reviews.

- **§2.1 FAIL FAST, FAIL LOUD.** Assertions and crashes, not silent returns or corrupted state.
  Especially: feasibility acceptance, objective sign, and phase-machine consistency. A solution reported
  feasible that fails `eval_constraints` is a crash-worthy bug, not a warning.
- **§2.2 RED-GREEN TDD.** Write the failing test **first**, then the minimal code to pass it. "It compiles"
  and "it runs without errors" are **not** passing tests — verify against a *known-correct* answer
  (golden values, RHS baselines, determinism). See §8 for the baselines you must pin.
- **§2.3 GET FEEDBACK FAST.** Rebuild and run the relevant tests every ~50 lines, not after 500. The build
  is part of your type-checker: a cross-boundary change (e.g. callback arity) **must** break compilation if
  done wrong — let it. Don't code blind across the C/Cython boundary.
- **§2.4 SKEPTICISM.** Do not trust: subagent output, existing code comments (the `qtg_applications`
  comment at `SearchLib.c:101` *falsely* claims it is single-threaded), prior assumptions, or NORTHSTAR's
  internal line citations. **Open the file and verify.**
- **§2.5 BUGS ARE DEEP AND INTERLOCKED.** The phase machine, threading, objective sign, and feasibility
  accounting are coupled. A fix that passes one test but breaks an invariant (§1) is not a fix. Find the
  root cause.
- **§2.6 NORTHSTAR-DRIVEN.** Implement against the milestone you are on (NORTHSTAR §12). Don't build
  features outside its scope or skip its exit criteria. File every unit of work as a `bd` issue under the
  M0–M5 epic.
- **§2.7 DON'T DUPLICATE.** Bias/param setters already exist (`solver_ctx_set_*`, per-phase variants);
  the vectorized bilinear build path already exists (`VariableVector.pyx`). Check before adding a parallel
  path. Reuse `_propagate_phase_params`; don't invent a second propagation route.
- **§2.8 RESEARCH STEPS ARE EXPLICIT.** If you are unsure what the C actually does (which stats struct a
  call site reads, whether a term is live), extract the real behavior and state it — don't guess. Example:
  the look-ahead term *looks* live but is dead (§5).

---

## 3. Core-change protocol

**Core = faithfulness-critical code:** oracle accounting (`SearchLib.c` `ctg`, `model.h::qtg_applications`),
PRNG/seeding (`solver_ctx.c`, `prng.c`), branching/bias math (`Branching.h`, `solver_ctx.c` setters),
and the phase machine / transitions (`SearchLib.c` stage logic, `solver.c` `CSearch_*`).

**Rule:** a change to any core area runs the **`core-change` workflow** before merge:

```
Workflow({ name: "core-change", args: { task, files, northstarSection, diffReady } })
```

It applies the lean gate — **one proposer (test-first plan) → one adversarial reviewer (refute against
§1/§2 invariants, threading, sign, phase consistency, regression baselines) → verifier (build + targeted
tests + the relevant sanitizer)** — and **auto-escalates to a 3+1 blind-proposer panel** for *redesigns*
(reworking the phase machinery, the PRNG architecture, or the oracle-cost model). Non-core changes use the
ordinary gate (tests green + sanitizers clean in CI).

> Note: the workflow is the durable trigger; `ultracode` (when on) supplies the same machinery
> opportunistically but is per-session and not guaranteed. The rule here fires regardless.

---

## 4. Solver architecture

```
Python: Model.solve()  ── joblib Parallel(threading, num_workers≈12) ──▶ run_sampling()   (per worker)
        (Model.pyx)         each worker: OWN solver_ctx_t + cur_sol;  ALL share ONE model_t* (mod)
                                                   │
Cython: run_sampling (SearchLib.pyx) ── _propagate_phase_params ──▶ per-phase solver_ctx setters (runtime data)
                                                   │  installs void() history callback
C:      ctg()  (SearchLib.c:113)  ── the driver loop ──▶ CSearch_{sat,opt_sat,opt}  (solver.c)
                                                   │             consult BranchingFunction (Branching.h:76)
                                                   └─ accumulate oracles: mod->qtg_applications += 2j+1
```

**Three phases, one implicit state machine** (`stage` + `search_function` pointer + `active_stats` pointer
move together — keep them consistent):

1. **`sat`** — `CSearch_sat` (`solver.c:567`). Find any feasible point. `initial_state_preparation`
   (`solver.c:188`) is a single-threaded greedy warm start.
2. **`opt_sat`** — on first feasible → `stage=2`, `CSearch_opt_sat` (`solver.c:421`), minimize constraint
   violation (tighten). Bias consulted on both-feasible **and** both-infeasible choices (`solver.c:481`).
3. **`opt`** — when `counter > 10 && !updated` (`SearchLib.c:227`, the hardcoded exploit→explore switch
   that M-level work replaces with `opt_switch_oracles`) → `stage=3`, `CSearch_opt` (`solver.c:287`),
   maximize objective (explore). Bias consulted **only** where look-ahead leaves both values feasible
   (`solver.c:353`).

**Budget/termination:** `mod->M` bounds oracles *between* improvements via a local `m_tot` (reset at
`SearchLib.c:221`, **not** `mod->M` itself); cumulative oracles live in `mod->qtg_applications` (never
reset). A wall-clock stop also exists (`mod->stopping_time`, default 1e6 s, `model.c:28`) plus a per-ctx
timeout — NORTHSTAR M0 disables the wall-clock stop and gates on the oracle accumulator.

---

## 5. Correctness-risk hotspots (verified against source)

Each entry: **location → why dangerous → how to detect.** These are the landmines.

- **Racy oracle counter.** `mod->qtg_applications` (`model.h:28`, an `int`) is `+=`'d **unlocked** by all
  worker threads at `SearchLib.c:179`, outside the `update_lock` critical section. The comment at
  `SearchLib.c:101` *wrongly* says it's single-threaded. → Headline metric under-counts non-deterministically.
  → **Detect:** TSan with `num_workers>1`; a fixed-seed determinism test asserting identical `oracle_calls`.
  `mod->runtime` (`SearchLib.c:186`) has the same unlocked-write bug (last-writer-wins, not max).
- **`M` vs `m_tot` confusion.** `mod->M` is the *between-improvements* budget, enforced via the local
  `m_tot` reset to 0 on every improvement (`SearchLib.c:221`, alongside `rounds=0`). Removing that reset
  turns a per-improvement budget into a hard cumulative cap (premature stop) or, if `rounds` isn't reset,
  blows up the Grover schedule. → **Detect:** a multi-improvement instance must show
  `qtg_applications > M` while never exceeding `M` between two incumbents.
- **Portfolio collapse.** `solver_ctx_init_prng` hardcodes `prng_seed_thread(master, 0)`
  (`solver_ctx.c:535`); the `solve()` worker loop (`Model.pyx:780–783`) uses `_` (no worker index) and
  every worker copies the same `mod._seed`. → Under a fixed seed, all P workers run the **identical**
  trajectory: zero portfolio diversity. → **Detect:** 2 workers, fixed master seed → assert distinct
  incumbent trajectories. (Fix: plumb a `worker_id` through `run_sampling` into a non-zero `thread_id` or
  per-worker `ctx->seed`.)
- **Bias blend silently rescales the radius.** `BranchingFunction` (`Branching.h:88–109`) is a single
  shared-denominator convex average; enabling `branching_weights` changes `factor_sum` from 1→2, halving
  the bias term and inflating the radius (the "~4 → ~n/2 at n=3000" failure). `value` is **not clamped**
  (`Branching.h:104–118`) — signed normalized weights can push it outside `[0,1]`, silently forcing an
  assignment. → **Detect:** golden value `BranchingFunction(i,0,0,0) == 6/7` at `bias=5` (flip prob `1/7`);
  a fixed-`r` sweep over `n` asserting realized mean-flips/`n` is constant. This is where the **sigmoid+clamp**
  reparameterization lands — and you must remove the weight term from the convex sum (stop adding
  `branching_factor` to `factor_sum`) or the baseline `θ_i=0` won't recover exactly.
- **Dead look-ahead term.** Every one of the 7 `BranchingFunction` call sites passes `diffcount=0`, which
  zeroes the look-ahead factor (`Branching.h:82`). The live blend is effectively **2-term**, not 3. A tuner
  setting `look_ahead_factor` will see no effect; any change that starts passing real `diffcount`
  reactivates a dormant term and shifts the radius. → **Detect:** assert output invariant to
  `look_ahead_factor` while `diffcount==0`.
- **Phase-machine coupling.** `search_function`, `active_stats`, `stage`, `direction`, `counter`, `updated`
  must transition together (`SearchLib.c:134–157, 195–201, 227–234`). Setting `active_stats` without
  `search_function` (or running `CSearch_opt` before a feasible point exists) applies the wrong phase's
  stats or optimizes an infeasible state. → **Detect:** invariant assert
  `stage==3 ⇔ search_function==CSearch_opt ⇔ active_stats==&branching_stats_opt`; entry assert
  `cur_sol->feasible` in `CSearch_opt`.
- **Feasibility sign/EQUAL accounting.** `EQUAL` needs `potential==0` exactly; inequality needs
  `potential>=0`; violation sums use `llabs`/`-min(0,·)` (`solver.c:387–390, 510–517`). A flipped sign or
  dropped `llabs` silently accepts infeasible solutions that then poison transitions and `global_opt`.
  → **Detect:** property test — every reported-feasible solution must satisfy `eval_constraints==0`
  (the `verify=True` path, `Model.pyx:803`).
- **Eq.29 c2/c3 swap + objective sign.** The capacity `≤` constraint reads **c3**, the covering `≥` reads
  **c2** (`eq29_loader.py:92–99`) — inverted vs. intuition. Objective is `c1`, MAXIMIZE, with `MAXIMIZE=-1`
  and `objective_value = tot_profit*sense` (`Model.pyx:1045`) — reading `tot_profit` directly flips every
  sign. `close()` auto-sets `branching_bias = n/4` when unset (`Model.pyx:687–689`), **overriding**
  `phase_params.py`'s default of 5.0. → **Detect:** instance `100_0` RHS pins `le_rhs==5032863` (c3),
  `ge_rhs==5040079` (c2) — a swap flips them. `build_model` still uses the O(n²) Python loop; the
  vectorized `x @ (C @ x)` path exists (`VariableVector.pyx:104`) but **is not wired in** yet.
- **Param propagation is runtime-only.** `set_predicted_params` (Python, `SearchLib.pyx:533`) only writes
  the `mod._params` dict; live propagation is `_propagate_phase_params` (`SearchLib.pyx:223`) → per-phase
  setters. The C `solver_ctx_set_predicted_params` is **dead** from this path — don't assume it runs.
- **CI's C-test filter still has holes (verified 2026-06-10).** The `ctest -R` filter (test.yml) now
  matches **22 of the 23 registered** cmocka targets; the holes are: `test_opt_sample_cap` (registered,
  compiles under `-Werror`, but **never executes in CI**) and `test_predicted_params.c` (exists in
  `tests/` but is **not registered in CMakeLists at all** — never even built; it targets the dead C
  `set_predicted_params` path above). → **Always run the full local suite** (`ctest` with no `-R`)
  before touching those modules. The history-schema and eq29-RHS baselines are likewise only checked
  locally (the latter needs `CBQS_BENCHMARKS_DIR`). A *skipped* test is "unverified," not "passed."

---

## 6. File / module map

**C core (`cbqs/src/`)**
- `SearchLib.c` — `ctg()` driver loop: phase selection, exploit→explore switch, oracle accounting, M/time
  termination, mutex-protected `global_opt` update. **The accounting/threading hotspots live here.**
- `solver.c` — `CSearch_sat`/`CSearch_opt_sat`/`CSearch_opt`, `initial_state_preparation`,
  `look_ahead_correct`; the bias call sites and feasibility/sign accounting.
- `Branching.h` — `BranchingFunction` (inline): the per-variable assignment-probability lever. **The
  sigmoid+clamp edit lands here.** `solver_ctx.c` holds the bias/weights/factor setters.
- `model.h`/`model.c` — `model_t` (shared across workers: `M`, `qtg_applications`, `runtime`,
  `stopping_time`, `solver`). **No bias params live here** — they're in `solver_ctx_t`.
- `solver_ctx.c`/`.h` — per-worker context: three phase-specific `BranchingStats_t` + `active_stats`,
  PRNG seeding, `variable_order` argsort, the `solver_ctx_set_*` API.
- `prng.c` — `prng_seed_thread(master, thread_id)` (jump-decorrelated streams; `thread_id` hardcoded 0 today).
- `local_search.c` — a *separate* k-flip path (pthread fan-out, own termination); **not** the `ctg` path.
- `arena.c`, `dyn_expr.c`, `intarray.c`, `Expression.c`, `constraint.c`, `quantum_search.c`,
  `approximate_state_sampler.c` — supporting data structures / samplers.

**Cython layer (`cbqs/*.pyx`, `*.pxd`)**
- `Model.pyx` — `Model` class; `solve()` worker fan-out; objective sign; constraint push to C.
- `SearchLib.pyx` — `run_sampling` (per-worker driver), `_propagate_phase_params`, `set_predicted_params`,
  the `void()` history callback (`(value, elapsed_seconds)` today; migrating to `(value, oracle:int)`).
- `Expression.pyx` — `__le__/__ge__/__eq__` attach constraint sense+rhs (`__ge__` negates → internal LOWER).
- `VariableVector.pyx` — `__matmul__` → `bilinear_reduce`: the vectorized build path.

**Python (`cbqs/`, `benchmarks/`)**
- `phase_params.py` — `PhaseParamResolver`: phase→unprefixed→default resolution (5 params × 3 phases).
- `result.py` — `OptimizeResult` (documents the history schema being migrated).
- `Constants.py` — `MAXIMIZE=-1, MINIMIZE=1, OPTIMIZE=2, SATISFY=3, GREATER=6, LOWER=7, EQUAL=8`.
- `__init__.py` — public API (`Model`, `OptimizeResult`, constants); `__version__`.
- `benchmarks/eq29_loader.py` — Eq.29 instance loading, canonical preprocess, model build.

---

## 7. Build, test & sanitizer gates

**Build (local dev, in-place):**
```bash
python setup.py build_ext --inplace          # or: pip install --no-build-isolation -e .
# conftest documents: CC=gcc python3 setup.py build_ext --inplace
```
`Model is None` after import means the extension/optional deps failed to build — a silent-degradation mode;
treat it as a hard failure, not "skip."

**Python tests** (matches the CI python job):
```bash
pytest tests/ -v --tb=short --ignore=tests/test_stress.py
pytest tests/test_stress.py -v --timeout=180        # split out (slow)
```

**C tests — run the FULL suite locally** (CI's filter misses `test_opt_sample_cap`, and
`test_predicted_params.c` is unregistered; see §5):
```bash
cmake -S tests -B build-tests -DWERROR=ON
cmake --build build-tests -j
ctest --test-dir build-tests --output-on-failure    # ALL targets — do this before touching any C module
# CI's narrower filter (do not rely on it as your gate) — see test.yml for the current -R regex.
```

**Sanitizers — run the matching one before touching its code (see §3 core areas).**
The one-command gate runs both and picks a working toolchain automatically:
```bash
tests/run_sanitizers.sh            # ASan (full) + TSan (thread_safety); also: asan | tsan
```
> **macOS (bd aft):** Apple clang's sanitizer runtime SIGILLs at startup on macOS 26+
> (Darwin 25+) — every instrumented binary exits 132 *before* main, so the manual
> `cmake` commands below need Homebrew LLVM clang (`brew install llvm`) via
> `-DCMAKE_C_COMPILER=$(brew --prefix llvm)/bin/clang`. `run_sanitizers.sh` does this
> for you; the CMake config also **fails loudly** with this remedy if a sanitizer
> build is configured with the broken toolchain. Linux/CI are unaffected.

```bash
# ASan (heap/UAF/leaks) — before memory-ownership changes (arena, dyn_expr, state, local_search):
cmake -S tests -B build-asan -DASAN=ON -DWERROR=ON && cmake --build build-asan -j   # macOS: add -DCMAKE_C_COMPILER=$(brew --prefix llvm)/bin/clang
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ctest --test-dir build-asan --output-on-failure

# TSan (data races) — before touching solver_ctx, the threading workers, or the oracle counter:
cmake -S tests -B build-tsan -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_C_FLAGS="-fsanitize=thread -g -O1" -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=thread"   # macOS: -DCMAKE_C_COMPILER=$(brew --prefix llvm)/bin/clang
cmake --build build-tsan -j && TSAN_OPTIONS=halt_on_error=1 ctest --test-dir build-tsan -R test_thread_safety -V

# Valgrind (definite leaks / invalid access) — Expression/Constraint/state/local_search/solver:
valgrind --leak-check=full --error-exitcode=1 --errors-for-leak-kinds=definite \
  --suppressions=tests/valgrind-python.supp ./build-tests/test_solver
```

**Env:** `CBQS_DEBUG=1` → per-solve JSON stats to stderr; `CBQS_THREADS=N` → override worker count;
`CBQS_BENCHMARKS_DIR=<clone>` → enables the real Eq.29 RHS regression checks (else they *skip*, not fail).

---

## 8. Regression baselines — DO NOT silently change

A change to any of these must be deliberate, justified in the `bd` issue, and updated **everywhere at once**:

- **Branching golden value:** `BranchingFunction(i,0,0,0) == 6/7 ≈ 0.857` at `bias=5` (per-variable flip
  prob `1/7`). Pins the bias→value map; the sigmoid reparam must recover it at `θ_i=0`.
- **Eq.29 RHS (instance `100_0`):** `le_rhs==5032863` (sum over c3), `ge_rhs==5040079` (sum over c2).
  Encodes the LE-uses-c3 / GE-uses-c2 mapping. Needs `CBQS_BENCHMARKS_DIR`.
- **Frozen-default protocol = WARM (bd 8an.9, 2026-06-19).** `baselines_frozen.csv` / `floor_calibration.csv`
  are the **warm** default (published `iqs` `general_greedy` start), `protocol` column == `warm` on every
  scored row. The cold `0^n` tables are archived at `baselines_frozen_cold.csv` / `floor_calibration_cold.csv`
  for M1-cold provenance. The warm freeze **keeps the cold `L_I`** (shared normalizer) and re-scores only
  `default_PI` warm (`default_instance_anchors(L_I_override=)`); a warm `default_PI` is NOT comparable to a
  cold one (feasible from oracle 0), so `freeze_default_anchors` enforces a **single-protocol** guard. The
  canonical M3 driver is `run_m3_warm.py`; the cold `run_m3.py` fails loud against the warm table. To
  reproduce the cold M1 baselines, restore the `*_cold.csv` archive (or `m2 … --cold`).
- **Determinism:** fixed seed + single worker → identical objective **and** solution array
  (`test_determinism.py`). The M0 per-worker PRNG decorrelation must keep single-worker determinism intact
  and only change *multi-worker* trajectory divergence. Never "fix" a failing determinism assert by
  loosening it.
- **History schema:** currently `(value, elapsed_seconds: float)`. The M0 migration to
  `(value, oracle: int)` must update `SearchLib.pyx:170`, `test_concurrent_history.py`,
  `test_diagnostics_py.py`, and `result.py` (docstring + `summary()` formatting) **in the same commit**.
- **`branching_bias > -1`** (`test_bias_validation.py`) — the bias domain guard.

---

## 9. Task tracking & session completion

Use **`bd` (beads)** for all task tracking (run `bd prime`). File M0–M5 work under the NORTHSTAR epic.
The **mandatory session-completion / push protocol is in `AGENTS.md`** — follow it exactly. Work is not
complete until `git push` succeeds.
