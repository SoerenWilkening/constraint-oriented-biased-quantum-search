---
phase: 25-feature-extraction-ml-foundation
plan: 01
subsystem: ml
tags: [sklearn, optional-dependency, import-guard, packaging]

requires:
  - phase: 24
    provides: stable v2.1 codebase with pyproject.toml and setup.py
provides:
  - cbqs.ml subpackage with sklearn import guard
  - FeatureExtractor stub class in cbqs.ml.features
  - training.py and adaptation.py stub modules
  - "ml" extra in setup.py for pip install cbqs[ml]
affects: [25-02, 26, 27]

tech-stack:
  added: [scikit-learn>=1.2]
  patterns: [optional-dependency-import-guard, extras-require]

key-files:
  created:
    - cbqs/ml/__init__.py
    - cbqs/ml/features.py
    - cbqs/ml/training.py
    - cbqs/ml/adaptation.py
    - tests/test_ml_import.py
  modified:
    - setup.py

key-decisions:
  - "sklearn import guard in cbqs/ml/__init__.py raises ImportError with pip install instructions"
  - "cbqs/__init__.py left unchanged — ml subpackage is never auto-imported"

patterns-established:
  - "Optional dependency guard: try import sklearn / except ImportError raise with install instructions / from None"
  - "Subpackage re-export: from .features import FeatureExtractor in __init__.py"

requirements-completed: [INTG-01, INTG-02, INTG-03]

duration: 5min
completed: 2026-02-26
---

# Phase 25 Plan 01: ML Subpackage Skeleton Summary

**Optional sklearn dependency wired via extras_require with import guard and stub modules for features, training, and adaptation**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26
- **Completed:** 2026-02-26
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- setup.py extras_require includes "ml" key with scikit-learn>=1.2
- cbqs/ml/__init__.py checks sklearn availability with descriptive ImportError
- FeatureExtractor stub class ready for Plan 02 implementation
- training.py and adaptation.py stubs establish structure for Phases 26-27
- All 5 import isolation tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire optional sklearn dependency and create ml subpackage skeleton** - `8428d1c` (feat)
2. **Task 2: Write import isolation tests** - `26c4e8c` (test)

## Files Created/Modified
- `setup.py` - Added "ml" extra with scikit-learn>=1.2
- `cbqs/ml/__init__.py` - sklearn import guard, FeatureExtractor re-export
- `cbqs/ml/features.py` - Stub FeatureExtractor class with NotImplementedError methods
- `cbqs/ml/training.py` - Phase 26 stub module
- `cbqs/ml/adaptation.py` - Phase 27 stub module
- `tests/test_ml_import.py` - 5 import isolation tests

## Decisions Made
None - followed plan as specified

## Deviations from Plan
None - plan executed exactly as written

## Issues Encountered
- scikit-learn needed to be installed with --break-system-packages flag (PEP 668 environment restriction)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- cbqs/ml/ subpackage skeleton complete, ready for Plan 02 FeatureExtractor implementation
- Import guard verified working in both sklearn-present and sklearn-absent scenarios

---
*Phase: 25-feature-extraction-ml-foundation*
*Completed: 2026-02-26*
