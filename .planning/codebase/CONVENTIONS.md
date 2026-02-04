# Coding Conventions

**Analysis Date:** 2026-02-04

## Naming Patterns

**Files:**
- Python/Cython files: PascalCase for class modules (e.g., `Model.pyx`, `Constraint.pyx`, `Expression.pyx`)
- C source files: snake_case (e.g., `local_search.c`, `state_sampler.c`, `constraint.c`)
- Header files: snake_case (e.g., `model.h`, `constraint.h`, `state.h`)
- Python utility modules: snake_case (e.g., `state_sampler.pyx`, `Constants.py`)

**Functions:**
- C functions: snake_case (e.g., `init_model()`, `free_constraints()`, `eval_constraints()`)
- Static inline C functions: snake_case (e.g., `move_is_tabu()`, `first_clause_index()`)
- Python methods: snake_case (e.g., `add_variable()`, `add_constraint()`, `set_objective()`)
- Cython methods: snake_case (e.g., `add_expression()`, `eval_con()`, `merge()`)
- Property decorators: snake_case (e.g., `objective_value`, `oracle_calls`, `runtime`)

**Variables:**
- C struct types: snake_case suffix `_t` (e.g., `model_t`, `state_t`, `expression_t`)
- Python instance variables: snake_case (e.g., `self.n`, `self.variables`, `self.constraint`)
- C local variables: lowercase, short names (e.g., `i`, `j`, `count`, `tot`)
- Constants: UPPERCASE (e.g., `MAXIMIZE`, `MINIMIZE`, `SPARSE`, `DENSE`)
- Module-level constants: UPPERCASE from Constants.py (e.g., `OPTIMIZE`, `SATISFY`, `INTEGER`, `MAXCLAUSESIZE`)

**Types:**
- C typedef structs: PascalCase suffix `_t` (e.g., `model_t`, `state_t`, `new_constraints_t`)
- Cython cdef classes: PascalCase (e.g., `Model`, `Expression`, `new_constraint`, `state_py`)
- Cython type declarations: lowercase with `_py` suffix for Python wrappers (e.g., `state_py`)

## Code Style

**Formatting:**
- No enforced formatter detected (no .prettierrc, .black, clang-format config)
- Tab indentation appears in some files, spaces in others
- Lines exceed 100 characters in many files
- Cython files use mixed indentation with Python and C code

**Linting:**
- No linting configuration detected (.eslintrc, .flake8, .pylintrc missing)
- Code follows basic C11 standard (`CMakeLists.txt` specifies `CMAKE_C_STANDARD 11`)
- Compilation flags: `-O3 -flto -pthread` for optimization

**C Compiler Settings:**
- Location: `setup.py` lines 13
- Flags: `["-O3", "-flto", "-pthread"]`
- Language level for Cython: `language_level = 3` (Python 3)

## Import Organization

**Order:**
1. Standard library imports (sys, time, os, etc.)
2. Third-party imports (numpy, pandas, joblib, etc.)
3. Local imports from current package (. relative imports)
4. Cython imports (cimport declarations)

**Examples from codebase:**

Model.pyx (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/Model.pyx` lines 1-22):
```python
from copy import copy
from time import time
from warnings import warn

import numpy as np
from joblib import Parallel, delayed
from .CircuitBackendBinder import circuit
from .Constants import *
from .Expression import Variable
from .Expression cimport Expression
from .state import state_py
from .state cimport init_state
from .Constraint import new_constraint
from .Constraint cimport add_expression_to_constraints, process_constraints
```

StateGenerator.py (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/StateGenerator.py` lines 1-8):
```python
from time import time
import gurobipy as gp
from .state import read_nodes_wrapper, store
from .Constants import OPTIMIZE, SATISFY
from .SearchLib import QSearch_wrapper
from .state import state_py
from copy import copy
import sys
```

**Path Aliases:**
- Relative imports using dot notation: `.Constants`, `.Expression`, `.Model`, etc.
- No alias configuration detected (no tsconfig.json or Python path config)

## Error Handling

**Patterns:**

**C Error Handling:**
- Null pointer checks before dereferencing: `if (mod->manual_bias != NULL)`
- Allocation followed by initialization: `malloc()` then `memset()`/manual init
- Free patterns: Check before freeing: `if (ptr != NULL) free(ptr)`
- Example from `model.c` (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/src/model.c` lines 40-54):
```c
void free_model(model_t *mod){
    if (mod->manual_bias != NULL) free(mod->manual_bias);
    if (mod->initial_state != NULL) free_state(mod->initial_state, 1);
    if (mod->global_opt != NULL) free_state(mod->global_opt, 1);

    if (mod->obj != NULL) {
        free_constraints(mod->obj);
        free(mod->obj);
    }
    if (mod->con != NULL) {
        free_constraints(mod->con);
        free(mod->con);
    }
    free(mod);
}
```

**Python/Cython Error Handling:**
- Type checking with isinstance() for constraint validation
- Exception raising on invalid input: `raise TypeError` when type is invalid
- Example from `Expression.pyx` (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/Expression.pyx` lines 15-26):
```python
def __add__(self, other):
    if isinstance(other, float): raise TypeError("Not allowed type!")
    if isinstance(other, int):
        expr = Expression()
        add_constant(expr.expr, other)
        add_variable(expr.expr, self.index)
        return expr
```

- Assertion-based validation: `assert stopping_condition in [STOPATFIRST, STOPATBEST]`
- Try-except for fallback behaviors (rare):
```python
try:
    return int(res)
except:
    return 0
```

**Cython Error Handling:**
- C pointer validation: `if (ptr is NULL)` before dereferencing
- Resource cleanup via `__dealloc__()` method
- Property getters with fallback: `if self.state is NULL: return "NULL state"`

## Logging

**Framework:** Built-in `print()` function

**Patterns:**
- Direct printf in C code: `printf("Model\n")` and similar debug output
- Python print statements for progress: `print(f"...")` with f-string formatting
- Commented-out print statements throughout codebase for debug info
- Example from test.py (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/others/bounded_integers/test.py` line 65):
```python
def solve(index, k, n):
	print(n)
	# ... lots of print statements for debugging
	print(f"{n},{index},{bound},{-a},{c:.3f},{int(22.5 * 2 * counter[0] * n ** (k / 2))},{k},local-search")
```

**When to Log:**
- Callback outputs during model solving for progress tracking
- Initial state logging in constraint evaluation
- State transitions in search algorithms
- Objective value updates during optimization

## Comments

**When to Comment:**
- Complex algorithm logic (e.g., tabu list management in local_search.c)
- Non-obvious mathematical operations (e.g., quantum amplitude calculations)
- Data structure layout documentation (extensive inline comments in constraint.h)
- Memory management details

**Example from constraint.h** (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/src/constraint.h` lines 13-26):
```c
// create constraint_list in the follwoing way:
//  -> linear implementation of tensor
//  -> given C constraints and m clauses per constraint with k variables per clause
//  -> 1d arrays representing:
//      -> num_clauses: length = C: how many clauses in constraint
//      -> clauses_offset: given C, what is the index of clause cl
//      -> factors: length <= C * m, stores all factors of all clauses in constraints
```

**JSDoc/TSDoc:**
- Not used in this codebase
- Cython docstrings minimal or absent
- Python docstrings present but minimal (e.g., Model.solve() has docstring)

**Example from Model.pyx** (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/Model.pyx` lines 199-205):
```python
def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1, stop_val: int = -1, callback = None,
          max_delta = 7, reset_delta = True, depth_look_ahead = 0, num_workers: int = 12,
          results = "min", bfs = False,
          ignore_constraint_search = False,
          manual_bias: list[float] | None = None,
          bias_factor = 1.,
          manual_bias_factor = 0.,
          look_ahead_factor = 0.,
          monte_calor_estimate = False
          ) -> list | None:
	"""
	:param M:
	:param bias:
	:return:
		returns True if the Algorithm found a satisfying state
	"""
```

## Function Design

**Size:**
- C functions typically short (10-50 lines) with focus on specific tasks
- Python methods range from simple getters (~5 lines) to complex solvers (~20 lines with logic)
- Wrapper functions that bridge C and Python are usually concise

**Parameters:**
- Functions accept positional and keyword arguments
- Type hints used in Python/Cython: `int`, `float`, `list`, `dict`, optional types
- C functions use struct pointers for passing complex data: `model_t *mod`, `state_t *sol`
- Default parameter values common in Python methods
- Example from Model.pyx:
```python
def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1, ...):
```

**Return Values:**
- Python methods return objects (Model instances, lists, dictionaries)
- C functions return primitive types (int, size_t, pointers) or void
- Cython methods often return Cython class instances or None
- Multiple return values via tuple unpacking: `st, it, round = QSearch_wrapper(...)`

## Module Design

**Exports:**
- Main package exports defined in `__init__.py`: `Model`, `set_seed`, and all constants
- Location: `/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/__init__.py`
```python
from .Model import Model, set_seed
from .Constants import *
```

**Barrel Files:**
- Constants.py serves as central import for all constants: `from .Constants import *`
- Cython .pxd files contain type declarations and C bindings

**Module Organization:**
- Core logic in C (src/ directory)
- Python/Cython wrappers bind C functions
- Constants centralized in Constants.py
- Search algorithms (local_search, quantum_search) in separate C modules
- State management abstracted via state_py wrapper class

---

*Convention analysis: 2026-02-04*
