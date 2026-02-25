# Phase 20: API Consistency - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Unify parameter naming across C/Cython/Python layers, audit _PARAM_DEFS for disconnected entries (both directions), and align Cython type declarations with C headers. No new parameters or features — this is a consistency and correctness pass.

</domain>

<decisions>
## Implementation Decisions

### Parameter naming
- Canonical name for look-ahead depth factor: `look_ahead_factor` across all three layers
- Full audit of ALL parameter names across C, Cython, and Python — not just known mismatches
- "Best name wins" — the most descriptive/consistent name is chosen regardless of which layer currently uses it
- Same name must appear identically in C struct fields, Cython .pxd declarations, and Python _PARAM_DEFS — no translation or mapping layer
- C struct fields will be renamed if needed to match the chosen canonical name
- snake_case enforced everywhere, including C struct fields
- Naming pattern: `noun_qualifier` (domain-first), e.g., `constraint_weight`, `search_depth`
- Prefer shorter names when equally descriptive
- Common abbreviations allowed: num, iter, temp, max, min — but not obscure ones
- Boolean parameters: no `is_` or `use_` prefix (just `verbose`, not `is_verbose`)
- Count parameters: `num_` prefix (e.g., `num_iterations`, not `iteration_count`)
- Produce a committed before/after audit report (markdown table) documenting all renames

### Orphan handling
- Remove orphaned _PARAM_DEFS entries outright — clean break, no deprecation warnings
- If removal means old user scripts fail, that's acceptable (the param was silently doing nothing anyway)
- Bidirectional audit: also find C params accessible via set_param/get_param that are NOT in _PARAM_DEFS
- Unexposed C params should be added to _PARAM_DEFS for full consistency

### Backward compatibility
- No aliases for renamed parameters — old names stop working immediately
- All tests updated to use new canonical names only — no testing of old names
- Create migration notes (brief document listing old → new param name mappings)

### Type alignment
- Cython .pxd declarations must use exact C typedef names (uint32_t, not unsigned int)
- Full type audit — all types in .pxd files checked against C headers, not just integer widths
- Only declare struct fields in .pxd that Cython/Python code actually accesses — keep declarations minimal
- Audit includes both struct field types AND function signatures (return types, parameter types)

### Claude's Discretion
- Whether to bump version number in this phase or defer to Phase 21 (Build & Packaging)
- Order of operations for the cross-layer renames
- How to handle any edge cases discovered during the audit

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 20-api-consistency*
*Context gathered: 2026-02-25*
