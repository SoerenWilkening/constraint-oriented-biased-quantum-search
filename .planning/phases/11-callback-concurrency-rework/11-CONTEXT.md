# Phase 11: Callback Concurrency Rework - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Thread-safe history tracking for concurrent solves. Replace module-level cdef callback state with per-thread/per-solve isolation so concurrent solve() calls on different Model instances (or the same Model with different parameters) produce independent, correct history lists. No breaking changes to existing API.

</domain>

<decisions>
## Implementation Decisions

### History semantics
- Each history entry is a tuple: (value, elapsed_seconds) — value is objective for OPTIMIZE, constraint satisfaction count for SATISFY
- Only record improvements: append when value is strictly better than last entry (convergence staircase, not full activity log)
- Unlimited history length — no cap needed since improvements-only keeps it small
- SATISFY mode format: (satisfaction_count, elapsed_seconds) — consistent tuple pattern across modes
- Empty history is valid when no improvements occur during solve

### Concurrency model
- Primary use case: parameter sweeps (same model structure, different params in parallel via ThreadPoolExecutor)
- Same Model instance must support concurrent solve() calls (e.g., different seeds simultaneously) — each call gets independent history
- Async/thread model: Claude's discretion — choose between thread ID keying vs solve-call ID based on GIL behavior analysis
- Worker threads (num_workers): Claude's discretion — decide whether orchestrator-only or merged histories based on current callback architecture

### Error & edge cases
- Partial history returned on stop/timeout — whatever was collected before stopping is included in OptimizeResult
- Callback exceptions: silent drop — log warning, skip entry, continue solving (history may be incomplete but solve not ruined)
- Immediate cleanup: per-thread/per-solve history state removed right after solve returns (no stale data, predictable memory)
- Empty history is valid (no guarantee of at least one entry)

### Deprecation strategy
- New API: solve(track_history=True) opt-in parameter — zero overhead when not tracking
- Old module-level callback: silent redirect to new mechanism (no warning, no breakage, v1.1 zero-breaking-change constraint)
- History access: OptimizeResult.history — per-solve ownership, no global state
- When track_history=False (default): OptimizeResult.history returns empty list [] (safe to iterate without checking)

### Claude's Discretion
- Thread ID vs solve-call ID for state isolation (based on GIL/C solver analysis)
- Worker thread history: orchestrator-only vs merged
- Internal data structures for thread-safe history collection
- Exact timestamp source (monotonic clock preferred)

</decisions>

<specifics>
## Specific Ideas

- History format (value, elapsed_seconds) enables convergence plotting without separate timing instrumentation
- Silent redirect of old API means existing user code works unchanged — discovery of new track_history parameter is organic
- Parameter sweep is the primary concurrent use case — design should optimize for ThreadPoolExecutor with 4-8 concurrent solves

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-callback-concurrency-rework*
*Context gathered: 2026-02-08*
