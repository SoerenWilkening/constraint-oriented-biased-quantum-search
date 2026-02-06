# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** A stable, performant, and correct solver engine that researchers can trust for benchmarking and publishing results.
**Current focus:** v1.1 Bug Fixes & Polish

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-02-06 — Milestone v1.1 started

Progress: [v1.1] 0% (0 plans of 0 total)

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.
v1.1 constraint: No breaking changes (keep deprecated APIs working).

### Pending Todos

None — defining requirements.

### Blockers/Concerns

- GCC 15 compilation: Some type mismatch warnings remain (non-fatal)
- SATISFY mode crashes: run_sampling in SearchLib.pyx calls len() on int when solver == SATISFY
- Module-level cdef for history callback limits concurrent history tracking

## Session Continuity

Last session: 2026-02-06
Stopped at: Milestone v1.1 initialization
Resume file: None
