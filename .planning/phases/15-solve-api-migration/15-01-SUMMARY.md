---
phase: 15-solve-api-migration
plan: 01
subsystem: api
tags: [cython, set_param, parameter-registry, type-coercion, validation]

# Dependency graph
requires:
  - phase: 14-unified-branching
    provides: "_KNOWN_PARAMS set, set_param/get_param basic API, branching params"
provides:
  - "_PARAM_DEFS registry with 20 params (14 former solve() + 6 branching/config)"
  - "Type coercion on set_param (int, float, bool, str, callable)"
  - "Set-time validation for all params"
  - "_get_effective() helper for solve() internal reads"
  - "get_param() returns defaults for unset params"
affects: [15-02-PLAN, solve-api-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_PARAM_DEFS dict-of-dicts registry pattern for parameter metadata"
    - "_coerce_bool strict coercion (bool/int only, no strings)"
    - "set_param(name, None) resets to default via _params.pop()"

key-files:
  created: []
  modified:
    - cbqs/Model.pyx
    - tests/test_set_param.py

key-decisions:
  - "_PARAM_DEFS registry replaces flat _KNOWN_PARAMS set, with backward-compat derivation"
  - "Strict bool coercion via _coerce_bool rejects strings to prevent bool('False') == True surprise"
  - "get_param returns documented defaults for unset params (never None for params with defaults)"
  - "bias and manual_bias excluded from _PARAM_DEFS (dropped params raise ValueError)"
  - "monte_carlo_estimate is the canonical name (typo monte_calor_estimate rejected)"

patterns-established:
  - "_PARAM_DEFS dict-of-dicts: each entry has default, coerce, validate, validate_msg"
  - "_get_effective(name) reads stored value or default -- single source of truth for solve()"
  - "set_param(name, None) deletes from _params dict, get_param falls through to _PARAM_DEFS default"

# Metrics
duration: 5min
completed: 2026-02-14
---

# Phase 15 Plan 01: Parameter Infrastructure Summary

**_PARAM_DEFS registry with 20 params, type coercion, set-time validation, and default-returning get_param**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-14T20:01:40Z
- **Completed:** 2026-02-14T20:06:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Replaced flat `_KNOWN_PARAMS` set with `_PARAM_DEFS` dict-of-dicts registry containing all 20 params (14 former solve() + 6 branching/config)
- Type coercion, set-time validation, and None-resets-to-default in set_param()
- get_param() returns documented defaults for unset params (never None for params with defaults)
- Added `_get_effective()` helper for Plan 15-02 to use when rewriting solve() internals
- Comprehensive test suite: 94 tests covering coercion, validation, defaults, reset, unknown params, bool strictness, and callback validation

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace _KNOWN_PARAMS with _PARAM_DEFS registry and rewrite set_param/get_param** - `9534fd2` (feat)
2. **Task 2: Update test_set_param.py for expanded parameter infrastructure** - `77313c6` (test)

## Files Created/Modified
- `cbqs/Model.pyx` - Added _coerce_bool, _PARAM_DEFS registry, rewritten set_param/get_param with coercion/validation, _get_effective helper
- `tests/test_set_param.py` - Fixed test_get_param_unset_returns_default, added 8 new test classes (59 new tests)

## Decisions Made
- `_PARAM_DEFS` replaces `_KNOWN_PARAMS` set, with `_KNOWN_PARAMS = set(_PARAM_DEFS.keys())` for backward compat
- Strict bool coercion via `_coerce_bool` (bool and int only) to prevent `bool('False') == True` surprise
- `bias`, `manual_bias` excluded from `_PARAM_DEFS` -- they raise ValueError as unknown params per locked decision
- Phase 14 `bias_factor` (branching 3-term formula weight) kept as valid param -- distinct from removed model_t legacy field
- `monte_carlo_estimate` is the canonical name; old typo `monte_calor_estimate` rejected as unknown

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- _PARAM_DEFS registry complete with all 20 params and their defaults, coercion, and validation
- `_get_effective()` helper ready for Plan 15-02 to use when rewriting solve() internals
- solve() signature is unchanged -- Plan 15-02 will strip kwargs and read from _params
- Full test suite (376 tests) passes, backward compatible

## Self-Check: PASSED

- [x] cbqs/Model.pyx exists
- [x] tests/test_set_param.py exists
- [x] 15-01-SUMMARY.md exists
- [x] Commit 9534fd2 (Task 1) found
- [x] Commit 77313c6 (Task 2) found

---
*Phase: 15-solve-api-migration*
*Completed: 2026-02-14*
