# Phase 1: Test Foundation - Research

**Researched:** 2026-02-04
**Domain:** C unit testing (CMocka), Python testing (pytest), CMake build integration, GitHub Actions CI
**Confidence:** HIGH

## Summary

This research covers establishing a CMocka-based C test suite and a pytest-based Python test suite for the CBQS (Constraint-oriented Biased Quantum Search) solver project. The codebase consists of a C kernel (`cbqs/src/`) with 10 source files, Cython bindings (`.pyx` files), and Python wrapper classes. Currently there are zero tests -- only an ad-hoc `test.c` main function that exercises one knapsack instance.

The standard approach is to use CMocka (fetched via CMake FetchContent) for C-level unit tests and pytest with `@pytest.mark.xfail` for known-bug expected-failure tests. The C tests compile separately from the Cython build using a dedicated `tests/CMakeLists.txt`. Python tests exercise the installed Cython package through pytest.

**Primary recommendation:** Use CMocka 1.1.7 (stable, well-documented, proven CMake FetchContent pattern) for C tests, pytest for Python tests, with ASan opt-in via `-DASAN=ON`. Avoid CMocka 2.0.0 (released December 2025) -- it is too new, the FetchContent pattern is less proven, and the API changes (C99 requirement, type-safe macros) offer no compelling benefit for this project's needs.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CMocka | 1.1.7 | C unit testing framework | De facto standard for C testing; supports mock objects, assert macros, setup/teardown; lightweight with no dependencies beyond standard C library |
| pytest | 8.x (latest) | Python test framework | Standard Python testing; supports xfail markers, fixtures, parametrize; already available via pip |
| CMake | 3.14+ (FetchContent) | C test build system | Project already uses CMake 3.28; FetchContent is the modern way to pull CMocka without system install |
| CTest | (bundled with CMake) | C test runner | Integrates with CMake, discovered by `enable_testing()` + `add_test()` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| AddressSanitizer | (compiler built-in) | Memory error detection | Opt-in via `-DASAN=ON` flag; use `-fsanitize=address -fno-omit-frame-pointer` |
| GitHub Actions | N/A | CI runner | Runs both C and Python test suites on push |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CMocka 1.1.7 | CMocka 2.0.0 | 2.0 has type-safe macros and TAP 14 but was released Dec 2025; FetchContent integration less battle-tested; 1.1.7 is proven and stable |
| CMocka | Check / Unity | CMocka has better mock support and is more widely used for C projects of this complexity |
| pytest | unittest | pytest has cleaner syntax, xfail markers, better output; no reason to use unittest |

**Installation:**
```bash
# C tests: CMocka fetched automatically via CMake FetchContent (no manual install)
# Python tests:
pip install pytest
```

## Architecture Patterns

### Recommended Project Structure
```
tests/
  CMakeLists.txt           # CMake config for C tests (fetches CMocka, builds test executables)
  test_intarray.c          # Tests for intarray.h/c (bitarray operations)
  test_expression.c        # Tests for Expression.h/c
  test_constraint.c        # Tests for constraint.h/c
  test_state.c             # Tests for state.h/c
  test_branching.c         # Tests for Branching.h/c
  test_model.c             # Tests for model.h/c
  test_solver.c            # Tests for solver.h/c (initial_state_preparation, CSearch variants)
  test_quantum_search.c    # Tests for quantum_search.h/c (QSearch)
  test_searchlib.c         # Tests for SearchLib.h/c (ctg, bfs, incumbents)
  test_local_search.c      # Tests for local_search.h/c
  conftest.py              # pytest fixtures (build small models, known problems)
  test_expression_py.py    # Python-level Expression/Variable tests
  test_constraint_py.py    # Python-level Constraint wrapper tests
  test_model_py.py         # Python-level Model API tests (full integration)
```

### Pattern 1: CMocka Test File Structure
**What:** Each test file tests one C source module with setup/teardown fixtures
**When to use:** Every C test file
**Example:**
```c
// Source: https://api.cmocka.org/
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

#include "Expression.h"

// Setup fixture: create a fresh expression
static int setup_expression(void **state) {
    expression_t *expr = init_expression();
    *state = expr;
    return 0;
}

// Teardown fixture: free expression
static int teardown_expression(void **state) {
    expression_t *expr = *state;
    free_expression(expr);
    return 0;
}

static void test_add_constant(void **state) {
    expression_t *expr = *state;
    add_constant(expr, 42);
    assert_int_equal(expr->expr_size, 1);
    assert_int_equal(expr->literals[0], 42);
    assert_int_equal(expr->len_literal[0], 1);
}

static void test_add_variable(void **state) {
    expression_t *expr = *state;
    add_variable(expr, 3);
    assert_int_equal(expr->expr_size, 1);
    assert_int_equal(expr->literals[expr_index(0, 0)], 1);   // coefficient
    assert_int_equal(expr->literals[expr_index(0, 1)], 3);   // variable index
    assert_int_equal(expr->len_literal[0], 2);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test_setup_teardown(test_add_constant, setup_expression, teardown_expression),
        cmocka_unit_test_setup_teardown(test_add_variable, setup_expression, teardown_expression),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
```

### Pattern 2: CMake FetchContent for CMocka
**What:** Fetch and build CMocka as a static library during cmake configure
**When to use:** tests/CMakeLists.txt
**Example:**
```cmake
# Source: https://github.com/OlivierLDff/cmocka-cmake-example
cmake_minimum_required(VERSION 3.14)
project(cbqs_tests C)

set(CMAKE_C_STANDARD 11)

include(FetchContent)
FetchContent_Declare(
    cmocka
    GIT_REPOSITORY https://git.cryptomilk.org/projects/cmocka.git
    GIT_TAG        cmocka-1.1.7
    GIT_SHALLOW    1
)
set(WITH_STATIC_LIB ON CACHE BOOL "CMocka: Build with a static library" FORCE)
set(WITH_CMOCKERY_SUPPORT OFF CACHE BOOL "" FORCE)
set(WITH_EXAMPLES OFF CACHE BOOL "" FORCE)
set(UNIT_TESTING OFF CACHE BOOL "" FORCE)
set(PICKY_DEVELOPER OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(cmocka)

# Source files from the kernel (same list as setup.py sources)
set(CBQS_SOURCES
    ../cbqs/src/Expression.c
    ../cbqs/src/constraint.c
    ../cbqs/src/intarray.c
    ../cbqs/src/state.c
    ../cbqs/src/Branching.c
    ../cbqs/src/solver.c
    ../cbqs/src/model.c
    ../cbqs/src/local_search.c
    ../cbqs/src/quantum_search.c
    ../cbqs/src/approximate_state_sampler.c
)

# ASan opt-in
option(ASAN "Enable AddressSanitizer" OFF)
if(ASAN)
    add_compile_options(-fsanitize=address -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address)
endif()

enable_testing()

# Macro to add a test
macro(add_cbqs_test name)
    add_executable(${name} ${name}.c ${CBQS_SOURCES})
    target_include_directories(${name} PRIVATE ../cbqs/src)
    target_link_libraries(${name} PRIVATE cmocka-static m pthread)
    add_test(NAME ${name} COMMAND ${name})
endmacro()

add_cbqs_test(test_intarray)
add_cbqs_test(test_expression)
add_cbqs_test(test_constraint)
add_cbqs_test(test_state)
add_cbqs_test(test_branching)
add_cbqs_test(test_model)
add_cbqs_test(test_solver)
# ... etc
```

### Pattern 3: pytest xfail for Known Bugs
**What:** Mark tests that expose known bugs as expected failures
**When to use:** Tests that verify behavior of known bugs (Phase 2 will fix them)
**Example:**
```python
# Source: https://docs.pytest.org/en/stable/how-to/skipping.html
import pytest

@pytest.mark.xfail(reason="Known bug: objective value wrong for empty state (Phase 2 fix)")
def test_empty_state_objective():
    # This test documents the known bug
    model = create_simple_knapsack()
    result = model.solve(...)
    assert result == expected_value
```

### Pattern 4: Python Integration Test for Feasibility Check
**What:** Construct a model via Python API, solve it, verify all constraints satisfied
**When to use:** Integration tests that verify the solver produces feasible solutions
**Example:**
```python
from cbqs.Model import Model
from cbqs.Constants import MAXIMIZE, MINIMIZE

def test_knapsack_feasibility():
    """Verify solver finds a feasible solution for a small knapsack."""
    m = Model()
    x = m.add_variables(5)

    # Objective: maximize sum of x_i
    obj = sum(x[i] for i in x)
    m.set_objective(obj, sense=MAXIMIZE)

    # Constraint: 2*x0 + 3*x1 + x2 + 4*x3 + 2*x4 <= 7
    m.add_constraint(2*x[0] + 3*x[1] + x[2] + 4*x[3] + 2*x[4] <= 7)
    m.close()
    m.general_greedy()
    result = m.solve(stopping_time=10, num_workers=1)

    # Verify feasibility (all constraints satisfied)
    # Do NOT check objective quality -- solver is heuristic
    assert m.constraint.eval_con_from_array([...]) == 1
```

### Anti-Patterns to Avoid
- **Linking CMocka tests against Cython extensions:** The C tests must link directly against C source files, not the compiled `.so` extensions. Cython extensions embed Python interpreter state and cannot be loaded from pure C.
- **Testing objective quality in integration tests:** The solver is heuristic. Only test that solutions are *feasible* (constraints satisfied), not that they achieve optimal or near-optimal objective values.
- **Compiling all C sources into one test binary:** Each test file should compile to its own executable. This isolates failures and avoids symbol collisions (e.g., the global `BranchingStats`).
- **Forgetting `-pthread` on Linux:** The C source uses `#include <pthread.h>` extensively. Tests must link with `-lpthread`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| C test harness | Custom main() with if-checks | CMocka `cmocka_run_group_tests` | Handles signal catching, memory leak detection, structured output |
| Test discovery | Shell scripts listing test executables | CTest (`enable_testing()` + `add_test()`) | Standard CMake integration, `ctest --output-on-failure` |
| Expected failure tracking | Comment out failing tests | `@pytest.mark.xfail(reason="...")` | Visible in output, doesn't break suite, auto-detects when bug is fixed (XPASS) |
| ASan build variant | Separate Makefiles | CMake `option(ASAN)` + conditional flags | One build system, toggle with `-DASAN=ON` |
| CI pipeline | Custom shell scripts | GitHub Actions workflow YAML | Standard, well-documented, free for public repos |

**Key insight:** CMocka + CTest + pytest + GitHub Actions is the well-trodden path. Every piece already exists and integrates well. Custom build/test infrastructure would be wasted effort.

## Common Pitfalls

### Pitfall 1: CMocka Header Include Order
**What goes wrong:** Compilation errors from CMocka headers if included in wrong order
**Why it happens:** CMocka requires `stdarg.h`, `stddef.h`, `setjmp.h` included before `cmocka.h`
**How to avoid:** Always use this exact include order at the top of every test file:
```c
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
```
**Warning signs:** Cryptic compilation errors mentioning `jmp_buf` or `va_list`

### Pitfall 2: Global State in BranchingStats
**What goes wrong:** Tests that modify `BranchingStats` global variable pollute other tests
**Why it happens:** `BranchingStats` is a global variable (`extern BranchingStats_t BranchingStats`). C tests share the process.
**How to avoid:** Use CMocka setup/teardown fixtures to save and restore `BranchingStats` before/after each test. Or reset it to known defaults in each test's setup.
**Warning signs:** Tests pass individually but fail when run together

### Pitfall 3: Memory Leaks from Complex Constraint Setup
**What goes wrong:** Tests leak memory because they don't free constraints/expressions/states properly
**Why it happens:** The C API requires explicit `free_expression()`, `free_constraints()`, `free_state()` calls. The order matters (e.g., expressions can be freed after adding to constraints).
**How to avoid:** Use CMocka teardown fixtures that call the correct free functions. Run tests with ASan to catch leaks.
**Warning signs:** ASan reports, growing memory usage during test runs

### Pitfall 4: printf in Source Code
**What goes wrong:** Test output is polluted with progress indicators from the C kernel
**Why it happens:** Several C functions contain `printf("\r%f", ...)` progress output (e.g., `add_expression_to_constraints`, `merge_expression`, `preprocessing`). These print to stdout during test execution.
**How to avoid:** Accept the noise for Phase 1. Fixing the printf calls is a Phase 2 concern. Alternatively, redirect stdout in test fixtures.
**Warning signs:** Test output mixed with progress percentages

### Pitfall 5: Building Cython Extensions Before Python Tests
**What goes wrong:** Python tests fail with ImportError because Cython extensions are not compiled
**Why it happens:** The cbqs package contains `.pyx` files that must be compiled via `python setup.py build_ext --inplace` before pytest can import them
**How to avoid:** CI workflow must run `pip install -e .` or `python setup.py build_ext --inplace` before `pytest`
**Warning signs:** `ImportError: No module named 'cbqs.Model'`

### Pitfall 6: Circular Dependencies in C Headers
**What goes wrong:** Compilation errors when including solver.h or SearchLib.h in tests
**Why it happens:** The header dependency chain is deep: `SearchLib.h` -> `solver.h` -> `model.h` -> `constraint.h` -> `state.h` -> `intarray.h`. Some headers have commented-out includes suggesting past circular dependency issues.
**How to avoid:** Include the specific header for the module under test. The headers have proper include guards (`#ifndef`).
**Warning signs:** Redefinition errors, multiple definition of symbols

## Code Examples

### Example 1: Minimal intarray Test (Simplest Possible Test)
```c
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include "intarray.h"

static void test_sw_init(void **state) {
    (void)state;
    array_t arr = sw_init(64);
    assert_int_equal(arr.bits, 64);
    assert_int_equal(arr.n, 2);   // 64 >> 6 + 1 = 2
    assert_non_null(arr.part);
    sw_clear(arr);
}

static void test_sw_setbit_tstbit(void **state) {
    (void)state;
    array_t arr = sw_init(128);
    sw_setbit(arr, 0);
    assert_int_equal(sw_tstbit(arr, 0), 1);
    assert_int_equal(sw_tstbit(arr, 1), 0);
    sw_setbit(arr, 65);
    assert_int_equal(sw_tstbit(arr, 65), 1);
    sw_clear(arr);
}

static void test_sw_flpbit(void **state) {
    (void)state;
    array_t arr = sw_init(64);
    assert_int_equal(sw_tstbit(arr, 5), 0);
    sw_flpbit(arr, 5);
    assert_int_equal(sw_tstbit(arr, 5), 1);
    sw_flpbit(arr, 5);
    assert_int_equal(sw_tstbit(arr, 5), 0);
    sw_clear(arr);
}

static void test_sw_clrbit(void **state) {
    (void)state;
    array_t arr = sw_init(64);
    sw_setbit(arr, 10);
    assert_int_equal(sw_tstbit(arr, 10), 1);
    sw_clrbit(arr, 10);
    assert_int_equal(sw_tstbit(arr, 10), 0);
    sw_clear(arr);
}

static void test_sw_cmp(void **state) {
    (void)state;
    array_t a = sw_init(64);
    array_t b = sw_init(64);
    assert_int_equal(sw_cmp(a, b), 1);
    sw_setbit(a, 3);
    assert_int_equal(sw_cmp(a, b), 0);
    sw_setbit(b, 3);
    assert_int_equal(sw_cmp(a, b), 1);
    sw_clear(a);
    sw_clear(b);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_sw_init),
        cmocka_unit_test(test_sw_setbit_tstbit),
        cmocka_unit_test(test_sw_flpbit),
        cmocka_unit_test(test_sw_clrbit),
        cmocka_unit_test(test_sw_cmp),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
```

### Example 2: Constraint Evaluation Test (Core Logic)
```c
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include "constraint.h"

// Test: simple knapsack constraint 2*x0 + 3*x1 <= 5
static void test_eval_constraint_satisfied(void **state) {
    (void)state;

    // Build expression: 2*x0 + 3*x1 <= 5
    expression_t *expr = init_expression();
    add_variable(expr, 0);
    multiply_constant(expr, 2);
    add_variable(expr, 1);
    multiply_constant(expr, 3);  // Note: multiply_constant scales ALL terms
    // Actually need to build it differently -- see codebase pattern from test.c

    // ... (details depend on expression building semantics)

    free_expression(expr);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_eval_constraint_satisfied),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
```

### Example 3: GitHub Actions CI Workflow
```yaml
# .github/workflows/tests.yml
name: Tests

on:
  push:
    branches: [main, feature/*]
  pull_request:
    branches: [main]

jobs:
  c-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: sudo apt-get update && sudo apt-get install -y cmake

      - name: Configure C tests
        run: cmake -S tests -B tests/build -DASAN=ON

      - name: Build C tests
        run: cmake --build tests/build

      - name: Run C tests
        run: cd tests/build && ctest --output-on-failure

  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install pytest numpy pandas cython joblib
          pip install -e .

      - name: Run Python tests
        run: pytest tests/ -v
```

## Codebase Analysis: Function Prioritization for Testing

Based on thorough analysis of the C kernel, here is the priority ordering for which functions to test first:

### Priority 1 (Critical -- used everywhere, foundation for all other tests)
| Module | Functions | Why Critical |
|--------|-----------|-------------|
| `intarray.c/h` | `sw_init`, `sw_setbit`, `sw_tstbit`, `sw_clrbit`, `sw_flpbit`, `sw_cmp`, `sw_set`, `sw_set_ui_0` | Bit-array is the fundamental data structure; every other module depends on it |
| `Expression.c/h` | `init_expression`, `add_constant`, `add_variable`, `multiply_constant`, `multiply_variable`, `add_expression`, `merge_expression` | Expression building is required to construct any constraint/objective |
| `state.c/h` | `init_state`, `copy_state`, `free_state`, `copy_state_inplace` | State management is used in every solver path |

### Priority 2 (High -- core solver correctness)
| Module | Functions | Why Important |
|--------|-----------|---------------|
| `constraint.c/h` | `init_new_constraint`, `add_expression_to_constraints`, `eval_constraints`, `objective_value`, `constraint_violation`, `preprocessing` | Constraint evaluation determines feasibility -- the core correctness property |
| `model.c/h` | `init_model`, `free_model` | Model is the top-level container; init/free must not leak |
| `Branching.c/h` | `set_bias`, `set_factors`, `BranchingFunction`, `StateProbability` | Branching drives the sampling; incorrect bias = wrong search distribution |

### Priority 3 (Medium -- solver algorithms)
| Module | Functions | Why |
|--------|-----------|-----|
| `solver.c/h` | `initial_state_preparation`, `update_potentials` | State preparation is the greedy heuristic; potentials drive constraint satisfaction |
| `quantum_search.c/h` | `QSearch` | Core quantum search routine |
| `SearchLib.c/h` | `ctg`, `init_incumbents`, `compare` | Top-level search coordination |
| `local_search.c/h` | `local_search` | Alternative solver path |

### Python Test Scope Recommendation (Claude's Discretion)
Test the **full Model API** through pytest, not just Expression/Constraint wrappers. Rationale:
1. The Model class is the user-facing API -- it's what researchers actually call
2. Model.solve() exercises the entire pipeline: expression building -> constraint compilation -> preprocessing -> state preparation -> search
3. Expression and Constraint wrappers are already implicitly tested when building models
4. Add separate Expression/Constraint tests only for arithmetic correctness (operator overloading, `<=`, `>=`, `==`)

Recommended Python test files:
- `test_expression_py.py`: Variable arithmetic, Expression building, operator overloading
- `test_constraint_py.py`: Constraint construction, eval_con, eval_obj, process
- `test_model_py.py`: Full Model workflow (add variables, set objective, add constraints, close, solve, check feasibility)

## Important Codebase-Specific Notes

### Expression Building Semantics
The expression system uses a flat array representation where each "clause" occupies `MAXCLAUSESIZE=4` slots: `[coefficient, var1, var2, var3]` with `-1` as padding. The `multiply_constant` function multiplies ALL existing clauses' coefficients, not just the last one. This means building `2*x0 + 3*x1` requires:
```c
expression_t *e = init_expression();
add_constant(e, 2);        // e = [2]
multiply_variable(e, 0);   // e = [2, x0]
// Now need a NEW expression for the second term, or use add_variable then multiply
```
This is a critical detail -- the existing `test.c` shows the pattern used:
```c
add_variable(expr, 0);        // expr = [1, x0]
multiply_constant(expr, 2);   // expr = [2, x0]  -- multiplies ALL terms
add_variable(expr, 1);        // expr = [2, x0], [1, x1]
multiply_constant(expr, 2);   // expr = [4, x0], [2, x1]  -- WRONG if you wanted 2*x0 + x1
```
Tests must account for this multiplicative accumulation behavior. Building individual terms requires care.

### Thread Safety Concerns
- `BranchingStats` is a global variable. Tests modifying it must reset it.
- `srand()` is called in `test.c`. Tests using random functions should seed explicitly.
- `printf("\r...")` progress output in `add_expression_to_constraints`, `merge_expression`, and `preprocessing` will produce console noise during tests.

### Memory Management Pattern
The project follows a consistent alloc/free pattern:
- `init_*` functions return heap-allocated structs (or structs containing heap pointers)
- Corresponding `free_*` functions must be called
- `array_t` (intarray) is a value type with a heap-allocated `part` pointer -- `sw_clear()` frees the part
- `state_t` contains two `array_t` values -- `free_state()` clears both and frees the struct

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CMocka 1.1.x | CMocka 2.0.0 | December 2025 | Type-safe macros, TAP 14, C99 required. Not yet widely adopted via FetchContent. |
| System-installed CMocka | FetchContent CMocka | CMake 3.14 (2019) | No system dependency; hermetic builds |
| Manual CI scripts | GitHub Actions | 2019+ | Declarative YAML, free for open source |

**Deprecated/outdated:**
- CMocka `cmockery_support`: Legacy compatibility layer, disabled in recommended setup
- `run_tests()` function: Deprecated in favor of `cmocka_run_group_tests()`

## Open Questions

1. **Expression building for individual terms**
   - What we know: `multiply_constant` multiplies ALL clauses. The existing `test.c` shows a pattern that accumulates multiplications.
   - What's unclear: The cleanest way to build a linear expression like `a*x0 + b*x1 + c*x2` without the multiplicative accumulation issue.
   - Recommendation: Study the Cython `Expression.pyx` code which builds terms individually via `Variable.__mul__` creating fresh `Expression` objects. For C tests, create each term as a separate expression and combine with `add_expression`.

2. **User-provided optimization problem scripts**
   - What we know: User will provide specific Python scripts that construct models using the cbqs API for integration tests.
   - What's unclear: What those problems are specifically.
   - Recommendation: Create a placeholder integration test with the knapsack pattern from `test.c`, and add user-provided problems when available.

3. **Platform-specific concerns for CI**
   - What we know: Code uses `pthread.h`, `unistd.h`, and has macOS Metal code. The `u_int64_t` typedef in `intarray.h` is platform-dependent.
   - What's unclear: Whether the C tests will compile cleanly on Ubuntu (GitHub Actions default).
   - Recommendation: Metal code is separate from the core C kernel and need not be compiled in tests. The `#ifdef _WIN32` guard in `intarray.h` handles the type difference. Ubuntu CI should work with `-lpthread`.

## Sources

### Primary (HIGH confidence)
- CMocka official API documentation: https://api.cmocka.org/ - Assert macros, test registration, fixture patterns
- pytest xfail documentation: https://docs.pytest.org/en/stable/how-to/skipping.html - Expected failure marking
- Codebase analysis: Direct reading of all C headers, C source files, Cython bindings, setup.py, and existing CMakeLists.txt

### Secondary (MEDIUM confidence)
- CMocka FetchContent example: https://github.com/OlivierLDff/cmocka-cmake-example - CMake integration pattern verified against official CMocka repo
- CMocka 2.0.0 release announcement: https://blog.cryptomilk.org/2025/12/04/cmocka-2-0-released-enhancing-unit-testing-in-c/ - Version comparison
- GitHub Actions CMake patterns: https://cristianadam.eu/20191222/using-github-actions-with-c-plus-plus-and-cmake/

### Tertiary (LOW confidence)
- CMocka 2.0 FetchContent compatibility: Not directly verified; inferred from 1.1.x pattern. The 2.0 release mentions Meson support but CMake FetchContent should still work.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - CMocka and pytest are well-established; FetchContent pattern is documented
- Architecture: HIGH - Based on direct codebase analysis of all source files and build configuration
- Pitfalls: HIGH - Identified from actual code reading (global state, printf noise, expression semantics)
- Function prioritization: HIGH - Based on dependency analysis of actual header includes and function usage

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (stable technologies, 30-day validity)
