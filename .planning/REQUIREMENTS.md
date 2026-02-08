# Requirements: CBQS v1.1 Bug Fixes & Polish

**Defined:** 2026-02-06
**Core Value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## v1.1 Requirements

Requirements for v1.1 cleanup milestone. Each maps to roadmap phases.

### Crash Fixes

- [x] **CRASH-01**: SATISFY mode solve completes without crashing (fix len() on uint32_t at SearchLib.pyx:220)
- [x] **CRASH-02**: SATISFY mode uses solver_ctx_request_stop() instead of signal.raise_signal(SIGINT)
- [x] **CRASH-03**: objective_value property returns None in SATISFY mode (not meaningless violation count * sense)
- [x] **CRASH-04**: OptimizeResult correctly handles SATISFY mode (no objective, feasibility-based history)

### BranchingStats Correctness

- [x] **BRANCH-01**: Branching bias/factors from solve() parameters propagate to solver_ctx_t in run_sampling()
- [x] **BRANCH-02**: Branching bias/factors propagate to solver_ctx_t in run_local_search()
- [x] **BRANCH-03**: Deprecated global setters emit deprecation warnings when called

### Compiler Warnings

- [x] **GCC-01**: callback_t typedef uses explicit (void) parameter list for C23 compatibility
- [x] **GCC-02**: true/false macros replaced with stdbool.h or guarded against conflict
- [x] **GCC-03**: All implicit function declaration warnings resolved
- [x] **GCC-04**: All type mismatch warnings between int/size_t/uint32_t/int64_t resolved
- [x] **GCC-05**: Clean compilation with GCC 15 -Wall -Wextra (zero warnings)

### Memory Safety

- [x] **MEM-01**: Remaining VLA (int64_t remainings[C]) at local_search.c:286 replaced with arena allocation
- [x] **MEM-02**: local_search accept_best_routine uses update_lock mutex for global_opt writes

### Callback Concurrency

- [x] **CB-01**: History callback uses per-thread state (thread-keyed dictionary) instead of module-level cdef
- [x] **CB-02**: Concurrent solve() calls on different Model instances produce independent history lists
- [x] **CB-03**: History callback correctly handles SATISFY mode (reports feasibility progress, not objective)

### Code Cleanup

- [x] **CLEAN-01**: Commented-out VLA code removed from local_search.c (lines 158, 445)
- [x] **CLEAN-02**: Commented-out debug printf/print statements removed from Model.pyx, Expression.pyx, local_search.c
- [x] **CLEAN-03**: Bare except clause in Model.pyx replaced with except Exception (if still present)
- [x] **CLEAN-04**: local_search() C function has documented read/write field annotations

## v1.2 Requirements

Deferred to next cleanup release.

- **BRANCH-04**: Remove deprecated global BranchingStats setters entirely (breaking change)
- **BRANCH-05**: Move bias/factor configuration from Model.solve() into run_sampling() directly
- **API-01**: Extract local_search_params_t struct (decouple local_search from model_t)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Refactoring the solver loop (ctg) | Working correctly, too risky to restructure during cleanup |
| Re-enabling incremental constraint evaluation | Performance optimization, not bug fix. Was disabled for correctness reasons |
| New test infrastructure (fuzz, property-based) | Existing 200+ tests sufficient for v1.1 validation |
| Expression system rework | Operators work correctly after v1.0 fix; __eq__ returning self is intentional DSL |
| Cython free-threading (nogil) | Experimental, not production-ready |
| Removing deprecated BranchingStats API | Breaking change, deferred to v1.2+ |
| Performance optimization of any kind | Cleanup only, no perf work |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CRASH-01 | Phase 9 | Complete |
| CRASH-02 | Phase 9 | Complete |
| CRASH-03 | Phase 9 | Complete |
| CRASH-04 | Phase 9 | Complete |
| BRANCH-01 | Phase 12 | Complete |
| BRANCH-02 | Phase 12 | Complete |
| BRANCH-03 | Phase 12 | Complete |
| GCC-01 | Phase 10 | Complete |
| GCC-02 | Phase 10 | Complete |
| GCC-03 | Phase 10 | Complete |
| GCC-04 | Phase 10 | Complete |
| GCC-05 | Phase 10 | Complete |
| MEM-01 | Phase 10 | Complete |
| MEM-02 | Phase 12 | Complete |
| CB-01 | Phase 11 | Complete |
| CB-02 | Phase 11 | Complete |
| CB-03 | Phase 11 | Complete |
| CLEAN-01 | Phase 13 | Complete |
| CLEAN-02 | Phase 13 | Complete |
| CLEAN-03 | Phase 13 | Complete |
| CLEAN-04 | Phase 13 | Complete |

**Coverage:**
- v1.1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0

---
*Requirements defined: 2026-02-06*
*Last updated: 2026-02-08 after Phase 13 completion — all v1.1 requirements complete*
