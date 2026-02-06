# Phase 7: API Robustness - Context

**Gathered:** 2026-02-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Input validation and solution verification for the CBQS solver API. The solver rejects invalid inputs with clear error messages before solve begins, and can verify that returned solutions are actually correct. This phase covers the Python-facing API layer that researchers interact with.

</domain>

<decisions>
## Implementation Decisions

### Validation Strictness
- Duplicate variable indices in constraints: merge coefficients silently (3*x1 + 5*x1 -> 8*x1)
- Validation timing: eager — validate at construction time (Expression, Constraint creation), not at solve time
- NaN and Inf coefficients: always reject immediately (both are invalid in this solver)
- Inconsistent variable bounds (upper < lower): raise error — this is always a modeling bug

### Error Reporting Style
- Use standard Python exceptions (ValueError, TypeError) — no custom exception hierarchy
- Detailed error messages with context: include the offending value, valid range, and which object triggered it (e.g., "Variable index -3 is out of range [0, 99] in constraint 'power_limit'")
- Fail on first validation error — don't collect multiple errors
- Validation is bypassable with `validate=False` flag for performance-critical batch runs

### Post-solve Verification
- Off by default, opt-in — user calls with `verify=True` or calls a verify method after solve
- On violation: emit Python warning and set a flag on the result (e.g., result.verified=False) — don't raise exception
- Verification scope: check both constraint satisfaction AND recompute objective value to confirm match
- Objective comparison tolerance: small epsilon (e.g., 1e-9) to handle floating-point drift in intermediate math

### Edge Case Policy
- Empty model (no variables or no constraints): raise error — always a bug
- All-zero coefficients in constraints: warn and solve — technically valid but probably unintended
- Redundant/duplicate constraints: allow silently — doesn't break anything
- Very large models (100K+ variables): proceed silently — don't second-guess researchers

### Claude's Discretion
- Exact epsilon value for objective comparison
- Internal implementation of validation checks (C-level vs Python-level)
- Whether validate=False skips all checks or only expensive ones
- Warning category/class for post-solve violation warnings

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

*Phase: 07-api-robustness*
*Context gathered: 2026-02-06*
