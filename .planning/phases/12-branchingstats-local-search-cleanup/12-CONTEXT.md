# Phase 12: BranchingStats & Local Search Cleanup - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Branching parameters set via Python API actually reach the solver, and local_search writes to shared state safely. Includes introducing a generic `set_param`/`get_param` API on Model, deprecating old global setters, propagating branching params to both sampling and local search solvers, and adding mutex protection for `global_opt` writes in `accept_best_routine`.

</domain>

<decisions>
## Implementation Decisions

### Deprecation Strategy
- Deprecated global branching setters emit `DeprecationWarning` once per session (Python default warning filter)
- Warning message is generic (e.g., "set_branching_bias is deprecated"), no migration hint
- If user passes branching via both `set_param` and old global setter, `set_param` wins silently
- Claude's Discretion: whether deprecated setters remain functional or become no-ops (constrained by "no breaking changes" rule)

### Branching API Surface
- New generic `model.set_param(name, value)` and `model.get_param(name)` methods on Model
- Strict validation: `set_param` raises `ValueError` on unknown parameter names
- Supports all solver parameters initially (num_workers, timeout, track_history, branching_bias, branching_factors, etc.)
- Parameters persist across multiple `solve()` calls until changed
- Existing `solve()` keyword arguments remain for backward compatibility
- **Precedence: `set_param` values win over `solve()` kwargs** — if both are specified, `set_param` value is used
- `solve()` kwargs exist for backward compat only; they do NOT override `set_param` values

### Mutex Scope
- Global mutex (single mutex protecting all `global_opt` writes)
- Mutex protects writes only in `accept_best_routine` — reads are not locked
- If mutex lock fails, skip the write (solver continues, loses one update)
- Claude's Discretion: blocking `pthread_mutex_lock` vs non-blocking `pthread_mutex_trylock`

### Verification Approach
- Deterministic test: fixed seed + known problem, assert exact solution match with branching params applied
- Combined test exercising both sampling solver and local search solver paths
- ThreadSanitizer test runs in CI automatically (catches regressions on every push)
- Deprecation warning test verifies `DeprecationWarning` type only (not message text)

</decisions>

<specifics>
## Specific Ideas

- User wants `set_param` style (like `model.set_param("branching_bias", value)`) rather than solve() kwargs or dedicated methods
- Generic parameter API is extensible for future solver parameters
- `set_param` is the canonical way to configure solver behavior; `solve()` kwargs are legacy

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-branchingstats-local-search-cleanup*
*Context gathered: 2026-02-08*
