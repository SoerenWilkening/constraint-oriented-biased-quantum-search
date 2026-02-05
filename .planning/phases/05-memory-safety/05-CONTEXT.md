# Phase 5: Memory Safety - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix all memory leaks under normal operation and eliminate unsafe stack allocations (VLAs). The goal is zero leaks after a complete solve cycle, no stack overflow risk on large problems (10K+ constraints), and all code paths—including error paths—must be leak-free.

</domain>

<decisions>
## Implementation Decisions

### Leak Detection Scope
- All code paths must be leak-free, including error paths, timeouts, and exceptions
- Fix the pre-existing preprocessing() leaks tracked in STATE.md as part of this phase
- Audit both C kernel AND Cython layer for proper memory management (including Py_INCREF/DECREF patterns)
- All leak sources treated with equal priority—no specific ordering

### VLA Replacement Strategy
- Zero tolerance for VLAs—eliminate all VLAs in the codebase, even small fixed-size ones
- Buffers should support dynamic realloc if problem size somehow increases mid-solve
- Use descriptive names for scratch buffers in ctx (e.g., ctx->constraint_totals, ctx->constraint_remainings)
- Claude's discretion: choose pre-allocate in ctx vs. heap per-call based on performance vs. complexity tradeoff

### Large Problem Behavior
- Handle large problems (10K+ constraints) transparently—no arbitrary limits, if memory allows, solve it
- If malloc fails: propagate error status up, let Python layer raise MemoryError
- No pre-solve memory estimation needed—just try to allocate, fail if it fails
- Each thread gets its own scratch buffers—N threads = N× memory (no shared pool with locking)

### Validation Approach
- Both Valgrind AND ASan in CI for comprehensive coverage
- All existing tests must pass Valgrind with zero leaks
- Add new memory stress tests: create/destroy many models, run repeated solves, large problems
- Create suppressions file for known Python/numpy/Cython runtime leaks—our code must be clean

### Claude's Discretion
- Choice between pre-allocating buffers in ctx vs. heap allocation per-call (performance vs. complexity)
- Specific implementation of dynamic realloc for scratch buffers
- Which Python/Cython runtime leaks to suppress in Valgrind

</decisions>

<specifics>
## Specific Ideas

- preprocessing() leak is known—fix the realloc-to-zero issue completely
- Phase builds on solver_ctx_t architecture from Phase 3—scratch buffers can live in ctx
- VLAs like totals[C] and remainings[C] in explore_neighbourhood are the main targets

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-memory-safety*
*Context gathered: 2026-02-05*
