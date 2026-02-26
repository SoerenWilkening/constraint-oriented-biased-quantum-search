---
phase: quick-3
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [README.md]
autonomous: true
requirements: [quick-3]

must_haves:
  truths:
    - "README example code uses zero-argument solve() with set_param() for configuration"
    - "README example is runnable against current cbqs API"
  artifacts:
    - path: "README.md"
      provides: "Correct example code matching current solve() API"
      contains: "set_param"
  key_links:
    - from: "README.md"
      to: "cbqs/Model.pyx"
      via: "solve() and set_param() API usage"
      pattern: "set_param.*M.*1000"
---

<objective>
Update the README.md example code to match the current cbqs API where solve() accepts zero arguments and all parameters are configured via set_param().

Purpose: The README currently shows `m.solve(M=1000)` which is outdated. Since Phase 15 (solve API migration), solve() takes no arguments -- parameters like M are set via `m.set_param('M', 1000)`.

Output: README.md with correct, runnable example code.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@README.md
@cbqs/Model.pyx (lines 74-124 for _PARAM_DEFS, lines 178-253 for set_param/get_param, lines 396-426 for solve)
</context>

<interfaces>
<!-- Current solve() API from cbqs/Model.pyx -->

solve() signature (line 396):
```python
def solve(self):
    """Solve the optimization or satisfiability problem.

    All solver parameters are configured via set_param() before calling solve().
    solve() accepts zero arguments.

    Returns an OptimizeResult object containing solution, objective,
    timing, history, and verification data.
    """
```

set_param() signature (line 178):
```python
def set_param(self, str name, value):
    """Set a solver parameter by name.

    Parameters persist across multiple solve() calls until changed.
    set_param(name, None) resets the parameter to its default value.
    """
```

Key params relevant to the example:
- 'M': oracle application upper bound (default -1, coerced to int)
- 'stopping_time': time-based stopping (default 30, coerced to int)
- 'num_workers': parallel workers (default 12, coerced to int)

Test examples use this pattern:
```python
m.set_param('stopping_time', 5)
m.set_param('num_workers', 1)
result = m.solve()
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Update README.md example to use current solve() API</name>
  <files>README.md</files>
  <action>
In README.md, replace the example code block (lines 22-34) with the corrected version that uses set_param() instead of passing arguments to solve().

Change FROM:
```python
from cbqs import Model, MAXIMIZE

m = Model()
x = m.add_vars(n) # n variables

m.add_constraint(sum(x[i] * z[i] for i in x) <= Z)
m.set_objective(sum(x[i] * p[i] for i in x), MAXIMIZE)
m.close()
m.solve(M = 1000) # upper bound of 1000 oracle applications

del m
```

Change TO:
```python
from cbqs import Model, MAXIMIZE

m = Model()
x = m.add_vars(n) # n variables

m.add_constraint(sum(x[i] * z[i] for i in x) <= Z)
m.set_objective(sum(x[i] * p[i] for i in x), MAXIMIZE)
m.close()

m.set_param('M', 1000) # upper bound of 1000 oracle applications
m.solve()

del m
```

Key changes:
1. Move the `M=1000` argument from solve() to a set_param() call on its own line
2. Call solve() with no arguments (matches current API)
3. Add a blank line before set_param for readability (separating model setup from solver config)
4. Keep the inline comment explaining what M does, moved to the set_param line

Do NOT change anything else in the README (build instructions, citation, etc.).
  </action>
  <verify>grep -q "set_param.*M.*1000" README.md && grep -q "m.solve()" README.md && ! grep -q "solve(M" README.md && echo "PASS" || echo "FAIL"</verify>
  <done>README example uses m.set_param('M', 1000) followed by m.solve() with no arguments. The old m.solve(M=1000) pattern is gone.</done>
</task>

</tasks>

<verification>
- README.md contains `set_param('M', 1000)` on its own line
- README.md contains `m.solve()` with no arguments
- README.md does NOT contain `solve(M` (old pattern)
- No other content in README.md was changed
</verification>

<success_criteria>
The README example code matches the current zero-argument solve() API. A user copy-pasting the example would get working code against the current cbqs package.
</success_criteria>

<output>
After completion, create `.planning/quick/3-update-example-code-in-readme-md-fix-out/3-SUMMARY.md`
</output>
