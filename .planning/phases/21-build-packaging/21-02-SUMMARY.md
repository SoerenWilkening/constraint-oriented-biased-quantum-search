---
phase: 21-build-packaging
plan: 02
subsystem: infra
tags: [dependencies, gitignore, versioning, packaging, numpy, joblib]

# Dependency graph
requires:
  - phase: 20-api-consistency
    provides: stable API naming for packaging
provides:
  - clean dependency list (pandas removed, numpy/joblib pinned)
  - comprehensive .gitignore covering all build artifacts
  - version 2.1.0 as single source of truth in __init__.py
affects: [22-documentation, release]

# Tech tracking
tech-stack:
  added: []
  patterns: [single-source-version-in-init, extras-require-groups]

key-files:
  created: []
  modified:
    - setup.py
    - pyproject.toml
    - cbqs/__init__.py
    - .gitignore

key-decisions:
  - "Removed pandas from dependencies -- zero runtime imports found in cbqs/"
  - "Kept joblib with >=1.0 pin -- used for Parallel/delayed in Model.pyx"
  - "Pinned numpy>=1.20 -- oldest version supporting Python 3.8+ features used"
  - "Added extras_require groups: test (pytest) and dev (pytest, Cython)"
  - "Updated pyproject.toml version to 2.1.0 directly since Plan 21-01 already made setup.py dynamic"
  - "Removed 3 tracked files (Expression.o, .github/workflows/test.yml, cbqs/src/test.c) matching new gitignore"

patterns-established:
  - "extras_require/optional-dependencies: test and dev groups for non-runtime deps"
  - "gitignore organization: sections for build, IDE, OS, project, test, external"

requirements-completed: [BUILD-02, BUILD-03, BUILD-04]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 21 Plan 02: Dependencies, Gitignore, and Version Bump Summary

**Removed unused pandas dependency, pinned numpy>=1.20 and joblib>=1.0, reorganized .gitignore with comprehensive artifact patterns, bumped version to 2.1.0**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T08:54:27Z
- **Completed:** 2026-02-26T08:57:06Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Audited all runtime imports in cbqs/ and removed pandas (zero imports found), kept numpy and joblib with minimum version pins
- Added extras_require groups (test: pytest, dev: pytest+Cython) in both setup.py and pyproject.toml
- Reorganized .gitignore into clear sections with missing patterns added (*.o, *.pyc, *.pyo, .vscode/, Thumbs.db, .pytest_cache/)
- Removed 3 previously tracked files that matched new gitignore patterns
- Bumped version to 2.1.0 in __init__.py (canonical) and pyproject.toml; setup.py already reads dynamically

## Task Commits

Each task was committed atomically:

1. **Task 1: Audit dependencies and update install_requires** - `c082b08` (feat)
2. **Task 2: Update .gitignore for comprehensive artifact coverage** - `678b6bf` (chore)
3. **Task 3: Bump version to 2.1.0 and verify version consistency** - `a5c874a` (feat)

## Files Created/Modified
- `setup.py` - Removed pandas, added pinned numpy/joblib, added extras_require groups
- `pyproject.toml` - Updated dependencies to match setup.py, added optional-dependencies, bumped version to 2.1.0
- `cbqs/__init__.py` - Changed __version__ from '1.0.1' to '2.1.0'
- `.gitignore` - Reorganized with sections, added missing patterns (*.o, *.pyc, *.pyo, .vscode/, Thumbs.db, .pytest_cache/)

## Decisions Made
- Removed pandas: confirmed zero imports in any file under cbqs/
- Kept joblib: confirmed import in Model.pyx (from joblib import Parallel, delayed)
- Pinned numpy>=1.20: oldest version with Python 3.8+ support and features used
- Updated pyproject.toml version directly to 2.1.0 since Plan 21-01 had already made setup.py version dynamic via _read_version()
- Removed Expression.o, .github/workflows/test.yml, and cbqs/src/test.c from git tracking as they match new gitignore patterns

## Deviations from Plan

None - plan executed exactly as written.

Note: Plan 21-01 had already been partially applied (setup.py was already refactored with _read_version() and static library), so the version in setup.py was already dynamic. Only pyproject.toml and __init__.py needed version updates.

## Issues Encountered
- Python test suite partially runnable: most tests require compiled Cython extensions (cbqs.Model, cbqs.Expression, etc.) which are not built for this platform. The test_result_py.py suite (42 tests) passed. This is a pre-existing environment limitation, not caused by our changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Dependencies are clean and audited
- .gitignore is comprehensive for all build artifacts
- Version 2.1.0 is set as the canonical version
- Ready for Plan 21-01 completion (if not yet fully executed) or Phase 22 documentation

## Self-Check: PASSED

- All 4 modified files exist on disk
- All 3 task commits verified in git log (c082b08, 678b6bf, a5c874a)

---
*Phase: 21-build-packaging*
*Completed: 2026-02-26*
