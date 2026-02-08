# Phase 13: Dead Code & Documentation Cleanup - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove dead code, eliminate bare except clauses, and document local_search fields with read/write annotations. Pure codebase hygiene — no behavioral changes. Full test suite must pass after all removals.

</domain>

<decisions>
## Implementation Decisions

### Dead code scope
- Claude's discretion on commented-out code beyond the specific lines called out (VLA ~line 158/445, debug prints) — remove obvious dead code, keep intentional notes
- Claude's discretion on unused functions/variables — remove if confirmed unreachable, keep if intentionally retained
- Active unguarded debug printf/print statements: remove or guard behind CBQS_DEBUG (not just commented-out ones)
- Stale #ifdef/#ifndef blocks: clean up preprocessor guards for conditions that no longer apply
- Claude's discretion on preserving TODO/FIXME comments and intentional notes vs. removing dead code

### Exception specificity
- Claude's discretion on exception type per catch site — use narrowest appropriate type based on what can actually be raised
- Silent exception handling preserved — just specify the type, don't add logging
- Check ALL Cython files (.pyx) for bare excepts, not just Model.pyx
- Production code only — leave test file bare excepts alone

### Field annotation style
- Header comment table format above each function: "Reads: field1, field2 | Writes: field3, field4"
- Include mutex protection notes — mark which writes are mutex-protected vs. unprotected
- Annotate local_search() plus other major solver functions (sampling_solver(), preprocessing(), etc.)
- Claude's discretion on flat list vs. semantic grouping — pick the clearest format based on field count

### Cleanup boundary
- Full codebase sweep: all .c, .h, .pyx, .py, CMake, and CI config files
- CMake/CI cleanup included: remove stale targets, outdated workarounds, unused variables in build configs
- Minor style fixes allowed when encountered during cleanup (but no wholesale reformatting)

### Claude's Discretion
- Whether specific commented-out code blocks are "dead code" or "intentional reference notes"
- Which unused functions/variables to remove vs. keep
- Exception type narrowness per catch site
- Flat vs. semantic grouping for field annotation tables
- Which style inconsistencies warrant fixing vs. leaving alone

</decisions>

<specifics>
## Specific Ideas

- "Nothing sacred" attitude toward commented-out code — it's in git history if needed
- Active debug prints should either be removed or guarded, not left unguarded in production code
- Field annotations should note concurrency safety (mutex usage) to help future developers

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-dead-code-documentation-cleanup*
*Context gathered: 2026-02-08*
