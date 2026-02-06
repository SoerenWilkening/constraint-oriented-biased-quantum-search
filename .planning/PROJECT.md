# Constraint-Oriented Biased Quantum Search (CBQS)

## What This Is

A solver for integer programs combining probabilistic sampling and local search heuristics, with quantum search oracle call computation. Built as a Python API backed by Cython bindings over a C computation kernel. Supports binary and integer variables, thread-safe parallel solving with deterministic reproducibility, comprehensive input validation, and structured solve diagnostics.

## Core Value

A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## Requirements

### Validated

- ✓ Binary variable model definition (variables, constraints, objectives) — existing
- ✓ Probabilistic sampling solver with parallel workers — existing
- ✓ Local search solver — existing
- ✓ Quantum search oracle call computation for both solvers — existing
- ✓ Constraint-oriented biased branching with configurable factors — existing
- ✓ Dense and sparse constraint representations with automatic selection — existing
- ✓ Integer variable support via binary decomposition — existing
- ✓ Expression system with operator overloading for constraint/objective building — existing
- ✓ User callback mechanism during search — existing
- ✓ C unit test suite (CMocka) + Python test suite (pytest) + CI pipeline — v1.0
- ✓ Fix use-after-free, realloc condition, Expression mutation bugs — v1.0
- ✓ solver_ctx_t architecture eliminating global mutable state — v1.0
- ✓ Atomic stop flag replacing signal.raise_signal — v1.0
- ✓ Per-thread xoshiro256** PRNG with deterministic reproducibility — v1.0
- ✓ Configurable thread count via Model API — v1.0
- ✓ Memory leak fixes and VLA replacement with heap buffers — v1.0
- ✓ Arena allocator for hot-path allocation elimination — v1.0
- ✓ Dynamic expression storage (dyn_expr with small-object optimization) — v1.0
- ✓ Input validation at API boundary (coefficients, bounds, sense, indices) — v1.0
- ✓ Post-solve solution verification (verify_solution, verify=True) — v1.0
- ✓ Structured OptimizeResult with timing, history, and diagnostics — v1.0

### Active

- [ ] Fix SATISFY mode crash (run_sampling calls len() on int)
- [ ] Fix bare except clause in Model.pyx (should be except Exception)
- [ ] Fix incomplete local_search() API migration
- [ ] Replace remaining VLA at local_search.c:286 with heap allocation
- [ ] Remove commented-out VLA code (local_search.c:158, 445)
- [ ] Remove commented-out debug code (Model.pyx, Expression.pyx, local_search.c)
- [ ] Fix GCC 15 type mismatch warnings
- [ ] Rework module-level cdef history callback to support concurrent tracking
- [ ] Clean local_search() API (fix parameter passing, signature consistency)
- [ ] Clean deprecated BranchingStats implementation (keep API, improve internals)

### Out of Scope

- ML-based branching strategy selection — deferred to future milestone
- Adaptive branching that learns during search — deferred to future milestone
- Automatic multi-heuristic solver (combining sampling + local search) — deferred to future milestone
- Branch-and-bound extension — deferred to future milestone
- Circuit backend / quantum hardware execution — exists as submodule but not active
- GUI or web interface — CLI/API only
- Python free-threading (nogil) — Cython support experimental
- Metal/GPU acceleration — macOS-only, not relevant to solver stabilization

## Current Milestone: v1.1 Bug Fixes & Polish

**Goal:** Fix all known bugs, eliminate tech debt, and clean up code quality issues from v1.0.

**Target features:**
- Fix SATISFY mode crash and other runtime bugs
- Remove all dead/commented-out code
- Fix GCC 15 compiler warnings
- Rework history callback for concurrent tracking
- Clean local_search() API
- Replace remaining VLA with heap allocation

## Context

Shipped v1.0 with 15,211 LOC across C/Python/Cython.
Tech stack: Python 3.13.7, Cython 3, C11, CMocka, pytest, GitHub Actions CI.
Test suite: 58+ C tests, 200+ Python tests, 7 benchmarks. CI runs ASan, Valgrind, ThreadSanitizer.
v1.0 audit: 15/15 requirements satisfied, 6 tech debt items (0 blockers). All addressed in v1.1.

## Git Workflow

This project uses **Git Flow**:

- `main` — production-ready releases only
- `develop` — integration branch for feature work
- `feature/*` — feature development branches
- `release/*` — release preparation (develop → main)
- `hotfix/*` — urgent production fixes

**Current branch:** `feature/feature_branch`

All phase work is done on feature branches. Features merge to `develop`. Releases merge `develop` to `main`.

## Constraints

- **Language**: Must maintain Python/Cython/C architecture — core performance lives in C
- **Compatibility**: Python 3.13.7, C11 standard, Cython 3
- **Dependencies**: Minimal — numpy, joblib required; gurobipy optional
- **Build**: setuptools + Cython.Build with -O3 -flto -pthread flags

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Cleanup before features | Stabilize foundation before extending branching/integer UX | ✓ Good — v1.0 shipped stable |
| Dynamic expression arrays | Fixed-size wastes memory on small expressions, limits large ones | ✓ Good — dyn_expr with SOO |
| Encapsulate global state | BranchingStats as global breaks thread safety in parallel solves | ✓ Good — solver_ctx_t, zero TSan races |
| Expression operators return new objects | Standard Python semantics for binary ops | ✓ Good — mutation bug fixed |
| In-place operators mutate self | Match Python int behavior for +=, etc. | ✓ Good — consistent semantics |
| xoshiro256** with SplitMix64 seeding | Fast, high-quality per-thread PRNG with jump functions | ✓ Good — deterministic results |
| Arena allocator (1MB initial) | Eliminate malloc/free in hot loop | ✓ Good — zero hot-path allocations |
| verify=False default on solve() | Opt-in verification, no performance cost by default | ✓ Good — clean API |
| Module-level cdef for history callback | cpdef cannot use closures in Cython | ⚠️ Revisit — limits concurrent history tracking |
| Deprecated global BranchingStats kept | Backward compatibility for existing code | ⚠️ Revisit — remove in v2.0 |
| v1.1 no breaking changes | Aggressive cleanup but keep deprecated APIs working | — Pending |

---
*Last updated: 2026-02-06 after v1.1 milestone start*
