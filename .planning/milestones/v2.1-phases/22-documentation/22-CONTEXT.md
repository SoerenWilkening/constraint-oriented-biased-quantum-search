# Phase 22: Documentation - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Fill all docstring gaps across Python classes (Model, Expression, Constraint) and add algorithmic comments to the C kernel for branching formula, preprocessing, look-ahead logic, and all _PARAM_DEFS entries. No new features, no API changes — documentation only.

</domain>

<decisions>
## Implementation Decisions

### Docstring style & depth
- NumPy-style docstrings (Parameters, Returns, Raises, Examples sections with dashes)
- Include Examples section for the 5-10 most important/complex methods (e.g. Model.solve, Model.add_constraint); skip examples for trivial getters/setters
- Types appear in docstring Parameters section (e.g. `param : int`) rather than relying solely on type hints
- Include Raises section listing exceptions and when they occur for all public methods that raise

### C algorithm comments
- High-level block comments explaining WHAT each algorithm computes and WHY — not line-by-line narration
- Include mathematical formulas inline where they clarify the code (e.g. `bias = alpha * violation^beta`)
- Reference papers only when directly relevant
- Document branching, preprocessing, and look-ahead as independent standalone blocks — no system overview tying them together
- Use `/* ... */` multi-line block comment style

### Parameter documentation (_PARAM_DEFS)
- One sentence describing what the parameter controls, plus valid range/options and default value
- Always include default value for every parameter
- Note mutability: mark each param as "set before solve" or "can be changed mid-solve"
- For enum/choice parameters, explicitly list all valid values with a brief note for each (e.g. `"greedy" (fast, less optimal), "random" (stochastic), "adaptive" (default, adjusts during solve)`)

### Coverage scope
- Public methods only (no underscore-prefixed methods)
- Non-obvious dunder methods get docstrings (e.g. `__add__` for Expression combining); skip standard dunders (`__repr__`, `__str__`, `__init__`)
- Class-level docstrings for Model, Expression, Constraint: purpose summary, typical usage, key methods listed
- Thin wrappers over Cython/C get full docstrings from the user's perspective — document what it does, not that it wraps something

### Claude's Discretion
- Exact wording and phrasing of docstrings
- Which methods qualify as "key" for Examples sections
- Which dunders are "non-obvious" enough to warrant docstrings
- Order of Parameters within docstrings
- Level of detail in C algorithm comments for straightforward code sections

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

*Phase: 22-documentation*
*Context gathered: 2026-02-26*
