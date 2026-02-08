# Phase 13: Dead Code & Documentation Cleanup - Research

**Researched:** 2026-02-08
**Domain:** Codebase hygiene (C, Cython, CMake, CI)
**Confidence:** HIGH

## Summary

This phase is a pure cleanup pass: remove dead code, guard or remove unguarded debug output, replace any bare `except` clauses with specific exception types, and add read/write field annotations to major solver functions. The research involved a complete sweep of every source file in the project.

Key findings: (1) There is substantial commented-out code across local_search.c, Branching.c, solver.c, state.c, quantum_search.c, and Expression.pyx. (2) There are many **unguarded** `printf` calls in production C code (progress indicators in constraint.c, Expression.c, solver.c, SearchLib.c) and `print()` calls in Model.pyx that should be either removed or guarded behind `CBQS_DEBUG`. (3) The bare `except:` clause issue (CLEAN-03) appears to already be resolved -- all except clauses in .pyx files now specify `Exception`. (4) The `model_t` struct has 23 fields, and the `local_search()` function and related functions use specific subsets that need documenting.

**Primary recommendation:** Work file-by-file in a systematic sweep, starting with the C kernel (largest concentration of dead code and unguarded prints), then Cython layer, then build/CI. Run full test suite after each file to ensure no behavioral changes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Active unguarded debug printf/print statements: remove or guard behind CBQS_DEBUG (not just commented-out ones)
- Stale #ifdef/#ifndef blocks: clean up preprocessor guards for conditions that no longer apply
- Check ALL Cython files (.pyx) for bare excepts, not just Model.pyx
- Production code only -- leave test file bare excepts alone
- Silent exception handling preserved -- just specify the type, don't add logging
- Header comment table format above each function: "Reads: field1, field2 | Writes: field3, field4"
- Include mutex protection notes -- mark which writes are mutex-protected vs. unprotected
- Annotate local_search() plus other major solver functions (sampling_solver(), preprocessing(), etc.)
- Full codebase sweep: all .c, .h, .pyx, .py, CMake, and CI config files
- CMake/CI cleanup included: remove stale targets, outdated workarounds, unused variables in build configs
- Minor style fixes allowed when encountered during cleanup (but no wholesale reformatting)

### Claude's Discretion
- Whether specific commented-out code blocks are "dead code" or "intentional reference notes"
- Which unused functions/variables to remove vs. keep
- Exception type narrowness per catch site
- Flat vs. semantic grouping for field annotation tables
- Which style inconsistencies warrant fixing vs. leaving alone
- Preserving TODO/FIXME comments and intentional notes vs. removing dead code

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

This phase involves no new libraries or tools. It uses the existing project tooling:

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| gcc/clang | System | Compile after removing dead C code | Already configured |
| Cython | 3.x | Compile .pyx files after cleanup | Already configured |
| pytest | System | Verify no behavioral regressions | Already in CI |
| CMake | >= 3.14 | Build system for C test targets | Already configured |
| CMocka | 1.1.7 | C unit test framework | Already FetchContent'd |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| grep/rg | Find remaining dead code patterns | Verification pass |
| ASan/Valgrind | Ensure no memory regressions from removals | CI validation |

## Architecture Patterns

### Systematic Sweep Order

The cleanup should follow dependency order to avoid merge conflicts:

```
1. C kernel (cbqs/src/)          -- deepest layer, most dead code
2. Cython middleware (cbqs/*.pyx) -- depends on C layer
3. Python API (cbqs/*.py)        -- depends on Cython
4. Build system (CMakeLists.txt) -- configuration layer
5. CI config (.github/)          -- validation layer
```

### Pattern: Guard Debug Output Behind CBQS_DEBUG

The project already has `CBQS_DEBUG` infrastructure in `solver_ctx.c` and `solver_ctx.h`. The `ctx->debug_enabled` field is set from `getenv("CBQS_DEBUG")` at context creation time.

For C code where a solver_ctx_t is available:
```c
/* Guard behind debug flag */
if (ctx != NULL && ctx->debug_enabled) {
    fprintf(stderr, "debug info: %d\n", value);
}
```

For C code where no context is available (e.g., preprocessing, print_* diagnostic functions), there are two options:
1. **Remove** the printf if it's purely progress output that clutters production use
2. **Guard** behind a direct `getenv("CBQS_DEBUG")` check if the output has diagnostic value

Recommendation: Progress-bar-style `printf("\r%f %%", ...)` calls should be **removed** (they are UI noise, not debug data). Diagnostic `print_*` functions (like `print_model`, `print_state`, `print_new_constraint`) should be **kept as-is** since they are explicitly called functions, not implicit debug output.

### Pattern: Field Annotation Comment Format

Use a header comment block above each function:
```c
/*
 * Reads:  con->num_constraints, con->num_clauses[], mod->distance,
 *         mod->stopping_time, mod->stop_val, mod->max_worse_acceptances,
 *         mod->stopping_condition
 * Writes: mod->runtime (unprotected),
 *         mod->global_opt->tot_profit (mutex-protected via update_lock),
 *         mod->global_opt->vector (mutex-protected via update_lock),
 *         mod->global_opt->feasible (mutex-protected via update_lock)
 */
```

Grouping: Use flat list when <= ~8 fields per category. Use semantic grouping (by struct) when more.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Debug output infrastructure | New debug macro system | Existing `ctx->debug_enabled` and `CBQS_DEBUG` env var | Already implemented in Phase 3 |
| Exception type analysis | Guessing exception types | Read Cython/Python docs for what each operation raises | Specificity prevents swallowing unexpected errors |

## Common Pitfalls

### Pitfall 1: Removing Code That Looks Dead But Is Compiled Conditionally
**What goes wrong:** Code behind `#ifdef` or platform-specific paths gets removed but was actually used on other platforms.
**Why it happens:** The Metal/GPU code is macOS-only; the `setup.py` conditionally includes it.
**How to avoid:** Only remove dead code from the non-platform-specific core. The `Metal_executor.pyx` file and its `exec_metal.h`/`.m` files should be left alone for platform-specific dead code.
**Warning signs:** `#ifdef __APPLE__` or `sys.platform == "darwin"` guards.

### Pitfall 2: Removing Commented-Out Code That Documents Algorithmic Intent
**What goes wrong:** Commented-out alternative algorithm implementations serve as documentation for researchers.
**Why it happens:** In research code, commented alternatives show failed approaches or design decisions.
**How to avoid:** Use the "nothing sacred" attitude from CONTEXT.md -- it's in git history. But preserve short inline comments that explain *why* something was done a certain way.
**Warning signs:** Comments with algorithmic explanations (e.g., "// for tabu moves: if better than global opt: accept").

### Pitfall 3: Breaking Behavioral Semantics When Removing Debug Prints
**What goes wrong:** Some `printf("\r")` calls clear progress output and affect terminal behavior during legitimate use.
**Why it happens:** Progress bars using `\r` are embedded in production paths like `preprocessing()` and `add_expression_to_constraints()`.
**How to avoid:** The progress-bar printfs are in `preprocessing()` (constraint.c line 147, 186), `add_expression_to_constraints()` (constraint.c line 383, 408), `merge_expression()` (Expression.c line 41, 53), and `initial_state_preparation()` (solver.c line 175). These are **production code paths** that run during model setup. They should either be removed entirely or guarded behind CBQS_DEBUG.
**Warning signs:** `printf("\r%f %%"...)` pattern.

### Pitfall 4: Double-Declaring `compare()` in Multiple Headers
**What goes wrong:** The `compare()` function is declared in both `state.h` and `SearchLib.h` but appears to be unused (no callers found).
**Why it happens:** Legacy code that was replaced by inline comparisons.
**How to avoid:** Remove from both headers and from `state.c`. Verify no callers exist first.

## Code Examples

### Dead Code Inventory: local_search.c

Commented-out code blocks that should be removed:

```c
// Line 50: printf("move is tabu\n") -- commented-out debug print
// Lines 56-69: aspiration() function -- entire function commented out
// Lines 182-183: VLA code -- int64_t steps[C]; memset(steps, 0, ...)
// Lines 233-240: adjusted_constraint_violation calls -- commented-out alternative algorithm
// Lines 254: printf for violation -- commented out
// Lines 258: printf for feasibility -- commented out
// Lines 266, 270, 275, 293: stopping_criterion = 1 -- commented out
// Lines 286: objective_value_improved call -- commented out
// Lines 309: progress update -- commented out
// Lines 453: aspiration call -- commented out
// Lines 460-461: progress thread join -- commented out
// Lines 488-489: aspiration + accept_move -- commented out
// Lines 540-542: VLA remainings[C] -- commented out
// Lines 545-546: printf -- commented out
// Lines 550-556: printf loop for move list -- commented out
// Lines 566-567: clock_gettime -- commented out
// Lines 583-585: printf for callback/state/newline -- commented out
// Lines 587-588: printf for acceptance stats -- commented out
// Lines 775: printf M value -- commented out
// Lines 798-804: printf loops -- commented out
// Lines 860: printf global opt -- commented out
// Lines 863: printf total time -- commented out
// Lines 883-885: state swap -- commented out
// Lines 891-899: trailing data comment block -- dead output data
```

### Dead Code Inventory: Branching.c / Branching.h

```c
// Branching.c lines 48-97: Entire old BranchingFunction() -- commented out, replaced by inline version in header
// Branching.c line 101: printf for bias -- commented out
// Branching.c lines 111-130: printf debug output in StateProbability -- commented out
// Branching.c line 136: printf for bias in updated() -- commented out
// Branching.h lines 44, 48, 69, 77, 84, 88, 96: commented-out alternative formulas
// Branching.h lines 110-112: TODO comment about other branching rules
```

### Dead Code Inventory: solver.c

```c
// Line 40: printf for sparsity/item -- commented out
// Lines 63-65, 70-72: old function signature -- commented out
// Line 98: printf newline -- commented out
// Line 117: printf for potential inaccuracies -- commented out
// Line 125: return value comment -- commented out
// Line 175: UNGUARDED printf progress bar in initial_state_preparation
// Line 176: printf for bit check -- commented out
// Line 192: printf for counts -- commented out
// Lines 269, 288: printf lines -- commented out
// Lines 343, 346-348, 350-351, 359, 368: commented-out ChangedTerms code
// Line 654: printf for samples -- commented out
// Line 729: printf for estimate -- commented out
```

### Dead Code Inventory: constraint.c

```c
// Line 147: UNGUARDED printf progress bar in preprocessing()
// Line 186: UNGUARDED printf "\r" in preprocessing()
// Line 280: printf progress -- commented out
// Line 342: printf "\r" -- commented out
// Line 383: UNGUARDED printf progress in add_expression_to_constraints()
// Line 408: UNGUARDED printf "\r" in add_expression_to_constraints()
// Line 527: Old function signature comment -- commented out
// Line 572: printf for sparsity -- commented out
// Lines 595-596, 600, 606, 610, 613: commented-out realloc/changes tracking code
```

### Dead Code Inventory: Expression.c

```c
// Line 41: UNGUARDED printf progress in merge_expression()
// Line 53: UNGUARDED printf "\r" in merge_expression()
```

### Dead Code Inventory: SearchLib.c

```c
// Line 80: UNGUARDED printf "counts = ..." in bfs()
// Line 90: commented-out copy_state
// Lines 98, 134, 158: commented-out printf
// Lines 321-323: commented-out monte carlo code block
```

### Dead Code Inventory: quantum_search.c

```c
// Line 39: commented-out printf in amplitude_amplification
// Lines 55-58: commented-out print loop in QSearch
```

### Dead Code Inventory: state.c

```c
// Line 94: commented-out calloc (replaced by init_large_state)
// Line 105: commented-out printf for file
// Lines 123-124, 126-127: commented-out printf/code
// Line 140: commented-out realloc
// Line 145: commented-out printf
// Lines 155-179: Entire old updated() function -- commented out
```

### Dead Code Inventory: Model.pyx

```c
// Line 99: commented-out gpu_executor type hint
// Line 118: commented-out runtime
// Line 122: commented-out objective_value
// Lines 197, 284-286: commented-out print/code blocks
// Line 279: commented-out initial_state line
// Line 306-307: commented-out sparsity/print lines
// Line 498: UNGUARDED print(state) in approximate_benchmarking
// Lines 539-542: UNGUARDED print statements in solution property
```

### Dead Code Inventory: Expression.pyx

```c
// Lines 150-151: print statements in __str__ -- these are intentional (implementing __str__)
// Lines 182-183: commented-out print_expression calls in mul_expr
// Lines 370-378: commented-out potential calculation in __eq__
```

### Dead Code Inventory: state.pyx

```c
// Lines 49-50: commented-out __del__
// Lines 90, 93-94, 96-97, 98, 101, 105-106: commented-out print/debug
```

### Dead Code Inventory: Constraint.pyx

```c
// Lines 1-2: commented-out function wrapper
// Lines 12, 54: commented-out print statements
```

### Dead Code Inventory: state_sampler.pyx

```c
// Line 3: commented-out import
```

### Dead Code Inventory: SearchLib.pyx

```c
// Lines 321-323: commented-out monte carlo estimation block
```

### Unused Functions/Variables

| Item | Location | Status |
|------|----------|--------|
| `compare()` | state.c:9, state.h:15, SearchLib.h:32 | Defined and declared but never called -- remove |
| `bfs()` | SearchLib.c:59 | Defined, declared in SearchLib.h:36 -- contains unguarded printf, unclear if used from Cython |
| `objective_value_improved()` | constraint.c:627 | Defined but only called from commented-out code -- likely dead |
| `print_status()` / `dat_t` | local_search.c:155-171 | Progress bar thread code, never started (creation commented out at line 360) |
| Old `BranchingFunction` | Branching.c:48-97 | Commented-out version, replaced by inline in header |
| `test.c` | cbqs/src/test.c | Standalone test file compiled by root CMakeLists.txt -- may be stale |

### Field Access Analysis: local_search()

```c
/*
 * local_search(ctx, cur_sol, mod, callback)
 *
 * Reads:  cur_sol->vector.bits,
 *         mod->con->num_constraints, mod->con->num_clauses[],
 *         mod->obj->num_clauses[],
 *         mod->distance, mod->stopping_time, mod->stop_val,
 *         mod->max_worse_acceptances, mod->stopping_condition,
 *         mod->global_opt (passed to accept_best_routine)
 *
 * Writes: mod->runtime (unprotected -- written each iteration),
 *         mod->global_opt->tot_profit (mutex-protected via update_lock trylock),
 *         mod->global_opt->vector (mutex-protected via update_lock trylock),
 *         mod->global_opt->feasible (mutex-protected via update_lock trylock),
 *         cur_sol->vector (unprotected -- single-thread ownership),
 *         cur_sol->tot_profit (unprotected),
 *         cur_sol->feasible (unprotected)
 */
```

### Field Access Analysis: ctg() (sampling_solver)

```c
/*
 * ctg(ctx, mod, cur_sol, callback, incumbents)
 *
 * Reads:  mod->obj->num_clauses[], mod->con->num_constraints,
 *         mod->solver, mod->M, mod->depth_look_ahead,
 *         mod->stopping_time, mod->stop_val,
 *         mod->ignore_constraint_search, mod->con->sense[],
 *         cur_sol->vector.bits, cur_sol->tot_profit, cur_sol->feasible
 *
 * Writes: mod->qtg_applications (unprotected -- single-thread per ctx),
 *         mod->runtime (unprotected),
 *         mod->global_opt->tot_profit (mutex-protected via update_lock),
 *         mod->global_opt->vector (mutex-protected via update_lock),
 *         mod->global_opt->feasible (mutex-protected via update_lock),
 *         cur_sol->tot_profit (unprotected -- thread-local),
 *         cur_sol->vector (unprotected),
 *         cur_sol->branch (unprotected),
 *         cur_sol->feasible (unprotected),
 *         incumbents->states[], incumbents->head, incumbents->search_stage[],
 *         incumbents->initial_samples[]
 */
```

### Field Access Analysis: preprocessing()

```c
/*
 * preprocessing(n, con)
 *
 * Reads:  con->num_constraints, con->num_clauses[], con->clause_length[],
 *         con->variables[], con->factors[]
 *
 * Writes: con->sparsity, con->positive_indices, con->negative_indices,
 *         con->positive_offsets, con->negative_offsets,
 *         con->num_positive_indices, con->num_negative_indices,
 *         con->positive_array_length, con->negative_array_length,
 *         con->array_length
 *         (All unprotected -- called during single-threaded model setup)
 */
```

### Field Access Analysis: initial_state_preparation()

```c
/*
 * initial_state_preparation(mod)
 *
 * Reads:  mod->initial_state->vector.bits, mod->con->num_constraints,
 *         mod->con->rhs[], mod->depth_look_ahead,
 *         mod->obj (for objective_value)
 *
 * Writes: mod->initial_state->tot_profit (unprotected),
 *         mod->initial_state->vector (unprotected),
 *         mod->initial_state->branch (unprotected),
 *         mod->initial_state->feasible (unprotected),
 *         mod->break_item (unprotected),
 *         mod->global_opt->tot_profit (unprotected),
 *         mod->global_opt->vector (unprotected),
 *         mod->global_opt->feasible (unprotected)
 *         (All unprotected -- called during single-threaded setup before solve)
 */
```

### CMake/CI Findings

**Root CMakeLists.txt:**
- `metal_test` target: Only relevant on macOS. Not stale, but only buildable on macOS.
- `iqs/src` include directory: References a directory `iqs/src` that does not appear to exist in the project tree. This is a stale include path.
- The main executable target uses `test.c` which is a standalone test driver that duplicates what the proper CMocka test suite does. This could be considered stale.

**tests/CMakeLists.txt:**
- Clean and well-organized. No stale targets found.
- All test targets have proper dependency lists.

**CI config (.github/workflows/test.yml):**
- Clean and current. All jobs reference valid test targets.
- The `ASAN_OPTIONS` comment references "Phase 5" which is fine for historical context.
- No stale workarounds or unused variables.

**setup.py:**
- `sources_circuit` list (lines 16-35): Defines source files for a `CircuitBackendBinder` extension but the extension is not actually added to the `extensions` list. This is dead code in the build config (the files it references are in a `circuit_backend` directory that may or may not exist).
- `pandas` in `install_requires` (line 90): pandas is listed as a dependency but does not appear to be imported anywhere in the codebase. This may be dead.

### Bare Except Analysis

**Current state:** No bare `except:` clauses exist in any .pyx file. All catch sites in production Cython code already use `except Exception:`. CLEAN-03 appears to already be satisfied from prior phases.

Specific except clauses found in production .pyx files:
- `SearchLib.pyx:177` -- `except Exception:` (in `_history_callback_fn`)
- `SearchLib.pyx:183` -- `except Exception:` (in `_history_callback_fn`)

Both are already correctly typed. No changes needed for CLEAN-03 unless we want to narrow them further (e.g., `except AttributeError` where applicable).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global BranchingStats | Per-context branching_stats in solver_ctx_t | Phase 3/12 | Old global functions deprecated, still present |
| VLAs in local_search.c | Arena + heap allocation | Phase 5/6 | Old VLA code is commented out but still present |
| Bare `except:` | `except Exception:` | Phase 7 | Already migrated |
| Module-level callback state | Per-thread `_SolveState` dict | Phase 4 | Old global cdef globals removed |

## Open Questions

1. **`bfs()` function in SearchLib.c**
   - What we know: It has an unguarded printf and is declared in SearchLib.h. It does not appear to be called from any Cython code.
   - What's unclear: Whether it's used by any external consumer or is completely dead.
   - Recommendation: Check if any Cython .pxd file declares it; if not, it's dead and should be removed.

2. **`objective_value_improved()` in constraint.c**
   - What we know: It's defined and has a declaration in constraint.h. All call sites are commented out.
   - What's unclear: Whether it will be needed for future optimization work.
   - Recommendation: Remove. It's in git history if needed later.

3. **`sources_circuit` in setup.py**
   - What we know: It defines circuit backend source files but isn't used in any Extension.
   - What's unclear: Whether the circuit backend directory exists on the developer's machine.
   - Recommendation: Remove the unused list variable. The `CircuitBackendBinder` import in `__init__.py` already has a try/except for graceful failure.

4. **`pandas` dependency in setup.py**
   - What we know: Listed in install_requires but no import found.
   - What's unclear: Whether it's used in user scripts or optional features.
   - Recommendation: Flag for removal but verify with the user first. Could be deferred.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all .c, .h, .pyx, .py, CMakeLists.txt, and .yml files
- Line-by-line reading of local_search.c, Model.pyx, Expression.pyx, solver.c, constraint.c, Branching.c, SearchLib.c, state.c, solver_ctx.c
- grep/glob searches for printf, print, except, #ifdef patterns

### Secondary (MEDIUM confidence)
- CBQS_DEBUG infrastructure from Phase 3 documentation and solver_ctx.c implementation

## Metadata

**Confidence breakdown:**
- Dead code inventory: HIGH -- Every source file was read line by line
- Unguarded printf locations: HIGH -- Exhaustive grep with manual verification
- Bare except status: HIGH -- Grep confirmed no bare excepts in .pyx files
- Field access annotations: HIGH -- Traced through local_search(), ctg(), preprocessing(), initial_state_preparation()
- CMake/CI analysis: HIGH -- Both CMakeLists.txt files and CI config read completely
- Unused function analysis: MEDIUM -- grep for callers may miss dynamic dispatch or macro-generated calls

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (stable codebase, no external dependency changes)
