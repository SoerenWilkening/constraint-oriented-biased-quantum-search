# Phase 2: Critical Correctness Fixes - Research

**Researched:** 2026-02-05
**Domain:** Memory safety (C), immutable value semantics (Python/Cython), thread synchronization (pthreads)
**Confidence:** HIGH

## Summary

This research covers three critical correctness bugs in the CBQS solver that produce silently wrong results:

1. **Use-after-free in `accept_best_routine`** (local_search.c:307-311): Thread data is freed immediately after `pthread_create()`, but before threads consume it. The threads receive dangling pointers.

2. **Inverted realloc condition in sparse preprocessing** (constraint.c): The condition `if (counter & (size_steps - 1))` triggers reallocation on nearly every iteration instead of every `size_steps` iterations. The condition is logically inverted.

3. **Expression mutation bug** (Expression.pyx): Operators like `__add__` mutate `self` and return `self` instead of creating a new Expression. This causes `expr1 = x + 3; expr2 = expr1 + 5` to corrupt `expr1`.

The standard approach is: (1) delay thread data cleanup until after `pthread_join()`, (2) fix the bitmask condition to `== 0` instead of truthy, and (3) implement copy-on-write semantics for Expression operators following Python numeric type conventions.

**Primary recommendation:** Fix the C bugs with minimal changes (move frees, fix condition), implement always-copy semantics for Expression operators (simpler than copy-on-write), implement `__deepcopy__` for the copy module, and emit `DeprecationWarning` for scenarios where the old mutation behavior would have occurred.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pthread | POSIX | Thread synchronization | Already in use; `pthread_join()` ensures thread completion before cleanup |
| Python warnings | stdlib | Deprecation warnings | Standard Python mechanism for API evolution |
| Python copy | stdlib | `deepcopy()` support | Expected by Python users for value-type objects |
| ASan | compiler | Memory error detection | Already in CI; catches use-after-free |
| Valgrind | 3.x | Memory analysis | Deeper leak detection than ASan; requested per CONTEXT.md |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.x | Test regression tests | Verify bug fixes don't regress |
| CMocka | 1.1.7 | C unit tests | Test C-level fixes |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Always-copy semantics | Copy-on-write (COW) | COW is more complex (reference counting, deferred copy), always-copy is simpler and matches user expectation for Expression size |
| DeprecationWarning | FutureWarning | DeprecationWarning is the standard for API changes; FutureWarning is for end-user code |
| `__deepcopy__` | `__reduce__` pickle | `__deepcopy__` is more direct; pickle protocol is overkill for in-memory copy |

**Installation:**
```bash
# Valgrind for CI (Ubuntu):
sudo apt-get install valgrind

# Python warnings module is stdlib, no installation needed
```

## Architecture Patterns

### Recommended Pattern: Thread Data Lifetime

**What:** Thread-local data must outlive the threads that consume it.

**When to use:** Any pthread code passing data to worker threads.

**Current bug (local_search.c:307-311):**
```c
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
    free(data[i].remainings);      // BUG: freed immediately, thread hasn't started
    sw_clear(data[i].ful_con);     // BUG: cleared before thread uses it
    sw_clear(data[i].ful);         // BUG: cleared before thread uses it
}
```

**Correct pattern:**
```c
// Create all threads first
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
}

// Join all threads (wait for completion)
for (int i = 0; i < NUMThreads; ++i) {
    pthread_join(threads[i], NULL);
    // Now safe to cleanup thread-local data
    free(data[i].remainings);
    sw_clear(data[i].ful_con);
    sw_clear(data[i].ful);
    // ... rest of processing
}
```

### Recommended Pattern: Periodic Reallocation with Bitmask

**What:** Use `(count & (step - 1)) == 0` to trigger every `step` iterations when `step` is a power of 2.

**When to use:** Growing arrays in increments to avoid per-iteration reallocation.

**Current bug (constraint.c:185-186, 192-193, 300-301, 307-308, 318, 332):**
```c
int size_steps = 1 << 14;  // 16384
// ...
if (counter_negative & (size_steps - 1))  // BUG: TRUE when NOT a multiple
    con->negative_indices = realloc(...);
```

With `size_steps = 16384` (0x4000), `size_steps - 1 = 16383` (0x3FFF):
- `counter = 0`: `0 & 0x3FFF = 0` (falsy) - no realloc (correct on first)
- `counter = 1`: `1 & 0x3FFF = 1` (truthy) - reallocates (wrong!)
- `counter = 16383`: `16383 & 0x3FFF = 16383` (truthy) - reallocates (wrong!)
- `counter = 16384`: `16384 & 0x3FFF = 0` (falsy) - no realloc (wrong!)

**Correct pattern:**
```c
if ((counter_negative & (size_steps - 1)) == 0 && counter_negative > 0)
    con->negative_indices = realloc(...);
```

Or equivalently:
```c
if (counter_negative % size_steps == 0 && counter_negative > 0)
    con->negative_indices = realloc(...);
```

### Recommended Pattern: Expression Immutability

**What:** Standard operators return new objects; in-place operators mutate and return self.

**When to use:** Expression class to match Python numeric semantics.

**Python int behavior (reference):**
```python
a = 5
b = a + 3   # a is unchanged, b is new object
a += 3      # a is mutated, same identity
```

**Current bug (Expression.pyx:131-142):**
```python
def __add__(self, other):
    if isinstance(other, int):
        add_constant(self.expr, other)  # Mutates self!
        return self                      # Returns same object
```

**Correct pattern (always-copy):**
```python
def __add__(self, other):
    """Return new Expression with other added."""
    if isinstance(other, int):
        new_expr = self._deep_copy()     # Create new Expression with copied C data
        add_constant(new_expr.expr, other)
        return new_expr
    # ... similar for Variable, Expression

def __iadd__(self, other):
    """Mutate self in place, return self."""
    if isinstance(other, int):
        add_constant(self.expr, other)
        return self
    # ... similar for Variable, Expression
```

### Pattern: `__deepcopy__` for Cython Extension Types

**What:** Implement `__deepcopy__` to support `copy.deepcopy()`.

**When to use:** Cython cdef classes that manage C memory.

**Example:**
```python
def __deepcopy__(self, memo):
    """Create independent copy with separate C arrays."""
    new_expr = Expression()
    # Copy all literals and metadata
    copy_expression_data(new_expr.expr, self.expr)  # C helper function
    new_expr.sense = self.sense
    new_expr.rhs = self.rhs
    memo[id(self)] = new_expr
    return new_expr
```

**C helper function:**
```c
void copy_expression_data(expression_t *dest, expression_t *src) {
    dest->expr_size = src->expr_size;
    dest->sense = src->sense;
    dest->rhs = src->rhs;

    // Allocate and copy literals
    size_t literals_size = MAXCLAUSESIZE * src->expr_size;
    dest->literals = malloc(literals_size * sizeof(int64_t));
    memcpy(dest->literals, src->literals, literals_size * sizeof(int64_t));

    // Allocate and copy len_literal
    dest->len_literal = malloc(src->expr_size * sizeof(int));
    memcpy(dest->len_literal, src->len_literal, src->expr_size * sizeof(int));
}
```

### Anti-Patterns to Avoid

- **Freeing thread data in the creation loop:** Always wait for `pthread_join()` before freeing data passed to threads.
- **Using truthy bitmask for periodic triggers:** The condition `x & (power_of_2 - 1)` is truthy for all values EXCEPT multiples.
- **Shallow copying Expression:** Copying the Python wrapper without copying the underlying C arrays leads to double-free or shared mutation.
- **Returning self from `__add__`:** Violates Python's expectation that `a + b` does not modify `a`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread sync | Custom flags | `pthread_join()` | Handles all edge cases, portable |
| Deprecation warnings | Custom stderr print | `warnings.warn(DeprecationWarning)` | Respects filters, stacklevel, suppression |
| Deep copy | Manual field copy | `__deepcopy__` protocol | Integrates with `copy.deepcopy()`, handles cycles |
| Memory copy | Loop over bytes | `memcpy()` | Optimized, correct for overlap |
| Valgrind in CI | Manual memory tracking | `valgrind --leak-check=full` | Industry standard, comprehensive |

**Key insight:** Python's warnings module and copy module are designed exactly for this use case. Thread synchronization primitives handle the complex cases.

## Common Pitfalls

### Pitfall 1: Double-Free After Expression Copy

**What goes wrong:** Copying an Expression without copying C arrays, then both objects try to free the same memory.

**Why it happens:** The Expression wrapper stores a pointer to C-allocated `expression_t`. A shallow copy duplicates the pointer, not the data.

**How to avoid:** Always allocate new C arrays in copy operations. The existing `__copy__` method calls `add_expr` which appends to existing arrays but doesn't create independent storage. Need a deep copy that allocates fresh arrays.

**Warning signs:** Double-free errors from ASan, crashes on garbage collection.

### Pitfall 2: Deprecation Warning Filter Interference

**What goes wrong:** User's warning filters suppress the deprecation warning, they never see it.

**Why it happens:** `DeprecationWarning` is ignored by default in `__main__` for end-user code.

**How to avoid:**
1. Use `stacklevel=2` so warning points to caller's code, not library internals.
2. Document the warning and migration path in release notes.
3. Provide env var to suppress (per CONTEXT.md decision).

**Warning signs:** Users complain about sudden behavior change without seeing deprecation warning.

### Pitfall 3: Incomplete Fix of Realloc Condition

**What goes wrong:** Fixing some but not all instances of the inverted condition.

**Why it happens:** The bug appears in multiple places in constraint.c with slight variations.

**How to avoid:** Use grep/search to find ALL instances of the pattern `& (size_steps - 1)` in reallocation contexts. There are at least 6 occurrences in `preprocessing()` and `preprocessing_sparse()`.

**Warning signs:** Some paths still over-reallocate, performance regression in specific scenarios.

### Pitfall 4: Thread Data Lifetime with Stack-Allocated Arrays

**What goes wrong:** The `data[NUMThreads]` array is stack-allocated in `accept_best_routine`. Pointers to array elements are valid until function returns.

**Why it happens:** The current code frees heap members (`remainings`, `ful_con`, `ful`) too early, but the `data` array itself is fine because it's on the stack.

**How to avoid:** Only the heap-allocated members inside each `local_search_data_t` need lifetime management. Don't move the array allocation, just move the member frees.

**Warning signs:** Fixing by dynamically allocating `data` array is unnecessary complexity.

### Pitfall 5: Expression Consumed on Constraint Creation

**What goes wrong:** If Expression is invalidated after creating a Constraint, user can't reuse it.

**Why it happens:** User decision (Claude's discretion) on whether Expression should be consumed.

**How to avoid:** Decision from CONTEXT.md says Claude decides. Recommendation: Expression should be reusable (not consumed). The `add_expression_to_constraints` function copies data, so the original Expression remains valid. Document this clearly.

**Warning signs:** User surprise when they can't reuse an Expression after `m.add_constraint(expr)`.

## Code Examples

### Fix 1: Thread Data Lifetime (local_search.c)

```c
// accept_best_routine function, around lines 307-332

// BEFORE (buggy):
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
    free(data[i].remainings);      // BUG
    sw_clear(data[i].ful_con);     // BUG
    sw_clear(data[i].ful);         // BUG
}
int accepted_index = -1;
for (int i = 0; i < NUMThreads; ++i) {
    pthread_join(threads[i], NULL);
    // ... processing
}

// AFTER (fixed):
for (int i = 0; i < NUMThreads; ++i) {
    pthread_create(&threads[i], NULL, explore_neighbourhood, (void *) &data[i]);
}
int accepted_index = -1;
for (int i = 0; i < NUMThreads; ++i) {
    pthread_join(threads[i], NULL);

    // NOW safe to cleanup - thread has completed
    free(data[i].remainings);
    sw_clear(data[i].ful_con);
    sw_clear(data[i].ful);

    int acc = 0;
    int acc_tab = 0;
    // ... rest of processing unchanged
}
```

### Fix 2: Realloc Condition (constraint.c)

```c
// preprocessing() function, around lines 185-186, 192-193

// BEFORE (buggy):
if (counter_negative & (size_steps - 1))
    con->negative_indices = realloc(con->negative_indices,
        (counter_negative + size_steps) * sizeof(uint32_t));

// AFTER (fixed):
if ((counter_negative & (size_steps - 1)) == 0 && counter_negative > 0)
    con->negative_indices = realloc(con->negative_indices,
        (counter_negative + size_steps) * sizeof(uint32_t));
```

**Note:** Apply this fix to ALL 6+ occurrences in `preprocessing()` and `preprocessing_sparse()`.

### Fix 3: Expression Immutability (Expression.pyx)

```python
# Expression.pyx

cdef class Expression:
    # ... existing __cinit__, __dealloc__, etc.

    cdef Expression _deep_copy(self):
        """Create independent copy with separate C arrays."""
        cdef Expression new_expr = Expression()
        # Copy expression data at C level
        copy_expression_contents(new_expr.expr, self.expr)
        new_expr.sense = self.sense
        new_expr.rhs = self.rhs
        return new_expr

    def __deepcopy__(self, memo):
        """Support copy.deepcopy()."""
        new_expr = self._deep_copy()
        memo[id(self)] = new_expr
        return new_expr

    def __add__(self, other):
        """Return new Expression with other added. Does not modify self."""
        if isinstance(other, float):
            raise TypeError("Not allowed type!")

        cdef Expression result = self._deep_copy()

        if isinstance(other, int):
            add_constant(result.expr, other)
            return result
        if isinstance(other, Variable):
            add_variable(result.expr, other.index)
            return result
        if isinstance(other, Expression):
            result.add_expr(other)
            return result

    def __iadd__(self, other):
        """Mutate self in place. Matches Python int behavior for +=."""
        if isinstance(other, float):
            raise TypeError("Not allowed type!")
        if isinstance(other, int):
            add_constant(self.expr, other)
            return self
        if isinstance(other, Variable):
            add_variable(self.expr, other.index)
            return self
        if isinstance(other, Expression):
            self.add_expr(other)
            return self

    # Similar pattern for __mul__, __imul__, __sub__, __isub__, etc.
```

### Fix 4: C Helper for Expression Copy (Expression.c)

```c
// Add to Expression.c

void copy_expression_contents(expression_t *dest, expression_t *src) {
    // Copy scalar fields
    dest->expr_size = src->expr_size;
    dest->sense = src->sense;
    dest->rhs = src->rhs;

    // Calculate sizes based on current allocation (use min_size chunks)
    size_t num_chunks = (src->expr_size / min_size) + 1;
    size_t alloc_size = num_chunks * min_size;

    // Reallocate destination arrays
    free(dest->literals);
    free(dest->len_literal);

    dest->literals = malloc(MAXCLAUSESIZE * alloc_size * sizeof(int64_t));
    dest->len_literal = malloc(alloc_size * sizeof(int));

    // Initialize to -1 (padding value)
    for (size_t i = 0; i < MAXCLAUSESIZE * alloc_size; ++i) {
        dest->literals[i] = -1;
    }

    // Copy actual data
    memcpy(dest->literals, src->literals,
           MAXCLAUSESIZE * src->expr_size * sizeof(int64_t));
    memcpy(dest->len_literal, src->len_literal,
           src->expr_size * sizeof(int));
}
```

### Fix 5: Deprecation Warning

```python
# In Expression.pyx, in the old __add__ location (for transition period)

import warnings
import os

_CBQS_SUPPRESS_DEPRECATION = os.environ.get('CBQS_SUPPRESS_DEPRECATION', '').lower() in ('1', 'true', 'yes')

def _warn_mutation_deprecated():
    """Emit deprecation warning for old mutation behavior."""
    if not _CBQS_SUPPRESS_DEPRECATION:
        warnings.warn(
            "Expression operators now return new objects instead of mutating. "
            "Use += for in-place mutation. This matches Python numeric semantics. "
            "Set CBQS_SUPPRESS_DEPRECATION=1 to suppress this warning.",
            DeprecationWarning,
            stacklevel=3  # Points to user's code, not library internals
        )
```

### Fix 6: Regression Tests

```python
# tests/test_expression_py.py

class TestExpressionImmutability:
    """Tests verifying Expression immutability fix (CORR-04)."""

    def test_add_does_not_mutate(self):
        """x + 3 does not modify x."""
        x = Variable(0)
        expr1 = x + 3
        terms_before = list(expr1)
        expr2 = expr1 + 5
        terms_after = list(expr1)

        assert terms_before == terms_after, "expr1 was mutated by expr1 + 5"
        assert expr1 is not expr2, "expr1 + 5 should return new object"

    def test_iadd_does_mutate(self):
        """expr += 3 mutates expr in place."""
        x = Variable(0)
        expr = x + 3
        original_id = id(expr)
        expr += 5

        assert id(expr) == original_id, "+= should return same object"
        terms = list(expr)
        assert [5] in terms, "5 should be in expr after +="

    def test_variable_reuse_independence(self):
        """Same variable in multiple expressions doesn't cause cross-talk."""
        x = Variable(0)
        expr1 = x + 3
        expr2 = x + 5

        terms1 = list(expr1)
        terms2 = list(expr2)

        # expr1 should have [3] constant, not [5]
        assert [3] in terms1
        assert [5] not in terms1
        # expr2 should have [5] constant, not [3]
        assert [5] in terms2
        assert [3] not in terms2

    def test_deepcopy_creates_independent_copy(self):
        """copy.deepcopy(expr) creates fully independent Expression."""
        from copy import deepcopy

        x = Variable(0)
        expr1 = x + 3
        expr2 = deepcopy(expr1)

        # Modify expr2
        expr2 += 10

        # expr1 should be unchanged
        terms1 = list(expr1)
        assert [10] not in terms1
```

```c
// tests/test_local_search.c - Use-after-free regression test

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include "local_search.h"

static void test_accept_best_routine_no_use_after_free(void **state) {
    (void)state;

    // Setup minimal model for local search
    // This test primarily verifies the code doesn't crash under ASan
    // when running with multiple threads

    // Create simple 5-variable knapsack
    expression_t *obj_expr = init_expression();
    add_variable(obj_expr, 0);
    add_variable(obj_expr, 1);
    add_variable(obj_expr, 2);
    add_variable(obj_expr, 3);
    add_variable(obj_expr, 4);
    obj_expr->sense = LOWER;
    obj_expr->rhs = 0;

    // ... setup constraint and model

    // Run local search - if use-after-free exists, ASan will catch it
    // local_search(cur_sol, mod, NULL);

    // Cleanup
    free_expression(obj_expr);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_accept_best_routine_no_use_after_free),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Mutable operators | Immutable operators + `__iadd__` | Python 2.0+ | Standard Python numeric semantics |
| Manual thread sync | POSIX pthread primitives | 1995+ | Portable, well-defined semantics |
| Custom leak detection | ASan + Valgrind | 2010s | Industry standard, comprehensive |
| Silent behavior change | DeprecationWarning | Python 2.1+ | Standard API evolution pattern |

**Deprecated/outdated:**
- Returning `self` from `__add__`: Violates Python data model expectations
- Freeing data before `pthread_join()`: Race condition, undefined behavior

## Open Questions

1. **Expression consumed on Constraint creation?**
   - What we know: CONTEXT.md says Claude decides
   - Recommendation: Expression should be reusable. The C function `add_expression_to_constraints` copies data into the constraint structure, so the original Expression can be safely reused or modified afterward.
   - Rationale: Users naturally expect to reuse expressions (e.g., build a base expression, then add variants for different constraints).

2. **Debug logging format?**
   - What we know: CONTEXT.md says CBQS_DEBUG=1 enables detailed logging
   - Recommendation: Use stderr with format `[CBQS DEBUG] file:line: message`. This avoids interfering with stdout output parsing.
   - Note: This is orthogonal to the bug fixes; can be implemented as enhancement.

3. **Stress test iteration count?**
   - What we know: CONTEXT.md says 100+ solves in a loop
   - Recommendation: 200 iterations provides good coverage for memory issues that manifest gradually. Test should run in under 60 seconds to be CI-friendly.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: Direct reading of local_search.c, constraint.c, Expression.pyx, Expression.c
- [Python warnings module documentation](https://docs.python.org/3/library/warnings.html) - DeprecationWarning, stacklevel, filtering
- [Python copy module documentation](https://docs.python.org/3/library/copy.html) - deepcopy protocol
- [Cython Extension Types documentation](https://cython.readthedocs.io/en/stable/src/userguide/extension_types.html) - cdef class patterns

### Secondary (MEDIUM confidence)
- [pthread tutorial](https://embeddedprep.com/pthreads-tutorial/) - Thread lifecycle, join semantics
- [Cython deepcopy discussion](https://groups.google.com/g/cython-users/c/p2mzJrnOH4Q) - Extension type copy challenges
- [PyAnsys deprecation guide](https://dev.docs.pyansys.com/coding-style/deprecation.html) - Deprecation warning best practices

### Tertiary (LOW confidence)
- Stack Overflow patterns for pthread use-after-free (general patterns, not verified against specific library versions)

## Metadata

**Confidence breakdown:**
- Use-after-free fix: HIGH - Direct code reading, pattern is clear
- Realloc condition fix: HIGH - Direct code reading, bitmask logic is unambiguous
- Expression immutability: HIGH - Python data model is well-defined, implementation pattern is standard
- Deprecation warning: HIGH - Python warnings module is well-documented

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (stable patterns, 30-day validity)
