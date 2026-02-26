# Phase 19: Incremental Evaluation - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace full constraint recalculation with incremental evaluation in the classical `local_search` path (`explore_neighbourhood` and `accept_best_routine`), and benchmark the change across representative problem sizes. The incremental function `adjusted_constraint_violation()` already exists and is proven in `quantum_local_search_states()` — this phase adopts it in the remaining hot loops.

</domain>

<decisions>
## Implementation Decisions

### Benchmark design
- Cover a representative range of problem sizes: small (10-20 vars), medium (50-100 vars), and large (200+ vars)
- Vary both variable count and constraint count to show how incremental benefits from sparsity
- 5 timing runs per configuration, report median wall-clock time
- Python script drives the solver via existing bindings (no standalone C harness)
- Output as a BENCHMARK.md markdown table committed alongside the code change

### Adoption scope
- Replace full-recalc `constraint_violation()` loop in both `explore_neighbourhood()` AND `accept_best_routine()`
- Mirror the pattern already proven in `quantum_local_search_states()`: use `prepare_constraints()` + `adjusted_constraint_violation()` for incremental delta computation
- Remove old full-recalc code entirely after adoption — no compile flags, no conditional paths (consistent with Phase 18's dead code cleanup philosophy)

### Correctness validation
- Add a side-by-side comparison test to existing `test_constraint.c` that runs both full-recalc and incremental paths on the same inputs
- Assert exact integer equality (all constraint math is int64_t, no floating-point drift)
- Existing 446 tests provide additional regression coverage

### Performance expectations
- Commit fully to the incremental path — no auto-switching based on problem size
- Any measurable improvement on larger problems is sufficient for success
- Accept possible minor slowdown on tiny problems (they're fast either way, and one code path is cleaner)

### Claude's Discretion
- Exact benchmark problem generation (how to construct representative constraint sets)
- Integration details for threading/arena allocation compatibility in the incremental path
- BENCHMARK.md table formatting and column layout

</decisions>

<specifics>
## Specific Ideas

- The `quantum_local_search_states()` function (local_search.c:533-637) is the reference implementation for incremental adoption — mirror its pattern of `prepare_constraints()` + double `adjusted_constraint_violation()` call (positive then negative indices)
- `explore_neighbourhood()` lines 194-196 is the primary hot loop to replace (iterates all constraints with full `constraint_violation()` per move)
- `accept_best_routine()` line 295 is the secondary replacement site

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 19-incremental-evaluation*
*Context gathered: 2026-02-25*
