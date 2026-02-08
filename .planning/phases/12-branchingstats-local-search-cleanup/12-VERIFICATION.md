---
phase: 12-branchingstats-local-search-cleanup
verified: 2026-02-08T17:42:35Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 12: BranchingStats & Local Search Cleanup Verification Report

**Phase Goal:** Branching parameters set via Python API actually reach the solver, and local_search writes to shared state safely

**Verified:** 2026-02-08T17:42:35Z

**Status:** passed

**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | model.set_param('branching_bias', value) stores and retrieves via get_param | ✓ VERIFIED | Model.pyx lines 143-163 implement set_param/get_param with _KNOWN_PARAMS validation; test_set_param.py tests pass |
| 2 | model.set_param('unknown_param', value) raises ValueError | ✓ VERIFIED | Model.pyx line 151-152 validates against _KNOWN_PARAMS; test_set_param_unknown_raises passes |
| 3 | Branching bias set via set_param propagates to solver_ctx_t in run_sampling | ✓ VERIFIED | SearchLib.pyx lines 234-240 read _params.get('branching_bias') and call solver_ctx_set_bias; test_branching_bias_deterministic_sampling passes |
| 4 | Branching bias set via set_param propagates to solver_ctx_t in run_local_search | ✓ VERIFIED | SearchLib.pyx lines 379-383 read _params.get('branching_bias') and call solver_ctx_set_bias; test_branching_bias_deterministic_local_search passes |
| 5 | Calling set_branching_bias (old global setter) emits DeprecationWarning | ✓ VERIFIED | branching.pyx lines 14 emits DeprecationWarning with stacklevel=2; test_set_bias_wrapper_deprecation passes |
| 6 | accept_best_routine uses pthread_mutex_trylock around global_opt writes | ✓ VERIFIED | local_search.c lines 434-436 and 475-477 wrap accept_move with pthread_mutex_trylock/unlock; extern update_lock declared at line 11 |
| 7 | Branching bias set via set_param produces deterministic solver behavior (fixed-seed) | ✓ VERIFIED | test_branching_bias_deterministic_sampling and test_branching_bias_deterministic_local_search verify same seed + same bias = same result |
| 8 | Branching propagation works for both sampling solver and local search solver paths | ✓ VERIFIED | test_branching_factors_propagation_sampling and test_branching_factors_propagation_local_search verify factors tuple propagates correctly |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| cbqs/Model.pyx | set_param/get_param methods, _params dict | ✓ VERIFIED | Lines 143-163 implement API; line 119 initializes _params = {}; _KNOWN_PARAMS defined at module level |
| cbqs/Model.pxd | _params declaration | ✓ VERIFIED | Line 79: `cdef public object _params` |
| cbqs/branching.pyx | DeprecationWarning on deprecated setters | ✓ VERIFIED | Lines 10, 14, 18, 27 emit DeprecationWarning for all four wrapper functions |
| cbqs/SearchLib.pyx | Branching param propagation to solver_ctx_t | ✓ VERIFIED | Lines 234-259 (run_sampling) and 379-399 (run_local_search) read _params and call solver_ctx_set_bias/factors/obj_dependence |
| cbqs/src/local_search.c | Mutex-protected global_opt writes | ✓ VERIFIED | Lines 11 (extern declaration), 434-446 (thread join loop), 475-487 (main accept_move) use pthread_mutex_trylock with proper unlock |
| tests/test_set_param.py | Comprehensive API tests | ✓ VERIFIED | 24 tests covering basics, validation, persistence, copy, deprecation, precedence; all pass |
| tests/test_branching_propagation.py | Deterministic propagation tests | ✓ VERIFIED | 8 tests covering sampling solver, local search, branching factors, determinism; all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| Model._params | SearchLib.run_sampling | _params.get('branching_bias') | ✓ WIRED | SearchLib.pyx line 234 reads mod._params.get('branching_bias'), line 236 calls solver_ctx_set_bias(ctx, param_bias) |
| Model._params | SearchLib.run_local_search | _params.get('branching_bias') | ✓ WIRED | SearchLib.pyx line 379 reads mod._params.get('branching_bias'), line 381 calls solver_ctx_set_bias(ctx, param_bias_ls) |
| local_search.c | SearchLib.c | extern pthread_mutex_t update_lock | ✓ WIRED | local_search.c line 11 declares extern update_lock; SearchLib.c defines it (referenced in plan); lines 434 and 475 use it |
| test_set_param.py | Model.set_param | import and call | ✓ WIRED | Test file imports Model, calls set_param/get_param in 24 tests; all pass |
| test_branching_propagation.py | Model.set_param + solve | set_param then solve/local_search | ✓ WIRED | Test file sets branching_bias via set_param, calls solve/local_search, verifies deterministic results |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| BRANCH-01: Branching bias/factors from solve() parameters propagate to solver_ctx_t in run_sampling() | ✓ SATISFIED | None — SearchLib.pyx lines 234-248 implement propagation with _params precedence; tests verify determinism |
| BRANCH-02: Branching bias/factors propagate to solver_ctx_t in run_local_search() | ✓ SATISFIED | None — SearchLib.pyx lines 379-399 implement propagation; test_branching_bias_deterministic_local_search verifies |
| BRANCH-03: Deprecated global setters emit deprecation warnings when called | ✓ SATISFIED | None — branching.pyx lines 10, 14, 18, 27 emit DeprecationWarning; 4 tests in test_set_param.py verify with pytest.warns |
| MEM-02: local_search accept_best_routine uses update_lock mutex for global_opt writes | ✓ SATISFIED | None — local_search.c lines 434-446 and 475-487 use pthread_mutex_trylock/unlock; non-blocking design per plan |

### Anti-Patterns Found

None detected. Scanned 5 modified files (Model.pyx, Model.pxd, SearchLib.pyx, branching.pyx, local_search.c) and 2 test files. No TODO/FIXME/HACK/PLACEHOLDER comments, no stub implementations, no empty handlers.

### Human Verification Required

None required. All Phase 12 requirements are verifiable programmatically:
- API validation verified by tests raising ValueError
- Deprecation warnings verified by pytest.warns
- Deterministic branching verified by fixed-seed tests comparing objective values
- Mutex protection verified by code inspection (ThreadSanitizer will verify at runtime in CI)

## Verification Summary

**All must-haves verified.** Phase 12 goal achieved.

The set_param/get_param API is fully functional with strict validation. Branching parameters propagate from _params to solver_ctx_t in both sampling and local search solver paths with correct precedence (_params > kwargs > defaults). Deprecated branching setters emit DeprecationWarning while remaining functional (no breaking changes). Mutex protection for global_opt writes uses pthread_mutex_trylock (non-blocking) as designed.

Test suite expanded from 272 to 304 tests (32 new tests). All tests pass with no regressions.

### Commits Verified

- `66fa4b2` - feat(12-01): add mutex protection for global_opt writes in accept_best_routine
- `80876ef` - feat(12-01): add set_param/get_param API, deprecation warnings, and branching propagation
- `2b57487` - test(12-02): add set_param/get_param API and deprecation warning tests
- `f00d058` - test(12-02): add deterministic branching propagation tests

All commits exist in git log and match the documented work.

---

_Verified: 2026-02-08T17:42:35Z_
_Verifier: Claude (gsd-verifier)_
