# Phase 6: Memory Optimization - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Eliminate hot-path allocations in the solver's inner loop through arena allocation, and make Expression storage scale with actual term count rather than fixed MAXCLAUSESIZE. This is internal optimization — the Python API remains stable.

</domain>

<decisions>
## Implementation Decisions

### Expression sizing strategy
- **Growth factor**: 2x (double capacity) when array needs to grow
- **Small-object optimization**: Inline storage for ≤8 terms (no heap allocation for small expressions)
- **Initial heap capacity**: 32 terms when expression exceeds inline threshold
- **No reserve() method**: Automatic growth only, keep API simple
- **No shrinking**: Once allocated, capacity stays — avoid realloc churn
- **Allocation failure**: Raise Python MemoryError exception, propagate cleanly
- **MAXCLAUSESIZE**: Remove entirely — no artificial limits, dynamic allocation handles any size
- **Unified approach**: Constraint storage uses same sizing strategy (8-term inline, 2x growth)

### Arena allocation scope
- **Lifetime**: Per-solve — arena created at solve start, freed at solve end, reset between iterations
- **Structure**: Single bump allocator — simple pointer bump, reset to start between iterations
- **Overflow handling**: Allocate new chunk and chain together — arena grows as needed, no hard limit
- **Initial size**: Fixed 1MB default

### Benchmark requirements
- **Success threshold**: Any statistically significant improvement (p<0.05), not a fixed percentage
- **Problem types**: Create representative benchmark suite — small/medium/large problems, sparse and dense constraints
- **CI integration**: Regression guard — track benchmark times in CI, fail if performance regresses significantly
- **Output format**: JSON for tooling — machine-readable for CI tracking and visualization

### API surface changes
- **Expression capacity**: Not exposed — internal implementation detail, users see len() only
- **Arena size**: Not configurable — 1MB default, internal tuning only
- **Backward compatibility**: Minor API tweaks acceptable if they improve the API, document in changelog
- **Memory stats**: Debug build only — CBQS_DEBUG=1 enables allocation stats, not in release builds

### Claude's Discretion
- Specific chunk size for arena overflow
- Benchmark suite problem parameters (exact constraint counts, variable counts)
- JSON schema for benchmark output
- How to detect CI performance regression (stddev threshold, etc.)

</decisions>

<specifics>
## Specific Ideas

- Expression inline threshold of 8 terms was chosen explicitly — "most expressions are small"
- Initial heap capacity of 32 terms provides headroom for medium expressions
- Single bump allocator chosen for simplicity over size-class pools
- Benchmark results should be machine-parseable for CI tooling integration

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-memory-optimization*
*Context gathered: 2026-02-05*
