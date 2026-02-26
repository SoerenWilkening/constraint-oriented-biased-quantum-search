# Constraint-Oriented Biased Quantum Search (CBQS)

## What This Is

A solver for integer programs combining probabilistic sampling and local search heuristics, with quantum search oracle call computation. Built as a Python API backed by Cython bindings over a C computation kernel. Supports binary and integer variables, thread-safe parallel solving with deterministic reproducibility, comprehensive input validation, structured solve diagnostics, per-thread history tracking with concurrent solve isolation, a unified branching model with all solver configuration via set_param()/get_param(), incremental constraint evaluation in local search, and full API documentation.

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
- ✓ SATISFY mode solve without crashes — v1.1
- ✓ SATISFY mode returns None objective, feasibility-based history — v1.1
- ✓ C23-compatible C kernel (stdbool.h, (void) params, portability macros) — v1.1
- ✓ Zero GCC 15 warnings with -Wall -Wextra, -Werror in CI — v1.1
- ✓ Zero VLA declarations in C kernel — v1.1
- ✓ Per-thread callback state for concurrent solve isolation — v1.1
- ✓ 2-tuple (value, elapsed_seconds) history format — v1.1
- ✓ set_param/get_param API with strict validation for branching configuration — v1.1
- ✓ Branching parameter propagation to both sampling and local search solvers — v1.1
- ✓ Deprecated global branching setters emit DeprecationWarning — v1.1
- ✓ Mutex-protected global_opt writes in local_search — v1.1
- ✓ Dead code and commented-out code removed from C kernel and Cython — v1.1
- ✓ Field annotations on major solver functions (local_search, ctg, preprocessing, initial_state_preparation) — v1.1
- ✓ Global BranchingStats variable and all deprecated global setters removed — v2.0
- ✓ Zero-arg solve(); all configuration via set_param() only — v2.0
- ✓ Unified branching_weights array replacing obj_dependent + constraint_dependent — v2.0
- ✓ 3-term BranchingFunction with L1 normalization and division-by-zero guard — v2.0
- ✓ set_param('branching_weights', array) API for per-variable branching values — v2.0
- ✓ All 14 former solve() params available via set_param() with _PARAM_DEFS registry — v2.0

- ✓ All orphaned model_t fields and dead/commented-out code removed from C/Cython/Python — v2.1
- ✓ Incremental constraint evaluation adopted in local_search with benchmark infrastructure — v2.1
- ✓ look_ahead_factor naming unified across C/Cython/Python, _PARAM_DEFS audited, Cython types aligned — v2.1
- ✓ Build system deduplicated (build_clib), pandas removed, version 2.1.0 — v2.1
- ✓ NumPy-style docstrings on all public Python methods, C kernel algorithm comments — v2.1

### Active

(No active requirements — use `/gsd:new-milestone` to define next milestone)

### Out of Scope

- ML-based branching strategy selection — deferred to future milestone
- Adaptive branching that learns during search — deferred to future milestone
- Automatic multi-heuristic solver (combining sampling + local search) — deferred to future milestone
- Branch-and-bound extension — deferred to future milestone
- Circuit backend / quantum hardware execution — exists as submodule but not active
- GUI or web interface — CLI/API only
- Python free-threading (nogil) — Cython support experimental
- Metal/GPU acceleration — macOS-only, not relevant to solver stabilization

## Context

Shipped v2.1 with C/Python/Cython codebase.
Tech stack: Python 3.13.7, Cython 3, C11 (C23-compatible), CMocka, pytest, GitHub Actions CI.
Test suite: 56 C tests, 390 Python tests, 7 benchmarks. CI runs ASan, Valgrind, ThreadSanitizer, -Werror.
v1.0 audit: 15/15. v1.1 audit: 21/21. v2.0 audit: 17/17. v2.1 audit: 18/18.
Package version 2.1.0. Build uses build_clib static library for C source deduplication.
All public Python methods have docstrings. C kernel has algorithm block comments.

Known tech debt: SearchLib.pyx local vars retain old `param_look_factor` naming (cosmetic only). Expression.c/dyn_expr.c compiled in both lib and extension (documented intentional).

## Git Workflow

This project uses **Git Flow**:

- `main` — production-ready releases only
- `develop` — integration branch for feature work
- `feature/*` — feature development branches
- `release/*` — release preparation (develop -> main)
- `hotfix/*` — urgent production fixes

**Current branch:** `feature/feature_branch`

All phase work is done on feature branches. Features merge to `develop`. Releases merge `develop` to `main`.

## Constraints

- **Language**: Must maintain Python/Cython/C architecture — core performance lives in C
- **Compatibility**: Python 3.13.7, C11 standard (C23-compatible), Cython 3
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
| objective_value returns None in SATISFY | None clearly signals "no objective" vs 0 which could be valid | ✓ Good — clean SATISFY semantics |
| Per-thread _SolveState for callbacks | threading.get_ident()-keyed dict for concurrent solve isolation | ✓ Good — zero cross-contamination |
| 2-tuple history format | (value, elapsed_seconds) simpler and sufficient vs old 4-tuple | ✓ Good — cleaner API |
| set_param/get_param with validation | Strict _PARAM_DEFS registry, ValueError for unknowns, type coercion | ✓ Good — safe API |
| pthread_mutex_trylock for global_opt | Non-blocking; contended lock skips update (loses one update at worst) | ✓ Good — no deadlock risk |
| v2.0 hard break on solve() args | All config via set_param(); cleaner API surface | ✓ Good — clean zero-arg solve() |
| Merge obj_dependent + constraint_dependent | Two arrays serving similar purpose; single unified array simpler | ✓ Good — single branching_weights array |
| 3-term BranchingFunction | unified_array + assignment_bias + look_ahead; dropped separate obj/constraint factors | ✓ Good — simpler formula, L1 normalization |
| L1 normalization at set-time | Ensures branching_weights sum to 1.0; division-by-zero guard returns 0.5 | ✓ Good — predictable behavior |
| _PARAM_DEFS registry | Dict-of-dicts replacing flat _KNOWN_PARAMS set; coercion, validation, defaults | ✓ Good — extensible parameter system |
| Remove set_seed from public API | srand() called directly from libc.stdlib; branching.pyx wrapper eliminated | ✓ Good — v2.0 breaking change, simpler |
| Remove deprecated global BranchingStats | All state in solver_ctx_t; backward compatibility period complete | ✓ Good — clean C layer |
| Dead code removal first | Low-risk, foundational — cleans codebase before behavior changes | ✓ Good — stable baseline for all v2.1 work |
| Caller-owns-baseline pattern | local_search() manages remainings[] and ful_con, passes to accept_best_routine() | ✓ Good — clear ownership semantics |
| Full-recalc refresh after accepted moves | Simpler than tracking exact flipped bits from threaded results | ✓ Good — correctness over micro-optimization |
| build_clib static library | 15 C sources compiled once, linked into 5 extensions | ✓ Good — eliminated duplicate compilation |
| Single-source version in __init__.py | pyproject.toml reads dynamically; one place to update | ✓ Good — no version drift |
| NumPy-style docstrings | Standard format with Parameters/Returns/Raises/Examples | ✓ Good — pydoc/help() readable output |

---
*Last updated: 2026-02-26 after v2.1 milestone completion*
