# Phase 10: C23 Migration & VLA Elimination - Research

**Researched:** 2026-02-08
**Domain:** C compiler standards migration (C11 -> C23), VLA elimination, warning remediation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### VLA replacement strategy
- Use arena allocation as the primary replacement for VLAs, matching existing v1.0 patterns
- Exception: VLAs under ~64 bytes in hot paths with provably bounded max size may use fixed-size stack buffers
- Arena lifetime: match whatever pattern v1.0 already uses -- do not introduce new lifetime semantics

#### Warning suppression policy
- Enable `-Werror` in CI only (not local development builds)
- Add `-Wpedantic` alongside `-Wall -Wextra` for strictest standard compliance
- Cython-generated C files: suppress warnings per-file using `#pragma` (these are outside our control)
- Unused parameters: use `__attribute__((unused))` -- wrapped in a portability macro for MSVC (see compiler scope)
- Sign comparison warnings: fix by changing variable types to match signedness (not casts)
- `stdbool.h` migration: include `stdbool.h` first in our headers; remove all `#define true/false` macros
- `callback_t` typedef: update to explicit `(void)` parameter list -- only `callback_t`, not all typedefs
- Implicit function declarations: Claude decides per-site whether to add missing includes or forward declarations

#### Compiler support scope
- Must support Windows/MSVC in addition to GCC/Clang on Linux/macOS
- Need a portability macro for `__attribute__((unused))` (e.g., `CBQS_UNUSED`) that maps to `__attribute__((unused))` on GCC/Clang and the MSVC equivalent
- Minimum GCC version, C standard version, and Clang support: Claude's discretion based on what the codebase actually needs and what the changes require

### Claude's Discretion
- VLA regression guard (compiler flag like `-Wvla` or CI grep check)
- Minimum GCC version to support
- C language standard to target (`-std=c11`, `-std=c17`, or `-std=c23`)
- Whether to also ensure Clang warning-free compilation
- Per-site choice of include vs forward declaration for implicit function warnings
- Portability macro implementation details

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Summary

This phase migrates the CBQS C kernel from its current informal C11 compilation mode to a GCC 15 / C23-compatible codebase with zero warnings under `-Wall -Wextra -Wpedantic`. The codebase has 17 C source files and 17 headers in `cbqs/src/`, plus 14 test files in `tests/`. The work spans six distinct categories: VLA elimination (1 remaining VLA), bool/true/false macro removal, callback_t parameter list fix, empty-parameter function declarations, sign/type mismatch fixes, and build system flag updates.

The codebase is in relatively good shape. Most VLAs were already replaced in earlier phases (Phase 5/6). The remaining issues are well-localized: one VLA in `local_search.c`, one `#define true/false` pair in `definitions.h`, one `callback_t` typedef needing `(void)`, several functions with empty `()` declarations, and systematic `int` vs `uint32_t` mismatches around `num_constraints`. The arena allocator is already production-ready and well-tested.

**Primary recommendation:** Target `-std=c17` (not C23) for maximum portability while fixing all C23-forward-compatible issues. Use `-Wvla -Werror=vla` in CI as the VLA regression guard. Ensure both GCC and Clang compile cleanly.

## Standard Stack

### Core

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| GCC | >= 12 | Primary compiler | CI runs on ubuntu-latest (GCC 13+) |
| Clang | >= 14 | Secondary compiler | TSan CI already uses Clang |
| CMake | >= 3.14 | Test build system | Already used in tests/CMakeLists.txt |
| CMocka | 1.1.7 | C unit tests | Already integrated via FetchContent |

### Supporting

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `-std=c17` | Language standard flag | All compilation units |
| `-Wall -Wextra -Wpedantic` | Warning flags | All compilation |
| `-Werror` | Warnings-as-errors | CI only |
| `-Wvla -Werror=vla` | VLA regression guard | CI only |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `-std=c17` | `-std=c23` | C23 would require addressing `_Thread_local` vs `__thread`, `u_int64_t` BSD type, and GCC 15+ minimum. C17 is safer for MSVC/portability and still allows all needed fixes. |
| `-std=c17` | `-std=c11` | Could work but c17 is a bug-fix release of c11 with no new features; no reason not to use it. |
| `-Werror=vla` | CI grep check | Compiler flag is more reliable than grep; grep can miss complex VLA patterns. |

## Architecture Patterns

### Codebase Structure (relevant to this phase)

```
cbqs/src/
  definitions.h         # Contains #define true/false and callback_t typedef -- PRIMARY TARGET
  arena.h/arena.c       # Arena allocator (already complete, v1.0 pattern)
  local_search.c        # Contains last VLA (line 332)
  solver_ctx.h/c        # Arena lifecycle management
  intarray.h            # Contains u_int64_t BSD type (needs portability fix)
  prng.h/c              # Uses __thread (GCC extension, needs portability consideration)
  constraint.h/c        # uint32_t num_constraints with int loop variables
  Expression.h/c        # init_expression() empty param list
  model.h/c             # init_model() empty param list
  solver.h/c            # Primary solver (many type pattern instances)
  SearchLib.h/c         # Python.h include, callback_t usage
  Branching.h/c         # Forward declarations, inline function
  state.h/c             # min() function name collision potential
  quantum_search.h/c    # Uses definitions.h patterns
  dyn_expr.h/c          # Modern patterns (already uses stdint.h properly)
  approximate_state_sampler.h/c  # Uses size_t C pattern
  solver_ctx.h/c        # Uses _GNU_SOURCE, stdatomic.h
tests/
  14 test_*.c files      # All need to compile warning-free
```

### Pattern 1: VLA Replacement with Arena Allocation

**What:** Replace `int64_t remainings[C]` with arena allocation matching existing patterns.
**When to use:** The single remaining VLA at `local_search.c:332`.
**Example (from existing code in same file, line 572):**
```c
/* Already done in quantum_local_search_states: */
int64_t *remainings = malloc(C * sizeof(int64_t));
if (remainings == NULL) {
    sw_clear(ful_con);
    return NULL;  /* Allocation failure */
}
/* ... use remainings ... */
free(remainings);
```

**For the accept_best_routine function at line 332:** This function already receives `solver_ctx_t *ctx` and uses the arena pattern elsewhere in the file. The replacement is:
```c
/* Replace: int64_t remainings[C]; */
int64_t *remainings;
int use_arena = (ctx != NULL && ctx->arena != NULL);
if (use_arena) {
    remainings = (int64_t *)arena_alloc(ctx->arena, C * sizeof(int64_t), 8);
} else {
    remainings = malloc(C * sizeof(int64_t));
}
if (remainings == NULL) { /* handle error */ }
/* ... use remainings ... */
if (!use_arena) free(remainings);
```

### Pattern 2: Portability Macro for CBQS_UNUSED

**What:** Cross-platform macro wrapping `__attribute__((unused))`.
**Where:** Add to `definitions.h` (the central definitions header).
```c
/* Portability: suppress "unused parameter" warnings */
#if defined(__GNUC__) || defined(__clang__)
  #define CBQS_UNUSED __attribute__((unused))
#elif defined(_MSC_VER)
  #define CBQS_UNUSED __pragma(warning(suppress: 4100))
#else
  #define CBQS_UNUSED
#endif
```

**Note:** MSVC `__pragma(warning(suppress: 4100))` only works as a statement, not on parameter declarations. A more portable alternative for MSVC is to simply use `(void)param;` at the function start. The recommended approach is:
```c
#if defined(__GNUC__) || defined(__clang__)
  #define CBQS_UNUSED __attribute__((unused))
#else
  #define CBQS_UNUSED
#endif
```
And on MSVC, rely on `/wd4100` or `(void)param;` idiom for unused parameters.

### Pattern 3: bool/true/false Migration

**What:** Remove `#define true 1` / `#define false 0` from `definitions.h`, add `#include <stdbool.h>`.
**Critical detail:** `definitions.h` is included by every source file via transitive includes. The migration must be atomic -- remove defines AND add stdbool.h in one change.
**C23 context:** In C23, `bool`, `true`, `false` are keywords. Including `stdbool.h` is harmless (it becomes a no-op in C23). This is the correct forward-compatible approach.

### Anti-Patterns to Avoid
- **Casting to suppress sign warnings:** User explicitly decided against casts. Fix the variable type instead.
- **`#pragma GCC diagnostic ignored` in our own code:** Only use for Cython-generated files.
- **Changing arena lifetime semantics:** User locked this -- match existing v1.0 patterns exactly.
- **Using C23-only features:** Keep to C17 features for MSVC portability.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Arena allocation | Custom allocator | Existing `arena.h/arena.c` | Already tested, production-ready |
| Boolean type | Custom defines | `<stdbool.h>` | Standard, C23-forward-compatible |
| Fixed-width integers | BSD types | `<stdint.h>` types | `uint64_t` is standard; `u_int64_t` is BSD-only |
| Thread-local storage | raw `__thread` | Keep `__thread` but document | `_Thread_local` has spotty support; `__thread` works on GCC/Clang; MSVC uses `__declspec(thread)` |

**Key insight:** The codebase already has all infrastructure needed (arena allocator, stdint types mostly). This phase is about cleanup, not new capabilities.

## Common Pitfalls

### Pitfall 1: Cython-Generated C Files Triggering Warnings

**What goes wrong:** `cbqs/SearchLib.c`, `cbqs/Model.c`, `cbqs/state_sampler.c`, etc. are Cython-generated and contain many constructs that trigger GCC warnings (unused variables, sign comparisons, etc.). These are NOT under our control.
**Why it happens:** Cython generates C code with its own patterns that don't match strict C warning policies.
**How to avoid:** The warning flags (`-Wall -Wextra -Wpedantic -Werror`) apply ONLY to the CMake test build and CI. The `setup.py` build uses its own `compiler_args = ["-O3", "-flto", "-pthread"]`. For the CMake build, Cython-generated files are not compiled (only `cbqs/src/*.c` files are). This is safe as-is.
**Warning signs:** If someone adds Cython-generated files to the CMake build, they'll get hundreds of warnings.

### Pitfall 2: `u_int64_t` Is a BSD Extension

**What goes wrong:** `intarray.h` line 12 uses `u_int64_t` which requires `_GNU_SOURCE` or BSD headers. MSVC doesn't have it.
**Why it happens:** Legacy BSD type usage from before standardization.
**How to avoid:** The file already has a `#ifdef _WIN32` guard using `uint64_t`. The non-Windows path should also use `uint64_t` and `#include <stdint.h>`. This removes the need for `_GNU_SOURCE` in `solver_ctx.c`.
**Warning signs:** Compile fails on strict-mode POSIX or MSVC without the guard.

### Pitfall 3: `__thread` Is Not Portable to MSVC

**What goes wrong:** `prng.h` uses `__thread` for thread-local PRNG state. MSVC uses `__declspec(thread)` instead.
**Why it happens:** `__thread` is a GCC/Clang extension, not C standard.
**How to avoid:** Add a `CBQS_THREAD_LOCAL` portability macro:
```c
#if defined(_MSC_VER)
  #define CBQS_THREAD_LOCAL __declspec(thread)
#elif defined(__GNUC__) || defined(__clang__)
  #define CBQS_THREAD_LOCAL __thread
#else
  #define CBQS_THREAD_LOCAL _Thread_local
#endif
```
C11 `_Thread_local` is the standard but has spotty runtime support. GCC/Clang `__thread` is reliable. MSVC `__declspec(thread)` is reliable. The macro covers all three.

### Pitfall 4: Sign Comparison Between `int` Loop Variable and `uint32_t` Fields

**What goes wrong:** GCC `-Wsign-compare` (enabled by `-Wextra`) flags `for (int cnstr = 0; cnstr < con->num_constraints; ++cnstr)` because `num_constraints` is `uint32_t` and `cnstr` is `int`.
**Why it happens:** Widespread pattern throughout `local_search.c` (4 instances), `constraint.c` (5 instances), `solver.c` (many instances), `metal_files/exec_metal.m` (3 instances).
**How to avoid:** User decided: change variable types to match signedness, not casts. Change `int cnstr` to `uint32_t cnstr` (or equivalently `size_t` where already used). Similarly for `num_clauses[cnstr]`, `clause_length[clause_index]`, etc.
**Warning signs:** Any loop comparing `int` to `uint32_t`, `size_t`, or other unsigned type.

### Pitfall 5: `callback_t` Change Affecting Cython Interface

**What goes wrong:** Changing `typedef void (*callback_t)();` to `typedef void (*callback_t)(void);` must be synchronized with the Cython `.pxd` declaration in `cbqs/SearchLib.pxd:31`.
**Why it happens:** Cython declarations must match C declarations exactly.
**How to avoid:** Update both `definitions.h` and `SearchLib.pxd` in the same change. The Cython declaration `ctypedef void (*callback_t)()` should remain as-is because Cython interprets `()` as `(void)` already.
**Warning signs:** Cython build errors or type mismatch warnings.

### Pitfall 6: Empty Parameter List Functions in Headers

**What goes wrong:** Several functions use `()` instead of `(void)`:
- `init_expression()` in `Expression.h:15` and `Expression.c:70`
- `init_new_constraint()` in `constraint.h:78` and `constraint.c:4`
- `init_model()` in `model.h:38` and `model.c:7`
- `main()` in `test.c:4`
**Why it happens:** In C17 and earlier, `()` means unspecified parameters (not zero parameters). In C23, `()` means zero parameters (same as `(void)`). However, `-Wpedantic` flags this in older standards.
**How to avoid:** Update all to explicit `(void)`. Must update both header declarations and function definitions.

## Code Examples

### VLA Replacement at local_search.c:332

Current code:
```c
int64_t remainings[C];
for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, new_sol, i);
```

Replacement using arena (matching existing v1.0 pattern in same file):
```c
int64_t *remainings;
int use_arena = (ctx != NULL && ctx->arena != NULL);
if (use_arena) {
    remainings = (int64_t *)arena_alloc(ctx->arena, C * sizeof(int64_t), 8);
} else {
    remainings = (int64_t *)malloc(C * sizeof(int64_t));
}
if (remainings == NULL) {
    free_state(cur_best, 1);
    free_state(cur_best_tabu, 1);
    sw_clear(ful);
    sw_clear(ful_con);
    free(prog_data.progress);
    free(data);
    free(threads);
    return -1;  /* Allocation failure */
}
for (int i = 0; i < C; ++i) remainings[i] = constraint_violation(con, new_sol, i);
/* ... use remainings ... */
if (!use_arena) free(remainings);  /* Only free if not arena-allocated */
```

### definitions.h Rewrite

Current:
```c
#define false 0
#define true 1
typedef void (*callback_t)();
```

Replacement:
```c
#include <stdbool.h>
typedef void (*callback_t)(void);
```

### intarray.h BSD Type Fix

Current:
```c
#ifdef _WIN32
typedef uint64_t part_length_t;
#else
typedef u_int64_t part_length_t;
#endif
```

Replacement:
```c
#include <stdint.h>
typedef uint64_t part_length_t;
```

### Sign Comparison Fix Pattern

Current:
```c
int C = con->num_constraints;  /* uint32_t -> int: sign mismatch */
for (int cnstr = 0; cnstr < C; cnstr++) { ... }
```

Replacement:
```c
uint32_t C = con->num_constraints;
for (uint32_t cnstr = 0; cnstr < C; cnstr++) { ... }
```

### CI Warning Flags in tests/CMakeLists.txt

Add to the `add_cmocka_test` function:
```cmake
function(add_cmocka_test NAME)
    set(SOURCES ${ARGN})
    add_executable(${NAME} ${SOURCES})
    target_include_directories(${NAME} PRIVATE
        "${CBQS_SRC_DIR}"
        "${cmocka_SOURCE_DIR}/include"
    )
    target_compile_options(${NAME} PRIVATE -Wall -Wextra -Wpedantic -Wvla)
    target_link_libraries(${NAME} PRIVATE cmocka-static pthread m)

    if(ASAN)
        target_compile_options(${NAME} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
        target_link_options(${NAME} PRIVATE -fsanitize=address)
    endif()

    add_test(NAME ${NAME} COMMAND ${NAME})
endfunction()

# CI-only: treat warnings as errors
option(WERROR "Enable -Werror (CI only)" OFF)
if(WERROR)
    # Applied after per-target options to override
    add_compile_options(-Werror -Werror=vla)
endif()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `#define bool int` / `#define true 1` | `#include <stdbool.h>` | C99 introduced `_Bool`; C23 makes `bool` a keyword | Macros conflict with C23 keywords |
| `void foo()` (unspecified params) | `void foo(void)` (zero params) | C23 merges meaning | `-Wpedantic` warns in C17; error-prone in C23 |
| `u_int64_t` (BSD extension) | `uint64_t` (`<stdint.h>`) | C99 standardized | BSD type requires `_GNU_SOURCE` on Linux |
| `__thread` (GCC extension) | `_Thread_local` (C11) | C11 standardized | MSVC uses `__declspec(thread)` |
| VLAs on stack | Arena/heap allocation | C11 made VLAs optional | VLAs have unbounded stack usage, banned in many codebases |
| GCC default `-std=gnu17` | GCC 15 default `-std=gnu23` | GCC 15 (2025) | Breaks `bool` macros, empty param lists |

**Deprecated/outdated:**
- `#define true 1` / `#define false 0`: Conflicts with C23 keywords. Replace with `<stdbool.h>`.
- `u_int64_t`: Non-standard BSD type. Replace with `uint64_t` from `<stdint.h>`.
- `typedef void (*callback_t)()`: Unspecified parameter list. Replace with `(void)`.

## Claude's Discretion Recommendations

### 1. VLA Regression Guard

**Recommendation:** Use `-Wvla` as a compile flag in CI combined with `-Werror=vla`.

**Rationale:** The compiler flag `-Werror=vla` turns any VLA usage into a hard compile error. This is more reliable than a CI grep check because:
- It catches VLAs with complex size expressions that grep would miss
- It works on preprocessed code (handles macros)
- It's zero maintenance

Add to the CMake test build: `target_compile_options(${NAME} PRIVATE -Wvla)` and in CI mode: `-Werror=vla`.

**Confidence:** HIGH -- `-Wvla` is supported by GCC >= 4.3 and all modern Clang versions.

### 2. Minimum GCC Version

**Recommendation:** GCC >= 10.

**Rationale:** The codebase uses C11 features (`<stdatomic.h>`, `_Atomic` via `atomic_bool`). GCC 10 has solid C17 support. Ubuntu 20.04 LTS ships GCC 9, but ubuntu-latest in CI is Ubuntu 22.04+ (GCC 12+). GCC 10 is a conservative minimum that covers all realistic deployment targets. There's no need to support GCC < 10 since the codebase uses `atomic_bool` which requires C11 minimum.

**Confidence:** HIGH -- based on actual codebase requirements.

### 3. C Language Standard

**Recommendation:** `-std=c17` (or `-std=gnu17` to preserve GNU extensions like `__thread`).

**Rationale:**
- **Why not C23:** C23 introduces `bool`/`true`/`false` as keywords and changes empty parameter list semantics, which is what we're migrating TOWARD. But MSVC C23 support is incomplete as of 2026. Targeting C17 keeps all compilers happy while the code changes themselves are C23-forward-compatible.
- **Why not C11:** C17 is a "bug-fix" release of C11 with no new features but corrects defect reports. No reason to stick with C11.
- **The `-std=gnu17` variant** preserves GNU extensions like `__thread` that the codebase already uses. Pure `-std=c17` would break `__thread`. With the `CBQS_THREAD_LOCAL` portability macro, we could use `-std=c17`, but `gnu17` is simpler.

**Confidence:** HIGH -- based on MSVC compatibility requirement and codebase analysis.

### 4. Clang Warning-Free Compilation

**Recommendation:** Yes, ensure Clang warning-free compilation.

**Rationale:** CI already uses Clang for ThreadSanitizer tests. Adding `-Wall -Wextra -Wpedantic` to the Clang TSan build is zero-cost. Clang's warnings are often stricter than GCC's, so passing Clang means definitely passing GCC. This provides defense-in-depth.

**Confidence:** HIGH -- CI already compiles with Clang.

### 5. Per-Site Include vs Forward Declaration

**Recommendation:** Prefer `#include` over forward declarations for implicit function warnings. Use forward declarations only when circular includes would result.

**Rationale:** The codebase already uses `#include` extensively. Forward declarations add maintenance burden (must be kept in sync). The primary case where forward declarations are needed is already handled: `Branching.h` forward-declares `struct solver_ctx` to break a circular dependency.

**Confidence:** HIGH -- based on codebase patterns.

### 6. Portability Macro Details

**Recommendation:** Add all portability macros to `definitions.h` (the existing central definitions file):

```c
/* --- Portability macros --- */

/* Suppress unused-parameter warnings */
#if defined(__GNUC__) || defined(__clang__)
  #define CBQS_UNUSED __attribute__((unused))
#else
  #define CBQS_UNUSED
#endif

/* Thread-local storage */
#if defined(_MSC_VER)
  #define CBQS_THREAD_LOCAL __declspec(thread)
#elif defined(__GNUC__) || defined(__clang__)
  #define CBQS_THREAD_LOCAL __thread
#else
  #define CBQS_THREAD_LOCAL _Thread_local
#endif
```

For MSVC, `CBQS_UNUSED` is defined as empty; MSVC users can suppress C4100 globally via project settings or `/wd4100`. The `CBQS_THREAD_LOCAL` macro covers all three major compilers.

**Confidence:** HIGH -- standard portability patterns widely used.

## Detailed Inventory of Changes Required

### File: `cbqs/src/definitions.h`
1. Remove `#define false 0` (line 45)
2. Remove `#define true 1` (line 46)
3. Add `#include <stdbool.h>` at top
4. Change `typedef void (*callback_t)();` (line 31) to `typedef void (*callback_t)(void);`
5. Add `CBQS_UNUSED` portability macro
6. Add `CBQS_THREAD_LOCAL` portability macro (optional, see prng.h below)

### File: `cbqs/src/intarray.h`
1. Remove `#ifdef _WIN32` / `u_int64_t` branch (lines 9-13)
2. Use `typedef uint64_t part_length_t;` unconditionally (stdint.h already included)

### File: `cbqs/src/local_search.c`
1. Replace VLA `int64_t remainings[C]` at line 332 with arena or malloc
2. Fix `int C = ...` to `uint32_t C = ...` at lines 178, 322, 484, 569 (4 instances)

### File: `cbqs/src/constraint.h`
1. Change `init_new_constraint()` declaration to `init_new_constraint(void)`

### File: `cbqs/src/constraint.c`
1. Change `init_new_constraint()` definition to `init_new_constraint(void)`
2. Fix format specifier `%zu` for `uint32_t num_constraints` at line 89

### File: `cbqs/src/Expression.h`
1. Change `init_expression()` declaration to `init_expression(void)`

### File: `cbqs/src/Expression.c`
1. Change `init_expression()` definition to `init_expression(void)`

### File: `cbqs/src/model.h`
1. Change `init_model()` declaration to `init_model(void)`

### File: `cbqs/src/model.c`
1. Change `init_model()` definition to `init_model(void)`

### File: `cbqs/src/solver_ctx.c`
1. Remove `#define _GNU_SOURCE` (no longer needed after u_int64_t fix)

### File: `cbqs/src/prng.h`
1. Replace `__thread` with `CBQS_THREAD_LOCAL` macro (2 instances: lines 31, 39)

### File: `cbqs/src/prng.c`
1. Replace `__thread` with `CBQS_THREAD_LOCAL` macro (2 instances: lines 24, 25)

### File: `cbqs/src/solver.c`
1. Fix `for (int cnstr = 0; cnstr < C; ...)` where C is `size_t` -- loop vars should be `size_t` or `uint32_t`
2. Multiple instances throughout the file (estimated 10+ loop fixes)

### File: `cbqs/src/SearchLib.c`
1. No changes to the file itself (callback_t change flows from definitions.h)
2. Verify `#include <Python.h>` doesn't cause issues with new warning flags

### File: `tests/CMakeLists.txt`
1. Add `-Wall -Wextra -Wpedantic -Wvla` to compile options
2. Add `-Werror` option gated behind `WERROR` CMake option
3. Set `-std=gnu17` explicitly

### File: `CMakeLists.txt` (root)
1. Change `set(CMAKE_C_STANDARD 11)` to `set(CMAKE_C_STANDARD 17)`
2. Add warning flags

### File: `.github/workflows/test.yml`
1. Add `-DWERROR=ON` to CI cmake invocations
2. Ensure Clang TSan build also gets warning flags

### File: `cbqs/SearchLib.pxd`
1. Verify `ctypedef void (*callback_t)()` remains compatible (Cython already interprets this as void params)

### Files: `cbqs/src/test.c`
1. Change `int main()` to `int main(void)`

## Open Questions

1. **Metal/Objective-C files:** `exec_metal.m` and `main.metal` contain VLAs (`state_32_t state[size]`, `uint state_copy[MAXINTEGER]`). These are Objective-C and Metal Shader Language respectively, not standard C. The `size` in `exec_metal.m` is actually `#define size 1024` (a compile-time constant), so it's not technically a VLA. `MAXINTEGER` in `.metal` is likely also a constant. These are probably out of scope but should be verified.
   - What we know: `exec_metal.m` uses `#define size 1024` so `state[size]` is not a VLA. Metal shaders are a different language.
   - What's unclear: Whether `-Wvla` will flag `exec_metal.m` (unlikely since it's compiled as Objective-C with different flags).
   - Recommendation: Exclude from scope. These files are macOS-only and compiled separately.

2. **`printf` format specifiers:** Several places use `%lld` for `int64_t` and `%zu` for `size_t`. Strictly, `int64_t` should use `PRId64` from `<inttypes.h>` for portability. However, `%lld` works on all target platforms (GCC, Clang, MSVC). `-Wpedantic` may warn about this. Need to test.
   - What we know: `%lld` is correct for `long long` but `int64_t` might not be `long long` on all platforms.
   - What's unclear: Whether GCC 15 `-Wpedantic` flags this.
   - Recommendation: Fix if warned, skip if not. Use `PRId64` from `<inttypes.h>` if needed.

3. **`operator &&` precedence without parentheses:** Line 545 in `local_search.c`: `if (time > mod->stopping_time || (cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1))` has `&&` inside `||` without explicit parens. GCC `-Wparentheses` (part of `-Wall`) will flag this. Similar patterns exist in `SearchLib.c:194`.
   - What we know: These are logic bugs waiting to happen.
   - Recommendation: Add explicit parentheses. No behavioral change intended.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: all 17 `.c` and 17 `.h` files in `cbqs/src/` read and analyzed
- `tests/CMakeLists.txt` and `.github/workflows/test.yml` analyzed for CI patterns
- `setup.py` analyzed for Cython build system
- GCC 15 official changelog: https://gcc.gnu.org/gcc-15/changes.html

### Secondary (MEDIUM confidence)
- GCC 15 C23 migration blog: https://trofi.github.io/posts/326-gcc-15-switched-to-c23.html (verified against official docs)
- C23 bool keyword changes: multiple sources agree (Wikipedia, GCC bug tracker, Hacker News discussion)
- MSVC `__attribute__((unused))` alternatives: https://windowsquestions.com/2021/05/08/msvc-equivalent-to-__attribute__unused-for-functions-arguments-and-local-variables/

### Tertiary (LOW confidence)
- GCC `-Wvla` flag behavior with Objective-C files: not verified, assumed out of scope
- MSVC C23 support completeness in 2026: web search suggests incomplete but improving

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - based on direct codebase analysis and CI configuration
- Architecture: HIGH - all patterns derived from existing codebase code
- Pitfalls: HIGH - each pitfall identified from actual code inspection
- VLA inventory: HIGH - grep-verified, single remaining VLA confirmed
- Type mismatch inventory: HIGH - comprehensive grep analysis across all files
- Discretion recommendations: HIGH - all based on verified codebase constraints

**Research date:** 2026-02-08
**Valid until:** 2026-04-08 (stable domain, C standards don't change frequently)
