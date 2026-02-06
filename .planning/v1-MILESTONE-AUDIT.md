---
milestone: v1
audited: 2026-02-06T14:30:00Z
status: tech_debt
scores:
  requirements: 15/15
  phases: 8/8
  integration: 6/6
  flows: 6/6
gaps: []
tech_debt:
  - phase: 06-memory-optimization
    items:
      - "No Phase 5 baseline captured — cannot verify measurable performance improvement from arena/dyn_expr (benchmark infrastructure exists but baseline missing)"
  - phase: 08-solve-diagnostics
    items:
      - "Missing VERIFICATION.md — phase was not formally verified by gsd-verifier (both plans completed and self-checked)"
  - phase: 05-memory-safety
    items:
      - "Remaining VLA at local_search.c:286 (accept_best_routine) — not hot-path, acceptable per phase design"
      - "Commented-out VLA code at local_search.c:158,445 — cleanup deferred"
  - phase: 03-solver-context-architecture
    items:
      - "Deprecated global BranchingStats and setters in Branching.c (backward compatibility only)"
      - "g_active_ctx static global for signal handler access (intentional, limited scope)"
---

# v1 Milestone Audit Report

**Milestone:** v1 — CBQS Stabilization & Optimization
**Audited:** 2026-02-06
**Status:** TECH DEBT (all requirements met, accumulated debt needs review)

## Requirements Coverage

| Requirement | Description | Phase | Status |
|-------------|-------------|-------|--------|
| CORR-01 | C unit test suite using CMocka | Phase 1 | SATISFIED |
| CORR-02 | Fix use-after-free in accept_best_routine | Phase 2 | SATISFIED |
| CORR-03 | Fix inverted realloc condition in preprocessing | Phase 2 | SATISFIED |
| CORR-04 | Fix Expression mutation bug | Phase 2 | SATISFIED |
| THRD-01 | Introduce solver_ctx_t, eliminate global mutable state | Phase 3 | SATISFIED |
| THRD-02 | Replace signal.raise_signal with atomic stop flag | Phase 3 | SATISFIED |
| THRD-03 | Replace global rand() with per-thread PRNG | Phase 4 | SATISFIED |
| THRD-04 | Make thread count configurable | Phase 4 | SATISFIED |
| MEM-01 | Fix memory leak in move list generation | Phase 5 | SATISFIED |
| MEM-04 | Replace VLAs with heap allocation | Phase 5 | SATISFIED |
| MEM-02 | Replace fixed-size expression arrays with dynamic allocation | Phase 6 | SATISFIED |
| MEM-03 | Implement arena allocator for hot-path allocations | Phase 6 | SATISFIED |
| RBST-01 | Add input validation at API boundary | Phase 7 | SATISFIED |
| RBST-02 | Add post-solve solution validation | Phase 7 | SATISFIED |
| RBST-03 | Return structured result object with solve diagnostics | Phase 8 | SATISFIED |

**Score: 15/15 requirements satisfied**

## Phase Verification Status

| Phase | Name | Verification | Score | Status |
|-------|------|-------------|-------|--------|
| 1 | Test Foundation | 01-VERIFICATION.md | 4/4 | PASSED |
| 2 | Critical Correctness Fixes | 02-VERIFICATION.md | 5/5 | PASSED |
| 3 | Solver Context Architecture | 03-VERIFICATION.md | 4/4 | PASSED |
| 4 | Thread Isolation | 04-VERIFICATION.md | 5/5 | PASSED |
| 5 | Memory Safety | 05-VERIFICATION.md | 8/8 | PASSED |
| 6 | Memory Optimization | 06-VERIFICATION.md | 3/4 | HUMAN_NEEDED |
| 7 | API Robustness | 07-VERIFICATION.md | 4/4 | PASSED |
| 8 | Solve Diagnostics | (no VERIFICATION.md) | N/A | UNVERIFIED |

**Phase 6 note:** 3/4 criteria verified programmatically. Truth 4 (measurable performance improvement) needs human benchmark run — no Phase 5 baseline was captured before Phase 6 work began. Benchmark infrastructure exists and works.

**Phase 8 note:** Both plans (08-01, 08-02) completed with self-check PASSED. 246 tests pass. Missing formal gsd-verifier run. Plans' SUMMARYs document all artifacts, decisions, and test results.

**Score: 7/8 phases formally verified, 1 unverified (Phase 8)**

## Cross-Phase Integration

| Check | Status | Details |
|-------|--------|---------|
| solver_ctx lifecycle (Ph3→4→5→6) | COMPLETE | Create → init PRNG → per-thread buffers → arena → free in finally |
| Expression pipeline (Ph2→6) | COMPLETE | Deep copy → dyn_expr integration → all operators work |
| Model API flow (Ph7→8) | COMPLETE | Validation → solve → verification → OptimizeResult |
| Test infrastructure (all phases) | COMPLETE | 58 C tests + 200+ Python tests, no conflicts |
| CI pipeline (Ph1→2→3→6) | COMPLETE | 6 CI jobs: c-tests, ASan, Valgrind, TSan, python-tests, benchmarks |

**Score: 6/6 integration checks passed**

## E2E User Flows

| Flow | Status | Verified By |
|------|--------|-------------|
| Basic solve → OptimizeResult | COMPLETE | test_diagnostics_py.py |
| Deterministic solve (same seed) | COMPLETE | test_determinism.py |
| Invalid input → exception | COMPLETE | test_validation_py.py, test_validation_model_py.py |
| Solve with verify=True | COMPLETE | test_verification_py.py |
| Local search → OptimizeResult | COMPLETE | test_diagnostics_py.py |
| Large problem (2K constraints) | COMPLETE | test_memory_stress.py |

**Score: 6/6 E2E flows complete**

## Tech Debt Summary

### Phase 6: Memory Optimization
- **Missing baseline:** No Phase 5 performance baseline was captured before arena/dyn_expr work. Benchmark infrastructure is complete but cannot verify "measurable improvement" without comparison point.

### Phase 8: Solve Diagnostics
- **Missing VERIFICATION.md:** Phase was not formally verified by gsd-verifier. Both plans completed with self-check passed, all tests pass, but no independent verification.

### Phase 5: Memory Safety
- **Remaining VLA:** `int64_t remainings[C]` at local_search.c:286 in accept_best_routine (not hot path, called once per solve). Acceptable per phase design.
- **Commented-out VLA code:** local_search.c:158,445. Non-blocking cleanup items.

### Phase 3: Solver Context Architecture
- **Deprecated globals:** Global BranchingStats and setter functions in Branching.c kept for backward compatibility. Marked DEPRECATED.
- **g_active_ctx pattern:** Static global for signal handler → ctx communication. Intentional and well-scoped.

### Total: 6 items across 4 phases (0 blockers)

## Orphaned Code / Missing Connections

**Orphaned exports:** 0
**Missing connections:** 0
**Circular dependencies:** 0

All phase outputs are consumed by subsequent phases. All test files import and exercise all features.

## Test Summary

| Category | Count | Status |
|----------|-------|--------|
| C unit tests (CMocka) | 58+ | ALL PASS |
| Python tests (pytest) | 200+ | ALL PASS |
| Integration tests | 23+ | ALL PASS |
| Benchmark tests | 7 | ALL PASS |
| ASan | CI job | CLEAN |
| Valgrind | CI job | CLEAN (with suppressions) |
| ThreadSanitizer | CI job | ZERO RACES |

---

*Audited: 2026-02-06*
*Auditor: Claude (gsd orchestrator + gsd-integration-checker)*
