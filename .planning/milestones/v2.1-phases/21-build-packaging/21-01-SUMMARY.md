---
phase: 21-build-packaging
plan: 01
subsystem: infra
tags: [setuptools, build_clib, pyproject.toml, MANIFEST.in, static-library, Cython]

# Dependency graph
requires:
  - phase: 20-api-consistency
    provides: stable C API with consistent naming conventions
provides:
  - Deduplicated C source compilation via build_clib static library (libcbqs_core.a)
  - Modernized pyproject.toml with dynamic version and full metadata
  - MANIFEST.in for source distribution control
  - Dynamic version reading from cbqs/__init__.py
affects: [21-build-packaging]

# Tech tracking
tech-stack:
  added: [build_clib]
  patterns: [static-library-linking, dynamic-version-from-init]

key-files:
  created: [MANIFEST.in]
  modified: [setup.py, pyproject.toml]

key-decisions:
  - "Used setuptools build_clib to compile 15 C sources into libcbqs_core.a static archive, linked by 5 Cython extensions"
  - "Added sysconfig.get_path('include') to library include_dirs because SearchLib.c includes Python.h"
  - "Expression.c and dyn_expr.c appear in both library and Expression extension (acceptable: library needs them for other extensions, Expression compiles them separately)"
  - "Removed dependencies and optional-dependencies from pyproject.toml to avoid overwriting setup.py install_requires/extras_require"

patterns-established:
  - "Static library pattern: shared C sources compiled once via build_clib, linked into Cython extensions via libraries=['cbqs_core']"
  - "Dynamic version: single source of truth in cbqs/__init__.py, read by both setup.py and pyproject.toml"

requirements-completed: [BUILD-01]

# Metrics
duration: 13min
completed: 2026-02-26
---

# Phase 21 Plan 01: Build Deduplication & Modernization Summary

**Deduplicated C source compilation via build_clib static library with modernized pyproject.toml and MANIFEST.in**

## Performance

- **Duration:** 13 min
- **Started:** 2026-02-26T08:54:27Z
- **Completed:** 2026-02-26T09:08:18Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Eliminated 5x compilation of 15 C source files by using build_clib to create a static archive (libcbqs_core.a) linked by each Cython extension
- Modernized pyproject.toml with dynamic version, full project metadata (author, classifiers, license, URLs), and PEP 621 compliance
- Created MANIFEST.in to control source distribution contents, excluding development files (.planning/, .claude/, venv/)
- Added -Wall -Wextra compiler warnings to catch issues at build time
- Version now single-sourced from cbqs/__init__.py (no hardcoded version in setup.py or pyproject.toml)

## Task Commits

Each task was committed atomically:

1. **Task 1: Deduplicate C sources in setup.py using libraries parameter** - `2d557d4` (feat)
2. **Task 2: Modernize pyproject.toml and create MANIFEST.in** - `64b9534` (feat)

## Files Created/Modified
- `setup.py` - Restructured to use build_clib static library, dynamic version, -Wall -Wextra flags
- `pyproject.toml` - Full PEP 621 metadata, dynamic version, removed hardcoded deps
- `MANIFEST.in` - New file controlling sdist include/exclude rules

## Decisions Made
- **build_clib approach for deduplication:** Used setuptools' `libraries` parameter to compile 15 C sources once into a static archive. This required adding `sysconfig.get_path('include')` because SearchLib.c includes `<Python.h>` which build_clib doesn't provide by default.
- **Expression.c + dyn_expr.c dual placement:** These 2 files appear in both the library and the Expression extension. The library needs them because other C code references Expression symbols. The Expression extension compiles them separately because it doesn't need the full library. This is acceptable (2 extra compilations vs the original 60+ extra).
- **Removed dependencies from pyproject.toml:** Both `dependencies` and `optional-dependencies` were removed because they override setup.py's `install_requires` and `extras_require`, causing setuptools warnings. Plan 21-02 will audit and place final dependency lists.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added Python include path to build_clib library definition**
- **Found during:** Task 1 (static library build)
- **Issue:** SearchLib.c includes `<Python.h>` but build_clib does not automatically include the Python header directory, causing compilation failure
- **Fix:** Added `sysconfig.get_path('include')` to the library's `include_dirs` list
- **Files modified:** setup.py
- **Verification:** Build succeeds, all 384 tests pass
- **Committed in:** 2d557d4 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for build_clib to compile SearchLib.c which depends on Python.h. No scope creep.

## Issues Encountered
- The existing venv had a broken symlink to pyenv Python 3.11 (not available on the build machine). Created a fresh .venv-test with system Python 3.13 for verification. This is an environment issue, not a code issue.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Build system modernized and deduplication complete
- Ready for Plan 21-02 (dependency audit and cleanup)
- MANIFEST.in in place for future sdist/wheel builds

## Self-Check: PASSED

All files verified present. All commit hashes verified in git log.

---
*Phase: 21-build-packaging*
*Completed: 2026-02-26*
