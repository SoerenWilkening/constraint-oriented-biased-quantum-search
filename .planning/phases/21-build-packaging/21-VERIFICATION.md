---
phase: 21-build-packaging
verified: 2026-02-26T10:30:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 21: Build & Packaging Verification Report

**Phase Goal:** setup.py compiles each C source exactly once, no unused dependencies are declared, build artifacts are gitignored, and the package version reflects v2.1.0
**Verified:** 2026-02-26T10:30:00Z
**Status:** passed
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each C source (solver.c, SearchLib.c, etc.) appears exactly once across Extension definitions -- the 5 core extensions link a static library, not per-extension sources | VERIFIED | `lib_cbqs_core` holds 15 unique sources; 5 extensions use `libraries=['cbqs_core']` in a loop (setup.py lines 93-105); Expression.c/dyn_expr.c dual-placement is an explicitly documented acceptable exception (plan 21-01 key-decisions) |
| 2 | All 5 Cython extensions (Model, SearchLib, state_sampler, state, Constraint) link against `cbqs_core` static library, not re-compiling full sources | VERIFIED | For-loop at setup.py lines 93-105 creates all 5 extensions with `libraries=['cbqs_core']` only; no C sources listed in those Extension constructors |
| 3 | Expression extension compiles Expression.c and dyn_expr.c only (not the full sources list) | VERIFIED | setup.py lines 74-79: `Extension("cbqs.Expression", [Expression.pyx, src/Expression.c, src/dyn_expr.c])` -- no link to cbqs_core |
| 4 | pyproject.toml contains [build-system] requires with Cython>=3.0, setuptools>=45, numpy>=1.20 | VERIFIED | `requires = ["setuptools>=45", "wheel", "Cython>=3.0", "numpy>=1.20"]` confirmed in pyproject.toml line 2 |
| 5 | pyproject.toml contains [project] metadata: name, description, requires-python>=3.8, classifiers, dynamic=["version"] | VERIFIED | All fields present; 12 classifiers; `requires-python = ">=3.8"`; `dynamic = ["version"]` |
| 6 | pyproject.toml does NOT hardcode a version string -- version is dynamic | VERIFIED | `version` key absent from `[project]`; `dynamic = ["version"]` present; `[tool.setuptools.dynamic] version = {attr = "cbqs.__version__"}` links to __init__.py |
| 7 | MANIFEST.in exists and includes C sources, headers, .pyx, .pxd; excludes .planning/, .claude/, venv/ | VERIFIED | MANIFEST.in exists (520 bytes); `recursive-include cbqs/src *.c *.h`; `recursive-include cbqs *.pyx *.pxd *.py`; `prune .planning`, `prune .claude`, `prune venv` all present |
| 8 | setup.py enables compiler warnings (-Wall -Wextra) in extra_compile_args | VERIFIED | `compiler_args = ["-O3", "-flto", "-pthread", "-Wall", "-Wextra"]` at setup.py line 26; applied to all extensions |
| 9 | pandas absent from install_requires and pyproject.toml dependencies | VERIFIED | `grep -c 'pandas' setup.py` = 0; `grep -c 'pandas' pyproject.toml` = 0; pyproject.toml has no `dependencies` key |
| 10 | numpy and joblib present in install_requires with minimum version pins; no undeclared runtime imports | VERIFIED | `install_requires = ["numpy>=1.20", "joblib>=1.0"]`; numpy confirmed in Model.pyx, SearchLib.pyx, state.pyx, result.py; joblib confirmed in Model.pyx |
| 11 | .gitignore covers *.so, *.o, *.pyc, __pycache__/, build/, dist/, *.egg-info/, .vscode/, Thumbs.db, cbqs/*.c | VERIFIED | All 10 required patterns present in .gitignore; cbqs/*.c at line 14, cbqs/generators/*.c at line 15 |
| 12 | cbqs/__init__.py contains `__version__ = '2.1.0'`; version is single source of truth | VERIFIED | `__version__ = '2.1.0'` at cbqs/__init__.py line 12; setup.py reads via `_read_version()`; pyproject.toml reads via `attr = "cbqs.__version__"`; no hardcoded 1.0.1 anywhere |

**Score:** 12/12 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `setup.py` | Deduplicated C sources via build_clib, dynamic version, -Wall -Wextra | VERIFIED | 126 lines; `lib_cbqs_core` static library; `_read_version()` function; compiler_args with -Wall -Wextra; no pandas; numpy/joblib in install_requires |
| `pyproject.toml` | [build-system] requires, [project] metadata with dynamic version, classifiers, URLs | VERIFIED | Valid TOML; complete metadata; `dynamic = ["version"]`; no hardcoded version string; author, license, URLs present |
| `MANIFEST.in` | Include C sources, headers, .pyx, .pxd; exclude .planning/, .claude/, venv/ | VERIFIED | Created in commit 64b9534; all required include/prune rules present |
| `cbqs/__init__.py` | `__version__ = '2.1.0'` | VERIFIED | Line 12: `__version__ = '2.1.0'` |
| `.gitignore` | Comprehensive build artifact coverage with organized sections | VERIFIED | Reorganized in commit 678b6bf; all required patterns present; `cbqs/*.c` covers Cython-generated files |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| 5 core Cython extensions | libcbqs_core.a static library | `libraries=['cbqs_core']` in Extension constructor | WIRED | For-loop creates all 5 extensions with static library link; no C sources re-listed |
| Expression extension | Expression.c + dyn_expr.c only | Direct sources in Extension constructor | WIRED | Extension.pyx + two .c files listed explicitly; `cbqs_core` NOT linked |
| setup.py | cbqs/__version__ | `_read_version()` parsing __init__.py | WIRED | `_read_version()` at lines 14-20; `version=_read_version()` at line 112 |
| pyproject.toml | cbqs.__version__ | `[tool.setuptools.dynamic] version = {attr = "cbqs.__version__"}` | WIRED | pyproject.toml line 34 correctly points to package attribute |
| .gitignore | Cython-generated .c files | `cbqs/*.c` pattern | WIRED | Line 14: `cbqs/*.c`; covers all Cython-transpiled C files in the package directory |
| install_requires | Actual runtime imports | numpy/joblib audit against cbqs/ | WIRED | numpy: Model.pyx, SearchLib.pyx, state.pyx, result.py; joblib: Model.pyx; pandas: zero imports (removed) |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BUILD-01 | 21-01-PLAN.md | setup.py source duplication eliminated (each C source compiled once) | SATISFIED | 15 sources in `lib_cbqs_core` static library; 5 extensions use `libraries=['cbqs_core']`; Expression uses only its 2 direct sources; all commit 2d557d4 |
| BUILD-02 | 21-02-PLAN.md | pandas dependency verified and removed if unused | SATISFIED | Zero pandas imports in cbqs/; removed from install_requires; numpy>=1.20 and joblib>=1.0 pinned; commit c082b08 |
| BUILD-03 | 21-02-PLAN.md | Stray build artifacts cleaned and .gitignore updated | SATISFIED | .gitignore reorganized with 10+ required patterns; `git ls-files -i --exclude-standard` returns no tracked files matching new patterns; 3 previously-tracked files removed (commit 678b6bf) |
| BUILD-04 | 21-02-PLAN.md | Package version updated to 2.1.0 | SATISFIED | `__version__ = '2.1.0'` in __init__.py; setup.py reads dynamically; pyproject.toml uses `attr = "cbqs.__version__"`; no hardcoded 1.0.1 anywhere; commit a5c874a |

All 4 requirement IDs from PLAN frontmatter accounted for. No orphaned requirements found for Phase 21 in REQUIREMENTS.md.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| setup.py | 41-42 | Expression.c and dyn_expr.c appear in lib_cbqs_core AND in Expression extension | Info | Documented intentional exception: library needs these for symbol resolution; Expression extension compiles them directly. 2 extra compilations vs original 60+. Explicitly recorded in 21-01-SUMMARY.md key-decisions. |

No blocker or warning anti-patterns found. The Expression.c/dyn_expr.c dual-placement is a documented, intentional architectural decision.

---

## Human Verification Required

### 1. Editable install succeeds

**Test:** Run `pip install -e .` in the project root
**Expected:** Build completes successfully, extensions compile without errors, package importable
**Why human:** Requires Cython compiler, C compiler, and Python.h headers on the test machine. The SUMMARY documents that the test venv used system Python 3.13 due to a pyenv symlink issue.

### 2. Full Python test suite passes after build

**Test:** After editable install, run `pytest tests/ -x -q`
**Expected:** All tests pass (SUMMARY reports 384 tests passing in 21-01)
**Why human:** Requires compiled extensions; cannot run without a built package.

### 3. importlib.metadata.version('cbqs') returns '2.1.0'

**Test:** After install: `python -c "from importlib.metadata import version; print(version('cbqs'))"`
**Expected:** `2.1.0`
**Why human:** Requires actual package installation to populate metadata registry.

---

## Gaps Summary

No gaps found. All 12 observable truths are verified, all 4 requirement IDs are satisfied, all key links are wired, and all artifacts are substantive. The phase goal is fully achieved:

- C source deduplication: 15 sources compiled once into `libcbqs_core.a` static archive; 5 extensions link against it
- Unused dependencies: pandas removed (zero runtime imports confirmed); numpy>=1.20 and joblib>=1.0 kept and pinned
- Build artifact gitignore: all required patterns present; no tracked files match new patterns
- Version v2.1.0: single source of truth in `cbqs/__init__.py`; both setup.py and pyproject.toml read dynamically

Three items are flagged for human verification (install, test suite, metadata version) because they require a compiled build environment.

---

_Verified: 2026-02-26T10:30:00Z_
_Verifier: Claude (gsd-verifier)_
