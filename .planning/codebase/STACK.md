# Technology Stack

**Analysis Date:** 2026-02-04

## Languages

**Primary:**
- Python 3.13.7 - Used for API, model definition, and constraint handling
- C (C11/C23) - Core solver engine and quantum search algorithms
- Cython - Bindings between Python and C, wraps performance-critical operations

**Secondary:**
- Objective-C - Metal framework integration for GPU acceleration
- Assembly - Quantum circuit assembly code generation

## Runtime

**Environment:**
- CPython 3.13.7
- Cython (Cythonized extensions for performance)

**Package Manager:**
- pip
- setuptools (with Cython.Build for extension compilation)

**Lockfile:**
- Missing (uses setup.py with install_requires)

## Frameworks

**Core:**
- Cython - Compiles Python to C for performance in `cbqs/Model.pyx`, `cbqs/SearchLib.pyx`, `cbqs/Constraint.pyx`, `cbqs/state.pyx`, `cbqs/state_sampler.pyx`, `cbqs/branching.pyx`
- Gurobi Optimizer (gurobipy) - Optional exact solver for state generation in `cbqs/StateGenerator.py`

**Testing:**
- Not formally configured (no pytest/unittest setup detected)

**Build/Dev:**
- CMake 3.28+ - Builds C executable and circuit backend
- setuptools - Python package build system
- Cython.Build.cythonize - Compiles Cython extensions to C code

## Key Dependencies

**Critical:**
- numpy - Numerical computing, array operations (used in `cbqs/Model.pyx`, `cbqs/SearchLib.pyx`, `cbqs/state.pyx`)
- pandas - Data manipulation (required in setup.py)
- joblib - Parallel execution for multi-worker sampling in `cbqs/Model.pyx` (Parallel, delayed)

**Optional (Commercial):**
- gurobipy - Gurobi Optimizer for exact state generation in `cbqs/StateGenerator.py`

**Build:**
- Cython - Cythonize Python to C extensions

## Configuration

**Environment:**
- No .env files detected
- Configuration via Python module constants (`cbqs/Constants.py`)
- Build flags via setup.py: `-O3` optimization, `-pthread` threading, `-flto` link-time optimization

**Build:**
- `setup.py` - Python package configuration with multiple Cython extensions
- `CMakeLists.txt` - C executable build configuration for standalone solver
- `circuit_backend/CMakeLists.txt` - Quantum circuit backend build

**Key Build Settings:**
- Compiler args: `-O3 -flto -pthread` for all extensions
- Language level: Cython 3
- C standard: C11 (main), C23 (circuit backend)

## Platform Requirements

**Development:**
- Python 3.13.7
- C compiler (gcc or clang with C11/C23 support)
- Objective-C compiler (for Metal executor on macOS)
- CMake 3.28+
- Cython (included via pip install)

**Production:**
- CPython 3.13.7
- Compiled Cython extensions (.so files on Linux/macOS, .pyd on Windows)
- Optional: Gurobi Optimizer license (for exact state generation)
- Optional: Metal framework (macOS only, for GPU acceleration)

## Installation

**From Source:**
```bash
python setup.py build_ext --inplace
# or
pip install .
```

This compiles:
- Main solver module from `cbqs/src/*.c` sources
- Quantum circuit backend from `circuit_backend/*/src/*.c`
- Multiple Cython extensions (Model, SearchLib, Constraint, state, branching, state_sampler, CircuitBackendBinder, Metal_executor, Expression)

## Known Limitations

- Gurobi dependency is optional but used in `cbqs/StateGenerator.py` for exact simulation
- Metal executor requires macOS with Metal framework
- Circuit backend is included but currently not utilized in main solver
- No formal test framework configured

---

*Stack analysis: 2026-02-04*
