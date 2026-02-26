# Phase 21: Build & Packaging - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Eliminate source duplication in setup.py, audit and clean dependencies, gitignore build artifacts, modernize the build configuration, and bump the package version to 2.1.0. This phase delivers a clean, modern build system — no new features or behavioral changes.

</domain>

<decisions>
## Implementation Decisions

### Dependency audit
- Audit ALL install_requires entries for actual usage, not just pandas
- Remove any dependency that isn't imported in runtime code
- Add any missing dependencies that are imported but not declared
- Move test-only and dev-only deps to extras_require (e.g., extras_require["dev"], extras_require["test"])
- Separate optional feature deps into extras_require groups (e.g., extras_require["plot"] for matplotlib if only used in plotting utilities)
- Pin minimum versions (>=X) based on features used — no upper bounds unless known breakage
- Declare build dependencies (Cython, setuptools, etc.) in pyproject.toml [build-system] requires

### Version placement
- Canonical version: `__version__ = "2.1.0"` in the package `__init__.py`
- setup.py dynamically reads __version__ from __init__.py — single source of truth, no manual sync
- pyproject.toml uses `[project] dynamic = ["version"]` to also read from __init__.py
- Both `package.__version__` and `importlib.metadata.version("package")` should return 2.1.0
- Update README version references (badge/number only, no release summary)
- Version number confirmed: 2.1.0 (semver, follows v2.0 from Phase 17)

### Gitignore coverage
- Scope: build artifacts + IDE/editor files + OS files
  - Build: *.so, *.o, *.pyc, __pycache__/, build/, dist/, *.egg-info/
  - IDE: .vscode/, .idea/
  - OS: .DS_Store, Thumbs.db
  - Cython-generated .c files (from .pyx compilation) — treat as build artifacts, ignore
- Remove already-tracked files that match new .gitignore patterns (git rm --cached)
- Clean working tree after a fresh build

### Setup.py restructure
- Full modernization with pyproject.toml + setup.py
- Add pyproject.toml with [build-system] requires and [project] metadata
- Add MANIFEST.in to control source distribution contents (include C sources, headers, .pyx, tests; exclude .planning/, .claude/)
- Update package metadata (author, description, classifiers, URLs, python_requires)
- Enable compiler warnings in Extension build flags (-Wall -Wextra)
- Support wheel builds (bdist_wheel) for binary distribution
- Ensure editable installs (pip install -e .) work cleanly
- Minimum Python version: 3.8+
- C source deduplication approach: Claude's discretion on implementation

### Claude's Discretion
- How to deduplicate C sources in Extension definitions (shared source lists, static library, or other approach)
- Whether to ignore .planning/ directory (evaluate based on project conventions)
- pyproject.toml vs setup.py split for Extension definitions
- Overall file structure and organization of modernized build config

</decisions>

<specifics>
## Specific Ideas

- User wants a fully modern build setup — not just a quick fix but proper modernization
- Build should work for both development (editable install) and distribution (wheels + sdist)
- Dependency groups should be meaningful: core runtime stays lean, optional features and dev tools in extras

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-build-packaging*
*Context gathered: 2026-02-26*
