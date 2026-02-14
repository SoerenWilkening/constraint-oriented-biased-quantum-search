# Phase 16: Global State Removal - Research

**Researched:** 2026-02-14
**Domain:** C global variable elimination, Cython module deletion, build system cleanup
**Confidence:** HIGH

## Summary

Phase 16 is a surgical deletion phase. The solver context (`solver_ctx_t`) already fully replaces the global `BranchingStats` variable -- all C kernel code (solver.c, SearchLib.c, local_search.c, quantum_search.c, approximate_state_sampler.c) exclusively uses `ctx->branching_stats`. The global variable in Branching.h/c is dead code. Similarly, `branching.pyx` has been reduced to a single `set_seed()` function (wrapping `srand()`), which is called in SearchLib.pyx and Model.pyx but is itself a legacy artifact since the solver context now manages PRNG via `solver_ctx_init_prng()`.

The phase requires four specific deletions: (1) the global `BranchingStats` variable from C headers/sources, (2) any remaining deprecated C setter functions, (3) the entire `branching.pyx` module, and (4) corresponding `.pxd` declarations. Each deletion has downstream dependencies that must be updated simultaneously to maintain a compilable codebase.

**Primary recommendation:** Execute as 2 ordered plans: first remove the C-layer global and update C tests, then delete branching.pyx/pxd and update all Cython/Python callers and the build system.

## Current State Analysis

### What Exists (Targets for Removal)

| Item | File | Line(s) | Status |
|------|------|---------|--------|
| `extern BranchingStats_t BranchingStats` | `cbqs/src/Branching.h` | 27 | Dead declaration -- no kernel code uses it |
| `BranchingStats_t BranchingStats = {...}` | `cbqs/src/Branching.c` | 6-13 | Dead definition -- only test files reference it |
| `branching.pyx` | `cbqs/branching.pyx` | 1-2 | Contains only `set_seed()` wrapping `srand()` |
| `branching.pxd` | `cbqs/branching.pxd` | 1-22 | Declares `BranchingStats_t`, `BranchingStats` global, `StateProbability` |
| `branching` Extension | `setup.py` | 58-59 | Build config for `cbqs.branching` module |

### What Already Works (No Changes Needed)

| Item | Evidence |
|------|----------|
| `BranchingStats_t` struct definition | Still needed -- `solver_ctx_t` embeds it. Stays in Branching.h. |
| `BranchingFunction()` inline | Still used by solver.c, Branching.c, approximate_state_sampler.c via `&ctx->branching_stats`. Stays. |
| `StateProbability()` function | Used by SearchLib.pxd/pyx via `ctx`. Stays in Branching.c. |
| `solver_ctx_*` setters | Fully operational, used by SearchLib.pyx. No changes. |

### GLOB-02: Deprecated C Setter Functions

Current codebase grep shows NO remaining `set_factors()`, `set_bias()`, `set_obj_dependence()`, or `set_constraint_dependence()` functions in any `.c` or `.h` file. These were already removed in Phase 14. **GLOB-02 is already satisfied** -- this phase only needs to verify it, not implement it.

## Architecture Patterns

### Dependency Graph for Deletion

```
branching.pyx  (GLOB-03: DELETE)
  |-- set_seed() --> srand()      [callers: SearchLib.pyx:13,190  Model.pyx:23,567]
  |                                [callers: __init__.py:3]

branching.pxd  (GLOB-04: DELETE)
  |-- BranchingStats_t struct     [imported by: SearchLib.pxd:6 (for StateProbability)]
  |-- BranchingStats global       [imported by: nothing active]
  |-- StateProbability decl       [imported by: SearchLib.pxd:6]

Branching.h line 27  (GLOB-01: DELETE extern)
  |-- extern BranchingStats       [used by: test_solver.c, test_local_search.c, test_integration.c]

Branching.c lines 6-13  (GLOB-01: DELETE definition)
  |-- BranchingStats = {...}      [linker symbol -- tests link against it]
```

### Deletion Order (Critical)

**Plan 16-01: C Layer Cleanup**
1. Remove `extern BranchingStats_t BranchingStats;` from `Branching.h` (line 27)
2. Remove `BranchingStats_t BranchingStats = {...};` from `Branching.c` (lines 6-13)
3. Update comments in `solver_ctx.h` and `solver_ctx.c` that reference "global BranchingStats"
4. Update 3 C test files that reset the global: `test_solver.c`, `test_local_search.c`, `test_integration.c`
5. Build C tests, run them, verify pass

**Plan 16-02: Cython/Python Layer Cleanup**
1. Move `set_seed()` functionality: inline `srand()` call directly in SearchLib.pyx and Model.pyx (or use `solver_ctx_init_prng` which already replaces it)
2. Update `SearchLib.pxd` to declare `StateProbability` directly from `Branching.h` instead of importing from `branching.pxd`
3. Delete `cbqs/branching.pyx`
4. Delete `cbqs/branching.pxd`
5. Remove `Extension("cbqs.branching", ...)` from `setup.py`
6. Update `cbqs/__init__.py` to remove branching import
7. Update tests that import from `cbqs.branching` (test_set_param.py)
8. Full build + test suite

### set_seed Migration Strategy

`set_seed()` in `branching.pyx` wraps `srand()` from libc. It is called in:

1. **SearchLib.pyx line 190:** `set_seed(randint(0, 10000000))` -- at top of `run_sampling()`, before `solver_ctx_init_prng()` is called on line 226. This seeds the legacy C `rand()` function. Since the solver now uses `prng_next_double()` (xoshiro256**) via the context, this `srand()` call may only be needed for `quantum_local_search()` and `initial_state_preparation()` which might still use `rand()`.

2. **Model.pyx line 567:** `set_seed(int(time()))` -- seeds `rand()` at some point.

**Recommended approach:** Replace `from .branching import set_seed` with direct `from libc.stdlib cimport srand` and call `srand()` directly. This is a 1-line Cython equivalent -- no wrapper module needed.

### StateProbability Declaration Migration

`SearchLib.pxd` line 6 imports `StateProbability` from `branching.pxd`:
```cython
from .branching cimport StateProbability
```

After deleting `branching.pxd`, this declaration must move into `SearchLib.pxd` as a direct `cdef extern from "src/Branching.h"` block. The `solver_ctx_t` forward declaration is already in `SearchLib.pxd`.

### Test Updates for Global Removal

Three C test files reset the global `BranchingStats` in helper functions:

| File | Function | Lines | Fix |
|------|----------|-------|-----|
| `test_solver.c` | `build_small_model()` | 18-24 | Remove the 6 lines -- they reset a variable that no longer exists |
| `test_local_search.c` | `reset_branching_stats()` | 36-43 | Delete function + all calls (lines 123, 167, 207, 258) |
| `test_integration.c` | `reset_branching_stats()` | 17-24 | Delete function + all calls (lines 153, 178) |

These tests already use `solver_ctx_create()` for their actual test logic, so removing the global reset is safe -- it was only there to prevent cross-test pollution from a variable that kernel code no longer reads.

### Python Test Updates

`tests/test_set_param.py` class `TestOldAPIRemoved` (lines 282-298) tries to import from `cbqs.branching`:
```python
from cbqs.branching import set_factors_wrapper  # expects ImportError
```

After deleting `branching.pyx`, `from cbqs.branching import anything` will raise `ModuleNotFoundError` (a subclass of `ImportError`), so these tests will **still pass** -- the `pytest.raises(ImportError)` catches `ModuleNotFoundError`. No changes needed to these tests unless we want to update the assertion to be more specific.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PRNG seeding | Custom seed wrapper module | `from libc.stdlib cimport srand` | Direct Cython access to libc, zero overhead |
| Cross-file extern declarations | Manual header coordination | `cdef extern from "header.h"` blocks | Cython's native mechanism for C interop |

## Common Pitfalls

### Pitfall 1: Linker Errors from Dangling References
**What goes wrong:** Removing the `BranchingStats` definition from Branching.c causes linker errors if any compilation unit still references the symbol.
**Why it happens:** The `extern` declaration in Branching.h means any file that `#include`s Branching.h *could* reference it, even if the source code doesn't explicitly use the variable.
**How to avoid:** Grep the entire codebase for `BranchingStats` (not `BranchingStats_t`) before removing. Confirmed: only test files and comments reference it.
**Warning signs:** `undefined reference to 'BranchingStats'` linker error.

### Pitfall 2: Cython Import Chain Breakage
**What goes wrong:** Deleting `branching.pxd` breaks `SearchLib.pxd` which `cimport`s `StateProbability` from it. This causes a cascade: SearchLib.pyx, Model.pyx (which imports from SearchLib), and state_sampler.pyx all fail to compile.
**Why it happens:** Cython resolves `cimport` at compile time. Missing `.pxd` is a hard compile error.
**How to avoid:** Move the `StateProbability` declaration into `SearchLib.pxd` BEFORE deleting `branching.pxd`.
**Warning signs:** `cbqs/SearchLib.pxd:6: 'branching.pxd' not found` compile error.

### Pitfall 3: setup.py Extension Still Listed
**What goes wrong:** Build system tries to compile deleted `branching.pyx` and fails.
**Why it happens:** `Extension("cbqs.branching", ["cbqs/branching.pyx"] + sources, ...)` is still in setup.py.
**How to avoid:** Remove the Extension entry from setup.py in the same commit as deleting the .pyx file.
**Warning signs:** `FileNotFoundError: cbqs/branching.pyx`.

### Pitfall 4: Generated .c and .so Files Linger
**What goes wrong:** Old compiled `cbqs/branching.c` (Cython-generated), `cbqs/branching.cpython-*.so` files remain and may be loaded at import time even after source deletion.
**Why it happens:** Python's import system finds `.so` files before checking if source exists.
**How to avoid:** Delete `cbqs/branching.c` (the Cython-generated C file, NOT `cbqs/src/Branching.c`), `cbqs/branching.cpython-311-darwin.so`, and `cbqs/branching.cpython-313-x86_64-linux-gnu.so` in the same step. Also do a clean rebuild (`pip install -e . --no-build-isolation`).
**Warning signs:** Tests pass locally because old .so is cached, but fail in CI.

### Pitfall 5: `__init__.py` Import Failure
**What goes wrong:** `from .Model import Model, set_seed` in `__init__.py` line 3 -- if Model.pyx still does `from .branching import set_seed`, importing Model will fail.
**Why it happens:** Module import chain: `__init__.py -> Model -> branching (deleted)`.
**How to avoid:** Update Model.pyx to use `from libc.stdlib cimport srand` BEFORE deleting branching.pyx.

### Pitfall 6: Confusing Branching.c (C kernel) with branching.c (Cython-generated)
**What goes wrong:** Accidentally deleting `cbqs/src/Branching.c` (the C kernel file with StateProbability and updated()) instead of `cbqs/branching.c` (the Cython-generated file).
**Why it happens:** Case-sensitive filesystem, similar names.
**How to avoid:** Be explicit: `cbqs/branching.pyx` and `cbqs/branching.c` (generated) are deleted. `cbqs/src/Branching.c` and `cbqs/src/Branching.h` are MODIFIED (global removed) but NOT deleted.

## Code Examples

### Removing Global from Branching.h

Before:
```c
// cbqs/src/Branching.h
typedef struct {
    double *branching_weights;
    int num_weights;
    double branching_factor;
    double bias_factor;
    double bias;
    double look_factor;
} BranchingStats_t;

extern BranchingStats_t BranchingStats; // branching stats as global variable  <-- DELETE THIS LINE
```

After:
```c
// cbqs/src/Branching.h
typedef struct {
    double *branching_weights;
    int num_weights;
    double branching_factor;
    double bias_factor;
    double bias;
    double look_factor;
} BranchingStats_t;

// Global variable removed -- all state lives in solver_ctx_t.branching_stats
```

### Removing Global Definition from Branching.c

Before:
```c
// cbqs/src/Branching.c
#include "Branching.h"
#include "solver_ctx.h"

BranchingStats_t BranchingStats = {     // <-- DELETE THIS BLOCK
    .branching_weights = NULL,
    .num_weights = 0,
    .branching_factor = 1.0,
    .bias_factor = 1,
    .bias = 5,
    .look_factor = 0.0
};
```

After:
```c
// cbqs/src/Branching.c
#include "Branching.h"
#include "solver_ctx.h"

// Global BranchingStats removed -- all state lives in solver_ctx_t
```

### Migrating set_seed in SearchLib.pyx

Before:
```cython
from .branching import set_seed  # line 13

# ... in run_sampling():
set_seed(randint(0, 10000000))   # line 190
```

After:
```cython
from libc.stdlib cimport srand   # replace branching import

# ... in run_sampling():
srand(randint(0, 10000000))      # direct call, same effect
```

### Migrating StateProbability in SearchLib.pxd

Before:
```cython
# cbqs/SearchLib.pxd line 6
from .branching cimport StateProbability
```

After:
```cython
# cbqs/SearchLib.pxd
# Forward declaration for solver context
cdef extern from "src/solver_ctx.h":
    ctypedef struct solver_ctx_t:
        pass

cdef extern from "src/Branching.h":
    double StateProbability(solver_ctx_t *ctx, state_t *state, state_t *threshold)
```

Note: `solver_ctx_t` is already declared in `SearchLib.pxd` (lines 10-18), so only the `StateProbability` extern block needs adding.

### Updating C Test Files

Before (test_local_search.c):
```c
static void reset_branching_stats(void) {
    BranchingStats.branching_weights = NULL;
    BranchingStats.num_weights = 0;
    BranchingStats.branching_factor = 1.0;
    BranchingStats.bias_factor = 1;
    BranchingStats.bias = 5;
    BranchingStats.look_factor = 0;
}
```

After: Delete the function entirely and remove all calls to it. The tests already create a fresh `solver_ctx_t` per test, which initializes its own `branching_stats` with the same defaults.

## Build System Changes

### setup.py

Remove this extension entry:
```python
Extension("cbqs.branching", ["cbqs/branching.pyx"] + sources,
          extra_compile_args=compiler_args,
          include_dirs=[os.path.join("cbqs", "src")]),
```

### Files to Delete

| File | Type | Reason |
|------|------|--------|
| `cbqs/branching.pyx` | Cython source | GLOB-03: module removed |
| `cbqs/branching.pxd` | Cython declarations | GLOB-04: declarations removed |
| `cbqs/branching.c` | Cython-generated C | Build artifact of deleted .pyx |
| `cbqs/branching.cpython-311-darwin.so` | Compiled extension | Build artifact |
| `cbqs/branching.cpython-313-x86_64-linux-gnu.so` | Compiled extension | Build artifact |

### Files to Modify

| File | Change |
|------|--------|
| `cbqs/src/Branching.h` | Remove `extern BranchingStats_t BranchingStats;` (line 27) |
| `cbqs/src/Branching.c` | Remove `BranchingStats_t BranchingStats = {...};` (lines 6-13) |
| `cbqs/src/solver_ctx.h` | Update comments referencing "global BranchingStats" |
| `cbqs/src/solver_ctx.c` | Update comment on line 30 |
| `cbqs/SearchLib.pyx` | Replace `from .branching import set_seed` with `from libc.stdlib cimport srand` |
| `cbqs/SearchLib.pxd` | Replace `from .branching cimport StateProbability` with direct `cdef extern` |
| `cbqs/Model.pyx` | Replace `from .branching import set_seed` with `from libc.stdlib cimport srand` |
| `cbqs/__init__.py` | Remove `set_seed` from Model import (if it re-exports it) |
| `setup.py` | Remove `cbqs.branching` Extension entry |
| `tests/test_solver.c` | Remove global BranchingStats reset (lines 18-24) |
| `tests/test_local_search.c` | Remove `reset_branching_stats()` function and calls |
| `tests/test_integration.c` | Remove `reset_branching_stats()` function and calls |

### Files Unchanged

| File | Why |
|------|-----|
| `cbqs/src/Branching.h` (struct + inline) | `BranchingStats_t` struct and `BranchingFunction()` still used by solver_ctx_t |
| `cbqs/src/Branching.c` (StateProbability, updated) | Functions still used, take `solver_ctx_t*` |
| `tests/test_branching.c` | Already uses `solver_ctx_t` exclusively, no global references |
| `tests/test_thread_safety.c` | Includes `Branching.h` for the type, but does not use the global |
| `tests/test_set_param.py` | Tests that `from cbqs.branching import X` raises `ImportError` will still pass after module deletion |

## Open Questions

1. **Should `set_seed()` be preserved as a public API?**
   - What we know: `set_seed()` is exported via `__init__.py` (`from .Model import Model, set_seed`). Model.pyx re-exports it from branching.pyx. Some users may call `cbqs.set_seed()` directly.
   - What's unclear: Whether any downstream user code calls `set_seed()`.
   - Recommendation: Since this is a v2.0 breaking change, remove it. The solver context manages its own PRNG. If backward compat is desired, Model.pyx can expose a trivial `set_seed()` function directly. But the PRNG context (`solver_ctx_init_prng`) makes `srand()` largely irrelevant to solver behavior.

2. **Does `initial_state_preparation()` still use `rand()`?**
   - What we know: SearchLib.pyx calls `srand()` before `initial_state_preparation()`. The solver.c code uses `prng_next_double()` in the branching loops.
   - What's unclear: Whether `initial_state_preparation()` in solver.c still calls `rand()` anywhere.
   - Recommendation: Grep solver.c for `rand()` calls. If none found, the `srand()` call in SearchLib.pyx is truly dead code and can be removed entirely.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all files in `cbqs/src/`, `cbqs/`, `tests/`, `setup.py`
- Grep results for `BranchingStats`, `set_factors`, `set_bias`, `set_obj_dependence`, `set_constraint_dependence`, `set_seed`, `from .branching`
- Line-by-line reading of Branching.h, Branching.c, branching.pyx, branching.pxd, SearchLib.pyx, SearchLib.pxd, Model.pyx, solver_ctx.h, solver_ctx.c, setup.py, test_solver.c, test_local_search.c, test_integration.c, test_branching.c, test_thread_safety.c, test_set_param.py

### Secondary (MEDIUM confidence)
- Phase 14 and 15 completion status from git log and REQUIREMENTS.md

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - this is pure deletion/refactoring of existing code, no new libraries
- Architecture: HIGH - full codebase analysis, every reference traced
- Pitfalls: HIGH - identified all 6 major pitfalls from actual dependency analysis
- GLOB-02 status: HIGH - confirmed zero matches for deprecated setter functions in .c/.h files

**Research date:** 2026-02-14
**Valid until:** Indefinite (codebase-specific findings, not library version dependent)
