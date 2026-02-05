# Phase 6: Memory Optimization - Research

**Researched:** 2026-02-05
**Domain:** C memory allocators, dynamic arrays, performance benchmarking
**Confidence:** HIGH

## Summary

This phase implements two optimizations: dynamic Expression storage that scales with actual term count using small-object optimization (inline storage for <=8 terms), and arena allocation to eliminate hot-path micro-allocations in the solver's inner loop. The decisions from CONTEXT.md are well-suited to the codebase architecture.

The codebase currently uses a fixed `MAXCLAUSESIZE=4` constant limiting Expression terms, with large initial allocations (`min_size=30000` terms). The inner loop in `explore_neighbourhood()` makes several allocations per move (calloc for `changed_con`, `changes`, `sw_init` for `inv` array). These are excellent candidates for arena allocation.

**Primary recommendation:** Implement the arena as a simple bump allocator integrated into `solver_ctx_t`, with per-iteration reset in `accept_best_routine()` between thread batches.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Standard C malloc/realloc/free | C11+ | Base allocator for Expression growth | Portable, well-understood |
| Custom arena allocator | N/A | Hot-path allocation elimination | No external deps, project-specific needs |
| pytest-benchmark | 5.2+ | Python benchmark framework | JSON output, CI comparison features |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time.h (CLOCK_MONOTONIC) | POSIX | C microbenchmarks | Already in codebase |
| pytest-timeout | 2.x | Prevent benchmark hangs | Already in test deps |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom arena | mimalloc arenas | External dep, overkill for this use case |
| pytest-benchmark | Google Benchmark (C) | Better C granularity, but Python layer easier |
| Custom dynamic array | C++ std::vector | Would require C++ compilation |

**Installation:**
```bash
pip install pytest-benchmark  # For benchmark framework
# Arena allocator is custom C code - no external deps
```

## Architecture Patterns

### Recommended Project Structure
```
cbqs/src/
├── arena.h              # Arena allocator API
├── arena.c              # Arena implementation
├── dyn_expr.h           # Dynamic expression with SOO
├── dyn_expr.c           # Dynamic expression implementation
├── solver_ctx.h         # Extended with arena pointer
└── ...

tests/
├── test_arena.c         # Arena unit tests
├── test_dyn_expr.c      # Dynamic expression tests
└── ...

benchmarks/
├── conftest.py          # pytest-benchmark fixtures
├── test_bench_solver.py # Solver benchmarks
└── bench_results/       # JSON output storage
```

### Pattern 1: Small-Object Optimization (SOO) for Expression

**What:** Store small expressions (<=8 terms) inline in the struct, avoiding heap allocation
**When to use:** Expression created with few terms, which is the common case

```c
// Decision: 8-term inline threshold, 2x growth, 32 initial heap capacity

#define EXPR_INLINE_CAPACITY 8

typedef struct {
    int64_t *literals;      // NULL when using inline storage
    int *len_literal;       // NULL when using inline storage
    size_t expr_size;       // Current term count
    size_t capacity;        // Allocated capacity (0 = using inline)
    int sense;
    int64_t rhs;
    // Inline storage (union would save space but complicate code)
    int64_t inline_literals[EXPR_INLINE_CAPACITY * MAXCLAUSESIZE];
    int inline_len_literal[EXPR_INLINE_CAPACITY];
} dyn_expression_t;

// Access macros
#define EXPR_LITERALS(e) ((e)->capacity == 0 ? (e)->inline_literals : (e)->literals)
#define EXPR_LEN_LITERAL(e) ((e)->capacity == 0 ? (e)->inline_len_literal : (e)->len_literal)
```

### Pattern 2: Arena Allocator with Chained Chunks

**What:** Bump allocator that chains chunks when overflow occurs
**When to use:** Per-solve lifetime, reset between iterations

```c
// Decision: 1MB initial, chain on overflow, reset between iterations

#define ARENA_DEFAULT_SIZE (1024 * 1024)  // 1MB
#define ARENA_CHUNK_SIZE   (256 * 1024)   // 256KB overflow chunks

typedef struct arena_chunk {
    struct arena_chunk *next;  // Linked list of chunks
    size_t size;               // Chunk size
    size_t used;               // Current offset
    char data[];               // Flexible array member
} arena_chunk_t;

typedef struct {
    arena_chunk_t *head;       // First chunk (initial allocation)
    arena_chunk_t *current;    // Current allocation chunk
} arena_t;

// API
arena_t *arena_create(size_t initial_size);
void *arena_alloc(arena_t *arena, size_t size, size_t align);
void arena_reset(arena_t *arena);  // Reset to start, keep memory
void arena_free(arena_t *arena);   // Free all chunks
```

### Pattern 3: Arena Integration with solver_ctx_t

**What:** Arena owned by solver context, lifetime tied to solve operation
**When to use:** All hot-path allocations during solve

```c
// In solver_ctx.h - extend existing struct
struct solver_ctx {
    // ... existing fields ...

    /** Arena for hot-path allocations (per-solve lifetime) */
    arena_t *arena;
};

// In solver_ctx.c
solver_ctx_t *solver_ctx_create(void) {
    solver_ctx_t *ctx = malloc(sizeof(solver_ctx_t));
    // ... existing init ...
    ctx->arena = arena_create(ARENA_DEFAULT_SIZE);
    return ctx;
}

void solver_ctx_free(solver_ctx_t *ctx) {
    // ... existing cleanup ...
    if (ctx->arena) arena_free(ctx->arena);
    free(ctx);
}
```

### Anti-Patterns to Avoid

- **Mixing arena and malloc lifetimes:** All arena allocations must have shorter lifetime than solve
- **Arena for long-lived objects:** Don't use arena for Expression storage (Python owns lifetime)
- **Forgetting alignment:** Always align arena allocations (8-byte minimum for int64_t)
- **Skipping reset:** Must call arena_reset() between solver iterations

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Benchmark statistics | Custom stats | pytest-benchmark | Handles outliers, percentiles, comparison |
| Benchmark CI tracking | Custom tracking | pytest-benchmark --benchmark-compare-fail | Built-in regression detection |
| JSON serialization | sprintf | Python json module | Less error-prone, handles escaping |
| Thread-safe counters | Custom atomic ops | C11 _Atomic | Compiler optimizes, correct memory ordering |

**Key insight:** The benchmark framework does the hard statistical work (Welch's t-test, outlier elimination, percentile calculation). Don't reimplement.

## Common Pitfalls

### Pitfall 1: Arena Alignment Bugs

**What goes wrong:** Unaligned accesses cause crashes on ARM, subtle corruption on x86
**Why it happens:** Simple pointer bump ignores alignment requirements
**How to avoid:** Always pad to alignment before allocation:
```c
ptrdiff_t padding = -(uintptr_t)ptr & (align - 1);
ptr += padding;
```
**Warning signs:** Intermittent crashes, ASan alignment errors

### Pitfall 2: Expression Growth Invalidating Pointers

**What goes wrong:** Code holds pointer to expression data, realloc moves it
**Why it happens:** 2x growth via realloc can return new address
**How to avoid:** Never cache pointers across operations that might grow expression
**Warning signs:** Use-after-free in ASan, random corruption

### Pitfall 3: SOO Transition Bugs

**What goes wrong:** Expression transitions from inline to heap incorrectly
**Why it happens:** Off-by-one in threshold check, or forgetting to copy inline data
**How to avoid:** Clear transition function, thorough testing at boundary (7, 8, 9 terms)
**Warning signs:** Lost data when expression grows past 8 terms

### Pitfall 4: Benchmark Noise in CI

**What goes wrong:** CI fails spuriously due to benchmark variance
**Why it happens:** Cloud VMs have noisy neighbors, throttling
**How to avoid:**
- Use relative comparison (% change), not absolute times
- Require multiple consecutive failures (not single run)
- Set threshold high enough (e.g., 20% regression, not 5%)
**Warning signs:** Flaky CI, benchmarks pass/fail randomly

### Pitfall 5: Arena Reset vs Free Confusion

**What goes wrong:** Memory leaks when arena chunks are reset but not freed
**Why it happens:** Reset keeps memory allocated, which is correct for reuse
**How to avoid:** arena_free() in solver_ctx_free(), arena_reset() between iterations
**Warning signs:** Memory growth over multiple solve calls

## Code Examples

Verified patterns from official sources and best practices:

### Arena Allocation with Alignment (from nullprogram.com)
```c
// Source: https://nullprogram.com/blog/2023/09/27/
void *arena_alloc(arena_t *a, size_t size, size_t align) {
    arena_chunk_t *chunk = a->current;

    // Calculate padding for alignment
    uintptr_t ptr = (uintptr_t)(chunk->data + chunk->used);
    size_t padding = (-(ptrdiff_t)ptr) & (align - 1);

    // Check if fits in current chunk
    if (chunk->used + padding + size > chunk->size) {
        // Overflow: allocate new chunk
        size_t new_size = (size + padding > ARENA_CHUNK_SIZE)
                          ? size + padding + 64  // Large allocation
                          : ARENA_CHUNK_SIZE;
        chunk = arena_chunk_create(new_size);
        chunk->next = NULL;
        a->current->next = chunk;
        a->current = chunk;

        // Recalculate padding for new chunk
        ptr = (uintptr_t)chunk->data;
        padding = (-(ptrdiff_t)ptr) & (align - 1);
    }

    void *result = chunk->data + chunk->used + padding;
    chunk->used += padding + size;
    return result;
}
```

### SOO Transition for Expression
```c
// Transition from inline to heap storage
static int expr_ensure_capacity(dyn_expression_t *expr, size_t needed) {
    if (expr->capacity == 0) {
        // Currently using inline storage
        if (needed <= EXPR_INLINE_CAPACITY) {
            return 0;  // Still fits inline
        }
        // Must transition to heap
        size_t new_cap = 32;  // Decision: initial heap capacity
        while (new_cap < needed) new_cap *= 2;

        expr->literals = malloc(new_cap * MAXCLAUSESIZE * sizeof(int64_t));
        expr->len_literal = malloc(new_cap * sizeof(int));
        if (!expr->literals || !expr->len_literal) {
            free(expr->literals);
            free(expr->len_literal);
            return -1;  // Allocation failure
        }

        // Copy from inline storage
        memcpy(expr->literals, expr->inline_literals,
               expr->expr_size * MAXCLAUSESIZE * sizeof(int64_t));
        memcpy(expr->len_literal, expr->inline_len_literal,
               expr->expr_size * sizeof(int));

        expr->capacity = new_cap;
        return 0;
    }

    // Already on heap - standard 2x growth
    if (needed <= expr->capacity) {
        return 0;  // Already enough
    }

    size_t new_cap = expr->capacity;
    while (new_cap < needed) new_cap *= 2;

    int64_t *new_lit = realloc(expr->literals,
                                new_cap * MAXCLAUSESIZE * sizeof(int64_t));
    int *new_len = realloc(expr->len_literal, new_cap * sizeof(int));
    if (!new_lit || !new_len) {
        // Keep old allocations on failure
        return -1;
    }

    expr->literals = new_lit;
    expr->len_literal = new_len;
    expr->capacity = new_cap;
    return 0;
}
```

### pytest-benchmark Usage
```python
# Source: https://pytest-benchmark.readthedocs.io/
def test_solver_performance(benchmark, small_problem):
    """Benchmark small problem solve time."""
    from cbqs import Model
    model = Model()
    # ... setup model with small_problem fixture ...

    result = benchmark(model.solve)

    # Assertions on result still work
    assert result.feasible

# Run with: pytest benchmarks/ --benchmark-json=bench_results/result.json
# Compare: pytest benchmarks/ --benchmark-compare --benchmark-compare-fail=mean:20%
```

### JSON Benchmark Output Schema
```json
{
    "machine_info": {
        "node": "ci-runner-01",
        "processor": "x86_64",
        "python_version": "3.13.0"
    },
    "benchmarks": [
        {
            "name": "test_solver_small",
            "stats": {
                "min": 0.0234,
                "max": 0.0312,
                "mean": 0.0256,
                "stddev": 0.0021,
                "rounds": 100,
                "median": 0.0251,
                "iqr": 0.0028
            },
            "extra_info": {
                "problem_size": "small",
                "constraints": 10,
                "variables": 20
            }
        }
    ]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| VLAs in inner loop | Heap allocation (Phase 5) | Phase 5 | Safe but slower |
| Fixed MAXCLAUSESIZE=4 | Dynamic with SOO | This phase | Flexible + efficient |
| malloc per iteration | Arena reset | This phase | Eliminates alloc overhead |
| Manual benchmark comparison | pytest-benchmark | This phase | Statistical rigor |

**Deprecated/outdated:**
- `MAXCLAUSESIZE` constant: Will be removed, dynamic sizing handles any count
- `min_size=30000` in Expression.c: Replaced by SOO + dynamic growth

## Open Questions

Things that couldn't be fully resolved:

1. **adjusted_constraint_violation commented out**
   - What we know: Commented out in explore_neighbourhood since before first commit
   - What's unclear: Why it was disabled (correctness issue? incomplete feature?)
   - Recommendation: Leave it commented, focus on arena allocation for current hot path

2. **Arena 50-100x speedup claim**
   - What we know: This speedup is domain-specific, claimed in game engine contexts
   - What's unclear: Actual improvement for this solver's allocation pattern
   - Recommendation: Benchmark before/after to measure real impact (may be 2-10x not 100x)

3. **CI benchmark stability**
   - What we know: GitHub Actions runners have variance
   - What's unclear: Exact threshold that avoids false positives
   - Recommendation: Start with 20% threshold, tune based on observed noise

## Sources

### Primary (HIGH confidence)
- [pytest-benchmark documentation](https://pytest-benchmark.readthedocs.io/) - JSON output, comparison features
- [nullprogram.com arena tips](https://nullprogram.com/blog/2023/09/27/) - Alignment handling, reset patterns
- Codebase analysis: local_search.c, Expression.c, solver_ctx.c

### Secondary (MEDIUM confidence)
- [Wikipedia: Region-based memory](https://en.wikipedia.org/wiki/Region-based_memory_management) - Conceptual foundation
- [Daniel Lemire: Dynamic array growth](https://lemire.me/blog/2013/02/06/how-fast-should-your-dynamic-arrays-grow/) - 2x vs 1.5x tradeoffs
- [Bencher: CI benchmarking](https://bencher.dev/learn/benchmarking/python/pytest-benchmark/) - CI integration patterns

### Tertiary (LOW confidence)
- [Medium: Arena 50-100x speedup](https://medium.com/@ramogh2404/arena-and-memory-pool-allocators-the-50-100x-performance-secret-behind-game-engines-and-browsers-1e491cb40b49) - Speedup claims need validation
- [CodSpeed: CI benchmark noise](https://www.webpronews.com/codspeed-macro-runners-cut-ci-benchmark-noise-below-1-variance/) - Dedicated hardware claims

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Well-established patterns, minimal external deps
- Architecture: HIGH - Clear integration points in existing codebase
- Pitfalls: HIGH - Based on codebase analysis and known C allocation issues

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days - stable domain)
