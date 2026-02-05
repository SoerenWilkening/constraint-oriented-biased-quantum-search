# Phase 5: Memory Safety - Research

**Researched:** 2026-02-05
**Domain:** C memory management, VLA elimination, leak detection, Valgrind/ASan integration
**Confidence:** HIGH

## Summary

This phase addresses memory safety issues in the CBQS solver: eliminating memory leaks and replacing unsafe Variable Length Arrays (VLAs) with heap or context-allocated buffers. The codebase has:

1. **Known leaks in preprocessing()**: The `realloc(ptr, 0)` pattern when `positive_array_length` or `negative_array_length` is 0 causes memory leaks. This is documented in STATE.md and tracked since Phase 1.

2. **VLAs in hot paths**: Several functions use VLAs sized by constraint count `C`, including `int64_t totals[C]`, `int64_t remainings[C]`, and `int64_t potentials[C]`. These risk stack overflow on large problems (10K+ constraints).

3. **Existing solver_ctx_t architecture**: Phase 3 established `solver_ctx_t` for per-solve state. Scratch buffers can be added to this struct, avoiding repeated malloc/free overhead.

**Primary recommendation:** Add scratch buffers to `solver_ctx_t` for VLA replacement; fix preprocessing() leak by handling zero-length arrays explicitly; create Valgrind suppressions for Python/numpy/Cython runtime leaks.

## Standard Stack

The established tools for memory safety in this domain:

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| Valgrind | 3.20+ | Leak detection, memory error detection | Gold standard for leak detection in C |
| AddressSanitizer (ASan) | GCC 12+ / Clang 15+ | Fast memory error detection | Faster than Valgrind, catches different bugs |
| ThreadSanitizer (TSan) | GCC 12+ / Clang 15+ | Data race detection | Already in CI from Phase 4 |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| Massif | (Valgrind) | Heap profiling | When investigating memory growth |
| PYTHONMALLOC=malloc | Python 3.6+ | Valgrind-compatible allocator | Required for accurate Valgrind with Python |
| --suppressions | Valgrind | Filter known false positives | Python/numpy runtime allocations |

### Already Configured
- ASan in CI (`-DASAN=ON`), but leak detection disabled due to preprocessing() leaks
- Valgrind running on subset of tests (expression, state, constraint)
- TSan for thread safety tests

**No additional dependencies needed.** Focus is on fixing code, not adding tools.

## Architecture Patterns

### Recommended: Scratch Buffers in solver_ctx_t

The existing `solver_ctx_t` (from Phase 3) already owns per-solve mutable state. Extend it with scratch buffers:

```c
struct solver_ctx {
    /* Existing fields from Phase 3 */
    BranchingStats_t branching_stats;
    atomic_bool stop;
    uint64_t timeout_ms;
    struct timespec start_time;
    int debug_enabled;
    uint64_t seed;
    uint64_t seed_used;
    int num_threads;
    int num_threads_used;
    prng_state_t master_prng;

    /* NEW: Scratch buffers for VLA replacement */
    int64_t *constraint_totals;      /* Replaces totals[C] */
    int64_t *constraint_remainings;  /* Replaces remainings[C] */
    int64_t *constraint_potentials;  /* Replaces potentials[C] */
    size_t scratch_capacity;         /* Current allocation size */
};
```

**Pattern for usage:**
```c
/* In solver_ctx_create() or initialization function */
void solver_ctx_ensure_scratch(solver_ctx_t *ctx, size_t num_constraints) {
    if (ctx->scratch_capacity >= num_constraints) {
        return;  /* Already big enough */
    }

    /* Realloc to larger size */
    ctx->constraint_totals = realloc(ctx->constraint_totals,
                                     num_constraints * sizeof(int64_t));
    ctx->constraint_remainings = realloc(ctx->constraint_remainings,
                                         num_constraints * sizeof(int64_t));
    ctx->constraint_potentials = realloc(ctx->constraint_potentials,
                                         num_constraints * sizeof(int64_t));

    if (!ctx->constraint_totals || !ctx->constraint_remainings ||
        !ctx->constraint_potentials) {
        /* Allocation failed - return error */
        return;  /* Or set error flag in ctx */
    }

    ctx->scratch_capacity = num_constraints;
}
```

### Pattern: Thread-Local Scratch Buffers

For `explore_neighbourhood()` which runs in parallel threads, each thread needs its own buffers. The `local_search_data_t` struct already exists:

```c
typedef struct {
    /* Existing fields */
    state_t *sol;
    new_constraints_t *con, *obj;
    int d, size_ful, initial_feasible, start_move, end_move;
    /* ... */

    /* NEW: Per-thread scratch (allocated by parent, not VLA) */
    int64_t *thread_totals;   /* Replaces totals[C] in explore_neighbourhood */
    int *thread_bits;         /* Replaces bits[d] - small, fixed max */
} local_search_data_t;
```

### Anti-Patterns to Avoid

- **VLAs of any size**: Even small VLAs risk portability issues (C11 made them optional, C23 removes them)
- **realloc(ptr, 0)**: Behavior is implementation-defined; may return NULL or non-NULL; loses memory either way
- **malloc in hot loops**: Allocate once in context initialization, reuse per-call
- **Ignoring malloc failures**: Always check return values; propagate error to Python layer

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Leak detection | printf-based tracking | Valgrind/ASan | Already integrated; catches all leaks |
| Suppression patterns | Grep Valgrind output | Standard Python suppression file | Python, numpy, Cython have known benign leaks |
| Dynamic array resize | Custom realloc wrapper | Existing pattern in constraint.c | `(counter & (size_steps - 1)) == 0 && counter > 0` already works |
| Thread-local storage | Manual pthread_key_t | __thread keyword | Already used in Phase 4 for PRNG |

**Key insight:** The codebase already has most patterns needed. The work is fixing specific bugs and applying existing patterns to VLA sites.

## Common Pitfalls

### Pitfall 1: realloc(ptr, 0) Memory Leak
**What goes wrong:** When `positive_array_length == 0`, calling `realloc(ptr, 0)` returns NULL (or a non-freeable pointer), and the original memory is leaked.
**Why it happens:** The preprocessing functions shrink arrays at the end, but if no elements exist, they try to realloc to size 0.
**How to avoid:** Check size before realloc; if size is 0, explicitly free() and set pointer to NULL.
**Warning signs:** ASan leak reports pointing to initial calloc() in preprocessing.

**Fix pattern:**
```c
/* Before (buggy) */
con->positive_indices = realloc(con->positive_indices,
                                con->positive_array_length * sizeof(uint32_t));

/* After (correct) */
if (con->positive_array_length == 0) {
    free(con->positive_indices);
    con->positive_indices = NULL;
} else {
    con->positive_indices = realloc(con->positive_indices,
                                    con->positive_array_length * sizeof(uint32_t));
}
```

### Pitfall 2: VLA Stack Overflow on Large Problems
**What goes wrong:** `int64_t totals[C]` with C=10000 allocates 80KB on stack; typical stack limit is 8MB but stack also holds call frames.
**Why it happens:** VLAs seem convenient and fast, but stack space is limited.
**How to avoid:** Replace with heap allocation in ctx or local_search_data_t; allocate once, reuse.
**Warning signs:** Segfault on large problems; works fine on small problems.

### Pitfall 3: Missing Cleanup on Error Paths
**What goes wrong:** Early return on error skips cleanup code at function end.
**Why it happens:** C lacks RAII; cleanup is manual.
**How to avoid:** Use consistent patterns: either goto cleanup or ensure all paths free resources.
**Warning signs:** Valgrind reports "definitely lost" on error conditions.

### Pitfall 4: Suppression File Over-Suppression
**What goes wrong:** Overly broad suppressions hide real bugs in project code.
**Why it happens:** Valgrind output is noisy; tempting to suppress liberally.
**How to avoid:** Suppress by specific function name (e.g., `PyObject_Free`, `numpy_*`), not by file or generic patterns.
**Warning signs:** Suppression file grows; real leaks slip through.

### Pitfall 5: free() Without NULL Check
**What goes wrong:** free(NULL) is safe, but double-free or free of uninitialized pointer crashes.
**Why it happens:** C doesn't track ownership; easy to free twice.
**How to avoid:** Set pointer to NULL after free; check before free if uncertain.
**Warning signs:** "Invalid free" from Valgrind/ASan.

## Code Examples

### VLA Replacement in explore_neighbourhood()

**Before (VLA, current code at local_search.c:188):**
```c
void *explore_neighbourhood(void *args) {
    local_search_data_t *dat = (local_search_data_t *) args;
    int C = dat->con->num_constraints;

    int bits[dat->d];           /* VLA - risk if d is large */
    int64_t totals[C];          /* VLA - stack overflow risk */
    /* ... */
}
```

**After (heap-allocated via local_search_data_t):**
```c
/* In accept_best_routine, when setting up thread data */
for (int i = 0; i < num_threads; ++i) {
    data[i].thread_totals = malloc(C * sizeof(int64_t));
    data[i].thread_bits = malloc(d * sizeof(int));  /* d is max distance, bounded */
    /* ... existing setup ... */
}

/* In explore_neighbourhood */
void *explore_neighbourhood(void *args) {
    local_search_data_t *dat = (local_search_data_t *) args;
    int C = dat->con->num_constraints;

    /* Use pre-allocated buffers */
    int *bits = dat->thread_bits;
    int64_t *totals = dat->thread_totals;
    memset(totals, 0, C * sizeof(int64_t));
    /* ... */
}

/* Cleanup after pthread_join */
for (int i = 0; i < num_threads; ++i) {
    pthread_join(threads[i], NULL);
    free(data[i].thread_totals);
    free(data[i].thread_bits);
    /* ... existing cleanup ... */
}
```

### preprocessing() Leak Fix

**Before (buggy, current code at constraint.c:209-210):**
```c
void preprocessing(int n, new_constraints_t *con) {
    /* ... */
    /* At end of function */
    con->positive_indices = realloc(con->positive_indices,
                                    con->positive_array_length * sizeof(uint32_t));
    con->negative_indices = realloc(con->negative_indices,
                                    con->negative_array_length * sizeof(uint32_t));
}
```

**After (correct):**
```c
void preprocessing(int n, new_constraints_t *con) {
    /* ... */
    /* At end of function - handle zero-length case */
    if (con->positive_array_length == 0) {
        free(con->positive_indices);
        con->positive_indices = NULL;
    } else {
        uint32_t *new_pos = realloc(con->positive_indices,
                                    con->positive_array_length * sizeof(uint32_t));
        if (new_pos != NULL) {
            con->positive_indices = new_pos;
        }
        /* If realloc fails, keep original (over-allocated but not leaked) */
    }

    if (con->negative_array_length == 0) {
        free(con->negative_indices);
        con->negative_indices = NULL;
    } else {
        uint32_t *new_neg = realloc(con->negative_indices,
                                    con->negative_array_length * sizeof(uint32_t));
        if (new_neg != NULL) {
            con->negative_indices = new_neg;
        }
    }
}
```

### Valgrind Suppression File Template

**Location: tests/valgrind-python.supp**
```
# Python allocator false positives
{
   PythonMalloc
   Memcheck:Leak
   ...
   fun:PyObject_Malloc
}

{
   PythonRealloc
   Memcheck:Leak
   ...
   fun:PyObject_Realloc
}

# Numpy initialization leaks (benign)
{
   NumpyInit
   Memcheck:Leak
   ...
   obj:*/numpy/*.so
   fun:PyInit_*
}

# Cython generated code
{
   CythonModule
   Memcheck:Leak
   ...
   fun:__pyx_*
   fun:PyModule_Create*
}

# Python GIL state
{
   PythonGIL
   Memcheck:Leak
   fun:malloc
   ...
   fun:PyEval_InitThreads
}
```

### Memory Stress Test for Large Problems

**Location: tests/test_memory_stress.py**
```python
import pytest
cbqs = pytest.importorskip("cbqs")
from cbqs.Model import Model

class TestLargeProblems:
    """Tests for large problem memory handling."""

    @pytest.mark.timeout(120)
    def test_10k_constraints_no_segfault(self):
        """Verify 10K constraints don't cause stack overflow."""
        m = Model()
        n = 100  # variables
        num_constraints = 10000

        xs = m.add_variables(n)
        x = [xs[j] for j in range(n)]

        # Add many constraints
        for i in range(num_constraints):
            # Simple constraint using 3 variables
            vars_to_use = [x[j % n] for j in range(i, i + 3)]
            m.add_constraint(sum(vars_to_use) <= 2)

        m.set_objective(sum(x[j] for j in range(n)))
        m.close()

        # Should not segfault
        try:
            m.solve(stopping_time=5, num_workers=1)
        except MemoryError:
            # Expected if system can't allocate - not a test failure
            pytest.skip("System memory limit reached")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| VLAs for temporary arrays | Heap/context-allocated buffers | C11 (2011) made VLAs optional, C23 removes them | Required for portability and large problems |
| realloc(ptr, 0) for cleanup | Explicit free + NULL assignment | Always was UB-adjacent | Fixes preprocessing leaks |
| ASan OR Valgrind | ASan AND Valgrind in CI | Modern CI practice | Different tools catch different bugs |
| Manual leak tracking | Tool-based detection | Always | Never hand-roll what tools do better |

**Deprecated/outdated:**
- VLAs: Optional in C11, removed in C23; always use heap allocation for runtime-sized arrays
- realloc to size 0: Behavior varies by platform; always free explicitly

## Open Questions

Things that couldn't be fully resolved:

1. **Exact preprocessing() leak location**
   - What we know: Leak is in realloc-to-zero pattern at lines 209-210 in preprocessing() and similar in preprocessing_sparse()
   - What's unclear: Whether other arrays (offsets, num_indices) also need the same fix
   - Recommendation: Audit all final realloc() calls in both functions

2. **Maximum safe constraint count**
   - What we know: VLAs with 10K constraints use 80KB stack
   - What's unclear: Exact stack limit on CI runners and target platforms
   - Recommendation: No artificial limits; allocate on heap, fail gracefully on malloc failure

3. **Python/Cython layer leaks**
   - What we know: Cython extension types use `__dealloc__` for cleanup
   - What's unclear: Whether all Py_INCREF have matching Py_DECREF
   - Recommendation: Code review of .pyx files; Valgrind with PYTHONMALLOC=malloc

## Sources

### Primary (HIGH confidence)
- Codebase analysis: local_search.c (VLA locations lines 158, 161, 188, 284, 482, 515)
- Codebase analysis: constraint.c (preprocessing() lines 129-211, preprocessing_sparse() lines 238-349)
- Codebase analysis: solver_ctx.h/c (Phase 3 context architecture)
- STATE.md: Tracked preprocessing() leak documentation

### Secondary (MEDIUM confidence)
- [Python Valgrind suppression file](https://svn.python.org/projects/python/trunk/Misc/valgrind-python.supp) - Standard Python suppressions
- [Using Valgrind with Cython](https://adrianeboyd.github.io/using-valgrind-with-cython/) - Cython-specific guidance
- [VLA best practices](https://runebook.dev/en/docs/gcc/variable-length) - GCC documentation on VLA alternatives

### Tertiary (LOW confidence)
- [NumPy Valgrind issue #18271](https://github.com/numpy/numpy/issues/18271) - NumPy-specific leak patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using existing tools already in CI
- Architecture: HIGH - Based on existing solver_ctx_t pattern from Phase 3
- Pitfalls: HIGH - Based on documented issues in STATE.md and code analysis
- VLA replacement: HIGH - Standard C practice, well-documented in standards

**Research date:** 2026-02-05
**Valid until:** Indefinite (memory safety practices are stable)
