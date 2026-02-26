---
phase: 25-feature-extraction-ml-foundation
plan: 02
subsystem: ml
tags: [feature-extraction, numpy, mip-features, normalization]

requires:
  - phase: 25-01
    provides: cbqs.ml subpackage skeleton with FeatureExtractor stub
provides:
  - FeatureExtractor.extract_variable_features() returning (n_vars, 9) ndarray
  - FeatureExtractor.extract_instance_features() returning (11,) ndarray
  - 9 per-variable features (degree, coeff stats, objective, bounds, integrality, neighbors)
  - 11 instance features (counts, ratios, coefficient stats, bounds tightness)
  - Z-score normalization with zero-variance handling
affects: [26, 27, 28]

tech-stack:
  added: []
  patterns: [expression-term-parsing, per-column-zscore-normalization]

key-files:
  created:
    - tests/test_feature_extraction.py
  modified:
    - cbqs/ml/features.py
    - tests/test_ml_import.py

key-decisions:
  - "Per-column z-score normalization: zero-variance columns set to zero (not NaN)"
  - "Expression terms parsed via _parse_expression_terms helper filtering list items from int sense/rhs values"
  - "Variable features use absolute coefficient values from both constraints and objective"
  - "close(validate=False) needed for testing no-constraint models since Model.close() requires constraints"

patterns-established:
  - "Expression parsing: use _parse_expression_terms() to extract (coeff, var_indices) pairs, filtering sense/rhs ints"
  - "Feature matrix convention: rows in sorted variable index order, columns in VARIABLE_FEATURE_NAMES order"

requirements-completed: [FEAT-01, FEAT-02, FEAT-03]

duration: 10min
completed: 2026-02-26
---

# Phase 25 Plan 02: Feature Extraction Implementation Summary

**FeatureExtractor with 9 per-variable and 11 instance features extracted via Expression iteration protocol with z-score normalization**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-26
- **Completed:** 2026-02-26
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- FeatureExtractor.extract_variable_features() returns (n_vars, 9) ndarray with degree, coefficient stats, objective coefficient, bounds width, integrality flag, neighbor features
- FeatureExtractor.extract_instance_features() returns (11,) ndarray with variable/constraint counts, density ratios, coefficient statistics, bounds tightness
- Per-column z-score normalization handles zero-variance columns safely
- 11 comprehensive tests covering all three FEAT requirements plus edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement FeatureExtractor class** - `d653e28` (feat)
2. **Task 2: Write comprehensive feature extraction tests** - `7fd0372` (test)

## Files Created/Modified
- `cbqs/ml/features.py` - Full FeatureExtractor implementation with _parse_expression_terms helper
- `tests/test_feature_extraction.py` - 11 tests for feature extraction
- `tests/test_ml_import.py` - Updated stub test to match implemented interface

## Decisions Made
- Used close(validate=False) for no-constraint test fixture since Model.close() requires constraints
- Updated test_ml_import.py test_feature_extractor_stub_raises to test_feature_extractor_has_expected_interface since stub is now implemented

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed single_var_model fixture constraint creation**
- **Found during:** Task 2 (test writing)
- **Issue:** Variable <= int not supported; need Expression <= int
- **Fix:** Changed `xs[0] <= 1` to `xs[0] + 0 <= 1` to create Expression first
- **Files modified:** tests/test_feature_extraction.py
- **Verification:** Test passes
- **Committed in:** 7fd0372 (Task 2 commit)

**2. [Rule 2 - Missing Critical] Updated test_ml_import.py for implemented FeatureExtractor**
- **Found during:** Task 2 (test writing)
- **Issue:** test_feature_extractor_stub_raises tested NotImplementedError which no longer applies after implementation
- **Fix:** Renamed to test_feature_extractor_has_expected_interface, checks method/property existence
- **Files modified:** tests/test_ml_import.py
- **Verification:** All 16 tests pass
- **Committed in:** 7fd0372 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
- Model.close() requires at least one constraint (validate=True). Used close(validate=False) for the no-constraint test case.
- Objective expression coefficients are negated after close() (internal solver representation). Using abs() handles this correctly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Feature extraction complete, ready for Phase 26 (Offline Training Pipeline)
- FeatureExtractor produces numpy arrays directly usable by sklearn models
- Expression parsing pattern established for any future model data access

---
*Phase: 25-feature-extraction-ml-foundation*
*Completed: 2026-02-26*
