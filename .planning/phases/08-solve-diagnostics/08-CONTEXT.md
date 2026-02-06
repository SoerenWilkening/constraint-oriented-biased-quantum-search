# Phase 8: Solve Diagnostics - Context

**Gathered:** 2026-02-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Researchers get a structured result object from solve() and local_search() containing everything needed to analyze solver behavior: solution, objective, feasibility, timing, iteration count, oracle calls, and improvement history. No manual instrumentation needed.

</domain>

<decisions>
## Implementation Decisions

### Result object design
- Class name: `OptimizeResult` (matches scipy convention, familiar to researchers)
- Named attribute access: `result.objective`, `result.solution`, etc. (not dict-style)
- Short `__repr__`: `OptimizeResult(obj=42.0, feasible=True, time=1.23ms, iterations=5000)` for quick checks
- Detailed `.summary()` method for multi-line formatted report
- `.to_dict()` method returning JSON-serializable dictionary for logging/persistence

### Improvement history
- Records only when a new best objective is found (not every iteration)
- Each entry contains: (iteration, objective_value, elapsed_ms, is_feasible)
- No cap on history entries — improvements are rare relative to total iterations
- Works alongside existing callback mechanism — callback still fires for real-time use, history accumulates in result for post-solve analysis
- History hooks into existing callback infrastructure rather than adding new C-level instrumentation

### Timing breakdown
- Two segments: preprocessing_time + solve_time (strict split, total = sum of both)
- Wall clock only (no CPU time)
- Stored in milliseconds (float) — e.g., 1234.5 ms

### API integration
- **Breaking change**: solve() and local_search() both always return OptimizeResult
- Solution accessible via `result.solution` (no opt-in parameter)
- Verification results included in result: `result.verified`, `result.violations` (integrates Phase 7's verify_solution)
- Reproducibility fields: `result.num_threads` and `result.seed` included

### Claude's Discretion
- Internal implementation of timing instrumentation points
- How to wire history accumulation into the existing callback
- OptimizeResult field ordering and summary formatting
- How to handle the breaking change in existing tests

</decisions>

<specifics>
## Specific Ideas

- Follow scipy.optimize.OptimizeResult naming convention — researchers are familiar with it
- Improvements are already tracked via a callback function; the history should build on that mechanism
- Include enough in the result object that a researcher can reproduce the run (seed, threads) and analyze convergence (history) from a single object

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-solve-diagnostics*
*Context gathered: 2026-02-06*
