# Phase 4: Thread Isolation - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Each worker thread operates with fully isolated random state and the user controls parallelism at runtime. This phase delivers per-thread PRNG instances (replacing global `rand()` calls), runtime-configurable thread count (replacing compile-time `NUMThreads`), and deterministic results when same seed + thread count are used.

</domain>

<decisions>
## Implementation Decisions

### PRNG Selection
- Use xoshiro256** algorithm — fast, high-quality, widely used in scientific computing
- PRNG state lives in thread-local storage (`__thread` or `pthread_key_t`)
- Claude's discretion on seeding strategy (jump functions vs hash-based derivation)
- PRNG is internal implementation detail — users see only seed parameter, not PRNG state

### Seed Management
- Model has a default seed attribute, solve() can override per-call
- If user doesn't provide a seed, use system entropy (/dev/urandom or time-based) — non-deterministic by default
- Result object includes the actual seed used (especially useful when auto-generated)
- Provide single-threaded mode for strict determinism regardless of thread count

### Thread Count API
- Thread count set via Model attribute (`model.num_threads = N`)
- Default thread count: auto-detect all available CPU cores
- Environment variable `CBQS_THREADS` available for override
- Claude's discretion on precedence (Model attribute vs env var)

### Determinism Guarantees
- Guarantee: same seed + same thread count = same result (on same machine/build)
- Cross-platform reproducibility not guaranteed
- Claude's discretion on handling thread scheduling (static work assignment vs deterministic reduction)
- CI test suite verifies determinism (run same problem twice with same seed, assert identical)
- Replace ALL global `rand()` calls with thread-local PRNG — full audit

### Migration Path
- Silent migration — new behavior just works, no warnings for existing code
- Ignore any existing `srand()` calls — new PRNG system is completely separate
- Remove `NUMThreads` compile-time constant entirely — clean break
- Update docstrings only — no separate migration guide needed

### Claude's Discretion
- Seeding strategy (jump functions vs hash-based seed derivation)
- Thread count precedence order (env var vs Model attribute)
- Thread scheduling approach for determinism
- Thread-local storage implementation (`__thread` vs `pthread_key_t`)

</decisions>

<specifics>
## Specific Ideas

- Result object should include seed_used field for reproducibility tracking
- Single-threaded mode (threads=1) should be the escape hatch for exact reproducibility when debugging

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-thread-isolation*
*Context gathered: 2026-02-05*
