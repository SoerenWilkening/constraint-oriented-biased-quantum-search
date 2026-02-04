# Phase 1: Test Foundation - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish a CMocka test suite and pytest suite that validates core solver correctness in the C kernel and Cython/Python bindings. This provides a safety net for all subsequent phases. No bug fixes or new features -- only test infrastructure and test cases.

</domain>

<decisions>
## Implementation Decisions

### Test scope & coverage
- Broad but shallow: at least one test per major C function to catch regressions everywhere
- Both C-level (CMocka) and Python-level (pytest) tests -- test the C kernel directly AND the Cython bindings
- Write known-bug tests as expected-failure tests (visible in output, marked as expected-to-fail, don't break the suite) -- Phase 2 will make them pass
- Claude analyzes codebase to determine which functions are most critical to test first
- Skip edge cases for now -- focus on happy-path correctness
- No existing tests to formalize -- building from scratch

### Test organization
- All tests in `tests/` directory at project root
- One-to-one mapping: test_constraint.c tests constraint.c, test_model.c tests model.c, etc.
- Python tests use pytest, living in same `tests/` directory alongside C test files (distinguished by extension)

### Build & run integration
- CMake for C test compilation (CMakeLists.txt in tests/)
- Separate commands for C and Python tests (no single `make test` that runs both)
- ASan is opt-in via `-DASAN=ON` flag (not default)
- GitHub Actions CI workflow that runs tests on push

### Known-problem test cases
- User has specific optimization problems as Python scripts that construct models using the cbqs API
- User will provide these during implementation
- Integration tests verify feasibility only (all constraints satisfied) -- do not check objective quality (solver is heuristic)

### Claude's Discretion
- Python test scope (whether to test full Model API or just Expression/Constraint wrappers)
- Exact CMocka test structure and fixture patterns
- Which C functions to prioritize based on codebase analysis
- GitHub Actions workflow configuration details

</decisions>

<specifics>
## Specific Ideas

- Known-bug tests should document which roadmap bug they target (e.g., "CORR-02: use-after-free in accept_best_routine")
- Problem instances for integration tests come from existing Python scripts in the repo that the user will identify during implementation

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 01-test-foundation*
*Context gathered: 2026-02-04*
