---
phase: 09-satisfy-mode-crash-fixes
plan: 01
subsystem: solver-engine
tags: [satisfy, crash-fix, cython, solver-path, history-callback, verification]
requires: []
provides:
  - "SATISFY mode solver path no longer crashes"
  - "SATISFY-aware objective_value, history callback, verify_solution"
affects:
  - "09-02 (SATISFY mode tests)"
  - "Phase 11 (callback rework)"
tech-stack:
  added: []
  patterns:
    - "SATISFY guard pattern: check mod.mod[0].solver == SATISFY before objective access"
key-files:
  created: []
  modified:
    - cbqs/SearchLib.pyx
    - cbqs/Model.pyx
key-decisions:
  - decision: "objective_value returns None (not 0) in SATISFY mode"
    rationale: "None clearly communicates 'no objective' vs 0 which could be a valid objective value"
  - decision: "Keep import signal in SearchLib.pyx"
    rationale: "May be used elsewhere or by callers; only removed the raise_signal call"
  - decision: "History callback records one entry in SATISFY mode (first callback)"
    rationale: "C callback only fires once when feasibility achieved; None != None is False, so no duplicates"
duration: "4m 32s"
completed: 2026-02-06
---

# Phase 9 Plan 1: SATISFY Mode Crash Fixes Summary

Fixed SATISFY mode crash by removing len() on scalar num_constraints, replacing signal.raise_signal with solver_ctx_request_stop, and adding SATISFY guards to objective_value, history callback, and verify_solution.

## Performance

| Metric | Value |
|--------|-------|
| Duration | 4m 32s |
| Start | 2026-02-06T17:05:00Z |
| End | 2026-02-06T17:09:32Z |
| Tasks | 3/3 |
| Files modified | 2 |
| Build verified | Yes (Cython compilation succeeded) |

## Accomplishments

### CRASH-01: TypeError on len() of scalar
- `num_constraints` is a `uint32_t` scalar in C, not a sequence
- Removed `len()` wrapper: `stpvl = -mod.mod[0].con[0].num_constraints`

### CRASH-02: signal.raise_signal(SIGINT) in SATISFY path
- `signal.raise_signal(SIGINT)` is a process-level signal that kills the entire process
- Replaced with `solver_ctx_request_stop(ctx)` which cooperatively stops the C-level solve loop
- `ctx` was already in scope; `solver_ctx_request_stop` was already declared in `SearchLib.pxd`

### CRASH-03: objective_value meaningless in SATISFY mode
- `tot_profit` in SATISFY mode holds an internal violation-count progress value
- `objective_value` property now returns `None` when `solver == SATISFY`
- `verify_solution` skips objective comparison in SATISFY mode (prevents `abs(None - 0)` TypeError)

### CRASH-04: History callback records meaningless objective in SATISFY mode
- `_history_callback_fn` now sets `obj_val = None` when `solver == SATISFY`
- History tuples maintain consistent format `(iteration, obj_val, elapsed_ms, is_feasible)` with `None` for objective

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix CRASH-01 and CRASH-02 in SearchLib.pyx | dc141eb | cbqs/SearchLib.pyx |
| 2 | Fix CRASH-04 history callback in SearchLib.pyx | f37fe87 | cbqs/SearchLib.pyx |
| 3 | Fix CRASH-03 objective_value and verify_solution in Model.pyx | 3d7d546 | cbqs/Model.pyx |

## Files Modified

| File | Changes |
|------|---------|
| cbqs/SearchLib.pyx | Removed len() on scalar (line 220), replaced signal.raise_signal with solver_ctx_request_stop (line 236), added SATISFY guard to _history_callback_fn (lines 151-154) |
| cbqs/Model.pyx | Added SATISFY guard to objective_value property (lines 468-469), wrapped verify_solution objective block in SATISFY check (line 572) |

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Return None (not 0) for objective in SATISFY mode | None clearly signals "no objective" vs 0 which could be valid |
| Keep `import signal` in SearchLib.pyx | May be used by other code paths or callers |
| One history entry in SATISFY mode | C callback fires once on feasibility; None==None prevents duplicates, which is correct |

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None. All changes were straightforward mechanical fixes. Cython compilation succeeded on first attempt after each task.

## Next Phase Readiness

- **09-02 (SATISFY mode tests):** Ready. The four CRASH bugs are fixed; tests can now exercise the SATISFY solver path end-to-end.
- **Phase 11 (callback rework):** The SATISFY guard in `_history_callback_fn` establishes the pattern that the callback rework must preserve.

## Self-Check

- [x] CRASH-01: No len() on num_constraints scalar
- [x] CRASH-02: solver_ctx_request_stop replaces signal.raise_signal
- [x] CRASH-03: objective_value returns None in SATISFY mode
- [x] CRASH-04: History callback records None objective; verify_solution skips objective check
- [x] Cython compilation succeeds
- [x] Constraint verification in verify_solution still runs in SATISFY mode
