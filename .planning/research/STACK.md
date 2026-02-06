# Stack Research: v1.1 Bug Fixes and Code Polish

**Project:** CBQS v1.1
**Researched:** 2026-02-06
**Scope:** Stack additions/changes needed for GCC 15 warnings, Cython callback rework, VLA cleanup, dead code removal
**Confidence:** HIGH (verified against official GCC docs, Cython docs, C standard references)

---

## 1. GCC 15 Type Mismatch Warnings

### What Changed

GCC 15 defaults to `-std=gnu23` (C23) instead of `-std=gnu17`. This is the root cause of all new warnings/errors. Three specific C23 changes affect this codebase.

**Confidence:** HIGH -- verified via [GCC 15 Porting Guide](https://gcc.gnu.org/gcc-15/porting_to.html) and [trofi's analysis](https://trofi.github.io/posts/326-gcc-15-switched-to-c23.html).

### Issue 1: `callback_t` Empty Parameter List

**File:** `cbqs/src/definitions.h:31`
```c
typedef void (*callback_t)();  // <-- Problem
```

In C17, `()` means "unspecified parameters" (accepts anything). In C23, `()` means `(void)` -- zero parameters. Every function that takes a `callback_t` and calls it with zero arguments technically works, but the Cython-generated code casts a `void (*)(void)` to this type when the actual C callback `my_callback_c` is declared `cdef void my_callback_c() with gil:` -- which Cython compiles into a function taking no arguments. So the types happen to match, but GCC 15 may still warn during intermediate casts.

**The real problem:** If the callback_t typedef is ever used to pass functions that DO take parameters (e.g., future callbacks with context), the C23 interpretation breaks that. The typedef should be explicit.

**Fix:**
```c
typedef void (*callback_t)(void);  // Explicit: takes no arguments
```

This is a one-line change. It matches the actual usage (all callbacks in this codebase take zero arguments). No behavioral change.

**Impact:** All files using `callback_t` -- `SearchLib.c`, `SearchLib.h`, `local_search.c`, `local_search.h`, `solver.c`, `solver.h`, `definitions.h`.

### Issue 2: `#define false 0` / `#define true 1`

**File:** `cbqs/src/definitions.h:45-46`
```c
#define false 0
#define true 1
```

In C23, `bool`, `true`, and `false` are **keywords** (not macros from `<stdbool.h>`). `#define true 1` redefines a keyword, which is an error in C23.

**Confidence:** HIGH -- verified via [OpenSSL issue #27516](https://github.com/openssl/openssl/issues/27516) and [open-simh issue #490](https://github.com/open-simh/simh/issues/490).

**Fix:**
```c
// Remove the #define false 0 and #define true 1 lines entirely.
// C23 provides them as keywords.
// For C11/C17 compatibility, use a version guard:
#if __STDC_VERSION__ < 202311L
#include <stdbool.h>
#endif
```

Or simpler: just `#include <stdbool.h>` and remove the defines. `<stdbool.h>` in C11 defines `bool`, `true`, `false` as macros; in C23 the header is a no-op (keywords already exist). Both ways work.

**Note:** The codebase also uses `atomic_bool` in `solver_ctx.h` via `<stdatomic.h>`, which already implies `bool` support. The `#define` macros in `definitions.h` are technically conflicting even in C11 if `<stdbool.h>` is included transitively.

### Issue 3: Operator Precedence Warnings

GCC 15 has improved diagnostic coloring and may surface new `-Wparentheses` warnings for expressions like:

```c
// local_search.c:545
if (time > mod->stopping_time || (cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1)) break;
```

The `&&` binds tighter than `||`, so this may not behave as intended. GCC 15's enhanced diagnostics will flag this more visibly.

**Fix:** Add explicit parentheses:
```c
if (time > mod->stopping_time || ((cur_sol->tot_profit <= mod->stop_val) && (mod->stop_val != -1))) break;
```

Several similar patterns exist in `SearchLib.c:194` and `solver.c` with mixed `&&`/`||` without parentheses.

### Recommended Approach

**Do NOT add `-std=gnu17` to suppress warnings.** That is a workaround, not a fix, and delays the inevitable.

**Instead:**
1. Fix `callback_t` typedef to use `(void)` -- 1 line
2. Remove `#define true/false`, add `#include <stdbool.h>` -- 3 lines
3. Add parentheses to ambiguous `&&`/`||` expressions -- ~5 locations
4. Optionally add `-std=gnu11` explicitly to `setup.py` compiler_args and CMakeLists.txt to document the intentional standard choice, since the codebase uses C11 features (`_Atomic`, `<stdatomic.h>`). This pins the standard explicitly rather than relying on compiler defaults.

**CI consideration:** `ubuntu-latest` currently ships GCC 13 or 14. When it upgrades to GCC 15 (likely Ubuntu 25.10), these will become build failures if not fixed. Fix proactively.

---

## 2. Cython Callback Concurrency Rework

### Current Problem

`SearchLib.pyx` uses four module-level `cdef` variables for history callback state:

```python
cdef object _history_list = None
cdef object _history_prev_best = None
cdef object _history_original_callback = None
cdef Model _history_mod = None
```

These are shared across ALL concurrent workers spawned by `joblib.Parallel(n_jobs=num_workers, backend="threading")`. When `run_sampling` is called by 12 threads simultaneously (the default `num_workers=12`), every thread overwrites the same globals. The history captured is from whichever thread wrote last, not from all threads.

**Why it exists:** Cython `cdef` functions cannot capture closures, and the C callback signature `void (*)()` has no `void *user_data` parameter to pass context through. The module-level globals were the path of least resistance.

### Recommended Pattern: Per-Thread Dict Keyed by Thread ID

**Confidence:** MEDIUM -- pattern derived from Cython docs and general Python threading practices. Not verified in an identical codebase.

**Approach:** Replace the four module-level variables with a single thread-safe dict, keyed by `threading.get_ident()`:

```python
import threading

# Single module-level dict, protected by the GIL
cdef dict _callback_state = {}

cdef void my_callback_c() with gil:
    tid = threading.get_ident()
    state = _callback_state.get(tid)
    if state is not None:
        state['callback']()

def _history_callback_fn():
    tid = threading.get_ident()
    state = _callback_state.get(tid)
    if state is None:
        return
    mod = state['mod']
    history_list = state['history']
    # ... rest of callback logic using state dict ...

cpdef run_sampling(Model mod, object callback, not_stop):
    tid = threading.get_ident()
    _callback_state[tid] = {
        'history': [],
        'prev_best': None,
        'original_callback': callback,
        'mod': mod,
    }
    try:
        # ... existing solve logic ...
        history = list(_callback_state[tid]['history'])
    finally:
        del _callback_state[tid]  # Clean up
```

**Why this works:** The GIL protects Python dict operations. The `with gil` on `my_callback_c` ensures the GIL is held when accessing `_callback_state`. Each thread gets its own history list.

**Why NOT a C-level `void *user_data` approach:** That would require changing the `callback_t` signature throughout the C kernel to `void (*callback_t)(void *user_data)`, which is a larger refactor affecting `ctg()`, `local_search()`, `quantum_local_search()`, and all callers. Save that for v2.0 if needed.

**Why NOT `threading.local()`:** `threading.local()` is a Python-level construct. Accessing it inside a `cdef` function that was called from C (via `with gil`) works but adds overhead from the descriptor protocol. A plain dict lookup by `threading.get_ident()` is faster and more explicit.

### Alternative: Callback Context Struct (v2.0)

For a future clean architecture, change the C callback signature:

```c
typedef void (*callback_t)(void *ctx);
```

Then pass a `solver_ctx_t *` as the callback context. This is the "correct" pattern used by most C libraries (pthreads, libevent, etc.) but requires touching every callback call site in the C kernel. Not appropriate for a bug-fix milestone.

### No New Dependencies

This rework uses only `threading.get_ident()` from the Python standard library. No new packages needed.

---

## 3. VLA Replacement for Remaining Instance

### Current State

Most VLAs were already replaced in v1.0 Phase 5. One remains:

**File:** `cbqs/src/local_search.c:332`
```c
int64_t remainings[C];  // C = con->num_constraints (user-controlled)
```

This is inside `accept_best_routine()`, which runs on the main thread (not inside the pthread workers). The VLA is stack-allocated with a size determined by the number of constraints, which is user input.

### Why It Must Go

1. **Stack overflow risk:** If `C` is large (hundreds of constraints), `C * sizeof(int64_t)` = `C * 8` bytes on the stack. At 1000 constraints, that's 8KB. Default thread stack is 2-8MB, so this is unlikely to overflow for the main thread, but it is unbounded.
2. **MSVC incompatibility:** VLAs are not supported by MSVC, blocking any future Windows build.
3. **C23 status:** VLAs are optional in C11 and remain optional in C23. The `__STDC_NO_VLA__` macro may be defined on some compilers.
4. **Consistency:** The rest of the codebase was already converted to heap allocation. This one instance is an oversight.

**Confidence:** HIGH -- VLA status in C standards verified via [cppreference](https://en.cppreference.com/w/c/language/array) and [Wikipedia VLA article](https://en.wikipedia.org/wiki/Variable-length_array).

### Recommended Fix

Replace with heap allocation, matching the pattern already used elsewhere in the same file:

```c
// Before:
int64_t remainings[C];

// After:
int64_t *remainings = malloc(C * sizeof(int64_t));
if (remainings == NULL) {
    // Handle allocation failure - clean up and return error
    free_state(cur_best, 1);
    free_state(cur_best_tabu, 1);
    return -1;
}
// ... use remainings ...
free(remainings);  // Before each return path
```

This matches the exact pattern used at `local_search.c:572` for the same purpose in `quantum_local_search_states()`.

### Alternative Considered: Arena Allocation

The `solver_ctx_t` already contains an arena allocator. Could use:
```c
int64_t *remainings = (int64_t*)arena_alloc(ctx->arena, C * sizeof(int64_t), 8);
```

However, `accept_best_routine()` already has a well-defined lifecycle (allocate at start, free at end), so a simple `malloc/free` is clearer and sufficient. Arena is better for the hot inner loop (which already uses it).

### No Other VLAs Remain

Grep confirms:
- `local_search.c:332` -- the one remaining VLA (`int64_t remainings[C]`)
- `local_search.c:496` -- already commented out (dead code, should be deleted)
- All other former VLA sites already converted to heap or arena allocation

---

## 4. Dead/Commented-Out Code Cleanup

### Scale of the Problem

A grep for comment patterns resembling code (commented `printf`, `for`, `if`, assignments) found **260 occurrences across 15 files** in `cbqs/src/`. This is substantial noise.

### Cleanup Strategy: No New Tools Needed

**Do NOT add cppcheck, clang-tidy, or other static analysis tools just for this.** The problem is well-defined and can be solved with manual review.

**Approach:**
1. **Remove all `//` commented-out code blocks** -- These are debug artifacts, old algorithm attempts, and disabled features. They add cognitive overhead, confuse grep searches, and make diffs noisier.
2. **Preserve `/* ... */` documentation comments** -- Block comments explaining WHY something works should stay.
3. **Use `git blame` before deleting** -- If a commented block was recently added (v1.0), verify it is not a deliberate "keep for reference" note.

### Files with the Most Commented-Out Code

| File | Commented Lines | Nature |
|------|----------------|--------|
| `local_search.c` | ~52 | Old VLA code, disabled aspiration criterion, debug printf |
| `Branching.c` | ~42 | Disabled branching strategies |
| `solver.c` | ~40 | Old objective computation, disabled constraints paths |
| `SearchLib.c` | ~5 | Old iteration tracking |
| `constraint.c` | ~33 | Old constraint evaluation methods |

### GCC Warning Flags for Dead Code

Already available in the toolchain, no installation needed:

| Flag | What It Catches |
|------|----------------|
| `-Wunused-function` | Static functions never called |
| `-Wunused-variable` | Variables declared but never used |
| `-Wunused-parameter` | Function parameters never used |
| `-Wunused-but-set-variable` | Variables set but never read |
| `-Wunreachable-code` | Code after unconditional return/break |

**Recommendation:** Add `-Wall -Wextra` to both `setup.py` `compiler_args` and the CMake test build. This captures all of the above. Currently only `-O3 -flto -pthread` is specified. Adding warnings does not change runtime behavior.

```python
# setup.py
compiler_args = ["-O3", "-flto", "-pthread", "-Wall", "-Wextra", "-Wno-unused-parameter"]
```

The `-Wno-unused-parameter` exception is needed because many callback and API functions have intentionally unused parameters (e.g., `direction` in some solver paths).

### Python-Side Bare Except

The milestone description mentions a "bare except clause." Grep found none in the current `.py` or `.pyx` files. This may have already been fixed, or it may be in a file not yet checked. If it exists, the fix is:

```python
# Before:
except:
    pass

# After:
except Exception:
    pass
```

Or more specifically, catch only the expected exception type.

---

## 5. What NOT to Add

| Temptation | Why Avoid | Instead |
|------------|-----------|---------|
| clang-tidy or cppcheck for this milestone | Overkill for a targeted cleanup. These tools produce hundreds of findings, most irrelevant to the v1.1 goals. | Manual review guided by GCC warnings |
| Linting CI job (flake8/pylint) | Not in scope for a C-focused bug fix milestone. Would require significant configuration to avoid noise. | Defer to v2.0 |
| `-std=gnu23` flag | The codebase uses `_Atomic` (C11) but not C23 features. Explicitly targeting C23 invites more breakage with no benefit. | Keep C11, fix only the forward-compatibility issues |
| PyCapsule-based callback architecture | Requires rewriting the entire callback chain through C. Correct but too much churn for a cleanup milestone. | Thread-ID dict for v1.1, C-level context for v2.0 |
| alloca() for VLA replacement | Non-standard, not portable, same stack overflow risk as VLAs | malloc/free (already the codebase pattern) |
| Free-threaded Python (3.13t) | Experimental. Cython support for free-threading is incomplete. Would introduce new concurrency bugs. | Stay on GIL-based Python 3.13.7 |

---

## 6. Compiler/Standard Recommendations

### Explicit Standard Pin

Add `-std=gnu11` to compiler flags in both `setup.py` and `CMakeLists.txt`. This:
- Documents the intended standard
- Prevents GCC 15's default-to-C23 from causing surprise failures
- Still allows all C11 features used (`_Atomic`, `<stdatomic.h>`, designated initializers)

```python
# setup.py
compiler_args = ["-std=gnu11", "-O3", "-flto", "-pthread", "-Wall", "-Wextra", "-Wno-unused-parameter"]
```

```cmake
# CMakeLists.txt - already has set(CMAKE_C_STANDARD 11)
# Add warning flags:
add_compile_options(-Wall -Wextra -Wno-unused-parameter)
```

### Forward Compatibility

Even with `-std=gnu11`, fix the three C23 issues (`callback_t`, `true`/`false` defines, parentheses) anyway. This way:
- The fixes are correct under any standard
- When the project eventually moves to C23, there is no breakage
- The code is cleaner regardless of compiler version

---

## Summary of Changes Required

| Change | Files Affected | Risk | Effort |
|--------|---------------|------|--------|
| `callback_t` typedef: `()` to `(void)` | `definitions.h` | None | 1 line |
| Remove `#define true/false`, add `<stdbool.h>` | `definitions.h` | Low (test all builds) | 3 lines |
| Add parentheses to `&&`/`||` expressions | `local_search.c`, `SearchLib.c`, `solver.c` | None | ~5 locations |
| Replace VLA `remainings[C]` with malloc | `local_search.c` | Low | ~10 lines |
| Rework history callback to per-thread dict | `SearchLib.pyx` | Medium (needs testing) | ~40 lines |
| Delete commented-out code | 15 C files | Low | ~260 lines deleted |
| Add `-Wall -Wextra` to build flags | `setup.py`, `CMakeLists.txt` | Low (may surface warnings to fix) | 2 lines |
| Add `-std=gnu11` to build flags | `setup.py`, `CMakeLists.txt` | None | 2 lines |

**No new dependencies. No new tools. No new packages.**

---

## Confidence Assessment

| Item | Confidence | Source |
|------|------------|--------|
| GCC 15 C23 default change | HIGH | [GCC 15 Porting Guide](https://gcc.gnu.org/gcc-15/porting_to.html) |
| Empty `()` meaning `(void)` in C23 | HIGH | [trofi's blog](https://trofi.github.io/posts/326-gcc-15-switched-to-c23.html), GCC docs |
| `bool`/`true`/`false` as C23 keywords | HIGH | [OpenSSL #27516](https://github.com/openssl/openssl/issues/27516), C23 standard |
| Thread-ID dict pattern for Cython callbacks | MEDIUM | Derived from Cython threading docs and Python stdlib; not verified in identical codebase |
| VLA replacement with malloc | HIGH | Standard C practice, matches existing codebase pattern |
| 260 commented-out code lines count | HIGH | Direct grep of source tree |
| `-Wall -Wextra` safety | HIGH | GCC official documentation |

## Sources

- [GCC 15 Porting Guide](https://gcc.gnu.org/gcc-15/porting_to.html) -- official migration guide
- [gcc-15 switched to C23 (trofi)](https://trofi.github.io/posts/326-gcc-15-switched-to-c23.html) -- detailed analysis of C23 breaking changes
- [6 usability improvements in GCC 15 (Red Hat)](https://developers.redhat.com/articles/2025/04/10/6-usability-improvements-gcc-15) -- diagnostic improvements
- [OpenSSL C23 bool keyword issue #27516](https://github.com/openssl/openssl/issues/27516) -- real-world bool breakage example
- [open-simh C23 bool issue #490](https://github.com/open-simh/simh/issues/490) -- another bool breakage example
- [Cython free threading docs](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) -- Cython concurrency model
- [Cython external C code docs](https://cython.readthedocs.io/en/latest/src/userguide/external_C_code.html) -- callback GIL handling
- [SciPy LowLevelCallable pattern](https://github.com/scipy/scipy/blob/main/scipy/_lib/_ccallback.py) -- reference for callback architecture
- [Wikipedia: Variable-length array](https://en.wikipedia.org/wiki/Variable-length_array) -- VLA standard status
- [CERT C: VLA size validation](https://wiki.sei.cmu.edu/confluence/x/AdcxBQ) -- security implications of VLAs
- [GCC Warning Options](https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html) -- `-Wunused-*` flag reference

---
*Stack research for: CBQS v1.1 bug fixes and code polish*
*Researched: 2026-02-06*
