# Phase 15: Solve API Migration - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove all keyword arguments from `solve()` so it accepts zero arguments. Every former solve() parameter becomes configurable via `set_param(name, value)` and readable via `get_param(name)`. The `bias` parameter is dropped entirely (replaced by `branching_bias` from Phase 14). The `manual_bias` and `bias_factor` params are silently removed (already superseded by `branching_weights` in Phase 14).

</domain>

<decisions>
## Implementation Decisions

### Parameter naming & grouping
- Keep original solve() parameter names exactly (M, bfs, stop_val, etc.) — no renaming
- Fix the `monte_calor_estimate` typo to `monte_carlo_estimate` — this is the one name change
- Flat keys only — no namespacing (set_param('M', 100), not set_param('solver.M', 100))
- Drop the `bias` param entirely — `branching_bias` from Phase 14 replaces it
- `manual_bias` and `bias_factor` silently removed — Phase 14's `branching_weights` supersedes them

### Default & reset behavior
- Params persist across multiple solve() calls — configure once, solve many
- `set_param(name, None)` resets that specific param to its default value
- No bulk reset_params() method — individual reset via None is sufficient
- Callback persists like all other params — consistent behavior, no special clearing
- `get_param(name)` always returns a value: the set value if configured, or the documented default — never returns None for params that have defaults

### Validation & error messages
- Validate at set-time — set_param('M', -5) raises immediately, fail fast
- Unknown parameter names raise ValueError — strict, catches typos immediately
- Type coercion when possible — set_param('M', '100') coerces to int, fails only when coercion impossible
- Warn on known conflicting parameter combinations — log warnings but don't block

### Deprecation transition
- Hard break in v2.0 — solve(M=100) raises TypeError, no deprecation period
- Simple rejection message — "TypeError: solve() takes no arguments"
- Removed params (bias, manual_bias, bias_factor) treated as unknown — standard ValueError, no special redirect messages

### Claude's Discretion
- Internal parameter storage implementation
- Coercion rules for each specific param type
- Which param combinations trigger conflict warnings
- How solve() internally reads from the params dict

</decisions>

<specifics>
## Specific Ideas

- The `monte_calor_estimate` → `monte_carlo_estimate` rename is the only name change from the original solve() signature
- "Configure once, solve many" pattern — researchers typically set params once and run multiple solves with different seeds

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-solve-api-migration*
*Context gathered: 2026-02-14*
