# Codebase Structure

**Analysis Date:** 2026-02-04

## Directory Layout

```
constraint-oriented-biased-quantum-search/
├── cbqs/                       # Main Python/Cython package
│   ├── src/                    # C kernel implementation
│   ├── generators/             # Problem generators
│   ├── Model.pyx               # Core Model class
│   ├── SearchLib.pyx           # Search algorithm wrappers
│   ├── Constraint.pyx          # Constraint container
│   ├── Expression.pyx          # Expression builder
│   ├── state.pyx               # State representation
│   ├── branching.pyx           # Branching strategy
│   ├── state_sampler.pyx       # State sampling
│   ├── StateGenerator.py       # Exact state simulator
│   ├── Constants.py            # Constants (MINIMIZE, MAXIMIZE, SATISFY, OPTIMIZE, etc.)
│   ├── CircuitBackendBinder.pyx # Quantum circuit bindings (unused)
│   ├── Metal_executor.pyx      # macOS Metal GPU executor (unused)
│   ├── __init__.py             # Package exports
│   ├── *.pxd                   # Cython declarations (type signatures)
│   └── __pycache__/            # Generated Python bytecode
│
├── circuit_backend/            # Quantum circuit backend (submodule)
│   ├── Backend/                # Core quantum simulator
│   │   ├── include/            # Header files (QPU.h, gate.h, Integer.h, etc.)
│   │   └── src/                # C implementations
│   ├── Assembly/               # Quantum instruction assembly
│   │   ├── include/
│   │   └── src/
│   ├── Execution/              # Runtime execution
│   │   ├── include/
│   │   └── src/
│   ├── CMakeLists.txt          # Circuit backend build config
│   └── main.c                  # Standalone example
│
├── others/                     # Example problems and benchmarks
│   ├── 2DVBP/                  # 2D Vehicle Routing Problem
│   ├── MaxClique/              # Maximum Clique problem
│   └── bounded_integers/       # Bounded integer constraints
│
├── build/                      # CMake build output directory
├── cmake-build-debug/          # CLion IDE build directory
├── dist/                       # Package distribution files
├── cbqs.egg-info/              # Package metadata
├── venv/                       # Python virtual environment
├── .planning/                  # Planning documents (newly created)
│   └── codebase/               # Architecture analysis
├── setup.py                    # Cython build configuration
├── CMakeLists.txt              # Circuit backend CMake
├── makefile                    # Build convenience targets
├── README.md                   # Project overview
├── LICENSE                     # MIT License
└── .gitignore                  # Version control exclusions
```

## Directory Purposes

**cbqs/:**
- Purpose: Main package directory containing Python/Cython solver implementation
- Contains: API classes (Model, Variable, Expression), algorithm wrappers, C interface declarations
- Key files: Model.pyx (entry point), SearchLib.pyx (search), Constraint.pyx (constraint handling)

**cbqs/src/:**
- Purpose: C kernel implementation (~3400 lines total)
- Contains: Core data structures, constraint evaluation, local search, branching, state manipulation
- Organized by functionality: solver.c (main search), constraint.c (constraint evaluation), local_search.c (neighborhood exploration), Branching.c (bias calculation)

**cbqs/generators/:**
- Purpose: Problem-specific generators for creating test instances
- Contains: `quantum_assembly_ilp_generator.py` - generates quantum assembly format ILP instances

**circuit_backend/:**
- Purpose: Quantum circuit compilation and simulation infrastructure (currently unused per README)
- Contains: Gate operations, arithmetic circuits, assembly language, Metal GPU execution
- Status: Included as Git submodule, compiled but not invoked by current solver

**others/:**
- Purpose: Example problems demonstrating solver usage and benchmarking
- Contains: Three problem categories with respective test runners and analysis scripts
- Key files: `bounded_integers/run.py`, `MaxClique/run_quantum.py`, `2DVBP/run_local.py`

## Key File Locations

**Entry Points:**
- `cbqs/__init__.py`: Package exports (Model, set_seed, Constants)
- `cbqs/Model.pyx`: Main Model class with solve() method
- `setup.py`: Build script defining Cython extension compilation

**Configuration:**
- `setup.py`: Specifies C sources, compiler flags (-O3 -flto -pthread), include directories
- `CMakeLists.txt`: (Unused) Circuit backend configuration
- `makefile`: Convenience targets for build_ext

**Core Logic:**
- `cbqs/Model.pyx`: Problem definition, constraint/objective management, parallel solve dispatch
- `cbqs/SearchLib.pyx`: Main search loop implementation (run_sampling), algorithm selection
- `cbqs/src/solver.c`: Classical and Monte Carlo search algorithms (CSearch_opt, CSearch_sat)
- `cbqs/src/local_search.c`: Neighborhood evaluation and move acceptance (720 lines)
- `cbqs/src/constraint.c`: Constraint parsing, evaluation, preprocessing (682 lines)

**Testing:**
- `others/bounded_integers/test.py`: Unit tests for bounded integer constraints
- `others/bounded_integers/run.py`: Solver benchmark script
- `cbqs/src/test.c`: Unused C test file

## Naming Conventions

**Files:**
- Cython source: `[Name].pyx` (implementation), `[Name].pxd` (declarations)
- C source: `[lowercase_with_underscores].c`, `[lowercase_with_underscores].h`
- Python: `[PascalCase].py` for modules with classes, `[lowercase_with_underscores].py` for utilities

**Directories:**
- Package directories: lowercase (`cbqs`, `circuit_backend`)
- Problem directories: PascalCase or descriptive lowercase (`MaxClique`, `bounded_integers`, `2DVBP`)

**C Data Structures:**
- Struct types: `[name]_t` (e.g., `state_t`, `new_constraints_t`, `model_t`)
- Struct functions: `[action]_[struct_name]` (e.g., `init_state`, `free_constraints`, `copy_state`)

**Cython Classes:**
- Python-visible: PascalCase (Model, Variable, Expression, state_py)
- Internal: lowercase with leading underscore if private conceptually

**Functions:**
- C functions: `snake_case` (update_potentials, constraint_violation, eval_constraints)
- Python/Cython: `snake_case` (add_constraint, set_objective, run_sampling)
- Inline C helpers: `[name]_inline` or static prefix

## Where to Add New Code

**New Constraint Type (e.g., Quadratic Constraints):**
- Primary code: `cbqs/src/constraint.c` (add evaluation logic to eval_constraints)
- Header: `cbqs/src/constraint.h` (extend new_constraints_t struct if needed)
- Cython wrapper: `cbqs/Constraint.pyx` if new Python-accessible methods needed
- Tests: `others/bounded_integers/test.py` or new test module

**New Search Algorithm:**
- Implementation: `cbqs/src/solver.c` (add CSearch_[algorithm_name] function)
- Header: `cbqs/src/solver.h` (declare function)
- Cython dispatch: `cbqs/SearchLib.pyx` (add conditional call in run_sampling)
- Parameter passing: Extend model_t struct in `cbqs/src/model.h` if new parameters needed

**New Branching Strategy:**
- Implementation: `cbqs/src/Branching.c` (modify or add to BranchingFunction or create variant)
- Configuration: `cbqs/branching.pyx` (add wrapper function set_[strategy_name]_wrapper)
- Integration: Model.solve() parameters to expose strategy selection

**New Problem Generator:**
- Location: `cbqs/generators/[problem_name].py`
- Pattern: Import Model and Constants, build expressions, return configured Model instance

**New Example/Benchmark:**
- Location: `others/[problem_name]/run.py`
- Pattern: Import problem generator, instantiate Model, call solve() with parameters, report results

**Utilities (Shared Helpers):**
- Helper functions: `cbqs/StateGenerator.py` (state initialization), or new `cbqs/utils.py`
- Math utilities: `cbqs/src/[utility_name].c` for C-level operations

## Special Directories

**cbqs/__pycache__/:**
- Purpose: Python bytecode cache
- Generated: Yes (automatically by Python)
- Committed: No (excluded by .gitignore)

**build/, cmake-build-debug/, dist/, cbqs.egg-info/:**
- Purpose: Build artifacts and distribution metadata
- Generated: Yes (by setup.py and build tools)
- Committed: No (excluded by .gitignore)

**circuit_backend/:**
- Purpose: Quantum circuit infrastructure (Git submodule)
- Generated: No (manually cloned via git clone --recurse-submodules)
- Committed: As Git submodule pointer

**venv/:**
- Purpose: Python virtual environment
- Generated: Yes (manually created)
- Committed: No (excluded by .gitignore)

**.planning/codebase/:**
- Purpose: Architecture and design documentation
- Generated: Yes (by GSD mapping tools)
- Committed: Yes (documentation for team reference)

## Build and Compilation

**Compilation Entry:** `setup.py`
- Cython compiles `.pyx` files to C
- C compiler combines generated C with hand-written C sources
- Extensions built separately (Model, SearchLib, Constraint, state, branching, etc.) to enable independent compilation

**Include Paths:**
- `cbqs/src/` for solver headers (included in Model, SearchLib, etc. extensions)
- `circuit_backend/Backend/include/` for quantum simulator headers (CircuitBackendBinder extension)
- `circuit_backend/Assembly/include/` for assembly headers

**Compiler Flags:**
- `-O3` for optimization
- `-flto` for link-time optimization
- `-pthread` for threading support
- `-ObjC` flag added for Metal_executor.pyx (macOS only)

## Development Workflow

1. **Modify C code** → Edit `cbqs/src/*.c` or `cbqs/src/*.h`
2. **Modify Cython** → Edit `cbqs/*.pyx` or `cbqs/*.pxd`
3. **Recompile:** Run `python setup.py build_ext --inplace` or `pip install -e .`
4. **Test:** Run `python others/bounded_integers/test.py` or custom test script
5. **Benchmark:** Run example scripts in `others/[problem]/run.py`
