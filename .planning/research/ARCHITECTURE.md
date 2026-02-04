# Architecture Research

**Domain:** C-based constraint-oriented quantum search solver (CBQS) -- stabilization and optimization
**Researched:** 2026-02-04
**Confidence:** HIGH (based on direct codebase analysis + established C systems programming patterns)

## Current System Overview

```
+---------------------------------------------------------------+
|                     Python API Layer                           |
|  Model.pyx  |  Constraint.pyx  |  Expression.pyx  |  state.pyx|
+------+---------------------------+------------------------+---+
       |                           |                        |
+------v---------------------------v------------------------v---+
|                     Cython Binding Layer                       |
|  SearchLib.pyx (run_sampling, run_local_search, etc.)         |
|  Model.pxd / Constraint.pxd / SearchLib.pxd                  |
+------+---------------------------+------------------------+---+
       |                           |                        |
+------v---------------------------v------------------------v---+
|                      C Kernel Layer                            |
|  +-----------+  +-------------+  +-----------+  +-----------+ |
|  | model.c   |  | constraint.c|  | solver.c  |  |Branching.c| |
|  +-----------+  +-------------+  +-----------+  +-----------+ |
|  +-----------+  +-------------+  +-----------+  +-----------+ |
|  |local_search| |quantum_search| | state.c   |  |intarray.h | |
|  +-----------+  +-------------+  +-----------+  +-----------+ |
|  +-----------+                                                 |
|  |Expression.c|  (+ approximate_state_sampler, metal_files)   |
|  +-----------+                                                 |
+---------------------------------------------------------------+
```

### Current Component Responsibilities

| Component | Responsibility | Current Issues |
|-----------|----------------|----------------|
| `model_t` (model.h/c) | Holds all solver parameters, pointers to constraints/objective/states | Flat struct, no separation of shared vs mutable state |
| `BranchingStats` (Branching.h/c) | Branching heuristic weights and per-variable biases | **GLOBAL VARIABLE** -- data race under joblib threading |
| `new_constraints_t` (constraint.h/c) | Stores constraint/objective expressions in flattened arrays | Read-only after preprocessing; safe to share |
| `expression_t` (Expression.h) | Intermediate expression builder with MAXCLAUSESIZE=4 fixed slots | Fixed `MAXCLAUSESIZE` wastes memory for linear terms, blocks higher-order |
| `state_t` (state.h) | Solution vector (bit array) + objective + feasibility | Copied per thread correctly |
| `local_search_data_t` (local_search.h) | Per-thread work packet for neighbourhood exploration | Reasonably isolated, but references shared `con`/`obj` |
| `array_t` (intarray.h) | Compact bit vector using uint64 parts | Good design; inline ops; heap-allocated parts |
| `move_t` / `tabu_list_t` (local_search.h) | Move generation and tabu memory | Each move allocates its own `flips` array via malloc |

## Critical Architectural Problems

### Problem 1: Global BranchingStats (Thread Safety Violation)

**Location:** `Branching.c` line 5: `BranchingStats_t BranchingStats = { ... };`

**Impact:** `BranchingStats` is a process-wide global. When `Model.solve()` calls `joblib.Parallel(n_jobs=num_workers, backend="threading")`, all threads read/write the same `BranchingStats`. The `set_bias()`, `set_factors()`, `set_obj_dependence()` functions mutate it without synchronization. The `BranchingFunction()` inline reads it on every branching decision.

**Current usage path:**
```
Python Model.solve()
  -> joblib Parallel (threading backend)
    -> run_sampling() per worker
      -> set_bias_wrapper() [WRITES global BranchingStats]
      -> ctg() -> solver -> BranchingFunction() [READS global BranchingStats]
```

**Severity:** This is a data race. Under threading, workers may see torn writes or stale values. Because all workers currently use the same bias value, the race is "benign" (same value written), but it is still undefined behavior, and any future per-worker bias tuning will break silently.

### Problem 2: malloc/free in Hot Loops

**Location:** `explore_neighbourhood()` in `local_search.c`, lines 178-179 and 225:
```c
int *changed_con = calloc(MINSIZE, sizeof(int));  // every move iteration
...
free(changed_con);
...
int *changes = calloc(MINSIZE, sizeof(int));       // every feasible move
...
free(changes);
```

Also: `sw_init()` allocates `part` array on heap via `malloc` for temporary `inv` bit arrays created per move.

**Impact:** For a problem with n=100 variables and distance d=2, there are ~5050 moves. Each move allocates and frees 2-3 heap buffers. This means roughly 15,000 malloc/free pairs per neighbourhood scan, per iteration. Heap allocator overhead dominates for small allocations.

### Problem 3: Fixed MAXCLAUSESIZE in Expressions

**Location:** `Expression.h` line 10: `#define MAXCLAUSESIZE 4`

**Impact:** Every clause occupies `(MAXCLAUSESIZE - 1) = 3` variable slots in the flattened `variables` array, regardless of actual clause length. A linear constraint (1 variable) wastes 2/3 of its variable storage. The `variable_index()` function hardcodes stride as `(MAXCLAUSESIZE - 1)`:
```c
static inline size_t first_variable_index(size_t cls, size_t clause_offset) {
    return clause_offset * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}
```

This creates a tight coupling: changing MAXCLAUSESIZE requires recompiling everything and changes memory layout for all clauses. Higher-order terms (degree > 3) are impossible.

### Problem 4: Redundant Full Constraint Re-evaluation

**Location:** `explore_neighbourhood()` lines 181-183:
```c
for (int i = 0; i < C; ++i){
    totals[i] = constraint_violation(dat->con, new_sol, i);
}
```

The optimized `adjusted_constraint_violation()` path is commented out (lines 184-190). Instead, every move re-evaluates ALL clauses of ALL constraints from scratch, even though only d bits changed. This is O(total_clauses) per move instead of O(affected_clauses).

## Recommended Architecture After Refactoring

```
+---------------------------------------------------------------+
|                     Python API Layer                           |
|  Model (Python)  -- owns model_t via Cython                   |
+---------------------------------------------------------------+
       |
+------v--------------------------------------------------------+
|                     Cython Binding Layer                       |
|  Creates solver_ctx_t per worker thread                       |
|  Shares model_t (read-only after close())                     |
+------+--------------------------------------------------------+
       |
+------v--------------------------------------------------------+
|                      C Kernel Layer                            |
|                                                                |
|  SHARED (read-only after preprocessing):                      |
|  +-------------------+  +-------------------+                  |
|  | model_t           |  | new_constraints_t |                  |
|  | (parameters only) |  | (obj + con)       |                  |
|  +-------------------+  +-------------------+                  |
|                                                                |
|  PER-SOLVER (one per thread):                                 |
|  +-------------------+                                         |
|  | solver_ctx_t      |                                         |
|  |  - branching_stats|  (was global BranchingStats)            |
|  |  - scratch arena  |  (replaces hot-loop malloc)             |
|  |  - state buffers  |  (cur_best, new_sol, etc.)              |
|  |  - tabu list      |                                         |
|  |  - move list      |                                         |
|  |  - rng state      |  (thread-local PRNG)                    |
|  +-------------------+                                         |
+---------------------------------------------------------------+
```

### Component Responsibilities (Target)

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| `model_t` | Solver parameters + pointers to shared constraint data. Immutable after `close()`. | Read by all `solver_ctx_t` instances |
| `new_constraints_t` | Flattened constraint/objective arrays + preprocessing indices. Immutable after `preprocessing()`. | Read by solver functions via `model_t` |
| `solver_ctx_t` (NEW) | Per-thread mutable state: branching config, scratch memory, working states, tabu, RNG | Owns all mutable data for one solve thread |
| `arena_t` (NEW) | Bump allocator for scratch memory within one neighbourhood scan | Owned by `solver_ctx_t`, reset per iteration |
| `expression_t` | Build-time only. Consumed by `add_expression_to_constraints()`, then freed. | Feeds into `new_constraints_t` at setup time |

## Architectural Patterns

### Pattern 1: Solver Context Struct (Eliminate Globals)

**What:** Bundle all per-solve mutable state into a single `solver_ctx_t` allocated per thread. Pass it explicitly to every function that currently touches `BranchingStats` or thread-local scratch data.

**When to use:** Whenever converting global/static mutable state to thread-safe code in C.

**Trade-offs:** Every function signature gains a `solver_ctx_t *ctx` parameter (more verbose), but eliminates all global mutable state and makes thread safety trivially verifiable.

**Recommended struct design:**
```c
typedef struct {
    // Branching configuration (was global BranchingStats)
    BranchingStats_t branching;

    // Thread-local PRNG state (replace global rand())
    uint64_t rng_state;

    // Scratch arena for hot-loop allocations
    arena_t arena;

    // Pre-allocated working state buffers
    state_t *cur_best;
    state_t *cur_best_tabu;
    state_t *new_sol;

    // Pre-allocated scratch arrays (sized to problem)
    int64_t *totals;        // [num_constraints]
    int *changed_con;       // [MINSIZE]

    // Tabu list (per solver invocation)
    tabu_list_t tabu;

    // Move list (can be shared read-only OR per-ctx)
    move_t *moves;
    int num_moves;

    // Statistics
    int count_states;
    int id;
} solver_ctx_t;

solver_ctx_t *solver_ctx_create(const model_t *mod);
void solver_ctx_destroy(solver_ctx_t *ctx);
void solver_ctx_reset(solver_ctx_t *ctx);  // reset arena + working state between iterations
```

**Migration path for BranchingFunction:**
```c
// BEFORE (reads global):
static inline double BranchingFunction(int index, int bit_S, int bit_T,
                                        int diffcount, const BranchingStats_t *stats);
// This already takes stats as parameter! The fix is ensuring callers
// pass &ctx->branching instead of &BranchingStats.

// Functions that need updating:
// - StateProbability()   -- currently uses &BranchingStats directly
// - updated()            -- currently uses &BranchingStats via StateProbability
// - set_bias()           -- becomes: ctx->branching.bias = bias
// - set_factors()        -- becomes: set on ctx->branching fields
// - set_obj_dependence() -- becomes: allocate into ctx->branching.obj_dependent
```

### Pattern 2: Arena (Bump) Allocator for Scratch Memory

**What:** Pre-allocate a contiguous memory block per solver context. Hot-loop code "allocates" by bumping a pointer. Reset the entire arena between neighbourhood scans (zero-cost "free").

**When to use:** When many small, short-lived allocations happen in a tight loop (exactly the case in `explore_neighbourhood()`).

**Trade-offs:** Cannot free individual allocations (only reset entire arena). Requires knowing upper bound on total scratch memory per iteration. Dramatically reduces allocator overhead (pointer bump vs syscall).

**Recommended implementation:**
```c
typedef struct {
    char *base;       // start of memory block
    size_t capacity;  // total bytes
    size_t offset;    // current bump position
} arena_t;

static inline void arena_init(arena_t *a, size_t capacity) {
    a->base = malloc(capacity);
    a->capacity = capacity;
    a->offset = 0;
}

static inline void *arena_alloc(arena_t *a, size_t size) {
    // Align to 8 bytes
    size = (size + 7) & ~7;
    if (a->offset + size > a->capacity) return NULL;  // or grow
    void *ptr = a->base + a->offset;
    a->offset += size;
    return ptr;
}

static inline void arena_reset(arena_t *a) {
    a->offset = 0;  // "free" everything at once
}

static inline void arena_destroy(arena_t *a) {
    free(a->base);
}
```

**Sizing the arena:** For `explore_neighbourhood()`, per-move scratch is:
- `changed_con`: `MINSIZE * sizeof(int)` = 8192 bytes
- `inv` bit array parts: `ceil(total_clauses / 64) * 8` bytes
- `changes`: `MINSIZE * sizeof(int)` = 8192 bytes (feasible path)

A conservative arena of 64KB per solver context handles all scratch for one move evaluation. Reset between moves.

### Pattern 3: Pre-allocated Working Buffers

**What:** Instead of allocating `cur_best`, `cur_best_tabu`, `new_sol` states inside every `explore_neighbourhood()` call, pre-allocate them once in `solver_ctx_t` and reuse.

**When to use:** When the same-sized temporary objects are created and destroyed on every function call.

**Current waste in `explore_neighbourhood()`:**
```c
state_t *cur_best = copy_state(dat->sol);      // malloc for vector.part
state_t *cur_best_tabu = copy_state(dat->sol);  // malloc for vector.part
state_t *new_sol = copy_state(dat->sol);         // malloc for vector.part
// ... work ...
free_state(new_sol, 1);  // free vector.part
// cur_best, cur_best_tabu returned to caller who frees them
```

**After:** Working states live in `solver_ctx_t`, just reset their contents:
```c
// In solver_ctx_create():
ctx->cur_best = copy_state(initial);
ctx->cur_best_tabu = copy_state(initial);
ctx->new_sol = copy_state(initial);

// In explore_neighbourhood():
sw_set_inplace(ctx->new_sol->vector, sol->vector);
ctx->cur_best->tot_profit = INT64_MAX;
ctx->cur_best_tabu->tot_profit = INT64_MAX;
// ... use ctx->new_sol, ctx->cur_best, ctx->cur_best_tabu ...
// No malloc, no free
```

### Pattern 4: Dynamic Variable Storage (Replace Fixed MAXCLAUSESIZE Stride)

**What:** Replace the fixed-stride `variable_index()` with offset-based variable storage that adapts to actual clause length.

**When to use:** When clause sizes vary significantly (many linear terms mixed with few quadratic/cubic terms).

**Current layout (fixed stride = MAXCLAUSESIZE - 1 = 3):**
```
variables[]: [v0 v1 v2 | v0 v1 __ | v0 __ __ | v0 v1 v2 | ...]
              clause 0    clause 1   clause 2   clause 3
              (3 vars)    (2 vars)   (1 var)    (3 vars)
              ^ wastes 0  ^ wastes 1 ^ wastes 2  ^ wastes 0
```

**Recommended layout (packed with offset array):**
```
variables[]: [v0 v1 v2 v0 v1 v0 v0 v1 v2 ...]
              clause 0  cl 1  cl2 clause 3
variable_offset[]: [0, 3, 5, 6, 9, ...]  // start index per clause
```

**Migration approach:**
```c
// Replace:
static inline size_t variable_index(size_t cls, size_t k, size_t clause_offset) {
    return first_variable_index(cls, clause_offset) + k;
}

// With:
static inline size_t variable_index_packed(const new_constraints_t *con,
                                            size_t clause_index, size_t k) {
    return con->variable_offset[clause_index] + k;
}
```

**Trade-offs:**
- Pro: Eliminates wasted memory (significant for large linear programs)
- Pro: Better cache locality (denser packing)
- Pro: Removes MAXCLAUSESIZE compile-time limit
- Con: Requires populating `variable_offset[]` during `add_expression_to_constraints()`
- Con: One extra indirection per variable access (offset lookup)
- Con: Touches many call sites that use `variable_index()`

**Build order dependency:** This change touches `constraint.h` (the most widely included header) and every function that iterates clause variables. It must be done carefully with a compatibility shim or all-at-once.

## Data Flow

### Solve Request Flow (Current)

```
Python: model.solve(num_workers=12)
    |
    v
Cython: run_sampling(Model mod, callback, not_stop)
    |
    +-- set_bias_wrapper()          [WRITES global BranchingStats]
    +-- set_seed()                  [WRITES global rand state]
    |
    v
C: ctg(model_t *mod, state_t *cur_sol, callback, incumbents)
    |
    +-- initial_state_preparation(mod)
    |       +-- CSearch_opt/sat(cur_sol, ..., &BranchingStats)
    |                              [READS global BranchingStats]
    |
    +-- [loop] QSearch / updated / StateProbability
                                   [READS global BranchingStats]
```

### Solve Request Flow (Target)

```
Python: model.solve(num_workers=12)
    |
    v
Cython: creates solver_ctx_t per worker
    |
    +-- solver_ctx_create(mod)      [allocates per-thread state]
    +-- ctx->branching.bias = ...   [thread-local write]
    |
    v
C: ctg(model_t *mod, solver_ctx_t *ctx, state_t *cur_sol, callback, incumbents)
    |
    +-- initial_state_preparation(mod, ctx)
    |       +-- CSearch_opt/sat(cur_sol, ..., &ctx->branching)
    |
    +-- [loop] QSearch / updated(... &ctx->branching) / StateProbability(... &ctx->branching)
```

### Shared vs Thread-Local State Boundaries

| Data | Shared/Thread-Local | Mutability | Notes |
|------|---------------------|------------|-------|
| `model_t` parameters (M, stopping_time, etc.) | Shared | Read-only after `close()` | Safe |
| `model_t.obj`, `model_t.con` (constraint arrays) | Shared | Read-only after `preprocessing()` | Safe |
| `model_t.global_opt` | **Shared mutable** | Written by accept_move | **Needs mutex or atomic compare-swap** |
| `model_t.runtime` | **Shared mutable** | Written in local_search loop | **Needs protection or move to ctx** |
| `model_t.qtg_applications` | **Shared mutable** | Accumulated across workers | **Needs atomic add or move to ctx** |
| `BranchingStats` | Currently shared mutable (global) | **Move to solver_ctx_t** | Critical fix |
| `state_t` (cur_sol, new_sol) | Thread-local | Mutable | Already per-thread in local_search |
| `tabu_list_t` | Thread-local | Mutable | Already per-thread in local_search |
| `move_t[]` list | Can be shared | Read-only during search | Generated once, shared across threads |
| `rand()` state | Process-global | **Use per-ctx PRNG** | `rand()` is not thread-safe |

### Key Shared Mutable Data Requiring Synchronization

1. **`model_t.global_opt`** -- multiple threads call `accept_move()` which writes to this. Needs either:
   - A mutex around global_opt updates, OR
   - Per-thread best, merged after join (current local_search does this correctly; ctg path does not)

2. **`model_t.qtg_applications`** -- accumulated counter. Use `__atomic_add_fetch` or merge after join.

3. **`model_t.runtime`** -- written by each worker. Move to `solver_ctx_t`, report max after join.

## Build Order for Refactoring

The refactoring has strict dependency ordering. Phases must proceed in this sequence:

```
Phase 1: solver_ctx_t introduction
    |  - Define struct, create/destroy functions
    |  - Thread BranchingStats into ctx (eliminate global)
    |  - Thread rand() into ctx (per-thread PRNG)
    |  - Update Cython bindings to create/pass ctx
    |
    v
Phase 2: Arena allocator + pre-allocated buffers
    |  - Implement arena_t
    |  - Add arena to solver_ctx_t
    |  - Replace hot-loop malloc/free with arena_alloc/arena_reset
    |  - Pre-allocate working states in ctx
    |
    v
Phase 3: Re-enable incremental constraint evaluation
    |  - Fix/uncomment adjusted_constraint_violation() path
    |  - Verify correctness against full re-evaluation
    |  - Benchmark improvement
    |
    v
Phase 4: Dynamic variable storage (optional, higher risk)
    |  - Add variable_offset[] to new_constraints_t
    |  - Migrate add_expression_to_constraints() to pack variables
    |  - Update all variable_index() call sites
    |  - Remove MAXCLAUSESIZE dependency
    |
    v
Phase 5: Shared mutable state cleanup
    - Protect or eliminate model_t.global_opt sharing
    - Move runtime/qtg_applications to per-ctx, merge after join
```

**Why this order:**
- Phase 1 is prerequisite for everything: without solver_ctx_t, you cannot safely add per-thread arenas or buffers
- Phase 2 is independent of constraint evaluation changes and gives immediate perf wins
- Phase 3 is the biggest algorithmic performance win but requires correctness verification
- Phase 4 is a data structure change touching the most code; defer until core is stable
- Phase 5 is cleanup that can happen anytime after Phase 1 but is lower priority than perf work

## Anti-Patterns

### Anti-Pattern 1: Global Mutable State for Thread Configuration

**What people do:** Define a global struct (like `BranchingStats`) to hold configuration, mutate it before launching threads, read it from threads.

**Why it's wrong:** Even if all threads write the same value, this is undefined behavior per C11. Compiler/CPU may reorder or cache stale values. Any future differentiation per thread will silently corrupt.

**Do this instead:** Allocate configuration per thread in a context struct. Pass context pointer explicitly to all functions.

### Anti-Pattern 2: malloc/free for Fixed-Size Scratch in Tight Loops

**What people do:** `calloc()` a temporary buffer at the top of a loop body, `free()` it at the bottom.

**Why it's wrong:** Heap allocation is O(log n) or worse, involves locks in many allocators, causes fragmentation, and thrashes the allocator metadata cache.

**Do this instead:** Pre-allocate buffers in the solver context or use a bump arena. Reset between iterations instead of freeing.

### Anti-Pattern 3: Compile-Time Array Size Limits via #define

**What people do:** `#define MAXCLAUSESIZE 4` and use it to compute fixed-stride indexing into arrays.

**Why it's wrong:** Wastes memory for smaller elements, prevents larger elements, requires full recompilation to change, and the constant propagates through many translation units.

**Do this instead:** Store per-element offsets in an auxiliary array. The one extra indirection is negligible compared to the memory and flexibility gains.

### Anti-Pattern 4: Using `rand()` in Multi-Threaded Code

**What people do:** Call `rand()` or `srand()` from multiple threads (e.g., `move_list()` with Fisher-Yates shuffle uses `rand()`).

**Why it's wrong:** `rand()` uses global state and is not thread-safe. Results will be correlated across threads or cause data races.

**Do this instead:** Use a per-thread PRNG. A simple xoshiro256** or even `rand_r()` with per-thread seed stored in `solver_ctx_t`.

### Anti-Pattern 5: Freeing Memory Immediately After Thread Creation

**What people do:** In `accept_best_routine()` lines 308-311:
```c
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
    free(data[i].remainings);     // <-- freed while thread may still be using it!
    sw_clear(data[i].ful_con);    // <-- freed while thread may still be using it!
    sw_clear(data[i].ful);
}
```

**Why it's wrong:** `pthread_create` returns before the thread has necessarily started executing. The thread's `explore_neighbourhood()` accesses `dat->remainings` and `dat->ful_con`, but these are freed in the loop that created the thread. This is a use-after-free race condition.

**Do this instead:** Free thread-local data after `pthread_join()`, not after `pthread_create()`.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| n < 100 vars, C < 50 constraints | Current architecture works. Global state races are "benign" (same values). Malloc overhead is tolerable. |
| n = 100-1000, C = 50-500 | Arena allocator essential. Incremental constraint evaluation essential. Per-thread PRNG needed for reproducibility. |
| n > 1000, C > 500 | Dynamic variable storage important (memory savings compound). Constraint preprocessing sparse path (`preprocessing_sparse`) already exists. Consider SIMD for bit operations in `intarray.h`. |

### Scaling Priorities

1. **First bottleneck:** `constraint_violation()` called for ALL constraints on EVERY move. Re-enabling incremental evaluation (Phase 3) gives the largest algorithmic speedup: O(affected_clauses) vs O(total_clauses) per move.

2. **Second bottleneck:** Heap allocation overhead in hot loops. Arena allocator (Phase 2) eliminates this. Expected 10-50x improvement in allocation-dominated portions.

3. **Third bottleneck:** Memory waste from MAXCLAUSESIZE padding. For large linear programs (many 1-variable clauses), this can waste 66% of variable storage, reducing cache effectiveness.

## Integration Points

### Cython-C Boundary

| Boundary | Communication | Refactoring Notes |
|----------|---------------|-------------------|
| Model.pyx -> model.c | `model_t *mod` pointer | Add `solver_ctx_t *` parameter to `ctg()`, `local_search()`, `initial_state_preparation()` |
| SearchLib.pyx -> local_search.c | Direct C function calls with `nogil` | `run_sampling()` must create `solver_ctx_t` before entering nogil block |
| SearchLib.pyx -> Branching.c | `set_bias_wrapper()` etc. | Replace global setters with `ctx->branching.bias = value` |
| Constraint.pyx -> constraint.c | `add_expression_to_constraints()` | No change needed (build-time only) |

### joblib Parallel Integration

Currently: `Parallel(n_jobs=num_workers, backend="threading")` calls `run_sampling()` which shares `Model` object across threads.

Target: Each `run_sampling()` call creates its own `solver_ctx_t` from the shared (read-only) `model_t`. All mutable state lives in `solver_ctx_t`. The `model_t` fields that are currently mutated (`global_opt`, `runtime`, `qtg_applications`) move to `solver_ctx_t` and are merged back after all workers complete.

### pthread Integration (local_search.c)

Currently: `accept_best_routine()` spawns `NUMThreads` pthreads with `local_search_data_t` per thread.

Target: Each pthread gets its own `solver_ctx_t` (or a lightweight sub-context derived from it). The `#define NUMThreads 6` should become a runtime parameter on `model_t`. The use-after-free bug in the create/free loop must be fixed.

## Sources

- Direct codebase analysis (HIGH confidence) -- all architecture observations verified against source files
- [Ryan Fleury: Untangling Lifetimes: The Arena Allocator](https://www.rfleury.com/p/untangling-lifetimes-the-arena-allocator) -- arena allocator design patterns (MEDIUM confidence)
- [Arena and Memory Pool Allocators: 50-100x Performance Secret](https://medium.com/@ramogh2404/arena-and-memory-pool-allocators-the-50-100x-performance-secret-behind-game-engines-and-browsers-1e491cb40b49) -- performance characteristics of arena allocators (LOW confidence, single source)
- [SEI CERT: MEM33-C Flexible Array Members](https://wiki.sei.cmu.edu/confluence/display/c/MEM33-C.++Allocate+and+copy+structures+containing+a+flexible+array+member+dynamically) -- flexible array member patterns (HIGH confidence, authoritative)
- [Red Hat: Benefits and Limitations of Flexible Array Members](https://developers.redhat.com/articles/2022/09/29/benefits-limitations-flexible-array-members) -- flexible array member trade-offs (MEDIUM confidence)
- [Clang Thread Safety Analysis](https://clang.llvm.org/docs/ThreadSafetyAnalysis.html) -- annotation-based thread safety verification (HIGH confidence, official docs)
- [Fast Efficient Fixed-Size Memory Pool](https://arxiv.org/pdf/2210.16471) -- pool allocator design for fixed-size objects (MEDIUM confidence, academic paper)

---
*Architecture research for: CBQS solver stabilization and optimization*
*Researched: 2026-02-04*
