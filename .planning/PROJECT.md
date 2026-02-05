# Constraint-Oriented Biased Quantum Search (CBQS)

## What This Is

A solver for integer programs combining probabilistic sampling and local search heuristics, with the ability to compute quantum search oracle call counts for both solvers. Built as a Python API backed by Cython bindings over a C computation kernel. Currently works well for binary problems; integer variable support exists but has usability issues.

## Core Value

A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.

## Requirements

### Validated

- ✓ Binary variable model definition (variables, constraints, objectives) — existing
- ✓ Probabilistic sampling solver with parallel workers (joblib) — existing
- ✓ Local search solver — existing
- ✓ Quantum search oracle call computation for both solvers — existing
- ✓ Constraint-oriented biased branching with configurable factors (objective, constraint, lookahead, base) — existing
- ✓ Dense and sparse constraint representations with automatic selection — existing
- ✓ Integer variable support via binary decomposition — existing (but mutation bug)
- ✓ Expression system with operator overloading for constraint/objective building — existing
- ✓ User callback mechanism during search — existing

### Active

- [ ] Fix integer variable expression mutation — reusing a variable silently corrupts expressions
- [ ] Remove global BranchingStats — encapsulate in model/solver context for thread safety
- [ ] Fix bare except clause in Model.pyx — replace with proper exception handling
- [ ] Remove commented-out debug code throughout codebase
- [ ] Replace signal.raise_signal with thread-safe stopping mechanism
- [ ] Fix incomplete API migration in Model.local_search()
- [ ] Validate MAXCLAUSESIZE change impact (2→4) and add tests
- [ ] Fix potential memory leak in move list generation (local_search.c)
- [ ] Add NULL pointer checks in SearchLib.c
- [ ] Protect BranchingStats access across threads (extend mutex or per-thread stats)
- [ ] Fix Python callback GIL safety in nogil context
- [ ] Replace fixed-size expression arrays with dynamic allocation
- [ ] Optimize constraint evaluation in hot loop (caching, batch checks)
- [ ] Reduce malloc/free in hot path (memory pools, pre-allocation, stack allocation)
- [ ] Make thread count configurable instead of hardcoded NUMThreads
- [ ] Add post-solve solution validation (constraint satisfaction + objective correctness)
- [ ] Add input validation on user-supplied data (coefficients, bounds, sense values)

### Out of Scope

- ML-based branching strategy selection — deferred to future milestone
- Adaptive branching that learns during search — deferred to future milestone
- Automatic multi-heuristic solver (combining sampling + local search) — deferred to future milestone
- Branch-and-bound extension — deferred to future milestone
- Circuit backend / quantum hardware execution — exists as submodule but not active
- GUI or web interface — CLI/API only

## Context

- This is a research solver used for academic work on quantum-inspired optimization
- The codebase has a three-layer architecture: Python API → Cython middleware → C kernel
- Recent commits (741e97f) introduced bug fixes but also potentially incomplete migrations
- The solver uses joblib for parallel sampling with 12 workers by default
- Expression system uses fixed-size arrays (`MAXCLAUSESIZE`) which wastes memory for small expressions and limits large ones
- Integer variables return expressions (binary decomposition) but operations mutate the expression in-place, requiring manual copying — this is the most user-facing bug
- CONCERNS.md from codebase mapping identifies thread safety, memory management, and missing tests as primary issues

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
| Cleanup before features | Stabilize foundation before extending branching/integer UX | — Pending |
| Dynamic expression arrays | Fixed-size wastes memory on small expressions, limits large ones | — Pending |
| Encapsulate global state | BranchingStats as global breaks thread safety in parallel solves | — Pending |

---
*Last updated: 2026-02-04 after initialization*
