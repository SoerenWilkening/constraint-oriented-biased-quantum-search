# Phase 14: Unified Branching Model - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the dual-array branching struct (obj_dependent + constraint_dependent) with a single unified weights array and a 3-term formula at the C layer. Expose the new model through `set_param('branching_weights', array)`. The old dual-array fields, old C setters, and old Cython wrappers are removed in this and later phases.

</domain>

<decisions>
## Implementation Decisions

### Array Semantics
- One weight per decision variable — array length = num_variables
- Array length must strictly match num_variables; error if mismatched
- Weight of 0.0 means no branching preference (neutral) — assignment_bias and look_ahead still apply
- Weights are auto-normalized before use in the 3-term formula

### Default Behavior
- When no branching_weights are set, the pointer is NULL — BranchingFunction skips the weights term entirely
- When weights=NULL, the formula simplifies to 2 terms: `assignment_bias * bias_factor + look_ahead * look_factor`
- branching_factor defaults to 1.0
- bias_factor and look_factor default to matching existing code behavior (Claude determines exact values from current implementation)
- `set_param('branching_weights', None)` is allowed — clears weights back to NULL
- Weights persist across multiple solve() calls (sticky, like other params)
- All three factors (branching_factor, bias_factor, look_factor) are exposed as settable params via set_param()

### Validation & Errors
- Wrong-sized array raises ValueError immediately at set_param() time: "Expected array of length N, got M"
- Negative weight values are rejected with ValueError
- NaN and Inf values are rejected with ValueError
- Factor values (branching_factor, bias_factor, look_factor) must be non-negative; reject with ValueError otherwise

### Migration from Old API
- Old branching setters (set_obj_dependence, set_constraint_dependence) are removed immediately in Phase 14 — no deprecation period
- Old struct fields (objective_factor, constraint_factor, obj_dependent, constraint_dependent) are deleted — compile error for any code referencing them, no compat macros
- Phase 14 updates existing branching tests just enough to compile and pass with the new struct — keeps CI green
- No per-phase migration docs; migration guide deferred to v2.0 release notes

### Claude's Discretion
- Exact normalization algorithm (L1, L2, max-norm, etc.)
- Internal memory layout and allocation strategy for the weights array
- Exact default values for bias_factor and look_factor (derived from current code behavior)
- How the 3-term formula interacts with existing BranchingFunction internals

</decisions>

<specifics>
## Specific Ideas

- The 3-term formula: `branching_weights * branching_factor + assignment_bias * bias_factor + look_ahead * look_factor`
- This is a v2.0 hard breaking change — no backward compatibility shims
- Clean struct: just `double *branching_weights` + `double branching_factor` replacing the old dual fields

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-unified-branching-model*
*Context gathered: 2026-02-14*
