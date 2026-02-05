# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-04)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** Phase 6 Memory Optimization in progress

## Current Position

Phase: 6 of 8 (Memory Optimization)
Plan: 4 of 4 complete (06-01, 06-02, 06-03, 06-04 done)
Status: Phase 6 complete
Last activity: 2026-02-05 - Completed 06-04-PLAN.md (benchmark suite)

Progress: [████████████] 91% (29 plans of 32 total through Phase 6)

## Performance Metrics

**Velocity:**
- Total plans completed: 25
- Average duration: ~7m
- Total execution time: ~3 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5/5 | ~46m | ~9m |
| 02 | 6/6 | ~39m | ~6m |
| 03 | 5/5 | ~47m | ~9.4m |
| 04 | 3/3 | ~31m | ~10m |
| 05 | 5/5 | ~106m | ~21m |
| 06 | 4/4 | ~16m | ~4m |

**Recent Trend:**
- Last 5 plans: 05-05 (~12m), 06-01 (~3m), 06-02 (~4m), 06-03 (~4m), 06-04 (~5m)
- Trend: Phase 6 Memory Optimization COMPLETE - arena allocator, dynamic expression, solver context arena, and benchmark suite all done

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Cleanup before features: Stabilize foundation before extending branching/integer UX
- Dynamic expression arrays: Fixed-size wastes memory on small expressions, limits large ones
- Encapsulate global state: BranchingStats as global breaks thread safety in parallel solves
- Explicit per-target source deps in test CMake: SearchLib.c needs Python.h, local_search.c has type errors
- Feasibility-only solve verification: heuristic solver means tests check constraint satisfaction, not optimality
- xfail for Expression mutation bug: Expression.__add__ mutates self and returns self, Phase 2 fix - FIXED in 02-03
- Build expressions term-by-term to avoid multiply_constant pitfall (01-02)
- Setup/teardown fixtures for BranchingStats global reset (01-02)
- Python3 include discovery for SearchLib.c test compilation (01-03)
- cmocka FetchContent URL switched to gitlab.com mirror (01-03)
- free_incumbents uses num_states(0) instead of allocated(1024) -- pre-existing leak (01-03)
- Disable ASan leak detection in CI due to pre-existing preprocessing() leaks (01-05) - RE-ENABLED in 05-04
- Skip Metal_executor build on Linux -- requires macOS Objective-C runtime (01-05)
- Filter ctest to project tests only, exclude cmocka internal tests (01-05)
- Thread cleanup after pthread_join, not pthread_create (02-01)
- Realloc condition uses == 0 && counter > 0 pattern (02-01)
- copy_expression_contents added for deep copying (02-02)
- Standard operators return new objects, in-place operators mutate self (02-03)
- In-place operators match Python int behavior: mutate and return self (02-04)
- Deprecation warning is informational, respects CBQS_SUPPRESS_DEPRECATION env var (02-05)
- Made CircuitBackendBinder and Model imports optional (02-05)
- Valgrind tests subset of critical tests due to performance overhead (02-06)
- Stress tests run separately from unit tests in CI for visibility (02-06)
- Embedded BranchingStats_t in solver_ctx_t for cache locality (03-01)
- atomic_bool for stop signal - lower overhead than mutex for single flag (03-01)
- CLOCK_MONOTONIC for timeout - not affected by system time changes (03-01)
- _GNU_SOURCE for BSD type compatibility with intarray.h u_int64_t (03-01)
- Forward declaration in Branching.h to avoid circular include with solver_ctx.h (03-02)
- Preserve global BranchingStats and setters with DEPRECATED comments for backward compatibility (03-02)
- g_active_ctx pattern for signal handler access to ctx in ctg() (03-03)
- Periodic stop checks every 256 iterations via bitmask for low overhead (03-03)
- Thread workers access ctx via local_search_data_t.ctx field (03-03)
- Redesigned stop flag visibility test to use atomic coordination instead of timing (03-05)
- Added solver_ctx.c dependency to test_branching for StateProbability API migration (03-05)
- Named struct 'solver_ctx' in solver_ctx.h to match forward declaration in Branching.h (03-04)
- cdef _set_ctx() method for sharing ctx with incumbents class (03-04)
- approximate_state class owns its ctx (created in __cinit__, freed in __del__) (03-04)
- state.pyx update() creates temporary ctx for single call (03-04)
- branching.pyx unchanged - uses deprecated global setters for backward compatibility (03-04)
- __thread keyword for thread-local PRNG storage (faster than pthread_key_t) (04-01)
- SplitMix64 for xoshiro256** seeding (recommended by algorithm authors) (04-01)
- Jump function (2^128 steps) for parallel stream derivation (04-01)
- _POSIX_C_SOURCE 199309L for clock_gettime/CLOCK_MONOTONIC (04-01)
- Default to 4 threads if sysconf fails and CBQS_THREADS not set (04-02)
- CBQS_THREADS env var takes priority over CPU auto-detection (04-02)
- Reuse existing id field as thread_id for PRNG seeding in local_search (04-02)
- dat_t progress array dynamically allocated based on num_threads (04-02)
- cdef struct + ctypedef pattern for proper Cython field access (04-03)
- Model.pxd declarations required for cdef class attributes (04-03)
- try/except for backward-compatible attribute access in Cython (04-03)
- Explicit free() for zero-length realloc instead of realloc(ptr, 0) - C11 impl-defined behavior (05-01)
- Use positive_offsets as guard in free_constraints() - always allocated if preprocessing ran (05-01)
- free(ptr) immediately after set_*_dependence() since C function copies data (05-05)
- Free char** in reverse order: strings first, then array (05-05)
- Suppress Python 3.13 internal allocations in Valgrind (debug symbols stripped) (05-05)
- Per-thread buffers stored in local_search_data_t struct for cache-friendly access (05-02)
- Allocation failure in accept_best_routine returns -1 with full cleanup (05-02)
- Early return at max_worse_acceptances now includes cleanup (05-02)
- Return 0 on allocation failure in search functions (no improvement found) (05-03)
- Return -1 on allocation failure in CSearch_opt_sampler (distinguishes from valid 0) (05-03)
- Use size_t C = con->num_constraints for consistency in heap allocation (05-03)
- Reduce stress test constraint counts to 2K/1K for CI timeout compliance (05-04)
- Memory stress tests check no-crash rather than global_opt assertions (05-04)
- 1MB initial chunk size for arena allocator (ARENA_DEFAULT_SIZE) (06-01)
- 256KB overflow chunks for arena growth (ARENA_CHUNK_SIZE) (06-01)
- Alignment via padding formula: (-(ptrdiff_t)ptr) & (align - 1) (06-01)
- Non-power-of-2 alignment defaults to 8 bytes (06-01)
- Flexible array member for zero-overhead chunk storage (06-01)
- capacity==0 indicates inline mode, capacity>0 indicates heap mode (06-02)
- Initial heap capacity 32 terms when exceeding 8-term inline threshold (06-02)
- Zero constants skipped in dyn_expr_add_constant (matches Expression.c) (06-02)
- Accessor functions hide storage mode: dyn_expr_literals() returns correct array (06-02)
- Arena owned by solver_ctx_t, created at ctx creation, freed at ctx destruction (06-03)
- Fallback to malloc/calloc when ctx or arena is NULL for backward compatibility (06-03)
- Arena reset after pthread_join in accept_best_routine between iterations (06-03)
- sw_init_arena helper for arena-based array_t allocation (06-03)
- Alignment 8 for part_length_t, 4 for int arrays in arena allocations (06-03)
- Seeded random (seed=42) for reproducible benchmark problems (06-04)
- Pedantic mode for controlled benchmark iterations/rounds (06-04)
- Benchmark job depends on python-tests in CI (06-04)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 6: Arena allocator "50-100x speedup" claim needs validation on this codebase
- Phase 6: Incremental constraint evaluation (adjusted_constraint_violation) was commented out for unknown reasons -- investigate git history during planning
- GCC 15 compilation: Most type mismatches fixed, some warnings remain (non-fatal)
- SATISFY mode crashes: run_sampling in SearchLib.pyx calls len() on int when solver == SATISFY
- Root CMakeLists.txt test.c has pre-existing API mismatch with quantum_local_search (tests/CMakeLists.txt works correctly)
- C tests couldn't run in 03-04 due to network issues - verify in CI

## Session Continuity

Last session: 2026-02-05T19:36:15Z
Stopped at: Completed 06-04-PLAN.md (benchmark suite) - Phase 6 COMPLETE
Resume file: None
