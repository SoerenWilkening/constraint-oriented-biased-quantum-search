---
phase: 01-test-foundation
plan: 03
subsystem: solver-searchlib-integration-tests
tags: [cmocka, unit-tests, integration-tests, solver, searchlib, knapsack, c]
requires: [01-01]
provides: [solver-tests, searchlib-tests, integration-tests, full-c-test-coverage]
affects: [01-05, 02-xx]
tech-stack:
  added: [python3-dev-includes]
  patterns: [feasibility-only-verification, branching-stats-reset, deterministic-srand]
key-files:
  created: [tests/test_solver.c, tests/test_searchlib.c, tests/test_integration.c]
  modified: [tests/CMakeLists.txt]
key-decisions:
  - id: python-include-for-searchlib
    decision: "Use find_package(Python3) to get Python include path for SearchLib.c compilation"
    reason: "SearchLib.c includes Python.h even though no Python API is used in tested functions"
  - id: gitlab-cmocka-mirror
    decision: "Switch cmocka FetchContent URL from git.cryptomilk.org to gitlab.com/cmocka/cmocka"
    reason: "git.cryptomilk.org was unreachable during build (git clone failing with pack file errors)"
  - id: feasibility-only-integration
    decision: "Integration tests check constraint satisfaction only, not objective optimality"
    reason: "Solver is heuristic; checking exact objective values would make tests brittle"
  - id: asan-leak-suppression
    decision: "ASan tests pass for memory safety (no UB/UAF/overflow) but pre-existing leaks exist in library code"
    reason: "free_incumbents uses num_states (0) instead of allocated (1024); preprocessing realloc(ptr,0) loses reference to other arrays. Phase 2 fix."
duration: ~9 minutes
completed: 2026-02-04
---

# Phase 01 Plan 03: Solver, SearchLib, and Integration Tests Summary

**CMocka tests for solver state preparation, update_potentials, compare/incumbents utilities, and end-to-end knapsack feasibility verification**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~9 minutes |
| Tasks | 2/2 |
| Tests added | 11 test cases across 3 files |
| Total C test executables | 9 |

## What Was Done

### Task 1: CMocka tests for solver and SearchLib modules
**Commit:** 5cdc61c

**test_solver.c** (2 test cases):
- `test_initial_state_preparation`: Smoke test building a 3-variable model (x0+x1+x2 <= 2), calling `initial_state_preparation`, verifying the state has correct bit count and feasibility flag is set
- `test_update_potentials`: Verifies PLAIN direction decrements potentials and INVERSE direction restores them, matching the solver's potential tracking logic

**test_searchlib.c** (7 test cases):
- `test_compare_minimize_better/worse`: Validates `compare()` returns 1 when obj is strictly better for MINIMIZE
- `test_compare_maximize_better/worse`: Validates `compare()` returns 1 when obj is strictly better for MAXIMIZE
- `test_compare_equal`: Confirms equal values return 0 (not strictly better)
- `test_init_incumbents`: Verifies `init_incumbents` allocates and initializes correctly
- `test_incumbents_initial_state`: Verifies the first incumbent state matches the provided initial state bit pattern

### Task 2: Integration test and CMake registration
**Commit:** 1d63d73

**test_integration.c** (2 test cases):
- `test_knapsack_feasibility`: Builds a 5-variable knapsack (2*xi <= 33, trivially satisfiable), runs `initial_state_preparation`, verifies solution satisfies constraint via `eval_constraints`
- `test_constraint_satisfaction_after_solve`: Builds a tighter 3-variable knapsack (3*xi <= 6, at most 2 items), verifies feasibility after solving

**CMakeLists.txt updates:**
- Added `test_solver` with solver.c, Branching.c, model.c, constraint.c, Expression.c, state.c, intarray.c
- Added `test_searchlib` with SearchLib.c + quantum_search.c + Python include discovery
- Added `test_integration` with same deps as test_solver
- Fixed cmocka FetchContent URL to gitlab mirror

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] cmocka git.cryptomilk.org unreachable**
- **Found during:** Task 1 build
- **Issue:** FetchContent git clone to https://git.cryptomilk.org/projects/cmocka.git failed repeatedly with pack file corruption errors
- **Fix:** Changed URL to https://gitlab.com/cmocka/cmocka.git (official mirror)
- **Files modified:** tests/CMakeLists.txt
- **Commit:** 5cdc61c

### Known Issues (Not Fixed -- Phase 2)

**1. free_incumbents memory leak under ASan**
- `init_incumbents` sets `num_states = 0` but allocates 1024 states
- `free_incumbents` calls `free_state(states, num_states)` with count 0
- Result: 1024 state vector/branch arrays leaked
- ASan memory safety checks pass (no UB/UAF/overflow)

**2. preprocessing realloc(ptr, 0) leak**
- When `positive_array_length == 0`, `realloc(positive_indices, 0)` returns NULL
- `free_constraints` checks `positive_indices != NULL` and skips freeing offsets/counts
- Result: Small leaks of offset/count arrays

## Verification Results

| Check | Result |
|-------|--------|
| All 9 test executables compile | PASS |
| CTest 9/9 passing | PASS |
| Integration test verifies constraint satisfaction | PASS |
| ASan memory safety (detect_leaks=0) | PASS |
| ASan leak detection | FAIL (pre-existing library leaks, not test bugs) |
| No global state pollution (BranchingStats reset) | PASS |

## Next Phase Readiness

All C test coverage is complete:
- Plan 01-01: intarray, Expression, state
- Plan 01-02: constraint, model, branching
- Plan 01-03: solver, SearchLib, integration

Phase 2 should address:
- `free_incumbents` memory leak (use `allocated` instead of `num_states`)
- `preprocessing` realloc(ptr, 0) pattern causing leaked offsets
