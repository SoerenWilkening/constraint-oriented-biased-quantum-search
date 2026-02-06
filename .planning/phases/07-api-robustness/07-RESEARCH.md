# Phase 7: API Robustness - Research

**Researched:** 2026-02-06
**Domain:** Python API input validation, post-solve solution verification, Cython boundary checks
**Confidence:** HIGH

## Summary

This phase adds input validation and post-solve verification to the CBQS solver API. The solver currently accepts any input without checking validity -- negative variable indices, nonsensical constraint senses, and invalid coefficient values all pass through to the C kernel where they cause silent corruption or crashes. The fix is straightforward: add validation at the Python/Cython layer where users construct objects (Expression, Variable, Constraint, Model), and add an opt-in verification step after solve.

The codebase uses integer arithmetic throughout (`int64_t` for coefficients, `int` for variable indices). NaN and Inf are floating-point concepts that currently trigger `TypeError` because the API rejects `float` types. The decision to use eager validation at construction time means checks are inserted into Expression.pyx (Variable class, operator overloads), Constraint.pyx, and Model.pyx -- not at solve time. Post-solve verification reuses the existing `eval_constraints()` and `objective_value()` C functions already present in constraint.c.

**Primary recommendation:** Implement all validation in the Cython/Python layer (not C), add a `validate=False` parameter to construction methods for bypass, and implement post-solve verification as a Python method on Model that calls existing C evaluation functions through the already-exposed Cython bindings.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `math` module | stdlib | `math.isnan()`, `math.isinf()` checks | Built-in, no deps |
| Python `warnings` module | stdlib | Post-solve violation warnings | Already used in Expression.pyx |
| `pytest` | 7.x+ | Testing validation behavior | Already in test suite |
| `pytest.raises` | -- | Asserting specific exceptions | Standard for validation testing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest.warns` | -- | Testing warning emission | For post-solve verification tests |
| `numpy` | existing dep | Array type coercion checks | Already imported in Model.pyx |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python-level validation | C-level validation | C is faster but error messages harder to format, exceptions harder to raise from C |
| `warnings.warn()` | `logging.warning()` | warnings module is standard for library-to-user communication; logging is for app developers |
| `math.isnan/isinf` | `numpy.isnan/isinf` | math is lighter, numpy already imported but not needed |

## Architecture Patterns

### Recommended Implementation Structure

Validation is added to the **existing** files, not new modules:

```
cbqs/
  Expression.pyx    # Validation in Variable.__init__, operator overloads
  Constraint.pyx    # Validation in new_constraint.add_expression()
  Model.pyx         # Validation in add_variable, add_constraint, set_objective, close
                    # Post-solve verification method
                    # validate=False parameter on construction methods

tests/
  test_validation_py.py    # Input validation tests (RBST-01)
  test_verification_py.py  # Post-solve verification tests (RBST-02)
```

### Pattern 1: Eager Validation at Construction (Locked Decision)

**What:** Validate inputs when Expression, Variable, and Constraint objects are created, not at solve time.
**When to use:** Always -- this is a locked decision from CONTEXT.md.
**Why it fits:** The Variable, Expression, and Constraint classes already raise `TypeError` for float inputs. This extends that pattern.

```python
# In Expression.pyx, Variable class
class Variable:
    def __init__(self, index=0, name="__", lb=0, ub=1, vtype=INTEGER):
        if not isinstance(index, int):
            raise TypeError(f"Variable index must be int, got {type(index).__name__}")
        if index < 0:
            raise ValueError(f"Variable index {index} must be non-negative")
        if ub < lb:
            raise ValueError(
                f"Variable '{name}' has inconsistent bounds: upper ({ub}) < lower ({lb})"
            )
        self.vtype = vtype
        self.index = index
        # ... rest of init
```

### Pattern 2: Coefficient Validation in Operators

**What:** Check for NaN/Inf and reject before passing to C layer.
**When to use:** In all operator overloads that accept numeric input.
**Key insight:** The existing API already rejects `float` with `TypeError`. Coefficients are `int64_t` (64-bit integer). Python integers can be arbitrarily large, but `int64_t` overflows. The NaN/Inf check applies if the user somehow passes a float-like value through numpy or similar.

```python
# In Expression.pyx -- validation helper
import math

def _validate_numeric(value, context=""):
    """Validate a numeric value for use as coefficient or constant."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"NaN/Inf coefficient not allowed{' in ' + context if context else ''}"
            )
        raise TypeError("Float coefficients not allowed; use int")
```

### Pattern 3: validate=False Bypass (Locked Decision)

**What:** Construction methods accept `validate=False` to skip validation.
**When to use:** Performance-critical batch runs where user guarantees valid input.
**Key design choice (Claude's Discretion):** `validate=False` should skip ALL checks, not just expensive ones. Rationale: the checks in this phase are all O(1) per operation, so "expensive" vs "cheap" doesn't really apply. The flag exists for users who need maximum throughput and take responsibility for input correctness.

```python
# In Model.pyx
def add_constraint(self, Expression constraint=None, validate=True) -> None:
    if validate:
        if constraint is None:
            raise ValueError("Constraint expression cannot be None")
        if constraint.sense == -2:
            raise ValueError("Expression has no constraint sense; use <=, >=, or ==")
    expr = constraint
    expr.merge()
    # ... existing C-level calls
```

### Pattern 4: Post-Solve Verification (Locked Decision: Opt-In)

**What:** After solve(), optionally verify that the returned solution satisfies all constraints and has correct objective value.
**When to use:** When user calls `solve(verify=True)` or `model.verify_solution()`.
**Uses existing C functions:** `eval_constraints()` and `objective_value()` in constraint.c are already exposed through Cython.

```python
# In Model.pyx
import warnings

def verify_solution(self):
    """Verify that the current solution satisfies all constraints
    and the reported objective value matches recomputation.

    Returns True if solution is valid, False otherwise.
    Emits warnings on violations but does not raise exceptions.
    """
    if self.final_state is None:
        warnings.warn("No solution to verify (solve() not called)")
        return False

    # Check constraint satisfaction using existing eval_con
    constraints_ok = self.constraint.eval_con(self.final_state)

    # Recompute objective value using existing eval_obj
    recomputed_obj = self.objective.eval_obj(self.final_state)
    reported_obj = self.objective_value

    EPSILON = 1e-9
    obj_ok = abs(recomputed_obj - reported_obj) < EPSILON

    if not constraints_ok:
        warnings.warn(
            "Post-solve verification: solution violates one or more constraints",
            UserWarning, stacklevel=2
        )
    if not obj_ok:
        warnings.warn(
            f"Post-solve verification: reported objective {reported_obj} "
            f"does not match recomputed {recomputed_obj}",
            UserWarning, stacklevel=2
        )

    self._verified = constraints_ok and obj_ok
    return self._verified
```

### Pattern 5: Duplicate Variable Index Merging (Locked Decision)

**What:** When a constraint has duplicate variable indices (e.g., 3*x1 + 5*x1), merge coefficients silently to produce 8*x1.
**Where:** The existing `merge_expression()` C function only merges constants. The merge of duplicate variable terms should happen at the Python/Cython level or by extending merge_expression.
**Key insight:** The existing `merge_expression()` in Expression.c only handles constant terms (len_literal==1). It does NOT merge terms with the same variable set. This must be extended or augmented.

```python
# Approach: augment merge at Python level during add_constraint
# The Expression.merge() call in add_constraint already invokes merge_expression()
# We need to add variable term merging logic
```

### Anti-Patterns to Avoid

- **Validation in C kernel:** Error messages from C are hard to format, can't raise Python exceptions, and the C code shouldn't know about Python semantics.
- **Custom exception classes:** The decision explicitly says use standard `ValueError`/`TypeError`. No `CBQSValidationError`.
- **Collecting multiple errors:** The decision says fail on first error. Don't buffer errors and report them all at once.
- **Raising exceptions from post-solve verification:** The decision says emit warnings and set flags, not exceptions.
- **Validation at solve time:** Eager validation at construction is the locked decision. Don't defer to `solve()` or `close()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NaN/Inf detection | Custom bit-pattern checks | `math.isnan()`, `math.isinf()` | Standard, handles edge cases (signaling NaN, etc.) |
| Constraint evaluation | Custom Python loop over assignments | `eval_constraints()` C function | Already implemented and tested in constraint.c |
| Objective recomputation | Custom Python summation | `objective_value()` C function | Already implemented in constraint.c |
| Warning emission | Custom print-to-stderr | `warnings.warn()` | Filterable, integrates with Python warning system |

**Key insight:** The C kernel already has `eval_constraints()` and `objective_value()` functions, and they are already exposed to Python through the `new_constraint` Cython class (`eval_con`, `eval_obj`). Post-solve verification should call these existing functions, not reimplement evaluation logic.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests with Eager Validation

**What goes wrong:** Adding validation to Variable/Expression constructors breaks existing tests that rely on the current permissive behavior.
**Why it happens:** Existing tests may use edge-case values that would now be rejected.
**How to avoid:**
- Run the full test suite after each validation addition
- Check existing tests for: negative indices, zero-size constructions, etc.
- The existing tests appear clean (test_expression_py.py, test_model_py.py use valid inputs)
**Warning signs:** Existing test failures after adding validation

### Pitfall 2: Comparison Operators Mutating Self

**What goes wrong:** The `<=`, `>=`, `==` operators on Expression currently MUTATE self (they call `multiply_constant(self.expr, -1)` for `>=`). Adding validation to these operators must not interfere with the mutation semantics.
**Why it happens:** These operators were intentionally designed to mutate because they set sense/rhs on the expression. They return `self`.
**How to avoid:** Understand that comparison operators ARE supposed to mutate -- they convert an Expression into a Constraint-expression. Validation should check the RHS value, not prevent mutation.
**Warning signs:** Constraint creation tests failing

### Pitfall 3: Integer Overflow in int64_t

**What goes wrong:** Python integers can be arbitrarily large, but C uses `int64_t`. Passing a Python int larger than 2^63-1 causes silent overflow.
**Why it happens:** Cython doesn't automatically check for overflow when converting Python int to C int64_t.
**How to avoid:** Add a range check for coefficients: `-2^63 <= value <= 2^63-1`
**Warning signs:** Very large coefficients producing wrong solver results

### Pitfall 4: NaN/Inf Check is Redundant for Pure int API

**What goes wrong:** The existing API already rejects `float` with `TypeError("Not allowed type!")`. So NaN and Inf (which are floats) are already rejected.
**Why it happens:** NaN and Inf are IEEE 754 floating-point values. If the API only accepts `int`, they can never be passed.
**How to avoid:**
- Keep the explicit NaN/Inf check for clarity and defense-in-depth (e.g., numpy.int64 or numpy.float64 could sneak through)
- Check for numpy scalar types that might pass isinstance(x, int) but carry float values
- The `isinstance(other, float)` check catches most cases, but `numpy.int64` is NOT a float
**Warning signs:** numpy values passing through without validation

### Pitfall 5: Post-Solve State Access When Solve Not Called

**What goes wrong:** Calling `verify_solution()` or accessing `objective_value` before `solve()` crashes or returns garbage.
**Why it happens:** `self.mod[0].global_opt` is NULL or uninitialized before solve.
**How to avoid:** Check for solve completion (e.g., `self.final_state is None`) before accessing results.
**Warning signs:** Segfault on verification without prior solve

### Pitfall 6: Objective Value Comparison with Integer Arithmetic

**What goes wrong:** Using floating-point epsilon for comparing integer objective values.
**Why it happens:** The decision says "small epsilon (e.g., 1e-9) to handle floating-point drift."
**How to avoid:** The solver uses `int64_t` for all values. The objective_value property returns `self.mod[0].global_opt[0].tot_profit * self.sense` where `self.sense` is -1 or 1. The multiplication is integer. So the comparison should be exact (epsilon=0) for the integer path. However, if future floating-point extensions are added, epsilon protects against that. Use epsilon as decided, but know it's effectively exact for the current int64 arithmetic.
**Warning signs:** Verification false positives/negatives

## Code Examples

### Existing Validation Points (already in codebase)

```python
# Expression.pyx already rejects float:
def __add__(self, other):
    if isinstance(other, float): raise TypeError("Not allowed type!")

# Model.pyx already validates sense:
def set_objective(self, Expression objective=None, sense: int = MAXIMIZE) -> None:
    if sense not in [MINIMIZE, MAXIMIZE]:
        raise TypeError

# Model.pyx already checks compile state:
def solve(self, ...):
    if not self.constraints_compiled:
        raise ValueError("No constraints compiled")
```

### Existing C Evaluation Functions (already exposed)

```python
# Constraint.pyx already exposes evaluation:
class new_constraint:
    def eval_con(self, state: state_py):
        return eval_constraints(&self.con, state.state, state.state[0].vector.bits)

    def eval_obj(self, state: state_py):
        return objective_value(&self.con, state.state)
```

### Variable Index Validation

```python
# In Expression.pyx, Variable class (add to __init__)
class Variable:
    def __init__(self, index=0, name="__", lb=0, ub=1, vtype=INTEGER):
        if not isinstance(index, int):
            raise TypeError(
                f"Variable index must be int, got {type(index).__name__}"
            )
        if index < 0:
            raise ValueError(f"Variable index {index} must be non-negative")
        if not isinstance(lb, int) or not isinstance(ub, int):
            raise TypeError("Variable bounds must be int")
        if ub < lb:
            raise ValueError(
                f"Variable bounds inconsistent: upper ({ub}) < lower ({lb})"
            )
        # ... existing initialization
```

### Model-Level Validation

```python
# In Model.pyx
def add_constraint(self, Expression constraint=None, validate=True) -> None:
    if validate:
        if constraint is None:
            raise ValueError("Constraint cannot be None")
        if constraint.sense == -2:
            raise ValueError(
                "Expression is not a constraint. Apply <=, >=, or == first."
            )
    expr = constraint
    expr.merge()
    add_expression_to_constraints(self.mod.con, <expression_t *> constraint.expr)
    self.constraint.add_expression(expr)
    self.con_expr.append(expr)

def close(self, enforce_density=False, validate=True):
    if validate:
        if self.n == 0:
            raise ValueError("Model has no variables")
        if len(self.con_expr) == 0 and self.mod.solver == SATISFY:
            raise ValueError("Model has no constraints")
    # ... existing compilation
```

### Post-Solve Verification

```python
# In Model.pyx
def verify_solution(self):
    """Check that solution satisfies all constraints and objective matches.

    Returns True if valid, False otherwise.
    Emits UserWarning on violations.
    """
    if self.final_state is None:
        warnings.warn(
            "No solution to verify (solve() has not been called)",
            UserWarning, stacklevel=2
        )
        return False

    verified = True

    # Check constraint satisfaction
    st = self.final_state
    if isinstance(st, list):
        # solve() returns list; use first element or global_opt
        # Access the C-level global_opt state
        pass  # Need to use mod.global_opt directly

    # Use existing C evaluation
    constraints_ok = self.constraint.eval_con(st)
    if not constraints_ok:
        warnings.warn(
            "Post-solve verification FAILED: solution violates constraints",
            UserWarning, stacklevel=2
        )
        verified = False

    # Recompute objective
    recomputed = self.objective.eval_obj(st)
    reported = self.objective_value
    EPSILON = 1e-9
    if abs(recomputed - reported) > EPSILON:
        warnings.warn(
            f"Post-solve verification FAILED: reported objective {reported} "
            f"!= recomputed {recomputed}",
            UserWarning, stacklevel=2
        )
        verified = False

    self._verified = verified
    return verified
```

### Warning Category for Post-Solve Violations (Claude's Discretion)

**Recommendation:** Use `UserWarning` (not a custom subclass). Rationale:
- The decision says "emit Python warning" -- `UserWarning` is the default category
- Researchers can filter with `warnings.filterwarnings('ignore', category=UserWarning)` if needed
- A custom `SolutionViolationWarning(UserWarning)` subclass adds precision but also complexity
- Since this is a research tool, not a production library, `UserWarning` is sufficient

If finer control is desired later, a trivial subclass can be added:
```python
class SolutionViolationWarning(UserWarning):
    """Warning emitted when post-solve verification detects a violation."""
    pass
```

### Epsilon Value for Objective Comparison (Claude's Discretion)

**Recommendation:** `1e-9` as suggested in CONTEXT.md.

Rationale: The solver uses `int64_t` arithmetic internally, so in practice the comparison is exact (integer equality). The epsilon is a safety margin for:
1. The `self.sense` multiplication (`* -1` or `* 1`) which is exact for integers
2. Future extensions that might introduce floating-point
3. Potential Python float conversion during comparison

`1e-9` is small enough to catch any real discrepancy while handling any microscopic floating-point drift in the comparison pathway.

### Implementation Level for Validation (Claude's Discretion)

**Recommendation:** All validation in Python/Cython layer, none in C.

Rationale:
1. All validation checks are O(1) per operation -- no performance concern
2. Python exceptions with formatted error messages are the output format
3. The C kernel uses `int64_t` -- it has no concept of "invalid" beyond what the type system enforces
4. The `validate=False` bypass is trivially implemented with a Python `if` guard
5. The C functions `eval_constraints()` and `objective_value()` for post-solve verification are already C-level -- no need for additional C validation there

### validate=False Scope (Claude's Discretion)

**Recommendation:** `validate=False` skips ALL checks.

Rationale:
1. All validation checks in this phase are O(1) per operation (type check, range check, None check)
2. There are no "expensive" checks to distinguish from "cheap" ones
3. The performance benefit comes from eliminating Python-level branching and function calls in tight loops
4. Simpler semantics: validate=True means "check everything", validate=False means "trust me"
5. Researchers using validate=False are explicitly opting into "I guarantee my input is valid"

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No input validation | Eager validation at construction | This phase | Catches bugs before solve |
| Silent garbage results | Post-solve verification | This phase | Detects solver/encoding bugs |
| `TypeError("Not allowed type!")` | Detailed error messages with context | This phase | Better developer experience |
| No variable bound checking | Bounds validated at Variable creation | This phase | Prevents modeling bugs |

**Deprecated/outdated:**
- Generic `TypeError` messages: Will be replaced with specific, contextual error messages
- `assert results in ["min", "average"]` in solve(): Should become proper ValueError

## Open Questions

1. **solve() return type inconsistency**
   - What we know: `solve()` returns a list of (objective, iterations) tuples. But `self.final_state` is set to `self.global_opt`, which is a Python attribute. The actual state is in `self.mod[0].global_opt` (C-level).
   - What's unclear: How to access the actual solution state for verification -- `self.final_state` may not be a `state_py` after solve (it's set to `self.global_opt` which starts as None).
   - Recommendation: The verification method should access `self.mod[0].global_opt` via a Cython-level helper, or create a `state_py` wrapper around it. Investigate during implementation.

2. **Duplicate variable merging scope**
   - What we know: Decision says merge 3*x1 + 5*x1 -> 8*x1 silently
   - What's unclear: The existing `merge_expression()` only merges constants. Merging variable terms requires sorting and combining terms with identical variable sets.
   - Recommendation: Implement a new `merge_variable_terms()` function or extend `merge_expression()` to handle this. This is a moderate algorithmic task (sort terms by variable indices, then linear scan to combine).

3. **numpy integer types**
   - What we know: `numpy.int64` passes `isinstance(x, int)` in Python 3 (it's a subclass of int)
   - What's unclear: Whether `numpy.float64` or NaN values can sneak through operator overloads via numpy
   - Recommendation: Test with numpy scalars during implementation. The `isinstance(other, float)` check should catch `numpy.float64` since it inherits from `float`.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: Expression.pyx, Constraint.pyx, Model.pyx, SearchLib.pyx
- Codebase analysis: constraint.c (eval_constraints, objective_value functions)
- Codebase analysis: Expression.c, dyn_expr.c (coefficient storage as int64_t)
- Codebase analysis: test_expression_py.py, test_model_py.py, test_constraint_py.py (existing test patterns)
- Python docs: warnings module, math.isnan/isinf

### Secondary (MEDIUM confidence)
- Python docs: isinstance() behavior with numpy scalar types
- Phase 2 research: Expression immutability fix patterns (CORR-04)

### Tertiary (LOW confidence)
- None -- this phase is primarily codebase-internal work with no external library dependencies

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No external libraries needed; all stdlib Python
- Architecture: HIGH - Clear integration points in existing Expression/Constraint/Model classes
- Pitfalls: HIGH - Based on direct codebase analysis of existing patterns and C data types
- Post-solve verification: HIGH - Uses existing eval_constraints/objective_value C functions already exposed via Cython

**Research date:** 2026-02-06
**Valid until:** 2026-03-06 (30 days - stable domain, no external library concerns)
