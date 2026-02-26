# Phase 18: Dead Code Removal - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove orphaned model_t fields and all remaining dead/commented-out code across C, Cython, and Python layers. The 4 explicit requirements (DEAD-01 through DEAD-04) are the minimum — a full sweep of all layers is in scope. No new functionality is added; the test suite must pass with zero new failures after all removals.

</domain>

<decisions>
## Implementation Decisions

### Sweep scope
- Full sweep across all three layers: C kernel, Cython bindings, Python layer
- Hit the 4 explicit requirements (DEAD-01–DEAD-04) first, then scan for other dead code
- No exclusions — sweep everything including tests, fixtures, benchmarks
- If code is confirmed dead and tests pass without it, remove it

### What counts as dead code
- Commented-out code blocks (/* ... */, //, #)
- Unused functions, unreachable branches, stale declarations
- Orphaned struct fields with no remaining references
- Unused #include directives and #ifdef blocks never triggered
- Unused Python imports
- Leave TODO/FIXME/HACK comments alone — they are informational, not dead code

### Removal ordering
- Bottom-up: C → Cython → Python (removing from foundation reveals stale references above)
- Incremental with test validation: run full test suite after each layer's removals
- Batch commits by layer (one commit per layer of removals)
- On test failure: revert the removal and investigate why the test depends on it before deciding

### Claude's Discretion
- Exact order of removals within each layer
- How to identify dead code (static analysis, grep, compiler warnings, manual inspection)
- Grouping of related removals within a layer commit

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for dead code identification and removal.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-dead-code-removal*
*Context gathered: 2026-02-25*
