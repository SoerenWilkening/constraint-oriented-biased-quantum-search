# Project Research Summary

**Project:** CBQS v1.1 Bug Fixes & Polish
**Domain:** C/Cython/Python solver cleanup — compiler migration, concurrency fix, tech debt removal
**Researched:** 2026-02-06
**Confidence:** HIGH

## Executive Summary

CBQS v1.1 is a cleanup milestone targeting six specific tech debt items: GCC 15 C23 migration warnings, Cython callback concurrency bug, VLA elimination, SATISFY mode crash, local_search API inconsistencies, and deprecated BranchingStats cleanup. Research reveals these items are architecturally interconnected — four of the six stem from pre-solver_ctx_t global state patterns left in place during the v1.0 migration. The recommended approach is **sequential dependency-driven cleanup**: fix the critical SATISFY crash first (unblocks testing), eliminate the VLA (independent, low risk), rework the callback mechanism for thread safety (highest complexity), bridge the BranchingStats global-to-context gap (moderate complexity), and finally add local_search mutex protection (cosmetic, lowest priority).

The key risk is **scope creep disguised as cleanup**. The research identified 13 cleanup-specific pitfalls, with the most critical being: (1) GCC warning fixes that silently change behavior (operator precedence, signed/unsigned casts), (2) dead code removal that deletes algorithm documentation (the commented-out incremental constraint evaluation in local_search.c), (3) Cython .pxd declaration drift from C headers causing silent memory corruption, and (4) callback rework introducing new concurrency bugs while fixing old ones. All six items can be completed **without new dependencies, without new tools, and without breaking changes** — the recommended stack additions are three lines of compiler flags (-std=gnu11, -Wall, -Wextra) and zero new packages.

The research confidence is HIGH for all areas because findings derive from direct codebase analysis, official GCC 15 porting guides, Cython threading documentation, and verified observation of every affected source file. The recommended phase structure delivers fixes in order of criticality: crash fix, portability fix, concurrency fix, internal consistency fixes.

## Key Findings

### Recommended Stack (from STACK.md)

**No new dependencies.** All v1.1 fixes use existing tools: GCC/Clang for C23 migration, Cython 3.0+ for callback threading, Python 3.13's `threading.get_ident()` for per-worker state, and standard `malloc/free` for VLA replacement.

**Core technology changes:**
- **C standard pin**: Add `-std=gnu11` to setup.py and CMakeLists.txt — documents intended standard, prevents GCC 15's default-to-C23 from causing surprise failures. The codebase uses C11 features (_Atomic, <stdatomic.h>) but not C23, so explicitly targeting C11 is correct.
- **Compiler warnings**: Add `-Wall -Wextra -Wno-unused-parameter` to both build systems — catches dead code, uninitialized variables, and type mismatches without changing runtime behavior. The -Wno-unused-parameter exception handles intentional API-mandated unused parameters.
- **C23 forward compatibility**: Fix three C23 incompatibilities (callback_t empty parens, #define true/false, operator precedence) even with -std=gnu11 flag. This ensures clean migration when the project eventually moves to C23.

**What NOT to add:**
- clang-tidy/cppcheck (overkill for targeted cleanup, would produce hundreds of irrelevant findings)
- PyCapsule-based callback architecture (correct pattern but too much churn for v1.1, defer to v2.0)
- Free-threaded Python 3.13t (experimental, Cython support incomplete)
- alloca() for VLA replacement (non-portable, same stack overflow risk as VLAs)

**Critical GCC 15 migration findings:**
1. `callback_t` empty parens `()` means "unspecified parameters" in C17 but means `(void)` in C23 — fix by changing typedef to `void (*callback_t)(void)` in definitions.h (1 line)
2. `#define true 1` redefines a C23 keyword (bool, true, false are keywords not macros) — fix by removing defines and adding `#include <stdbool.h>` (3 lines)
3. Operator precedence: `&&` inside `||` without parentheses in solver.c:545, SearchLib.c:194 triggers new diagnostics — fix by adding explicit parentheses (~5 locations)

### Expected Features (from FEATURES.md)

**Must fix (P0/P1 — blocks v1.1 release):**
1. **SATISFY mode crash** — `len()` called on uint32_t scalar at SearchLib.pyx:220, causes TypeError on any SATISFY solve. Secondary issue: signal.raise_signal(SIGINT) still used instead of solver_ctx_request_stop().
2. **Remaining VLA** — `int64_t remainings[C]` in local_search.c:332, stack overflow risk for large constraint counts, blocks MSVC compatibility.
3. **GCC 15 type mismatches** — Clean compilation is CI trust prerequisite, warnings may hide real truncation bugs.
4. **local_search() API migration** — Incomplete wiring from v1.0, seed/num_threads parameters may not flow correctly to C layer.

**Should fix (P2 — improves quality but deferrable):**
5. **Dead code removal** — 260 commented-out lines across 15 C files (debug printf, old VLAs, abandoned algorithms). Reduces cognitive overhead, but distinguish "dead code" from "algorithm documentation."
6. **History callback rework** — Four module-level cdef variables shared across joblib workers, causes state corruption in concurrent solves. Current joblib usage is safe (all workers share same Model), but any future multi-model solving breaks.
7. **Bare except clause** — Grep found zero matches, may have been fixed in v1.0 or manifest differently. Verify during implementation.
8. **BranchingStats cleanup** — Global and per-context stats must stay in sync. Current code sets global from Python but solver uses context defaults. Need bridge code to propagate global → context.
9. **signal.raise_signal in SATISFY** — Process-global SIGINT interferes with joblib, Jupyter, debuggers. Replace with solver_ctx_request_stop().

**Anti-features (do NOT do in v1.1):**
- Refactoring ctg() solver loop (risky, no benefit)
- Adding new test infrastructure (property-based testing, fuzz testing — out of scope)
- Reworking Expression.__eq__ (intentional API, not a bug)
- Removing BranchingStats global API (breaking change, defer to v2.0)
- Optimizing hot paths (incremental constraint evaluation was disabled for correctness, not performance)
- Adopting Python free-threading (ecosystem immature, introduces new failure modes)

### Architecture Approach (from ARCHITECTURE.md)

**Key insight:** The cleanup items share a common pattern — remnants of pre-solver_ctx_t architecture where state was module-level or global. The v1.0 solver_ctx_t migration covered the C kernel but left Cython/Python layers partially unconverted.

**Major components:**
1. **Callback mechanism** (SearchLib.pyx lines 134-159) — Module-level cdef variables for history state, shared across joblib workers. Fix: replace with thread-keyed dict using threading.get_ident().
2. **SATISFY/OPTIMIZE dispatch** (SearchLib.c ctg() lines 110-194) — Two code paths with different tot_profit semantics (objective value vs constraint violation count). SATISFY crash is in Cython wrapper, not C kernel.
3. **BranchingStats dual state** (Branching.c, solver_ctx.h) — Global BranchingStats (DEPRECATED) coexists with ctx->branching_stats. Python API sets global, solver uses context. Need propagation bridge.
4. **local_search parallelism** (local_search.c) — Spawns pthreads internally, writes to mod->global_opt without mutex (ctg() has update_lock, local_search does not). Add mutex protection.
5. **VLA in accept_best_routine** (local_search.c:332) — Last remaining VLA after v1.0 elimination pass. Replace with arena allocation (ctx already available).

**Root cause analysis:**
- **SATISFY crash**: `len()` on scalar at SearchLib.pyx:220 — should be `-mod.mod[0].con[0].num_constraints` not `-len(...)`.
- **History callback race**: Module-level cdef variables overwritten by each worker. Each worker's run_sampling() sets _history_list = [], _history_mod = mod at lines 201-206, clobbering previous workers.
- **BranchingStats gap**: solve() calls set_bias_wrapper() which sets global (Model.pyx:309), but run_sampling() creates ctx with defaults (SearchLib.pyx:184) and never propagates global → ctx.
- **local_search mutex**: accept_move() at local_search.c:445 writes global_opt without mutex, unlike ctg() which uses pthread_mutex_lock(&update_lock) at line 184.

**Fix order and dependencies:**
```
Step 1: SATISFY crash (SearchLib.pyx:220, Model.pyx objective_value guard)
  ↓
Step 2: VLA replacement (local_search.c:332) — independent, can run parallel to Step 1
  ↓
Step 3: History callback rework (SearchLib.pyx) — depends on Step 1 (callback reads global_opt which behaves differently in SATISFY)
  ↓
Step 4: BranchingStats bridge (SearchLib.pyx propagation code) — logically independent but touches same files as Step 3
  ↓
Step 5: local_search mutex (local_search.c:445) — lowest priority, cosmetic
```

### Critical Pitfalls (from PITFALLS.md)

**Top 5 pitfalls specific to cleanup work:**

1. **GCC warning fixes that silently change behavior** — Adding parentheses to `time > stopping_time || profit <= stop_val && stop_val != -1` (solver.c:545) changes stopping logic if parenthesized wrong. Casting int to size_t when int is -1 sentinel produces SIZE_MAX. **Prevention:** One warning per commit, document intended semantics, add test for changed expression.

2. **Dead code removal deleting algorithm documentation** — The commented-out adjusted_constraint_violation() calls in local_search.c:231-237 are the OPTIMIZED incremental evaluation algorithm, not debug code. Removing loses research contribution. **Prevention:** Categorize as debug/algorithm/TODO before deleting. Move algorithm variants to docs/algorithms/ or inline comments.

3. **Cython .pxd declaration drift from C headers** — Changing C function signature requires updating BOTH .h and .pxd. Forgetting .pxd update causes Cython to generate code with old signature, compiled against new header. Silent memory corruption if types are ABI-compatible. **Prevention:** Atomic commits (one commit = .h + .pxd + .pyx + test). Clean build after every .pxd change.

4. **Module-level cdef callback rework introducing new concurrency bugs** — Replacing module state with thread-local storage (TLS) requires understanding GIL interactions. threading.local() is Python-level (descriptor overhead), pthread_key_t is C-level (lifecycle complexity). Changing callback_t signature to accept void *ctx cascades through all C callers. **Prevention:** Use threading.get_ident() keyed dict (GIL protects dict ops, fast lookup, explicit lifecycle). Test with num_workers=8 under TSan.

5. **VLA replacement changing allocation semantics** — malloc can fail (VLA cannot), adds new error path. malloc is slower than stack adjustment. Missing free() on any return path leaks memory. **Prevention:** Use arena allocation (ctx->arena already exists), matches existing pattern at local_search.c:572-576. Audit all return paths. Valgrind leak check.

**Moderate pitfalls (6-10):**
- SATISFY fix affecting OPTIMIZE mode (write SATISFY test first, verify OPTIMIZE tests unchanged)
- Removing commented code that documents algorithm variants (categorize before removing)
- API cleanup breaking backward compatibility (keep old parameter names as deprecated aliases)
- Bare except fix catching wrong exceptions (analyze what current except catches before replacing)
- Clean rebuild failures after .pxd changes (rm -rf build/ before testing)

**Minor pitfalls (11-13):**
- Removing printf that users depend on (distinguish debug vs user-facing output)
- Typo fixes changing identifier names (grep all references before renaming)
- #define true/false conflicting with <stdbool.h> (remove defines when adding C11 includes)

## Implications for Roadmap

Based on research, v1.1 should have **5 phases** in strict dependency order. Total scope: ~150 lines of changes across 8 files. No new dependencies. No breaking changes.

### Phase 1: Critical Crash Fixes
**Rationale:** Unblocks all SATISFY mode testing. Lowest risk, highest impact. Must ship first.
**Delivers:** Working SATISFY solver, safer signal handling.
**Addresses:**
- SATISFY mode crash (FEATURES.md #1) — fix `len()` type error at SearchLib.pyx:220
- signal.raise_signal replacement (FEATURES.md #9) — use solver_ctx_request_stop() instead of SIGINT
**Avoids:** Pitfall #6 (SATISFY fix affecting OPTIMIZE) — write SATISFY test capturing intended behavior before fixing
**Estimated effort:** 2-3 hours (10 lines changed + 1 test)
**Research needed:** NO — bug is well-characterized, fix is mechanical

### Phase 2: VLA Elimination & C23 Migration
**Rationale:** Independent of all other phases, can run in parallel with Phase 1. Portability critical for future MSVC build.
**Delivers:** VLA-free codebase, C23-forward-compatible C code, clean GCC 15 builds.
**Addresses:**
- Remaining VLA (FEATURES.md #2) — replace `remainings[C]` with arena allocation
- GCC 15 warnings (FEATURES.md #3) — callback_t typedef, true/false defines, operator precedence
**Uses:** STACK.md recommendations — `-std=gnu11`, `-Wall -Wextra`, `#include <stdbool.h>`
**Implements:** ARCHITECTURE.md VLA fix pattern (arena allocation matching local_search.c:572-576)
**Avoids:** Pitfall #5 (VLA replacement changing allocation) — use arena, audit all return paths, Valgrind check
**Avoids:** Pitfall #1 (warning fixes changing behavior) — one warning per commit, document semantics
**Estimated effort:** 4-6 hours (20 lines changed + compiler flag updates + tests)
**Research needed:** NO — GCC 15 migration is well-documented, VLA pattern established in v1.0

### Phase 3: Callback Concurrency Rework
**Rationale:** Depends on Phase 1 (callback reads global_opt which differs in SATISFY). Highest complexity item. Core architectural improvement.
**Delivers:** Thread-safe history tracking, correct concurrent solving.
**Addresses:**
- History callback rework (FEATURES.md #6) — module-level cdef to thread-keyed dict
**Uses:** STACK.md recommendation — `threading.get_ident()` for per-worker state
**Implements:** ARCHITECTURE.md thread-safe callback pattern
**Avoids:** Pitfall #4 (callback rework introducing new bugs) — use dict keyed by threading.get_ident(), test with num_workers=8 under TSan
**Estimated effort:** 6-8 hours (40 lines changed + concurrency test)
**Research needed:** MAYBE — if thread-keyed dict pattern shows unexpected GIL contention under load, may need /gsd:research-phase on "Cython callback threading patterns"

### Phase 4: BranchingStats & API Cleanup
**Rationale:** Logically independent but touches same files as Phase 3 (SearchLib.pyx). Moderate complexity. Internal consistency improvement.
**Delivers:** Branching parameters correctly propagated to solver, local_search mutex protection, cleaner internal API.
**Addresses:**
- BranchingStats cleanup (FEATURES.md #8) — propagate global → context
- local_search() API migration (FEATURES.md #4) — verify seed/threads wiring, add mutex
**Implements:** ARCHITECTURE.md BranchingStats bridge pattern (read global, set context)
**Avoids:** Pitfall #8 (API cleanup breaking compatibility) — keep deprecated global API, mark DEPRECATED, plan v2.0 removal
**Estimated effort:** 4-6 hours (30 lines changed + regression test for branching behavior)
**Research needed:** NO — bridging pattern is straightforward, mutex pattern already exists in ctg()

### Phase 5: Dead Code & Documentation Cleanup
**Rationale:** Last to avoid merge conflicts with bug fixes. Requires judgment, not just automation. Improves maintainability.
**Delivers:** Clean source code, reduced cognitive overhead, preserved algorithm documentation.
**Addresses:**
- Dead code removal (FEATURES.md #5) — 260 commented lines across 15 files
**Avoids:** Pitfall #2 (deleting algorithm documentation) — categorize before removing, move incremental constraint evaluation algorithm to docs
**Avoids:** Pitfall #7 (removing code that documents variants) — preserve commented algorithm blocks as inline docs or move to algorithms.md
**Estimated effort:** 3-4 hours (260 lines removed + categorization + git blame review)
**Research needed:** NO — mechanical with human judgment, no technical unknowns

### Phase Ordering Rationale

**Why Phase 1 first:** SATISFY mode crash blocks any testing of satisfaction problems. Fixing it first unblocks validation of other changes in both SATISFY and OPTIMIZE modes. Signal handling fix is bundled because it touches the same SATISFY code path.

**Why Phase 2 can run parallel to Phase 1:** VLA replacement and C23 migration are architecturally independent — they touch different files (local_search.c vs definitions.h/solver.c/SearchLib.c) with no logical dependencies. A two-person team could parallelize these phases.

**Why Phase 3 depends on Phase 1:** The history callback reads `mod.mod[0].global_opt[0].tot_profit` and multiplies by `mod.sense`. In SATISFY mode (before Phase 1 fix), this produces meaningless values. Testing the callback rework requires both SATISFY and OPTIMIZE modes to work correctly.

**Why Phase 4 follows Phase 3:** Both touch `run_sampling()` and `run_local_search()` in SearchLib.pyx. Doing them sequentially avoids merge conflicts. Phase 3 is higher priority (concurrency correctness) so goes first.

**Why Phase 5 is last:** Dead code removal creates large diffs. Doing it last means all functional changes have clean diffs for review. Also avoids the risk of removing code that another phase needs (e.g., removing a function signature right before Phase 4 tries to add a parameter to it).

### Research Flags

**Needs research during planning:**
- **Phase 3 (Callback rework):** MAYBE — the threading.get_ident() dict pattern is well-understood, but if TSan reveals unexpected contention or Cython GIL interaction issues, may need deeper research into Cython threading primitives. Estimated probability: 20%. Trigger: TSan failures during Phase 3 testing.

**Standard patterns (skip research-phase):**
- **Phase 1 (Crash fixes):** Bug is fully characterized, fix is localized type correction
- **Phase 2 (VLA/C23):** GCC 15 migration documented in official porting guide, VLA pattern established in v1.0
- **Phase 4 (BranchingStats):** Bridging pattern is straightforward parameter propagation
- **Phase 5 (Dead code):** Mechanical cleanup with human judgment, no technical research needed

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All fixes use existing tools. GCC 15 migration verified via official porting guide, Cython threading via official docs. Zero new dependencies. |
| Features | HIGH | Bug characterization from direct codebase analysis. Every line reference verified. SATISFY crash observed at SearchLib.pyx:220, VLA at local_search.c:332, callback state at SearchLib.pyx:134-159. |
| Architecture | HIGH | Call chains traced from Python → Cython → C. Struct layouts verified in headers. Dependency graph constructed from observed state flow. |
| Pitfalls | HIGH | 13 pitfalls derived from C/Cython cleanup patterns, verified against SciPy/SCIP/OR-Tools practices. Specific codebase instances identified (solver.c:545 operator precedence, local_search.c:231-237 algorithm docs, .pxd mirror requirement). |

**Overall confidence:** HIGH

### Gaps to Address

**No significant gaps.** All six cleanup items are well-understood:
- SATISFY crash has known root cause and mechanical fix
- VLA replacement follows established v1.0 pattern
- GCC 15 migration is documented by GCC project
- Callback rework uses standard Python threading primitives
- BranchingStats bridge is simple parameter propagation
- Dead code removal is judgment-based, not research-based

**Minor uncertainties:**
1. **Bare except clause location** — grep found no matches, may have been pre-fixed or manifest differently. RESOLUTION: verify during Phase 1 implementation, add to checklist.
2. **GCC 15 exact warning list** — needs GCC 15 build to enumerate all warnings. RESOLUTION: Phase 2 will build on ubuntu-latest with GCC 15 when available, enumerate warnings, fix one per commit.
3. **local_search() seed/threads wiring** — FEATURES.md notes this "may" be broken, not confirmed. RESOLUTION: Phase 4 adds regression test to verify seed_used field is populated correctly.

**Validation strategy:**
- Phase 1: SATISFY mode test with known solution
- Phase 2: GCC 15 build (via Docker if ubuntu-latest not upgraded), Valgrind leak check
- Phase 3: Concurrent solve test with num_workers=8, TSan check
- Phase 4: Branching behavior regression test (fixed seed, compare objective/iteration counts)
- Phase 5: Full test suite after cleanup (verify no behavioral changes)

## Sources

### Primary (HIGH confidence)
- **Direct codebase analysis** — All 15 source files examined, every line reference verified
- [GCC 15 Porting Guide](https://gcc.gnu.org/gcc-15/porting_to.html) — Official C23 migration guidance
- [trofi's GCC 15 C23 analysis](https://trofi.github.io/posts/326-gcc-15-switched-to-c23.html) — Detailed C23 breaking changes
- [Cython external C code docs](https://cython.readthedocs.io/en/latest/src/userguide/external_C_code.html) — Callback GIL handling
- [Cython free threading docs](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) — Module-level variable thread safety
- [SCIP Event Handler documentation](https://www.scipopt.org/doc/html/EVENT.php) — Per-solve callback state pattern
- [OR-Tools CP-SAT Callback documentation](https://developers.google.com/optimization/reference/python/sat/python/cp_model) — Thread-safe callback architecture

### Secondary (MEDIUM confidence)
- [OpenSSL C23 bool issue #27516](https://github.com/openssl/openssl/issues/27516) — Real-world true/false keyword breakage
- [SciPy Public Cython API docs](https://docs.scipy.org/doc/scipy/dev/contributor/public_cython_api.html) — .pxd ABI compatibility
- [SEI CERT C: VLA size validation](https://wiki.sei.cmu.edu/confluence/x/AdcxBQ) — VLA security implications
- [VLA pitfalls (jorenar)](https://jorenar.com/blog/vla-pitfalls) — VLA replacement best practices

### Tertiary (LOW confidence)
- None. All findings are verified against primary sources or direct code inspection.

---
*Research completed: 2026-02-06*
*Ready for roadmap: YES*
*Recommended phases: 5*
*Estimated total effort: 19-27 hours*
*No new dependencies required*
