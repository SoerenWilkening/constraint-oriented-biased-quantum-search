# External Integrations

**Analysis Date:** 2026-02-04

## APIs & External Services

**None detected** - This is a scientific computing library with no external HTTP APIs or cloud services.

## Data Storage

**Databases:**
- None - Pure computational library

**File Storage:**
- Local filesystem only - Reads/writes state files to disk
  - State persistence: `cbqs/StateGenerator.py` stores states to `states_1.txt`
  - Example problems in `others/` directory with instance files

**Caching:**
- None built-in

## Authentication & Identity

**Not applicable** - No authentication mechanisms required

## Monitoring & Observability

**Error Tracking:**
- None configured

**Logs:**
- Console output only via C printf and Python print statements
- Timing information captured via `time` module in `cbqs/StateGenerator.py`, `cbqs/Model.pyx`, `cbqs/SearchLib.pyx`

## CI/CD & Deployment

**Hosting:**
- None - Library published via pip/GitHub

**CI Pipeline:**
- None configured (no .github/workflows, no gitlab-ci.yml, etc.)

**Distribution:**
- PyPI package: installed via `pip install` after building from source
- Source repository: GitHub (as indicated by README references to GitHub URLs)

## External Optimizer Integration

**Gurobi Optimizer (Optional):**
- SDK/Client: `gurobipy` Python package
- Location: `cbqs/StateGenerator.py` (exact_simulator class)
- Purpose: Exact state generation and validation for quantum algorithms
- Usage: Creates binary optimization models, solves constraints exactly
- Not required for main solver - used only in state generation path
- Commercial software requiring separate license

## Parallel Processing

**joblib:**
- Package: `joblib` (installed via setup.py)
- Location: `cbqs/Model.pyx` lines 236, 280
- Purpose: Parallel execution of Monte Carlo sampling with threading backend
- Pattern: `Parallel(n_jobs=num_workers, backend="threading")(delayed(...) for ...)`

## Hardware Acceleration

**Metal Framework (macOS only):**
- Framework: Metal (Apple's GPU API)
- Implementation: `cbqs/src/metal_files/exec_metal.m`, `cbqs/Metal_executor.pyx`
- Purpose: GPU acceleration for quantum circuit execution
- Build: Requires `-framework Metal -framework Foundation` linker flags
- Status: Optional, compiled conditionally

## Command-Line Tools

**Remote Synchronization:**
- rsync: Used via makefile for syncing to university server
  - Target: `swilkening@book47.itp.uni-hannover.de:solver/improved_quantum_search`
  - File: `makefile` (push/pull targets)

## Environment Configuration

**Required env vars:**
- None specified - Configuration is code-based

**Secrets location:**
- None required for library itself
- University server credentials in makefile for rsync (not tracked in git)

## Webhooks & Callbacks

**None detected** - Scientific computing library with no callback mechanisms

## Third-Party Circuit Backend

**Git Submodule:**
- Repository: `https://github.com/SoerenWilkening/speed-oriented-quantum-circuit-backend`
- Location: `circuit_backend/` directory
- Cloned with: `git clone --recurse-submodules`
- Status: Included but currently not utilized in main solver (per README)
- Compiles via: `circuit_backend/CMakeLists.txt`

## Data Format Standards

**Binary State Format:**
- Custom C structures for quantum state representation
- State files: Plain text output to disk (`.txt` files)
- No standard serialization (JSON, protobuf, etc.)

---

*Integration audit: 2026-02-04*
