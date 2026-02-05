# Phase 3: Solver Context Architecture - Research

**Researched:** 2026-02-05
**Domain:** C threading, solver context patterns, atomic operations
**Confidence:** HIGH

## Summary

This phase introduces `solver_ctx_t`, a struct that encapsulates all per-solve mutable state (BranchingStats, stop flag, timeout) to eliminate global variables causing data races in multi-threaded solves. The codebase already uses C11 (`set(CMAKE_C_STANDARD 11)`) and pthreads extensively, so `<stdatomic.h>` is available and appropriate for the atomic stop flag.

The current global state consists of:
1. **BranchingStats** (Branching.c:5) - global struct with branching parameters and pointers to objective/constraint dependence arrays
2. **stop_flag** (SearchLib.c:46) - `volatile sig_atomic_t` used for SIGINT handling, checked in `ctg()` main loop
3. **update_lock** (SearchLib.c:9) - pthread mutex for global_opt updates (keep as-is, protect ctx instead)

The migration strategy follows the user's decisions: bottom-up function-by-function, no fallback to globals, compile errors catch missing updates.

**Primary recommendation:** Define `solver_ctx_t` in a new `solver_ctx.h` header with BranchingStats_t embedded (not pointer), atomic_bool stop flag, and timeout fields. Migrate leaf functions first (BranchingFunction callers), then intermediate functions (CSearch_*, look_ahead_correct), then entry points (ctg, local_search).

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdatomic.h | C11 | Atomic boolean for stop flag | Standard C11, no external deps, lock-free on most platforms |
| pthread.h | POSIX | Thread synchronization | Already in use throughout codebase |
| time.h | C standard | Timeout tracking (clock_gettime) | Already used in ctg() for runtime tracking |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib.h | C standard | malloc/free for ctx | Context allocation |
| string.h | C standard | memcpy/memset for ctx init | Initialize branching stats |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| atomic_bool | volatile sig_atomic_t | sig_atomic_t only guaranteed atomic for signal handlers, not general threading; atomic_bool is correct |
| atomic_bool | pthread_mutex | Overkill for simple flag checks; mutex adds overhead vs atomic load |
| Embedded BranchingStats_t | BranchingStats_t* pointer | Embedded avoids extra allocation and cache miss; pointer only needed if stats shared |

**Installation:**
No new dependencies required - all headers are part of C11 standard and POSIX.

## Architecture Patterns

### Recommended Project Structure
```
cbqs/src/
    solver_ctx.h         # NEW: solver_ctx_t definition
    solver_ctx.c         # NEW: init/free/debug functions
    Branching.h          # MODIFY: functions take ctx parameter
    Branching.c          # MODIFY: remove global, use ctx
    solver.h             # MODIFY: functions take ctx parameter
    solver.c             # MODIFY: use ctx->branching_stats
    SearchLib.h          # MODIFY: remove stop_flag global
    SearchLib.c          # MODIFY: check ctx->stop instead
    local_search.h       # MODIFY: local_search() takes ctx
    local_search.c       # MODIFY: use ctx for stopping
    approximate_state_sampler.c  # MODIFY: use ctx->branching_stats
```

### Pattern 1: Context Struct Definition
**What:** Transparent struct with embedded sub-structs and atomic flag
**When to use:** Always for solver_ctx_t
**Example:**
```c
// Source: C11 standard, verified with cppreference.com/w/c/header/stdatomic.h
#ifndef SOLVER_CTX_H
#define SOLVER_CTX_H

#include <stdatomic.h>
#include <stdint.h>
#include <time.h>
#include "Branching.h"  // for BranchingStats_t

typedef struct {
    // Branching statistics (embedded, not pointer)
    BranchingStats_t branching_stats;

    // Stop signal (atomic for thread-safe reads)
    atomic_bool stop;

    // Timeout tracking
    uint64_t timeout_ms;        // 0 = no timeout
    struct timespec start_time; // set at solve start

    // Debug output control
    int debug_enabled;          // check CBQS_DEBUG env var at init
} solver_ctx_t;

// Lifecycle
solver_ctx_t *solver_ctx_create(void);
void solver_ctx_free(solver_ctx_t *ctx);

// Stop signal API
void solver_ctx_request_stop(solver_ctx_t *ctx);
int solver_ctx_should_stop(solver_ctx_t *ctx);  // also checks timeout

// Debug output (JSON to stderr)
void solver_ctx_debug_stats(solver_ctx_t *ctx);

#endif
```

### Pattern 2: Atomic Stop Flag Check
**What:** Check stop flag periodically in iteration loops
**When to use:** Every N iterations in main solve loops
**Example:**
```c
// Source: https://en.cppreference.com/w/c/header/stdatomic.h
// Check every 256 iterations (balance between responsiveness and overhead)
#define STOP_CHECK_INTERVAL 256

for (int i = 0; i < n; i++) {
    // Periodic stop check
    if ((i & (STOP_CHECK_INTERVAL - 1)) == 0) {
        if (solver_ctx_should_stop(ctx)) {
            // Return best solution found so far
            break;
        }
    }
    // ... iteration body ...
}
```

### Pattern 3: Timeout Implementation
**What:** Check elapsed time against timeout_ms
**When to use:** Inside solver_ctx_should_stop()
**Example:**
```c
// Source: POSIX clock_gettime, already used in SearchLib.c:94
int solver_ctx_should_stop(solver_ctx_t *ctx) {
    // Check atomic stop flag first (fast path)
    if (atomic_load(&ctx->stop)) return 1;

    // Check timeout if set
    if (ctx->timeout_ms > 0) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        uint64_t elapsed_ms =
            (now.tv_sec - ctx->start_time.tv_sec) * 1000 +
            (now.tv_nsec - ctx->start_time.tv_nsec) / 1000000;
        if (elapsed_ms >= ctx->timeout_ms) {
            atomic_store(&ctx->stop, true);  // cache the result
            return 1;
        }
    }
    return 0;
}
```

### Pattern 4: Context Passing Through Call Chain
**What:** Pass ctx as first parameter to all functions that need branching/stop
**When to use:** All migrated functions
**Example:**
```c
// Before (uses global):
int CSearch_opt(state_t *cur_sol, int j, ...);

// After (explicit ctx):
int CSearch_opt(solver_ctx_t *ctx, state_t *cur_sol, int j, ...);

// Inside function:
// Before:
if (random_num > BranchingFunction(i, bit, 0, 0, &BranchingStats)) { ... }

// After:
if (random_num > BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)) { ... }
```

### Pattern 5: Cython Layer Integration
**What:** Cython allocates ctx, passes to C, frees after solve
**When to use:** run_sampling() and other entry points in SearchLib.pyx
**Example:**
```cython
# In SearchLib.pyx
cdef extern from "solver_ctx.h":
    ctypedef struct solver_ctx_t:
        pass  # opaque to Cython
    solver_ctx_t* solver_ctx_create()
    void solver_ctx_free(solver_ctx_t* ctx)
    void solver_ctx_request_stop(solver_ctx_t* ctx)

cpdef run_sampling(Model mod, object callback, not_stop: list[int]):
    cdef solver_ctx_t* ctx = solver_ctx_create()
    # ... configure ctx from mod ...

    try:
        with nogil:
            feasible = ctg(ctx, mod_ptr, stt, cb_ptr, inc.incumbent)
    finally:
        solver_ctx_free(ctx)
```

### Anti-Patterns to Avoid
- **Global fallback:** Never read globals as fallback when ctx is NULL -- this defeats the purpose and hides bugs
- **Shallow copy of ctx:** Don't memcpy ctx to threads -- all threads should share single ctx (atomic stop flag design assumes this)
- **Checking stop every iteration:** Too expensive; use STOP_CHECK_INTERVAL power-of-2 for fast modulo
- **Forgetting to free ctx:** Always use try/finally pattern in Cython to ensure cleanup

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic boolean | `volatile int` flag | `atomic_bool` from stdatomic.h | volatile is not sufficient for multi-core visibility |
| High-resolution timing | `time()` | `clock_gettime(CLOCK_MONOTONIC, ...)` | Already in codebase, sub-ms precision |
| Thread-safe print | `printf()` with lock | `fprintf(stderr, ...)` | stderr is line-buffered, sufficient for debug |
| JSON serialization | Custom string building | Simple fprintf with format | Debug output is simple enough, no library needed |

**Key insight:** The codebase already has all building blocks needed. The challenge is routing them through ctx rather than globals.

## Common Pitfalls

### Pitfall 1: Forgetting to Initialize Branching Stats
**What goes wrong:** ctx->branching_stats fields are uninitialized, causing garbage branching decisions
**Why it happens:** BranchingStats global has default initializers; ctx doesn't
**How to avoid:** Explicit initialization in solver_ctx_create():
```c
solver_ctx_t *solver_ctx_create(void) {
    solver_ctx_t *ctx = malloc(sizeof(solver_ctx_t));
    // Copy defaults from global initializer pattern
    ctx->branching_stats.objective_factor = 0;
    ctx->branching_stats.obj_dependent = NULL;
    ctx->branching_stats.constraint_factor = 0;
    ctx->branching_stats.constraint_dependent = NULL;
    ctx->branching_stats.bias_factor = 1;
    ctx->branching_stats.bias = 5;
    ctx->branching_stats.look_factor = 0.0;
    atomic_init(&ctx->stop, false);
    ctx->timeout_ms = 0;
    ctx->debug_enabled = (getenv("CBQS_DEBUG") != NULL);
    return ctx;
}
```
**Warning signs:** Random/inconsistent solve results

### Pitfall 2: Memory Leak on Dependence Arrays
**What goes wrong:** ctx->branching_stats.obj_dependent leaks when ctx freed
**Why it happens:** set_obj_dependence() allocates arrays that need freeing
**How to avoid:** Free in solver_ctx_free():
```c
void solver_ctx_free(solver_ctx_t *ctx) {
    if (ctx->branching_stats.obj_dependent)
        free(ctx->branching_stats.obj_dependent);
    if (ctx->branching_stats.constraint_dependent)
        free(ctx->branching_stats.constraint_dependent);
    free(ctx);
}
```
**Warning signs:** ASan reports on repeated solve calls

### Pitfall 3: Cython struct visibility
**What goes wrong:** Cython can't see solver_ctx_t fields, or needs full definition
**Why it happens:** Mixed C/Cython compilation with header visibility
**How to avoid:** Use opaque pointer pattern in Cython (just need create/free), keep struct transparent only for C code
**Warning signs:** Cython compile errors about incomplete type

### Pitfall 4: Signal Handler Race
**What goes wrong:** SIGINT handler tries to access ctx which may not exist
**Why it happens:** Current code has global signal handler setting stop_flag
**How to avoid:** Two options:
1. Keep minimal global stop_flag, have Cython set ctx->stop when global detected
2. Register signal handler per-solve that knows about ctx (complex)

Recommendation: Option 1 is simpler. Cython checks global stop_flag and calls solver_ctx_request_stop(ctx).
**Warning signs:** Crash on Ctrl+C during solve

### Pitfall 5: Test Fixture Changes
**What goes wrong:** Existing test_branching.c tests manipulate global BranchingStats
**Why it happens:** Tests were written against global API
**How to avoid:** Tests should create ctx, manipulate ctx->branching_stats, free ctx. Update fixtures.
**Warning signs:** Test compilation failures after migration

## Code Examples

Verified patterns from official sources:

### Creating and Using Atomic Bool
```c
// Source: https://en.cppreference.com/w/c/header/stdatomic.h
#include <stdatomic.h>

atomic_bool stop;

// Initialize
atomic_init(&stop, false);

// Write (from another thread or signal)
atomic_store(&stop, true);

// Read (in loop)
if (atomic_load(&stop)) {
    // handle stop
}
```

### JSON Debug Output to stderr
```c
// Source: C standard fprintf, JSON format per user request
void solver_ctx_debug_stats(solver_ctx_t *ctx) {
    if (!ctx->debug_enabled) return;

    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    double elapsed = (now.tv_sec - ctx->start_time.tv_sec) +
                    (now.tv_nsec - ctx->start_time.tv_nsec) / 1e9;

    fprintf(stderr,
        "{\"type\":\"solve_stats\","
        "\"elapsed_sec\":%.3f,"
        "\"bias\":%.2f,"
        "\"bias_factor\":%.2f,"
        "\"objective_factor\":%.2f,"
        "\"constraint_factor\":%.2f,"
        "\"look_factor\":%.2f}\n",
        elapsed,
        ctx->branching_stats.bias,
        ctx->branching_stats.bias_factor,
        ctx->branching_stats.objective_factor,
        ctx->branching_stats.constraint_factor,
        ctx->branching_stats.look_factor);
}
```

### Function Signature Migration Pattern
```c
// BEFORE: uses global BranchingStats
double BranchingFunction(int index, int bit_S, int bit_T,
                         int diffcount, const BranchingStats_t *stats);
// Note: already takes stats pointer! Good design.

// Functions that need migration (currently pass &BranchingStats):
// solver.c:282, 396, 520, 619, 721, 827
// approximate_state_sampler.c:150
// Branching.c:110

// AFTER: callers pass &ctx->branching_stats
if (random_num > BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)) { ... }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| volatile sig_atomic_t for threading | atomic_bool from stdatomic.h | C11 (2011) | Proper multi-core visibility guarantees |
| Global state with external linkage | Context struct passed through calls | Modern best practice | Thread safety, testability |
| signal.raise_signal for stop | Atomic flag checked in loop | Per-solve flags | Independent solve instances possible |

**Deprecated/outdated:**
- `volatile` alone: Not sufficient for multi-threaded visibility (only prevents compiler reordering)
- `sig_atomic_t` for non-signal use: Designed for signal handlers, not general threading

## Open Questions

Things that couldn't be fully resolved:

1. **Optimal STOP_CHECK_INTERVAL value**
   - What we know: Powers of 2 enable fast bitmask check; 100-1000 range specified in CONTEXT.md
   - What's unclear: Best value depends on iteration cost; need benchmarking
   - Recommendation: Start with 256 (within range, power of 2), add to debug output for tuning

2. **python_callback global in SearchLib.pyx**
   - What we know: Global `python_callback` stores callback for C to invoke
   - What's unclear: Should this move into ctx? Would require GIL management
   - Recommendation: Keep separate for now; callback is per-worker thread, not per-solve race condition

3. **Thread-local vs shared ctx for Joblib workers**
   - What we know: Each Joblib worker runs run_sampling() independently
   - What's unclear: Should workers share ctx (for coordinated stop) or have independent ctx?
   - Recommendation: Each worker gets own ctx; coordinate via global stop_flag checked by Cython

## Sources

### Primary (HIGH confidence)
- **cppreference.com** - C11 stdatomic.h documentation (atomic_bool, atomic_load, atomic_store)
- **Codebase analysis** - CMakeLists.txt confirms C11, existing pthread usage

### Secondary (MEDIUM confidence)
- [SEI CERT C Coding Standard](https://wiki.sei.cmu.edu/confluence/display/c/CON40-C.+Do+not+refer+to+an+atomic+variable+twice+in+an+expression) - Atomic variable best practices
- [LLNL HPC Tutorials](https://hpc-tutorials.llnl.gov/posix/passing_args/) - pthread context passing patterns
- [Beej's Guide to C](https://beej.us/guide/bgc/html/split/chapter-atomics.html) - C11 atomics tutorial

### Tertiary (LOW confidence)
- Web search for stop flag check frequency - no definitive benchmarks found; 256 is educated guess

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - C11 stdatomic.h is well-documented, codebase already uses C11
- Architecture: HIGH - Context passing is standard pattern, fits existing function signatures
- Pitfalls: HIGH - Based on direct codebase analysis and common C threading issues
- Stop check interval: MEDIUM - Within specified range, needs validation

**Research date:** 2026-02-05
**Valid until:** 60 days (stable C11 standard, mature codebase patterns)

## Migration Order (Bottom-Up)

Per CONTEXT.md decision, migrate leaf functions first:

### Level 1: Leaf Functions (no downstream callers need ctx)
1. `BranchingFunction()` - already takes BranchingStats_t*, just change call sites
2. `StateProbability()` - calls BranchingFunction with global
3. `set_factors()`, `set_bias()`, `set_obj_dependence()`, `set_constraint_dependence()` - modify global, need ctx versions

### Level 2: Solver Functions
4. `look_ahead_correct()` - calls update_potentials, needs ctx for future stop checks
5. `CSearch_opt()`, `CSearch_opt_sat()`, `CSearch_sat()` - call BranchingFunction with global
6. `CSearch_*_monte_carlo_sampler()` variants

### Level 3: Higher-Level Solvers
7. `initial_state_preparation()` - orchestrates setup
8. `local_search()` - already takes model_t, add ctx
9. `explore_neighbourhood()` - pthread worker, receives ctx via data struct

### Level 4: Entry Points
10. `ctg()` - main sampling loop, checks stop_flag
11. Cython entry points (`run_sampling`, `run_local_search`)

Each migration = one atomic commit for bisection.
