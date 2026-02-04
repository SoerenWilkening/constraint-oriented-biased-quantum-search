# Architecture

**Analysis Date:** 2026-02-04

## Pattern Overview

**Overall:** Hybrid Python-Cython-C layered architecture implementing a Constraint-Oriented Biased Quantum Search (CBQS) solver for combinatorial optimization problems.

**Key Characteristics:**
- Python API layer (user-facing interface) wraps Cython middleware
- Cython extensions provide efficient bindings to C computation kernels
- Three-layer data model: Python-level Model/Constraint objects → Cython state representations → C structures (new_constraints_t, state_t, model_t)
- Dual-solver support: SAT (constraint satisfaction) and OPTIMIZE (objective function optimization)
- Local search with quantum-inspired branching strategies combined with classical exploration
- Parallelized sampling via joblib for multi-worker exploration

## Layers

**Python API Layer:**
- Purpose: User-facing interface for defining optimization problems, variables, constraints, and objectives
- Location: `cbqs/__init__.py`, `cbqs/Model.pyx` (Python-callable methods), `cbqs/Expression.pyx` (Python Variable class)
- Contains: Model class, Variable class, Constraint wrapper, Constants definitions
- Depends on: Cython modules (state, Constraint, SearchLib, branching)
- Used by: User scripts and applications (example in README.md)

**Cython Middleware Layer:**
- Purpose: Bridge between Python and C, managing memory, calling C functions, wrapping C data structures
- Location: `cbqs/*.pyx` files (Model.pyx, SearchLib.pyx, Constraint.pyx, state.pyx, branching.pyx, etc.)
- Contains: Cython classes (Model, new_constraint, state_py, incumbents) that hold references to C structs and call C functions
- Depends on: C kernel functions and data structures
- Used by: Python API layer for delegating computation

**C Computation Kernel:**
- Purpose: High-performance constraint evaluation, state manipulation, search algorithms
- Location: `cbqs/src/*.c` and `cbqs/src/*.h` files
- Contains: Core data structures (state_t, new_constraints_t, model_t) and algorithms (solver, local_search, branching, constraint evaluation)
- Depends on: Standard C libraries only
- Used by: Cython middleware via C function calls (declared in .pxd files)

**Circuit Backend (Optional, Not Currently Used):**
- Purpose: Quantum circuit compilation and execution (submodule, included but inactive)
- Location: `circuit_backend/Backend/`, `circuit_backend/Assembly/`, `circuit_backend/Execution/`
- Contains: C implementations of quantum gates, integer operations, circuit assembly, and metal execution (macOS)
- Depends on: Hardware-specific implementations (Metal framework for GPU)
- Used by: Not currently utilized but compiled via `setup.py` extension

## Data Flow

**Problem Definition to Solver:**

1. **Model Initialization:** User creates `Model()` instance, initializing empty C `model_t` struct via `__cinit__`
2. **Variable Addition:** `add_variables(n)` creates Python `Variable` objects with indices, increments variable counter
3. **Expression Building:** User builds expressions via operator overloading (Variable + Variable, Variable * int, etc.) creating `Expression` objects wrapping C `expression_t` structs
4. **Constraint Addition:** `add_constraint(Expression)` calls `add_expression_to_constraints()` to append expression to `model_t.con` (constraints) C struct
5. **Objective Setting:** `set_objective(Expression, sense)` appends to both `model_t.obj` and Python `objective` wrapper, sets `model_t.solver = OPTIMIZE`
6. **Close/Compile:** `close()` invokes `preprocessing()` or `preprocessing_sparse()` on constraints based on density, converts to sparse or dense representation
7. **Solve Execution:** `solve(M, bias, ...)` dispatches to parallel workers via joblib, each calling `run_sampling()` with model reference

**Solve Algorithm Flow:**

1. **Initial State Preparation:** `initial_state_preparation(model_t)` performs greedy constraint satisfaction
2. **Search Loop:** Each worker in `run_sampling()` creates `incumbents` object to track candidate states
3. **Amplitude Estimation:** Calls `CSearch_opt_*` or `CSearch_sat_*` Monte Carlo samplers to estimate constraint satisfaction probability
4. **Quantum Iteration Calculation:** Uses estimated amplitude to compute Grover iterations via `emulate_QSearch()`
5. **State Updates:** `accept_move()` evaluates neighbor moves via `local_search.c` functions, accepts improving/feasible states
6. **Global Optimum Tracking:** `global_opt` state updated when better feasible solution found
7. **Result Aggregation:** All worker results merged, best solution returned in `Model.final_state`

**State Management:**

- **Python Level:** `state_py` Cython class wraps C `state_t*`, manages allocation/deallocation, provides Python-level access
- **C Level:** `state_t` struct holds bit vector (variable assignments), objective value (`tot_profit`), feasibility flag, and clause fulfillment tracking
- **Immutability Pattern:** States copied (not modified in-place) via `copy_state()` for thread safety in parallel workers

## Key Abstractions

**Expression (Linear Arithmetic):**
- Purpose: Represents linear constraints/objectives as sums of weighted variables and constants
- Examples: `cbqs/Expression.pyx`, `cbqs/src/Expression.c`
- Pattern: Expression is built via operator overloading (+=, *=), internally stored as sparse list of variable indices with coefficients, can be converted to constraint via comparison operators (<=, >=, ==)

**Constraint Collection (new_constraints_t):**
- Purpose: Store multiple constraints in linearized array format for cache efficiency
- Examples: `cbqs/src/constraint.h` struct definition, `cbqs/src/constraint.c` preprocessing logic
- Pattern: Constraints stored as clause arrays (groups of terms with shared constraint logic), support both dense (matrix-like) and sparse (CSR-like) representations; preprocessing phase determines sparsity and precomputes clause orderings for fast evaluation

**State (state_t):**
- Purpose: Represent a candidate solution (bit assignment to variables)
- Examples: `cbqs/src/state.h`, `cbqs/src/state.c`
- Pattern: Bit vector stores assignments, metadata fields (tot_profit, feasible, clause fulfillment array) support incremental evaluation without re-computing from scratch

**Branching Strategy (BranchingFunction):**
- Purpose: Compute bias probabilities for variable branching decisions combining objective, constraint, lookahead, and base biases
- Examples: `cbqs/src/Branching.h` inline function, `cbqs/branching.pyx` wrapper, `cbqs/src/Branching.c` implementation
- Pattern: Configurable weighted sum of four independent bias factors (objective_factor, constraint_factor, bias_factor, look_factor) normalized via allocation-weighted formula; supports per-variable customization via dependency arrays

**Model Container (model_t):**
- Purpose: Central data structure holding entire problem and solver state
- Examples: `cbqs/src/model.h`, `cbqs/src/model.c`
- Pattern: Stores objective constraints, problem constraints, initial state, global optimum, solver type (SATISFY/OPTIMIZE), parameters (M, stopping_time, max_delta), and biasing configuration; instantiated once per Model object, persists across solve() calls

## Entry Points

**Model.__init__():**
- Location: `cbqs/Model.pyx` line 29-67
- Triggers: User instantiation `m = Model()`
- Responsibilities: Initialize C model_t via `init_model()`, set default solver mode (SATISFY), create empty objective/constraint wrappers, zero variable counter

**Model.solve(M, bias, ...):**
- Location: `cbqs/Model.pyx` line 189-249
- Triggers: `m.solve()` call after close()
- Responsibilities: Validate compilation, set up solver parameters, launch parallel workers via joblib, aggregate results, update Model.final_state with best incumbent

**run_sampling(Model, callback, not_stop):**
- Location: `cbqs/SearchLib.pyx` line 119-150+ (excerpt shown)
- Triggers: Called by each joblib worker thread
- Responsibilities: Initialize thread-local random seed, create working state copy, run main search loop via C function calls (CSearch_opt/sat variants), track incumbent states, return results tuple (final_state, iterations, runtime, incumbent_list)

**initial_state_preparation(model_t):**
- Location: `cbqs/src/solver.c` (called via `cbqs/SearchLib.pyx`)
- Triggers: Called once per solve() if not manually initialized
- Responsibilities: Greedy constraint satisfaction starting from all-zeros state, iteratively sets variables to satisfy most constraints, produces initial feasible or near-feasible solution

## Error Handling

**Strategy:** Validation-first approach with exceptions raised at Python layer for invalid configurations; C layer assumes valid inputs and uses return codes for runtime conditions.

**Patterns:**
- Python layer validates solver type (SATISFY/OPTIMIZE), constraint compilation, parameter ranges before calling C
- Cython `__cinit__`/`__dealloc__` ensure C resources allocated/freed safely
- C functions return int status codes (feasible/not feasible) rather than throwing exceptions
- NULL pointer checks in Cython code for state/constraint results; raise ValueError if NULL returned

## Cross-Cutting Concerns

**Logging:**
- No centralized logging framework; uses printf() in C code for debugging (e.g., `print_state()`, `print_model()`, `print_incumbents()`)
- Python callback mechanism in `SearchLib.pyx` allows user-provided callback() to be invoked during search

**Validation:**
- Expression type checking in Python Variable class (rejects float operations, enforces int/Variable/Expression operands)
- Constraint density threshold check in `close()`: if density > 10%, use dense preprocessing; else sparse
- Solver type assertion in `solve()` with warnings for incompatible parameters (e.g., M parameter ignored for SAT)

**Authentication:** Not applicable (no external services)

**Concurrency:**
- Joblib parallelization with thread backend (not process) to share Model memory
- Each worker maintains independent `incumbents` object tracking candidate states
- Thread-local RNG seeding via `set_seed()` in `run_sampling()`
- Global `python_callback` variable protected by GIL for callback invocation with `with gil:` block

**Memory Management:**
- Cython manages C pointers via deallocation in `__dealloc__` methods
- Manual `free()` calls in `run_sampling()` for intermediate allocations
- State copying via `copy_state()` for thread safety rather than shared mutation
