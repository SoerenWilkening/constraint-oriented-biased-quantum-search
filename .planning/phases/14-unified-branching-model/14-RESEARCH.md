# Phase 14: Unified Branching Model - Research

**Researched:** 2026-02-14
**Domain:** C struct refactoring, 3-term branching formula, array parameter propagation across Python/Cython/C layers
**Confidence:** HIGH

## Summary

Phase 14 replaces the dual-array branching struct (`obj_dependent` + `constraint_dependent` with `objective_factor` + `constraint_factor`) with a single unified `double *branching_weights` array and a 3-term formula at the C kernel layer. The new formula is: `branching_weights * branching_factor + assignment_bias * bias_factor + look_ahead * look_factor`. When no `branching_weights` are set (pointer is NULL), the weights term is skipped entirely, reducing to the existing 2-term behavior.

This is a v2.0 hard breaking change. The old dual fields (`obj_dependent`, `constraint_dependent`, `objective_factor`, `constraint_factor`) are deleted from `BranchingStats_t`, old C setters (`solver_ctx_set_obj_dependence`, `solver_ctx_set_constraint_dependence`) are removed, and old Cython wrappers are removed. The new array is exposed through `set_param('branching_weights', array)`.

The codebase already has all the infrastructure needed: `solver_ctx_t` embeds `BranchingStats_t`, the `set_param`/`get_param` API exists on `Model`, and parameter propagation from Python through Cython to C solver context is proven by Phase 12's work with `manual_bias` and `branching_factors`. The primary work is: (1) restructuring `BranchingStats_t`, (2) rewriting `BranchingFunction` with the 3-term formula, (3) adding a new C setter `solver_ctx_set_branching_weights()`, (4) wiring `set_param('branching_weights', ...)` through Cython, and (5) updating all tests to use the new API.

**Primary recommendation:** Bottom-up implementation -- start with C struct changes, then rewrite BranchingFunction, then update solver_ctx setters, then update Cython declarations, then wire Python API, then update all tests. This ordering ensures each layer compiles before the next is modified.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Array Semantics:**
- One weight per decision variable -- array length = num_variables
- Array length must strictly match num_variables; error if mismatched
- Weight of 0.0 means no branching preference (neutral) -- assignment_bias and look_ahead still apply
- Weights are auto-normalized before use in the 3-term formula

**Default Behavior:**
- When no branching_weights are set, the pointer is NULL -- BranchingFunction skips the weights term entirely
- When weights=NULL, the formula simplifies to 2 terms: `assignment_bias * bias_factor + look_ahead * look_factor`
- branching_factor defaults to 1.0
- bias_factor and look_factor default to matching existing code behavior (Claude determines exact values from current implementation)
- `set_param('branching_weights', None)` is allowed -- clears weights back to NULL
- Weights persist across multiple solve() calls (sticky, like other params)
- All three factors (branching_factor, bias_factor, look_factor) are exposed as settable params via set_param()

**Validation & Errors:**
- Wrong-sized array raises ValueError immediately at set_param() time: "Expected array of length N, got M"
- Negative weight values are rejected with ValueError
- NaN and Inf values are rejected with ValueError
- Factor values (branching_factor, bias_factor, look_factor) must be non-negative; reject with ValueError otherwise

**Migration from Old API:**
- Old branching setters (set_obj_dependence, set_constraint_dependence) are removed immediately in Phase 14 -- no deprecation period
- Old struct fields (objective_factor, constraint_factor, obj_dependent, constraint_dependent) are deleted -- compile error for any code referencing them, no compat macros
- Phase 14 updates existing branching tests just enough to compile and pass with the new struct -- keeps CI green
- No per-phase migration docs; migration guide deferred to v2.0 release notes

### Claude's Discretion

- Exact normalization algorithm (L1, L2, max-norm, etc.)
- Internal memory layout and allocation strategy for the weights array
- Exact default values for bias_factor and look_factor (derived from current code behavior)
- How the 3-term formula interacts with existing BranchingFunction internals

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library/Tool | Purpose | Why Standard |
|-------------|---------|--------------|
| C standard library (`stdlib.h`, `string.h`, `math.h`) | Memory allocation, array normalization, NaN/Inf checks | Already used throughout codebase |
| Cython | Python-C bridge for weights array propagation | Already the middleware layer |
| NumPy | Python-side array creation and validation | Already used for array params in SearchLib.pyx |
| CMocka | C-level branching struct and function tests | Already the C test framework |
| pytest | Python-level set_param API and validation tests | Already the Python test framework |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| ASan (AddressSanitizer) | Memory safety for new weights array allocation/free | CI pipeline, already configured |
| `isnan()` / `isinf()` from `<math.h>` | NaN/Inf validation at C layer | When validating incoming weights |

## Architecture Patterns

### Current BranchingStats_t Struct (TO BE REPLACED)

```c
// Branching.h (current)
typedef struct {
    double objective_factor;      // REMOVE
    double *obj_dependent;        // REMOVE

    double constraint_factor;     // REMOVE
    double *constraint_dependent; // REMOVE

    double bias_factor;           // KEEP (assignment bias factor)
    double bias;                  // KEEP (assignment bias value)

    double look_factor;           // KEEP (look-ahead factor)
} BranchingStats_t;
```

### Target BranchingStats_t Struct (NEW)

```c
// Branching.h (new)
typedef struct {
    double *branching_weights;    // NEW: per-variable weights (NULL = no weights)
    int num_weights;              // NEW: length of branching_weights array

    double branching_factor;      // NEW: weight for branching_weights term (default 1.0)
    double bias_factor;           // KEEP: weight for assignment_bias term
    double bias;                  // KEEP: assignment bias value (n/4 default)
    double look_factor;           // KEEP: weight for look-ahead term
} BranchingStats_t;
```

### Current BranchingFunction Formula (TO BE REPLACED)

The current `BranchingFunction` computes a weighted sum of 4 terms, normalized by the sum of factors:

```
normalizer = 1 / (objective_factor + constraint_factor + bias_factor + look_factor)
total_bias = normalizer * objective_factor * f                    // obj_dependent term
           + normalizer * constraint_factor * q                   // constraint_dependent term
           + normalizer * bias_factor * (bias + 1) / (bias + 2)  // assignment bias term
           + normalizer * look_factor * lookahead_probability     // look-ahead term
```

Where:
- `f = obj_dependent[index]` (if array is not NULL, else 0)
- `q = constraint_dependent[index]` (if array is not NULL, else 0)
- Assignment bias = `(bias + 1) / (bias + 2)` -- this is the per-bit "bias towards the current best" probability
- look_ahead = `lookahead_0_probability` (1.0 if diffcount >= 0 towards 0, 0.0 otherwise; forced to 0 if diffcount == 0)

The formula output is the probability that variable `index` gets assigned the SAME value as the current best solution (bit_S). When bit_S != bit_T, the formula result is subtracted from 1.

### Target 3-Term Formula (NEW)

```
// When branching_weights != NULL:
normalizer = 1 / (branching_factor + bias_factor + look_factor)
total_bias = normalizer * branching_factor * branching_weights[index]   // unified weights term
           + normalizer * bias_factor * (bias + 1) / (bias + 2)        // assignment bias term
           + normalizer * look_factor * lookahead_probability           // look-ahead term

// When branching_weights == NULL:
normalizer = 1 / (bias_factor + look_factor)
total_bias = normalizer * bias_factor * (bias + 1) / (bias + 2)        // assignment bias term
           + normalizer * look_factor * lookahead_probability           // look-ahead term
```

### Default Factor Values (Derived from Current Code)

From the current global defaults in `Branching.c`:

```c
BranchingStats_t BranchingStats = {
    .objective_factor = 0,     // obj term effectively disabled
    .obj_dependent = NULL,
    .constraint_factor = 0,    // constraint term effectively disabled
    .constraint_dependent = NULL,
    .bias_factor = 1,          // assignment bias enabled at weight 1.0
    .bias = 5,                 // assignment bias value
    .look_factor = 0.0         // look-ahead disabled
};
```

**Analysis:** The current defaults set `objective_factor = 0` and `constraint_factor = 0`, meaning only the `bias_factor` term is active by default. The formula normalizer becomes `1 / (0 + 0 + 1 + 0) = 1`, and the result is purely `bias_factor * (bias + 1) / (bias + 2)`.

**Recommended defaults for new struct:**
- `branching_weights = NULL` (no weights -- weights term skipped)
- `num_weights = 0`
- `branching_factor = 1.0` (per user decision)
- `bias_factor = 1.0` (matches current default exactly)
- `bias = 5.0` (matches current default, overridden by `close()` to `n/4`)
- `look_factor = 0.0` (matches current default -- look-ahead disabled)

This produces identical behavior to the current code when no branching_weights are set: `normalizer = 1 / (1 + 0) = 1`, result = `1 * (5 + 1) / (5 + 2) = 6/7 ~= 0.857`.

### BranchingFunction Call Sites

All call sites in the solver pass `bit_T=0` and `diffcount=0`:

| File | Line | Pattern |
|------|------|---------|
| `solver.c` CSearch_opt | 307 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `solver.c` CSearch_opt_sat | 423 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `solver.c` CSearch_sat | 562 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `solver.c` CSearch_opt_monte_carlo | 674 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `solver.c` CSearch_opt_sat_monte_carlo | 784 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `solver.c` CSearch_sat_monte_carlo | 898 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `approximate_state_sampler.c` CSearch_opt_sampler | 159 | `BranchingFunction(i, bit, 0, 0, &ctx->branching_stats)` |
| `Branching.c` StateProbability | 53 | `BranchingFunction(j, bit_S, bit_T, 0, &ctx->branching_stats)` |

**Important observation:** `StateProbability` (in `Branching.c` line 53) is the ONLY call site that passes non-zero `bit_T` values (it passes the actual threshold bit). All sampling calls pass `bit_T=0`. This means the `bit_S == bit_T` vs `bit_S != bit_T` branching logic in the formula is only exercised by `StateProbability` during amplitude estimation.

**Since `bit_T=0` and `diffcount=0` in all solver call sites:**
- `look_factor` is forced to 0 (because `if (diffcount == 0) look_factor = 0`)
- `lookahead_0_probability = 1` (because `diffcount >= 0`)
- When `bit_S=0` (current bit=0, bit_T=0): "both 0" case, formula adds terms
- When `bit_S=1` (current bit=1, bit_T=0): "different bits" case, formula subtracts terms from 1

This means the look-ahead term is effectively dead code in the current solver call sites. The new formula should preserve this behavior for backward compatibility.

### Parameter Flow: Python to C

The existing pattern from Phase 12 (proven working) for `manual_bias`:

```
Python: model.set_param('manual_bias', [...])
  -> Model._params['manual_bias'] = [...]
  -> Model.solve() passes _params to run_sampling()
  -> SearchLib.pyx run_sampling():
      arr = np.array(manual_bias, dtype=np.double)
      dep_ptr = <double *> calloc(arr.shape[0], sizeof(double))
      for i in range(arr.shape[0]):
          dep_ptr[i] = <double> arr[i]
      solver_ctx_set_obj_dependence(ctx, dep_ptr, len(manual_bias))
      free(dep_ptr)
```

The new `branching_weights` will follow the exact same pattern, but call `solver_ctx_set_branching_weights()` instead of `solver_ctx_set_obj_dependence()`.

### Recommended Project Structure for Changes

```
cbqs/src/
  Branching.h        # Restructure BranchingStats_t, rewrite BranchingFunction
  Branching.c        # Update global defaults, update set_* functions, remove old setters
  solver_ctx.h       # Add solver_ctx_set_branching_weights(), remove old setters
  solver_ctx.c       # Implement new setter, update free/create, update debug_stats

cbqs/
  branching.pxd      # Update BranchingStats_t Cython declaration, remove old externs
  branching.pyx      # Remove deprecated wrappers (set_obj_dependence_wrapper, etc.)
  SearchLib.pxd      # Add solver_ctx_set_branching_weights() declaration, remove old setters
  SearchLib.pyx      # Wire branching_weights propagation in run_sampling/run_local_search
  Model.pyx          # Add 'branching_weights' to _KNOWN_PARAMS, add validation

tests/
  test_branching.c   # Rewrite tests to use new struct, add 3-term formula tests
  test_solver.c      # Remove global BranchingStats references
  test_integration.c # Remove reset_branching_stats() helper
  test_local_search.c # Remove reset_branching_stats() helper
  test_thread_safety.c # Update independent contexts test for new struct fields
  test_set_param.py  # Add branching_weights validation tests
  test_branching_propagation.py  # Update for new API
```

### Anti-Patterns to Avoid

- **Don't leave old struct fields with `#ifdef COMPAT`:** The decision says "compile error for any code referencing them, no compat macros." Clean removal only.
- **Don't store unnormalized weights in the struct:** Normalize once at set time, not on every BranchingFunction call. The hot path must remain fast.
- **Don't skip validation at the C layer:** Even though Python validates, the C setter should be defensive (NULL checks, size > 0).
- **Don't forget `num_weights` in the struct:** The C layer needs to know array length for bounds checking.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NaN/Inf detection | Custom bit manipulation | `isnan()` / `isinf()` from `<math.h>` | Standard, portable, compiler-optimized |
| Array copying | Manual loop | `memcpy()` | Already used in existing setters, no UB risk |
| Python array conversion | Manual element extraction | NumPy `np.array(value, dtype=np.double)` | Already the pattern in SearchLib.pyx |

**Key insight:** The entire parameter propagation pipeline (Python list -> NumPy array -> calloc + copy -> C function -> memcpy into struct -> free temp) is already proven by the `manual_bias` / `obj_dependence` path. Phase 14 replicates this exact pattern for `branching_weights`.

## Common Pitfalls

### Pitfall 1: Division by zero in normalizer when all factors are 0

**What goes wrong:** If `branching_factor = 0`, `bias_factor = 0`, and `look_factor = 0`, the normalizer `1 / (0 + 0 + 0)` produces infinity/NaN.

**Why it happens:** User could set all three factors to 0 via `set_param`.

**How to avoid:** In BranchingFunction, check if the factor sum is 0 and return a sensible default (e.g., 0.5 for uniform random branching). The current code has the same potential issue but it's hidden because `bias_factor` defaults to 1 and users rarely set all factors to 0.

**Warning signs:** NaN propagation causes all branching decisions to become deterministic or crash.

### Pitfall 2: Memory leak when overwriting branching_weights

**What goes wrong:** Calling `solver_ctx_set_branching_weights()` twice without freeing the first array leaks memory.

**Why it happens:** The new setter must free any existing `branching_weights` before allocating the replacement.

**How to avoid:** Follow the exact pattern from `solver_ctx_set_obj_dependence()`:
```c
if (ctx->branching_stats.branching_weights != NULL) {
    free(ctx->branching_stats.branching_weights);
}
ctx->branching_stats.branching_weights = calloc(n, sizeof(double));
```

**Warning signs:** ASan reports in CI, Valgrind leak reports.

### Pitfall 3: Global BranchingStats still referenced by test_solver.c and test_integration.c

**What goes wrong:** Several C test files reference the global `BranchingStats` variable and its old fields. After removing the old fields, these tests won't compile.

**Why it happens:** Tests were written before Phase 3's solver_ctx, and some still reset the global struct directly.

**How to avoid:** The global `BranchingStats` variable still exists (it's declared `extern` in Branching.h and defined in Branching.c), but its fields change. Tests that reference old field names (`objective_factor`, `constraint_factor`, `obj_dependent`, `constraint_dependent`) must be updated. Specifically:
- `test_solver.c`: `build_small_model()` resets `BranchingStats.objective_factor = 0` etc. -- update to new field names
- `test_integration.c`: `reset_branching_stats()` helper resets all fields -- update to new fields
- `test_local_search.c`: Same `reset_branching_stats()` helper -- update
- `test_thread_safety.c`: References `objective_factor` and `constraint_factor` in assertions -- update

**Warning signs:** Compile errors in test targets after struct change.

### Pitfall 4: Normalization timing - normalize at set time vs. use time

**What goes wrong:** If weights are normalized on every `BranchingFunction` call, performance degrades significantly (BranchingFunction is called once per variable per sample, thousands of times per second).

**Why it happens:** Normalization involves iterating the entire weights array, which is O(n) where n = num_variables.

**How to avoid:** Normalize the weights array ONCE when `solver_ctx_set_branching_weights()` is called. Store the already-normalized values in the struct. The BranchingFunction simply reads `branching_weights[index]` without any per-call normalization overhead.

**Warning signs:** Performance regression in solver benchmarks.

### Pitfall 5: `set_param('branching_weights', None)` must clear the array

**What goes wrong:** If clearing weights doesn't free the old array and set the pointer to NULL, the weights term remains active when it shouldn't be.

**Why it happens:** The `None` case requires special handling in the Python/Cython layer.

**How to avoid:** In the Cython propagation code, check for `None` explicitly:
```python
if branching_weights is None:
    # Clear weights back to NULL
    solver_ctx_set_branching_weights(ctx, NULL, 0)
else:
    # Validate and set weights array
```
The C setter should handle `dep == NULL || n <= 0` by freeing existing and setting to NULL.

### Pitfall 6: Array length validation requires num_variables knowledge at set_param time

**What goes wrong:** `set_param('branching_weights', array)` needs to validate that `len(array) == num_variables`, but `num_variables` isn't available until variables are added and the model is built.

**Why it happens:** `set_param` can be called at any time, but `self.n` may not be final yet.

**How to avoid:** Two options:
1. **Validate at set_param time** if `self.n > 0` (model has variables), defer validation otherwise and check at solve time.
2. **Always validate at solve time** in `run_sampling`/`run_local_search` where `n = mod.mod[0].initial_state[0].vector.bits` is known.

**Recommendation:** Validate at `set_param` time using `self.n`, which is set by `add_variable`/`add_variables`. If `self.n == 0`, defer validation to solve time. This matches the user decision of "error at set_param() time" while handling the case where set_param is called before variables are added.

## Code Examples

### Example 1: New BranchingStats_t struct (Branching.h)

```c
typedef struct {
    double *branching_weights;  /* Per-variable weights (NULL = no weights) */
    int num_weights;            /* Length of branching_weights (0 when NULL) */

    double branching_factor;    /* Factor for branching_weights term (default 1.0) */

    double bias_factor;         /* Factor for assignment_bias term (default 1.0) */
    double bias;                /* Assignment bias value (default 5.0) */

    double look_factor;         /* Factor for look-ahead term (default 0.0) */
} BranchingStats_t;
```

### Example 2: New BranchingFunction (Branching.h)

```c
static inline double BranchingFunction(int index, int bit_S, int bit_T,
                                       int diffcount,
                                       const BranchingStats_t *stats) {
    double total_bias;
    double bias_factor = stats->bias_factor;
    double look_factor = stats->look_factor;
    double branching_factor = stats->branching_factor;

    if (diffcount == 0) look_factor = 0;

    double lookahead_0_probability = (diffcount < 0) ? 0.0 : 1.0;
    double assignment_bias = (stats->bias + 1.0) / (stats->bias + 2.0);

    /* Compute factor sum for normalization */
    double factor_sum = bias_factor + look_factor;
    double w = 0.0;  /* branching weight for this variable */

    if (stats->branching_weights != NULL && index < stats->num_weights) {
        w = stats->branching_weights[index];
        factor_sum += branching_factor;
    }

    /* Guard against division by zero */
    if (factor_sum <= 0.0) {
        return 0.5;  /* Uniform random if all factors are zero */
    }

    double normalizer = 1.0 / factor_sum;

    /* 3-term (or 2-term) formula */
    double value = 0.0;
    if (stats->branching_weights != NULL && index < stats->num_weights) {
        value += normalizer * branching_factor * w;
    }
    value += normalizer * bias_factor * assignment_bias;
    value += normalizer * look_factor * lookahead_0_probability;

    /* Apply bit_S / bit_T branching logic (same as current code) */
    if (bit_T == 0) {
        total_bias = (bit_S == 0) ? value : (1.0 - value);
    } else {
        total_bias = (bit_S == 0) ? (1.0 - value) : value;
    }

    return total_bias;
}
```

### Example 3: New C setter (solver_ctx.c)

```c
void solver_ctx_set_branching_weights(solver_ctx_t *ctx, const double *weights,
                                       int n) {
    if (ctx == NULL) return;

    /* Free existing weights */
    if (ctx->branching_stats.branching_weights != NULL) {
        free(ctx->branching_stats.branching_weights);
        ctx->branching_stats.branching_weights = NULL;
        ctx->branching_stats.num_weights = 0;
    }

    /* NULL/empty means clear weights */
    if (weights == NULL || n <= 0) return;

    /* Allocate and copy */
    ctx->branching_stats.branching_weights = calloc((size_t)n, sizeof(double));
    if (ctx->branching_stats.branching_weights == NULL) return;

    memcpy(ctx->branching_stats.branching_weights, weights,
           (size_t)n * sizeof(double));
    ctx->branching_stats.num_weights = n;

    /* Normalize using L1 norm (sum of absolute values) */
    double sum = 0.0;
    for (int i = 0; i < n; i++) {
        sum += fabs(ctx->branching_stats.branching_weights[i]);
    }
    if (sum > 0.0) {
        for (int i = 0; i < n; i++) {
            ctx->branching_stats.branching_weights[i] /= sum;
        }
    }
}
```

### Example 4: Cython propagation (SearchLib.pyx)

```python
# In run_sampling(), after solver_ctx_create():

# Branching weights (new unified array)
param_weights = mod._params.get('branching_weights') if hasattr(mod, '_params') else None
if param_weights is not None:
    arr_bw = np.array(param_weights, dtype=np.double)
    bw_ptr = <double *> calloc(arr_bw.shape[0], sizeof(double))
    for i in range(arr_bw.shape[0]):
        bw_ptr[i] = <double> arr_bw[i]
    solver_ctx_set_branching_weights(ctx, bw_ptr, len(param_weights))
    free(bw_ptr)
    bw_ptr = NULL
```

### Example 5: Python validation in set_param (Model.pyx)

```python
def set_param(self, str name, value):
    if name not in _KNOWN_PARAMS:
        raise ValueError(f"Unknown parameter: '{name}'")

    # Special validation for branching_weights
    if name == 'branching_weights':
        if value is not None:
            import numpy as np
            arr = np.asarray(value, dtype=np.float64)
            if arr.ndim != 1:
                raise ValueError("branching_weights must be a 1D array")
            if self.n > 0 and len(arr) != self.n:
                raise ValueError(
                    f"Expected array of length {self.n}, got {len(arr)}"
                )
            if np.any(arr < 0):
                raise ValueError("branching_weights must be non-negative")
            if np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
                raise ValueError("branching_weights must not contain NaN or Inf")

    # Special validation for factor params
    if name in ('branching_factor', 'bias_factor', 'look_ahead_factor'):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")

    self._params[name] = value
```

## Normalization Algorithm Recommendation

**Recommendation: L1 normalization (sum of values).**

Rationale:
- The weights represent per-variable branching preferences. L1 normalization ensures the weights sum to 1.0, making each weight interpretable as a "fraction of the branching influence" for that variable.
- This matches the semantic of the existing `obj_dependent` and `constraint_dependent` arrays, which are used as direct multipliers in the formula.
- L1 is the simplest and most intuitive normalization for probability-like values.
- Since negative weights are rejected at validation time, all weights are non-negative, so L1 norm = simple sum.
- If all weights are 0.0, skip normalization (the entire branching_weights term contributes 0 anyway, since `w[i] = 0` for all i).

Alternative considered:
- **Max normalization** (divide by max value): Would make the largest weight = 1.0. Downside: changes the relative contribution of the weights term to the formula based on the maximum rather than the total mass.
- **L2 normalization**: Overkill for this use case; L2 is more appropriate for direction vectors.

## Memory Management Strategy

**Strategy: Copy-on-set with ownership in BranchingStats_t.**

This matches the existing pattern for `obj_dependent` and `constraint_dependent`:

1. `solver_ctx_set_branching_weights(ctx, weights, n)`:
   - Frees existing `ctx->branching_stats.branching_weights` if not NULL
   - Allocates new array via `calloc(n, sizeof(double))`
   - Copies from input via `memcpy`
   - Normalizes in place
   - The caller frees its own copy (the Cython temp allocation)

2. `solver_ctx_free(ctx)`:
   - Frees `ctx->branching_stats.branching_weights` if not NULL
   - Sets pointer to NULL (defensive)

3. `solver_ctx_create()`:
   - Initializes `branching_weights = NULL`, `num_weights = 0`

This is a simple, proven pattern. No shared ownership, no reference counting.

## Files Requiring Changes (Complete Inventory)

### C Layer (must compile first)

| File | Change Type | Details |
|------|------------|---------|
| `cbqs/src/Branching.h` | **MAJOR** | Restructure BranchingStats_t, rewrite BranchingFunction inline, remove old function declarations |
| `cbqs/src/Branching.c` | **MAJOR** | Update global defaults, remove `set_obj_dependence()`, `set_constraint_dependence()`, remove `set_factors()` (4-param version) |
| `cbqs/src/solver_ctx.h` | **MAJOR** | Remove `solver_ctx_set_obj_dependence()`, `solver_ctx_set_constraint_dependence()`, `solver_ctx_set_factors()` (4-param). Add `solver_ctx_set_branching_weights()`, `solver_ctx_set_branching_factor()`, `solver_ctx_set_bias_factor()`, `solver_ctx_set_look_factor()` |
| `cbqs/src/solver_ctx.c` | **MAJOR** | Implement new setters, update `solver_ctx_create()` defaults, update `solver_ctx_free()` to free `branching_weights`, update `solver_ctx_debug_stats()` |

### Cython Layer (after C compiles)

| File | Change Type | Details |
|------|------------|---------|
| `cbqs/branching.pxd` | **MAJOR** | Update BranchingStats_t fields, remove old extern declarations |
| `cbqs/branching.pyx` | **MAJOR** | Remove `set_obj_dependence_wrapper()`, `set_constraint_dependence_wrapper()`, `set_factors_wrapper()` |
| `cbqs/SearchLib.pxd` | **MODERATE** | Remove old solver_ctx setter declarations, add `solver_ctx_set_branching_weights()` |
| `cbqs/SearchLib.pyx` | **MODERATE** | Replace `manual_bias` propagation with `branching_weights` propagation in both `run_sampling()` and `run_local_search()`, remove old factor propagation |
| `cbqs/Model.pyx` | **MODERATE** | Add 'branching_weights', 'branching_factor' to `_KNOWN_PARAMS`, update factor params, add validation, update `solve()` to remove old branching kwargs |

### Test Files

| File | Change Type | Details |
|------|------------|---------|
| `tests/test_branching.c` | **MAJOR** | Rewrite all tests for new struct: remove old setter tests, add new setter and formula tests |
| `tests/test_solver.c` | **MINOR** | Update `build_small_model()` to reset new struct fields instead of old ones |
| `tests/test_integration.c` | **MINOR** | Update `reset_branching_stats()` for new fields |
| `tests/test_local_search.c` | **MINOR** | Update `reset_branching_stats()` for new fields |
| `tests/test_thread_safety.c` | **MINOR** | Update field assertions in `test_independent_contexts()`, `test_debug_output()` |
| `tests/test_set_param.py` | **MODERATE** | Add branching_weights validation tests, update factor tests |
| `tests/test_branching_propagation.py` | **MODERATE** | Update for new API (branching_weights instead of manual_bias) |

### Build Configuration

| File | Change Type | Details |
|------|------------|---------|
| `tests/CMakeLists.txt` | **NONE** | No changes needed -- same source files, just content changes |

## State of the Art

| Old Approach (v1.x) | New Approach (v2.0 Phase 14) | Impact |
|---------------------|------------------------------|--------|
| Dual arrays: `obj_dependent` + `constraint_dependent` | Single unified `branching_weights` array | Simpler API, one array to configure |
| Dual factors: `objective_factor` + `constraint_factor` | Single `branching_factor` | 3 factors total instead of 4 |
| 4-term formula | 3-term formula (or 2-term when weights=NULL) | Cleaner, easier to reason about |
| `set_param('manual_bias', [...])` for obj_dependence | `set_param('branching_weights', [...])` | Unified, clear semantics |
| `solver_ctx_set_obj_dependence()` + `solver_ctx_set_constraint_dependence()` | `solver_ctx_set_branching_weights()` | Single function, cleaner C API |

**Removed in Phase 14:**
- `BranchingStats_t.objective_factor` / `constraint_factor` / `obj_dependent` / `constraint_dependent`
- `solver_ctx_set_obj_dependence()` / `solver_ctx_set_constraint_dependence()`
- `solver_ctx_set_factors()` (4-parameter version)
- `set_obj_dependence()` / `set_constraint_dependence()` / `set_factors()` (global C setters)
- `set_obj_dependence_wrapper()` / `set_constraint_dependence_wrapper()` / `set_factors_wrapper()` (Cython wrappers)
- `_KNOWN_PARAMS` entries: `manual_bias`, `manual_bias_factor`, `branching_factors`

**Added in Phase 14:**
- `BranchingStats_t.branching_weights` / `num_weights` / `branching_factor`
- `solver_ctx_set_branching_weights()`
- `_KNOWN_PARAMS` entries: `branching_weights`, `branching_factor`

## Open Questions

1. **Should `branching_factor`, `bias_factor`, `look_factor` replace or augment the existing `branching_factors` param?**
   - What we know: The user decision says "All three factors are exposed as settable params via set_param()." Currently `branching_factors` is a 4-tuple `(obj, con, bias, look)`.
   - What's unclear: Should `set_param('branching_factors', ...)` be removed entirely, replaced with individual factor params, or kept alongside them?
   - Recommendation: Remove `branching_factors` tuple param. Replace with three individual params: `set_param('branching_factor', 1.0)`, `set_param('bias_factor', 1.0)`, `set_param('look_ahead_factor', 0.0)`. The old 4-tuple doesn't map cleanly to the 3-factor model. Note: `bias_factor` and `look_ahead_factor` already exist in `_KNOWN_PARAMS`.

2. **Should `StateProbability` still use the new BranchingFunction?**
   - What we know: `StateProbability` is the only call site that passes actual `bit_T` values (not always 0). It's used for amplitude estimation.
   - What's unclear: Whether the branching_weights should affect amplitude estimation at all.
   - Recommendation: Yes, keep `StateProbability` using the new `BranchingFunction`. The function signature doesn't change, only the internals. This is consistent behavior.

3. **What happens to `solve()` kwargs `manual_bias`, `bias_factor`, `manual_bias_factor`, `look_ahead_factor`?**
   - What we know: v2.0 removes all solve() kwargs per STATE.md: "Hard breaking change -- remove all solve() kwargs, set_param() only."
   - What's unclear: Whether all kwargs should be removed in Phase 14 or deferred to a later phase.
   - Recommendation: Phase 14 focuses on the struct and formula changes. Removing solve() kwargs is a separate concern (API cleanup) that may be part of another phase. For Phase 14, the old kwargs that correspond to removed struct fields (`manual_bias`, `manual_bias_factor`) should be removed since their C-level targets no longer exist. But `bias_factor` and `look_ahead_factor` kwargs can remain as they map to the new struct fields.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `cbqs/src/Branching.h`, `Branching.c`, `solver_ctx.h`, `solver_ctx.c`, `solver.c`, `approximate_state_sampler.c`
- Direct codebase analysis: `cbqs/branching.pxd`, `branching.pyx`, `SearchLib.pxd`, `SearchLib.pyx`, `Model.pyx`, `Model.pxd`
- Direct codebase analysis: All test files (`test_branching.c`, `test_solver.c`, `test_integration.c`, `test_local_search.c`, `test_thread_safety.c`, `test_set_param.py`, `test_branching_propagation.py`)
- Direct codebase analysis: `tests/CMakeLists.txt` build configuration
- Phase 12 RESEARCH.md for parameter propagation patterns and architecture context
- Phase 14 CONTEXT.md for locked user decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries/tools already in use in the project, no new dependencies
- Architecture: HIGH -- direct codebase analysis of every file that needs changes, with exact line-level understanding of current behavior
- Pitfalls: HIGH -- identified from specific code paths, memory management patterns, and formula edge cases
- Code examples: HIGH -- based on actual codebase patterns, tested against current formula behavior
- Default values: HIGH -- derived from exact current defaults in Branching.c line 6-21
- Normalization: MEDIUM -- L1 is recommended based on domain analysis, but alternatives exist

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable codebase, internal architecture)
