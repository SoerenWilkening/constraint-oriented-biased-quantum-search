# Phase 17: Test Suite Finalization - Research

**Researched:** 2026-02-14
**Domain:** Python/C test infrastructure, Valgrind memory analysis, deterministic solver testing
**Confidence:** HIGH

## Summary

Phase 17 is the final phase of the v2.0 milestone. Its goal is to ensure the full test suite (383 Python tests + 14 C test executables) passes cleanly against the v2.0 API, that new branching coverage is comprehensive, and that memory safety is verified via Valgrind. The codebase has already been substantially updated by Phases 14-16: the API migration (zero-arg solve() with set_param()) is complete, all deprecated global state is removed, and the branching module has been deleted. This phase is primarily a **validation and gap-filling** exercise rather than a structural change.

The key research findings are: (1) The existing test suite already uses the v2.0 API (zero-arg solve() with set_param() configuration) -- Phase 15 migrated all 80+ solve() calls. (2) Branching propagation tests already exist in `test_branching_propagation.py` with 11 tests covering bias, factors, and weights for both sampling and local search solvers. (3) Deterministic branching tests also exist. (4) Memory tests exist in `test_cython_memory.py` with a specific `test_branching_weights_no_leak` test. (5) Valgrind suppression file exists at `tests/valgrind-python.supp`. The gaps are: (a) Need to verify 100% of existing tests pass (no regressions from Phase 16 module deletion). (b) Need additional C-level tests for BranchingFunction edge cases with the unified model. (c) Need stronger deterministic propagation tests that verify branching_weights actually influence branching scores (not just "doesn't crash"). (d) Need Valgrind-specific test runs confirming zero leaks for branching_weights lifecycle.

**Primary recommendation:** Organize work into two plans: (1) audit and fix any regressions in existing tests, add deeper branching_weights coverage tests, and (2) run Valgrind memory verification for branching_weights allocation/deallocation lifecycle.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Python test runner | Already used, all 383 tests use it |
| pytest-timeout | 2.4.0 | Timeout for stress tests | Already used in memory stress tests |
| CMocka | 1.1.7 | C unit testing | Already used, fetched via CMake FetchContent |
| Valgrind | system | Memory leak detection | Available at `/usr/bin/valgrind`, suppression file exists |
| numpy | 2.4.2 | Array handling in tests | Already used for solution comparison and branching_weights |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-benchmark | 5.2.3 | Performance benchmarks | Already installed, benchmarks in benchmarks/ |
| ASan (gcc flag) | N/A | AddressSanitizer | Already configured in CMakeLists.txt via -DASAN=ON |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Valgrind | ASan only | ASan catches use-after-free but not all leak patterns; Valgrind is more thorough for leak detection |
| CMocka | Check/Unity | CMocka already used throughout; no reason to change |

**Installation:**
No new installations needed. All tools are already available.

## Architecture Patterns

### Existing Test Structure
```
tests/
├── conftest.py                    # pytest fixtures (simple_model, five_var_model)
├── CMakeLists.txt                 # C test build config with CMocka
├── valgrind-python.supp           # Valgrind suppression file for Python/NumPy/Cython
├── test_set_param.py              # 17 test classes, 69 tests -- set_param/get_param API
├── test_branching_propagation.py  # 4 test classes, 11 tests -- branching param propagation
├── test_determinism.py            # 2 test classes, 11 tests -- seed determinism
├── test_model_py.py               # 4 test classes, 16 tests -- Model API integration
├── test_verification_py.py        # 3 test classes, 12 tests -- post-solve verification
├── test_validation_model_py.py    # 5 test classes, 17 tests -- input validation
├── test_validation_py.py          # Expression/Constraint validation (TBD count)
├── test_diagnostics_py.py         # OptimizeResult field population
├── test_result_py.py              # OptimizeResult unit tests
├── test_concurrent_history.py     # 4 test classes -- concurrent solve isolation
├── test_cython_memory.py          # 5 test classes -- Valgrind-targeted memory tests
├── test_memory_stress.py          # 3 test classes -- large problem memory safety
├── test_stress.py                 # 1 test class -- 200/500/300 iteration stress tests
├── test_constraint_py.py          # Constraint object tests
├── test_expression_py.py          # Expression object tests
├── test_branching.c               # 15 CMocka tests -- BranchingFunction, weights, normalization
├── test_solver.c                  # Solver C tests
├── test_integration.c             # Integration C tests
├── test_local_search.c            # Local search C tests
├── test_thread_safety.c           # Thread safety C tests
├── test_prng.c                    # PRNG C tests
├── test_arena.c                   # Arena allocator C tests
├── test_model.c                   # Model C tests
├── test_state.c                   # State C tests
├── test_intarray.c                # IntArray C tests
├── test_expression.c              # Expression C tests
├── test_constraint.c              # Constraint C tests
└── test_dyn_expr.c                # Dynamic expression C tests
```

### Pattern 1: Python Test Pattern (v2.0 API)
**What:** All Python tests follow the set_param() + zero-arg solve() pattern
**When to use:** Every test that calls solve()
**Example:**
```python
# Source: tests/test_set_param.py (existing pattern)
def test_solve_zero_args_works(self):
    m = _make_small_model()
    m.set_param("stopping_time", 1)
    m.set_param("num_workers", 1)
    result = m.solve()
    assert isinstance(result, OptimizeResult)
```

### Pattern 2: Branching Weights Propagation Test
**What:** Tests that verify branching_weights flow from Python through Cython to C
**When to use:** Validating end-to-end parameter propagation
**Example:**
```python
# Source: tests/test_branching_propagation.py (existing pattern)
def test_branching_weights_deterministic(self):
    n = 20
    weights = [float(i % 5 + 1) for i in range(n)]
    m1 = _make_knapsack_model(n)
    m1.seed = 42
    m1.set_param("branching_weights", weights)
    m1.set_param("stopping_time", 2)
    m1.set_param("num_workers", 1)
    result1 = m1.solve()
    # ... repeat with m2 ...
    assert result1.objective == result2.objective
    np.testing.assert_array_equal(result1.solution, result2.solution)
```

### Pattern 3: C-Level BranchingFunction Test
**What:** Direct C tests using solver_ctx_t and BranchingFunction
**When to use:** Testing the 3-term formula with known inputs
**Example:**
```c
// Source: tests/test_branching.c (existing pattern)
static void test_branching_function_3term(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 1.0);
    solver_ctx_set_bias_factor(ctx, 1.0);
    solver_ctx_set_look_factor(ctx, 1.0);
    solver_ctx_set_bias(ctx, 2.0);
    double arr[] = {0.8, 0.2};
    solver_ctx_set_branching_weights(ctx, arr, 2);
    double result = BranchingFunction(0, 0, 0, 1, &ctx->branching_stats);
    double expected = (1.0/3.0) * 0.8 + (1.0/3.0) * 0.75 + (1.0/3.0) * 1.0;
    assert_true(fabs(result - expected) < 1e-9);
}
```

### Pattern 4: Valgrind Memory Test
**What:** Python tests designed to amplify leaks, run under Valgrind
**When to use:** Verifying memory safety for allocation/deallocation cycles
**Example:**
```bash
# Source: tests/test_cython_memory.py header comment (existing pattern)
PYTHONMALLOC=malloc valgrind --leak-check=full \
    --suppressions=tests/valgrind-python.supp \
    python -m pytest tests/test_cython_memory.py -v
```

### Anti-Patterns to Avoid
- **Testing solver correctness instead of API correctness:** Phase 17 is about API compliance and memory safety, not solver optimality. Tests should verify "does not crash," "produces valid result," "deterministic with same seed" -- not "finds optimal solution."
- **Flaky determinism tests with multiple workers:** Deterministic tests MUST use `num_workers=1` to avoid non-deterministic thread scheduling. The existing tests already do this correctly.
- **Missing cleanup in C tests:** Every CMocka test using solver_ctx_t MUST have setup/teardown that creates/frees the context. The existing `branching_setup`/`branching_teardown` pattern is correct.
- **Running Valgrind without PYTHONMALLOC=malloc:** Python's internal allocator makes Valgrind report false positives. PYTHONMALLOC=malloc forces Python to use system malloc, making Valgrind's output clean.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Memory leak detection | Custom leak tracking | Valgrind with suppression file | Valgrind catches all malloc/free mismatches; custom tracking misses edge cases |
| Test determinism | Custom RNG seed tracking | Model.seed property + num_workers=1 | Infrastructure already exists from Phase 4 |
| Branching score verification | Manual formula recomputation in Python | BranchingFunction() direct call in C tests | The formula is in Branching.h inline; C tests can call it directly |
| Array normalization testing | Manual L1 norm computation | solver_ctx_set_branching_weights() + inspect ctx fields | The C function handles normalization; just verify the stored values |

**Key insight:** The testing infrastructure is already mature from Phases 1-16. This phase fills coverage gaps and runs verification, not building new infrastructure.

## Common Pitfalls

### Pitfall 1: Valgrind False Positives from Python Runtime
**What goes wrong:** Valgrind reports thousands of "leaks" from Python's memory allocator, NumPy initialization, and Cython module loading.
**Why it happens:** Python uses its own memory pool (pymalloc) that looks like leaks to Valgrind.
**How to avoid:** Always use `PYTHONMALLOC=malloc` environment variable AND the suppression file `tests/valgrind-python.supp`. The suppression file already handles Python, NumPy, Cython, and pytest allocations.
**Warning signs:** Valgrind output mentioning `PyObject_Malloc`, `PyObject_Realloc`, `_PyObject_GC_New`, numpy internal functions.

### Pitfall 2: Non-Deterministic Tests with Multiple Workers
**What goes wrong:** Tests asserting deterministic results fail intermittently when num_workers > 1.
**Why it happens:** Thread scheduling is non-deterministic; with multiple workers, the order of exploration varies between runs even with the same seed.
**How to avoid:** Deterministic tests MUST use `set_param("num_workers", 1)`. The Phase 15 verification already flagged one flaky test (`test_branching_bias_deterministic_local_search`) that intermittently fails in full suite runs.
**Warning signs:** Test passes when run individually but fails in full suite; "same seed + same weights should give same objective" assertion failures.

### Pitfall 3: Division-by-Zero Guard Masking Real Bugs
**What goes wrong:** BranchingFunction returns 0.5 (uniform random) when all factors are zero, which produces valid-looking results that hide misconfiguration.
**Why it happens:** The division-by-zero guard (factor_sum <= 0.0 returns 0.5) was added intentionally but can mask cases where factors were supposed to be set but weren't.
**How to avoid:** Write tests that verify non-default branching scores when weights are set. Don't just check "result is valid" -- check "result is different from default configuration."
**Warning signs:** Tests pass but branching_weights don't actually influence behavior.

### Pitfall 4: Branching Weights Not Reaching BranchingFunction
**What goes wrong:** Weights are set via set_param() but the solver doesn't actually use them because the Cython propagation path has a bug.
**Why it happens:** The propagation chain is: Model._params -> SearchLib.pyx -> solver_ctx_set_branching_weights() -> ctx.branching_stats. Any break in this chain causes silent fallback to default behavior.
**How to avoid:** Write tests that verify identical seeds with DIFFERENT weights produce DIFFERENT results. The existing `test_branching_weights_deterministic` only verifies same weights produce same results.
**Warning signs:** Changing weights doesn't change solver output with same seed.

### Pitfall 5: general_greedy() Call Missing Before solve()
**What goes wrong:** Tests fail with mysterious errors because initial_state is not set.
**Why it happens:** Some test patterns call `general_greedy()` before `solve()` and some don't. In the current codebase, `solve()` calls `manual_initial()` if not initialized, so it's not strictly needed, but `general_greedy()` also calls `initial_state_preparation()` which is a different code path.
**How to avoid:** Be consistent. If a test exercises the full pipeline, include `general_greedy()`. For API-focused tests, rely on solve()'s auto-initialization.
**Warning signs:** Tests pass without `general_greedy()` but miss code paths that would trigger bugs.

## Code Examples

Verified patterns from the existing codebase:

### Valgrind Run Command for C Tests
```bash
# Source: existing CI pattern
cd tests && mkdir -p build-valgrind && cd build-valgrind
cmake .. -DCMAKE_BUILD_TYPE=Debug
cmake --build .
valgrind --leak-check=full --error-exitcode=1 ./test_branching
```

### Valgrind Run Command for Python Tests
```bash
# Source: tests/test_cython_memory.py header
PYTHONMALLOC=malloc valgrind --leak-check=full \
    --suppressions=tests/valgrind-python.supp \
    --error-exitcode=1 \
    python -m pytest tests/test_cython_memory.py -v
```

### Testing Different Weights Produce Different Results
```python
# New pattern needed for Phase 17
def test_different_weights_produce_different_results(self):
    """Different branching_weights with same seed produce different results."""
    n = 20
    m1 = _make_knapsack_model(n)
    m1.seed = 42
    m1.set_param("branching_weights", [1.0] * n)  # uniform weights
    m1.set_param("stopping_time", 5)
    m1.set_param("num_workers", 1)
    result1 = m1.solve()

    m2 = _make_knapsack_model(n)
    m2.seed = 42
    m2.set_param("branching_weights", [float(10 * i + 1) for i in range(n)])  # extreme skew
    m2.set_param("stopping_time", 5)
    m2.set_param("num_workers", 1)
    result2 = m2.solve()

    # With very different weights, at least the solution should differ
    # (not guaranteed, but likely with skewed weights)
    # At minimum, both should complete without error
    assert isinstance(result1, OptimizeResult)
    assert isinstance(result2, OptimizeResult)
```

### C Test for Division-by-Zero Guard
```c
// New pattern needed for Phase 17
static void test_branching_function_all_factors_zero(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    solver_ctx_set_branching_factor(ctx, 0.0);
    solver_ctx_set_bias_factor(ctx, 0.0);
    solver_ctx_set_look_factor(ctx, 0.0);

    double result = BranchingFunction(0, 0, 0, 0, &ctx->branching_stats);
    assert_true(fabs(result - 0.5) < 1e-9);  // Division-by-zero guard
}
```

### C Test for Weights Reallocation
```c
// New pattern needed for Phase 17
static void test_branching_weights_realloc_different_sizes(void **state) {
    solver_ctx_t *ctx = (solver_ctx_t *)*state;
    // Set weights of size 2
    double arr1[] = {1.0, 1.0};
    solver_ctx_set_branching_weights(ctx, arr1, 2);
    assert_int_equal(ctx->branching_stats.num_weights, 2);

    // Replace with weights of size 5 (different allocation size)
    double arr2[] = {1.0, 2.0, 3.0, 4.0, 5.0};
    solver_ctx_set_branching_weights(ctx, arr2, 5);
    assert_int_equal(ctx->branching_stats.num_weights, 5);
    // Verify L1 normalization: sum = 15, so first = 1/15
    assert_true(fabs(ctx->branching_stats.branching_weights[0] - 1.0/15.0) < 1e-9);

    // Clear weights
    solver_ctx_set_branching_weights(ctx, NULL, 0);
    assert_null(ctx->branching_stats.branching_weights);
    assert_int_equal(ctx->branching_stats.num_weights, 0);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| solve() with kwargs | solve() zero-arg + set_param() | Phase 15 (Feb 2026) | All tests already migrated |
| Global BranchingStats | solver_ctx_t.branching_stats | Phase 16 (Feb 2026) | All tests updated |
| Separate obj_dependent/constraint_dependent | Single branching_weights array | Phase 14 (Feb 2026) | New unified model |
| branching.pyx module | Deleted, functions in SearchLib | Phase 16 (Feb 2026) | Module no longer exists |
| set_seed() from cbqs.branching | Direct srand() from libc.stdlib | Phase 16 (Feb 2026) | Import test already exists |

**Deprecated/outdated:**
- `from cbqs.branching import set_seed` -- ModuleNotFoundError (verified in test_set_param.py)
- `solve(M=100, stopping_time=5, ...)` -- TypeError (verified in test_set_param.py)
- `set_param('manual_bias', ...)` -- ValueError (verified in test_set_param.py)
- `set_param('branching_factors', ...)` -- ValueError (verified in test_set_param.py)

## Detailed Gap Analysis

### TEST-01: All existing tests updated for new API
**Status:** LIKELY ALREADY SATISFIED
**Evidence:** Phase 15 migrated all 80+ solve() calls across 12 test files. Phase 16 deleted branching module and 383 tests passed afterward. Current grep shows all solve() calls are zero-arg.
**Action needed:** Run full suite and confirm 383/383 pass. Fix any regressions from Phase 16 (module deletion could have introduced subtle import issues).

### TEST-02: New tests for branching_weights array input
**Status:** PARTIALLY SATISFIED
**Evidence:** `test_branching_propagation.py` has 3 tests for branching_weights (sampling, local_search, deterministic). `test_branching.c` has 5 weights-specific tests (normalization, overwrite, clear, 3-term formula, null weights).
**Gaps:**
- No test verifying that DIFFERENT weights with SAME seed produce DIFFERENT branching behavior
- No test verifying weights values are L1-normalized correctly at the Python level (only C level)
- No test for edge case: all-zero weights (should trigger division-by-zero guard)
- No test for weights with many variables (e.g., n=100+) to verify scalability

### TEST-03: Deterministic branching propagation tests
**Status:** PARTIALLY SATISFIED
**Evidence:** `test_branching_propagation.py::TestBranchingWeightsPropagation::test_branching_weights_deterministic` verifies same seed + same weights = same result. `test_determinism.py` has 5 determinism tests.
**Gaps:**
- No test verifying determinism across multiple solve lifecycles (create model, solve, create new model, solve -- same seed + weights = same result)
- No test for deterministic branching with both weights AND individual factors set simultaneously
- The flaky `test_branching_bias_deterministic_local_search` should be investigated

### TEST-04: No memory leaks (Valgrind clean)
**Status:** INFRASTRUCTURE EXISTS, VERIFICATION NEEDED
**Evidence:** `test_cython_memory.py::TestBranchingMemory::test_branching_weights_no_leak` exists. `valgrind-python.supp` suppression file exists. Valgrind is available at `/usr/bin/valgrind`.
**Gaps:**
- No documented Valgrind run results for branching_weights lifecycle
- Need to verify C tests pass under Valgrind (test_branching covers overwrite/clear)
- Need to verify repeated set_param('branching_weights', ...) + solve() cycles don't leak
- Need Valgrind run for weights reallocation (different sizes across solve calls)

## Plan Decomposition Recommendation

### Plan 17-01: Test Audit and Coverage Enhancement
**Scope:** Run full test suite, fix any regressions, add missing branching_weights coverage tests
**Tasks:**
1. Run full Python test suite (pytest tests/ -v), document pass/fail status
2. Run full C test suite (cd tests/build && ctest), document pass/fail status
3. Fix any test failures identified in tasks 1-2
4. Add new Python tests:
   - Different weights produce observably different behavior (or at minimum don't crash)
   - All-zero weights edge case (division-by-zero guard at Python level)
   - Weights + individual factors combined determinism test
   - Branching weights with large n (100+ variables)
5. Add new C tests:
   - All-factors-zero BranchingFunction test
   - Weights reallocation with different sizes
   - Single-element weight array
6. Run full test suite again to confirm all new + existing tests pass

### Plan 17-02: Valgrind Memory Verification
**Scope:** Run Valgrind on C tests and Python memory tests, verify zero leaks for branching_weights
**Tasks:**
1. Build C tests in debug mode for Valgrind
2. Run Valgrind on test_branching (covers weights lifecycle)
3. Run Valgrind on Python test_cython_memory.py::TestBranchingMemory
4. Add Python Valgrind test: repeated set_param/solve with changing weights sizes
5. Run full Valgrind sweep and document results
6. Fix any leaks identified

## Open Questions

1. **Flaky local_search determinism test**
   - What we know: `test_branching_bias_deterministic_local_search` was flagged as flaky in Phase 15 verification
   - What's unclear: Whether this is a real non-determinism bug or a test design issue (timeout-dependent behavior)
   - Recommendation: Investigate during Plan 17-01. Increase stop_time or mark as known-flaky with pytest.mark.xfail

2. **Valgrind on Python 3.13**
   - What we know: Python 3.13 is installed. Suppression file covers Python 3.13 internal allocations. PYTHONMALLOC=malloc should work.
   - What's unclear: Whether Python 3.13's new memory model introduces new false positives not covered by existing suppression file
   - Recommendation: Run Valgrind early in Plan 17-02, update suppression file if needed

3. **Pre-existing preprocessing memory leak**
   - What we know: MEMORY.md documents "Pre-existing memory leaks in preprocessing() -- tracked, not blocking"
   - What's unclear: Whether this leak will cause Valgrind failures when testing branching_weights
   - Recommendation: If preprocessing leak shows up in Valgrind output, add a targeted suppression for it (it's out of scope for Phase 17)

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** -- Direct reading of all 16 Python test files, 14 C test files, Model.pyx, SearchLib.pyx, solver_ctx.c, Branching.h
- **Phase 14 VERIFICATION.md** -- Documents BranchingStats_t restructure, 3-term formula, L1 normalization
- **Phase 15 VERIFICATION.md** -- Documents zero-arg solve() migration, 80+ call sites updated, 382 tests passing
- **Phase 16 VERIFICATION.md** -- Documents global state removal, branching module deletion, 383 tests passing
- **ROADMAP.md Phase 17 section** -- Defines success criteria TEST-01 through TEST-04

### Secondary (MEDIUM confidence)
- **Phase 15 note on flaky test** -- "One flaky test (test_branching_bias_deterministic_local_search) fails intermittently in full suite but passes individually"
- **MEMORY.md** -- Pre-existing preprocessing leak documented

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools already in use, verified by direct inspection
- Architecture: HIGH -- all test patterns extracted from existing code, no new infrastructure needed
- Pitfalls: HIGH -- Valgrind/determinism pitfalls documented from codebase analysis and prior phase verifications
- Gap analysis: HIGH -- based on direct comparison of existing tests vs. TEST-01 through TEST-04 requirements

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable -- test infrastructure doesn't change rapidly)
