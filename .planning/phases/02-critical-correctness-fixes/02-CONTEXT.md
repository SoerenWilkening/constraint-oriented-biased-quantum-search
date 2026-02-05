# Phase 2: Critical Correctness Fixes - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix bugs that produce silently wrong results: use-after-free in accept_best_routine, excessive reallocation in sparse preprocessing, and Expression mutation that corrupts earlier expressions. The solver must produce correct results under ASan/Valgrind without heap errors.

</domain>

<decisions>
## Implementation Decisions

### Expression immutability
- Standard operators (__add__, __mul__, etc.) return new Expression objects (Claude decides copy strategy)
- `+=`, `-=`, `*=` etc. (__iadd__, __imul__) mutate in place — matches Python int behavior
- Provide explicit in-place methods (add_inplace, mul_inplace, etc.) for performance-critical code
- Copies are always deep copies — separate underlying C arrays, no aliasing
- Each Expression gets its own coefficient for shared IntegerVariables — no cross-talk between expressions
- Implement `__deepcopy__` for Python copy module; skip `__copy__` since shallow doesn't make sense
- No `.copy()` convenience method — users use `copy.deepcopy(expr)`
- Claude decides: whether Expression is consumed when creating Constraint, or reusable

### Error behavior
- Claude decides: logging level when fixes avoid what would have been bugs
- Warn once when sparse preprocessing reallocation triggers excessively (performance regression)
- Debug mode enabled via `CBQS_DEBUG=1` environment variable for detailed internal logging

### Validation approach
- ASan in CI only — no extra runtime checks in release builds (maximum performance)
- Add specific regression tests for each bug being fixed (use-after-free, Expression mutation, reallocation)
- Run Valgrind in CI in addition to ASan for deeper memory analysis
- Add stress test that runs 100+ solves in a loop to surface memory issues

### API compatibility
- Emit deprecation warning when old Expression mutation behavior would have been used
- Warning period: one minor version, then remove warning
- Provide way to suppress deprecation warning (env var or filter) for users who have updated
- Update documentation with correct Expression usage patterns
- Add changelog entry documenting the behavioral fix

### Git Workflow
- Work on `feature/feature_branch` per Git Flow
- Merge to `main` via pull request after phase completion

### Claude's Discretion
- Exact copy strategy for standard operators (always-copy vs copy-on-write)
- Whether Expression is consumed/invalidated when creating Constraint
- Debug logging format and verbosity levels
- Exact implementation of deprecation warning suppression mechanism

</decisions>

<specifics>
## Specific Ideas

- In-place operators (`+=`) should feel like Python built-ins — mutate and return self
- Deprecation warning should be actionable — tell users exactly what to change
- Stress test should catch issues that only surface after many iterations

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-critical-correctness-fixes*
*Context gathered: 2026-02-05*
