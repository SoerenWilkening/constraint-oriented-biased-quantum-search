# Codebase Concerns

**Analysis Date:** 2026-02-04

## Tech Debt

**Incomplete Branching Rules Implementation:**
- Issue: Only default branching function implemented; TODO comment indicates missing alternative branching strategies
- Files: `cbqs/src/Branching.h` (line 102-103)
- Impact: Limited ability to tune search heuristics for different problem classes; users stuck with single branching strategy
- Fix approach: Implement alternative branching rules mentioned in TODO (e.g., impact-based, activity-based); add parameter to Model.solve() to select branching strategy

**Global Variable State in Branching:**
- Issue: `BranchingStats` declared as global variable instead of encapsulated in model/solver context
- Files: `cbqs/src/Branching.h` (line 26)
- Impact: Thread-safety issues in parallel solving; state pollution between multiple model instances; side effects make testing difficult
- Fix approach: Encapsulate BranchingStats in solver_t or pass as function parameters; refactor setup_factors/set_bias functions to use context instead of globals

**Bare Except Clause:**
- Issue: Bare `except:` without exception type specification
- Files: `cbqs/Model.pyx` (line 257)
- Impact: Silently catches and hides all exceptions including KeyboardInterrupt, SystemExit; masks bugs and makes debugging difficult
- Fix approach: Replace with `except Exception:` to allow critical signals; log caught exceptions; refactor loop logic to use explicit condition

**Commented-Out Debug Code:**
- Issue: Multiple print statements and debugging logic left commented throughout codebase
- Files: `cbqs/Model.pyx` (lines 100-102, 162-164), `cbqs/Expression.pyx` (lines 108-109), `cbqs/src/local_search.c` (line 280)
- Impact: Code maintainability; unclear intent (debug code or intentional comments?); creates merge conflict potential
- Fix approach: Remove all commented debug code; add proper logging framework (e.g., Python logging module) for diagnostics

**Direct Signal Interruption in Solver:**
- Issue: `signal.raise_signal(signal.SIGINT)` called directly in solver loop to stop parallel execution
- Files: `cbqs/SearchLib.pyx` (line 184)
- Impact: Unsafe interrupt handling; may leave threads in inconsistent state; can cause data corruption in parallel solvers
- Fix approach: Use proper thread-safe stopping mechanism (e.g., atomic boolean flag in shared context, like `not_stop[0]` already used elsewhere)

## Known Bugs

**Incomplete API Migration in Model.local_search():**
- Symptoms: Function signature mismatch between implementation and call site
- Files: `cbqs/Model.pyx` (lines 262-276)
- Trigger: Calling `m.local_search()` with distance parameter
- Workaround: Method exists but recent refactoring (commit 741e97f, line 265 changed `self.initial_state` to `self.initialized`) suggests incomplete migration to new C API that passes full model_t structure to SearchLib functions
- Status: Bug fix commit (741e97f) attempted to fix initialization check but underlying API design appears unfinished

**MAXCLAUSESIZE Constraint Change:**
- Symptoms: Unexpected behavior changes in constraint processing
- Files: `cbqs/Constants.py` (line 21), `cbqs/src/Expression.h` (line 10)
- Trigger: Constraint processing with more than 2 variables per clause
- Status: Recent change from MAXCLAUSESIZE=2 to MAXCLAUSESIZE=4 (commit 741e97f) without explanation or test updates; may have upstream effects on branching factor calculations

## Memory Management

**Potential Memory Leak in Move List Generation:**
- Issue: `move_list()` allocates memory for move flips but cleanup path not visible in main code
- Files: `cbqs/src/local_search.c` (lines 72-100)
- Impact: Local search may leak memory on long runs or repeated calls
- Current state: Move structures allocated but freeing logic (`free_move_list()` if exists) not found in SearchLib.pyx

**NULL Pointer Dereference Risk in SearchLib:**
- Issue: Multiple places where state pointers could be NULL without defensive checks
- Files: `cbqs/src/SearchLib.c` (lines 76-80)
- Impact: Segmentation faults under edge cases (empty solution sets, early termination)
- Fix approach: Add explicit NULL checks before dereference; use assertions in debug mode

## Thread Safety Issues

**Unprotected Global State Access:**
- Issue: `BranchingStats` accessed without synchronization across multiple threads in `run_sampling()`
- Files: `cbqs/SearchLib.pyx` (lines 119-238), `cbqs/src/Branching.h`
- Impact: Race conditions when multiple solver threads update bias/factors simultaneously (Parallel n_jobs=12 default)
- Current lock mechanism: `pthread_mutex_t update_lock` exists in `SearchLib.c` but only protects specific state updates, not all global accesses
- Fix approach: Extend mutex protection to all BranchingStats reads/writes or pass stats per-thread

**Python Callback in Nogil Context:**
- Issue: `python_callback` global variable passed to C functions with `nogil` context
- Files: `cbqs/SearchLib.pyx` (lines 112-124, 159-160, 177-178)
- Impact: May cause GIL deadlocks or memory corruption if C code modifies Python state
- Current state: Code uses `with gil:` guard in callback but call sites don't hold GIL during potential callback invocation
- Fix approach: Ensure GIL held during callback execution; document callback safety constraints

## Scaling Limits

**Fixed Thread Count in Local Search:**
- Issue: `NUMThreads` hardcoded constant in local_search.c
- Files: `cbqs/src/local_search.c` (line 282)
- Limit: Cannot scale local search to systems with more threads than NUMThreads
- Scaling path: Make thread count configurable via model->num_workers; dynamically allocate thread array

**Constraint Processing Memory Usage:**
- Issue: Full constraint matrix materialized in memory during processing
- Files: `cbqs/src/constraint.c` (various matrix operations)
- Current capacity: Works for mid-size problems but large instances may exhaust memory
- Scaling path: Implement lazy/sparse constraint evaluation; support iterative refinement instead of full enumeration

## Fragile Areas

**Expression Multiplication in Constraint Generation:**
- Files: `cbqs/Expression.pyx` (lines 105-110), `cbqs/src/Expression.c`
- Why fragile: Recursive expression multiplication can create deeply nested structures; no depth limit; multiply_expressions() algorithm could explode in complexity
- Safe modification: Add depth limit; implement expression flattening/normal form conversion before operations
- Test coverage: No visible unit tests for expression operations; only system tests in others/bounded_integers/test.py

**Model Constraint Compilation:**
- Files: `cbqs/Model.pyx` (lines 174-182), `cbqs/Constraint.pyx`
- Why fragile: `close()` must be called before `solve()` but only checked by exception; multiple implicit state transitions (initialized → constraints_compiled); no explicit state machine
- Safe modification: Add state enum (NOT_INITIALIZED, OPEN, COMPILED, SOLVING); enforce state transitions; return False from solve() if not compiled instead of raising
- Test coverage: Minimal; test.py doesn't verify error conditions for skipping close()

**State Probability Calculation:**
- Files: `cbqs/src/Branching.h` (lines 99, 180)
- Why fragile: `StateProbability()` called but implementation not visible; depends on external state comparison logic
- Safe modification: Inline implementation or document exact interface contract; add bounds checking on probability values (0-1 range)

## Test Coverage Gaps

**No Unit Tests for Core Components:**
- What's not tested: Individual C functions (BranchingFunction, constraint evaluation, local_search moves)
- Files: `cbqs/src/*.c` (all files)
- Risk: Regressions in low-level algorithms go undetected; bug fix commits (741e97f) not validated with test suite
- Priority: High - quantum search correctness depends on these algorithms

**No Integration Tests for Parameter Sensitivity:**
- What's not tested: How changes to MAXCLAUSESIZE, bias_factor, look_ahead_factor affect solution quality and convergence
- Files: Entire solver pipeline
- Risk: Tuning parameters (commit 741e97f changes) may have unintended side effects
- Priority: Medium - affects reproducibility of research results

**No Regression Tests for Parallel Solver:**
- What's not tested: Thread-safety of parallel sampling; behavior with different num_workers values
- Files: `cbqs/SearchLib.pyx`, `cbqs/src/SearchLib.c`
- Risk: Race conditions and crashes under specific thread scheduling may only appear in production
- Priority: High - parallel execution is primary use case

**No Memory Leak Tests:**
- What's not tested: Long-running solver instances; repeated model creation/deletion
- Files: Model lifecycle and memory management
- Risk: Memory leaks only visible after hours of computation or across many benchmark runs
- Priority: Medium - matters for large benchmark studies

## Performance Bottlenecks

**Constraint Evaluation in Hot Loop:**
- Problem: Full constraint checks on every state evaluation during branching
- Files: `cbqs/src/SearchLib.c` (in ctg() solver loop)
- Cause: No caching of constraint results; redundant evaluations for similar states
- Improvement path: Implement constraint cache keyed by state signature; invalidate on state changes; batch constraint checks

**Expression Multiplication Complexity:**
- Problem: Quadratic expression size growth during constraint compilation
- Files: `cbqs/Expression.pyx` (mul_expr), `cbqs/src/Expression.c` (multiply_expressions)
- Cause: No simplification/reduction of intermediate expressions
- Improvement path: Implement expression normal form (CNF/DNF); simplify during multiplication; early termination for unsatisfiable expressions

**Memory Allocation in Main Loop:**
- Problem: malloc/free calls in hot path during state search
- Files: `cbqs/src/local_search.c` (move generation), `cbqs/src/SearchLib.c` (state copying)
- Cause: State objects copied frequently; move lists regenerated for each neighbor
- Improvement path: Use memory pool allocators; pre-allocate move lists; use stack allocation for temporary states

## Security Considerations

**No Input Validation on User-Supplied Data:**
- Risk: Users can create Models with negative coefficients, extremely large bounds, invalid sense values without checks
- Files: `cbqs/Model.pyx` (add_variable, set_objective, add_constraint methods)
- Current mitigation: Python type hints provide some safety but no runtime validation
- Recommendations: Add explicit bounds checking; validate coefficient ranges; sanitize user callbacks

**Signal Handling Vulnerability:**
- Risk: Arbitrary signal injection via solve() could be exploited to interrupt other threads/processes
- Files: `cbqs/SearchLib.pyx` (line 184)
- Current mitigation: None - signal raised unconditionally
- Recommendations: Replace with thread-safe stopping mechanism (already partially implemented via not_stop list); remove signal.raise_signal entirely

**Unchecked Callback Execution:**
- Risk: User-provided Python callback called from C code; callback could raise exceptions or corrupt state
- Files: `cbqs/SearchLib.pyx` (lines 112-127), callback invocation throughout solver
- Current mitigation: `with gil:` context guard but insufficient
- Recommendations: Document callback contract strictly; catch and handle callback exceptions; pass read-only state snapshot to callback

## Missing Critical Features

**No Solution Validation:**
- Problem: solve() returns solution but no guarantee of constraint satisfaction or objective correctness
- Blocks: Research reproducibility; debugging of solver bugs; performance benchmarking accuracy
- Recommendation: Implement post-solve validation; check all constraints; verify objective value against ground truth

**No Hot-Start/Warm-Start Support:**
- Problem: Must start from scratch each solve() call; cannot provide initial solution hint
- Blocks: Incremental solving; parameter tuning; use of multiple solver stages
- Recommendation: Add initial_solution parameter to solve(); precompute initial state bounds

**No Solution Statistics/Diagnostics:**
- Problem: solve() returns only final solution; no intermediate improvement trajectory, oracle call breakdown, constraint satisfaction details
- Blocks: Algorithm analysis; debugging; performance comparison with other solvers
- Recommendation: Return structured Result object with timing breakdown, constraint violations, improvement history

---

*Concerns audit: 2026-02-04*
