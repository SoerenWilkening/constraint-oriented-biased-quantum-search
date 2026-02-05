# Phase 3: Solver Context Architecture - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Introduce an explicit `solver_ctx_t` struct that carries all per-solve mutable state through call chains, eliminating global variables (BranchingStats, stop flag) that cause data races. This is purely internal C kernel refactoring — no Python API changes.

</domain>

<decisions>
## Implementation Decisions

### Context struct scope
- Minimal initial scope: BranchingStats + stop flag + timeout only
- Later phases add more (PRNGs in Phase 4, arena in Phase 6)
- Fixed struct with known fields — no reserved space for future expansion
- Transparent struct definition in header (not opaque)

### Context ownership
- Claude's discretion based on existing memory patterns in codebase

### API surface
- No Python API changes — purely internal C refactoring
- Cython layer allocates ctx, passes to C, frees after solve (minimal change)
- Debug stats accessible via CBQS_DEBUG=1 environment variable
- Debug output includes branching stats + basic solve timing
- Debug format: JSON to stderr

### Migration strategy
- Incremental function-by-function migration
- No fallback to globals — migrated functions require ctx (compile errors catch missing updates)
- Per-function atomic commits for easy bisection
- Bottom-up migration order: leaf functions first, entry points last

### Stop signal design
- Atomic boolean flag in solver_ctx_t (replaces signal.raise_signal pattern)
- Workers check stop flag every N iterations (100-1000, Claude determines optimal)
- Timeout built in: ctx->timeout_ms + ctx->start_time fields
- On stop/timeout: return best solution found so far (graceful degradation)

### Claude's Discretion
- Context ownership pattern (caller-owns vs solver-owns)
- Exact N for stop flag check frequency
- Which C type for atomic boolean (stdatomic.h vs compiler intrinsics)
- Migration order of specific functions within bottom-up strategy

</decisions>

<specifics>
## Specific Ideas

- "I want debug output in JSON for programmatic parsing"
- Per-function commits allow git bisect if issues arise
- Bottom-up migration minimizes temporary scaffolding
- No fallback to globals ensures complete migration (compile errors are features)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-solver-context-architecture*
*Context gathered: 2026-02-05*
