---
phase: 02
plan: 03
subsystem: expression-api
tags: [cython, operators, immutability, copy-semantics]

dependency_graph:
  requires:
    - 02-02 (copy_expression_contents C function)
  provides:
    - Immutable Expression standard operators
    - Deep copy support for Expression objects
    - In-place operators for performance-critical code
  affects:
    - 02-04 (deprecation warnings can reference new behavior)
    - User code using Expression arithmetic

tech_stack:
  patterns:
    - Copy-on-write semantics for numeric types
    - Cython cdef methods for internal operations
    - Python copy module integration (__deepcopy__)

key_files:
  modified:
    - cbqs/Expression.pyx (immutable operators, _deep_copy, __deepcopy__)
    - cbqs/Expression.pxd (copy_expression_contents declaration, _deep_copy declaration)
    - tests/test_expression_py.py (remove xfail, add deepcopy and immutability tests)

decisions:
  - key: "operators-return-new"
    choice: "Standard operators return new Expression via _deep_copy"
    rationale: "Match Python numeric semantics - a + b never modifies a"
  - key: "inplace-operators-mutate"
    choice: "__iadd__, __imul__, __isub__ mutate self and return self"
    rationale: "Performance optimization for code that doesn't need original"
  - key: "deep-copy-uses-c-function"
    choice: "_deep_copy calls copy_expression_contents C function"
    rationale: "Single source of truth for copying, consistent with 02-02"

metrics:
  duration: "6m 14s"
  completed: "2026-02-05"
---

# Phase 02 Plan 03: Expression Immutability Summary

**One-liner:** Immutable operators via _deep_copy, in-place variants for performance, deepcopy integration

## What Was Done

### Task 1: Add copy_expression_contents declaration to Expression.pxd
- Added `copy_expression_contents` C function declaration to extern block
- Added `_deep_copy` cdef method declaration to Expression class

**Commit:** 80cbd93

### Task 2: Add _deep_copy method and __deepcopy__ to Expression class
- Implemented `cdef Expression _deep_copy(self)` using `copy_expression_contents`
- Implemented `def __deepcopy__(self, memo)` for Python copy module integration
- Added `__iadd__` in-place operator for efficient mutation

**Commit:** b79f541

### Task 3: Convert standard operators to return new objects
- Modified `__add__`, `__radd__` to use `_deep_copy` and return new Expression
- Modified `__mul__`, `__rmul__` to use `_deep_copy` and return new Expression
- Added `__imul__` and `__isub__` in-place operators
- Fixed Variable class operators to not mutate Expression arguments

**Commit:** f647619

### Task 4: Update tests (bonus)
- Removed xfail marker from `test_expression_reuse_variable` (bug now fixed)
- Added `test_expression_deepcopy_independence`
- Added `test_expression_inplace_add`
- Added `test_expression_inplace_mul`
- Added `test_expression_mul_immutable`

**Commit:** d602a88

## Verification Results

All verification tests passed:

1. **Build succeeds:** `python3 setup.py build_ext --inplace` completed successfully
2. **Immutability test:** `e1 + 5` no longer mutates `e1`
3. **Deep copy test:** `deepcopy(e1)` creates independent copy

## Key Technical Details

### Operator Semantics (Now)

| Operator | Behavior | Returns |
|----------|----------|---------|
| `e1 + x` | Creates copy, modifies copy | New Expression |
| `e1 * x` | Creates copy, modifies copy | New Expression |
| `e1 += x` | Modifies e1 in place | Same Expression (self) |
| `e1 *= x` | Modifies e1 in place | Same Expression (self) |
| `deepcopy(e1)` | Creates fully independent copy | New Expression |

### Expression.pyx Changes
- Line count: 230 -> 322 lines (+92 lines)
- Added 6 new methods: `_deep_copy`, `__deepcopy__`, `__iadd__`, `__imul__`, `__isub__`
- Modified 4 methods: `__add__`, `__radd__`, `__mul__`, `__rmul__`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added __isub__ in-place operator**
- **Found during:** Task 3
- **Issue:** Plan mentioned __iadd__ and __imul__ but not __isub__; linter added it
- **Fix:** Kept the __isub__ method for completeness
- **Commit:** f647619

**2. [Rule 2 - Missing Critical] Updated test suite**
- **Found during:** Verification
- **Issue:** Test file had xfail marker that needed removal
- **Fix:** Updated tests and added new test cases
- **Commit:** d602a88

## Impact

### Fixed Bug
The Expression mutation bug is now fixed:
```python
x = Variable(0)
e1 = x + 3
e2 = e1 + 5  # Previously corrupted e1, now creates new Expression
# e1 is unchanged: [[3], [1, 0]]
# e2 is new: [[3], [1, 0], [5]]
```

### Migration Path
Existing code that relied on the mutation behavior (unlikely but possible) should:
1. Use in-place operators (`+=`, `*=`) for explicit mutation
2. Or continue using standard operators which now correctly return new objects

## Next Phase Readiness

**Ready for 02-04:** The immutability fix is complete. Deprecation warnings (02-04) can now reference the new behavior and warn users who might be relying on the old mutation semantics.

**Blockers:** None
