# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v2.1 — Code Audit & Optimization

**Shipped:** 2026-02-26
**Phases:** 7 | **Plans:** 14 | **Sessions:** ~4

### What Was Built
- Dead code elimination across all 3 language layers (C/Cython/Python)
- Incremental constraint evaluation in local_search with benchmark infrastructure
- Unified API naming (look_ahead_factor) across C/Cython/Python with full _PARAM_DEFS audit
- Modernized build system: build_clib deduplication, pyproject.toml PEP 621, MANIFEST.in
- Complete docstring coverage (NumPy-style) for all public Python methods
- C kernel algorithm documentation (branching formula, preprocessing, look-ahead, local search)
- VERIFICATION.md for all 7 phases confirming 18/18 requirements

### What Worked
- Dead code removal first created a stable baseline for all subsequent phases — no regressions from field removal
- Incremental evaluation adoption was straightforward because prepare_constraints() and adjusted_constraint_violation() already existed in constraint.c — just needed wiring
- Phase ordering (dead code → incremental → API → build → docs) avoided rework — each phase built on the previous
- Milestone audit before completion caught 2 gap-closure phases (23, 24) that would have been missed
- VERIFICATION.md files provide clear audit trail for requirement satisfaction

### What Was Inefficient
- Phase 20 ROADMAP entry was not updated during execution (still showed "TBD" plans) — required post-hoc correction
- Some phase SUMMARY.md files lacked `requirements-completed` frontmatter (convention introduced late in Phase 23)
- INCR-01 benchmark before-state timing was not captured at execution time — methodology for regeneration documented but not ideal
- Phase 24 (verification) could have been done incrementally per-phase rather than as a batch at the end

### Patterns Established
- `requirements-completed` frontmatter in SUMMARY.md files for traceability
- VERIFICATION.md as mandatory per-phase artifact
- Milestone audit → gap closure phases → re-audit → archive workflow
- build_clib pattern for C source deduplication across multiple Cython extensions
- NumPy-style docstrings as standard format for Python public methods

### Key Lessons
1. Always capture before-state measurements before making changes (benchmark baselines, test counts, etc.)
2. Phase verification should happen per-phase, not batched — prevents accumulation of verification debt
3. Milestone audits are valuable pre-completion gates — caught real gaps in this milestone
4. API renames need to propagate to test files in the same phase, not as a follow-up

### Cost Observations
- Model mix: 100% opus (quality profile)
- Sessions: ~4 (two for phases 18-21, one for 22, one for 23-24 + audit + completion)
- Notable: 7 phases in 2 days — cleanup/audit work is faster than feature development

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~6 | 8 | Established test foundation, solver_ctx_t architecture |
| v1.1 | ~3 | 5 | Bug fixes, C23 migration, callback rework |
| v2.0 | ~2 | 4 | First breaking release, unified branching model |
| v2.1 | ~4 | 7 | Milestone audit workflow, VERIFICATION.md standard |

### Cumulative Quality

| Milestone | Tests | Audit Score | Tech Debt Items |
|-----------|-------|-------------|-----------------|
| v1.0 | 258+ | 15/15 | 6 (0 blockers) |
| v1.1 | 304+ | 21/21 | 3 (0 blockers) |
| v2.0 | 446 | 17/17 | 2 (0 blockers) |
| v2.1 | 446 | 18/18 | 5 (0 blockers) |

### Top Lessons (Verified Across Milestones)

1. Foundational cleanup before behavior changes prevents cascading regressions (v1.0 tests-first, v2.1 dead-code-first)
2. Breaking changes are better done in dedicated milestones with clear migration paths (v2.0)
3. Milestone audits catch gaps that phase-level work misses (v2.1 caught 2 gap-closure phases)
4. Incremental progress with frequent verification beats large batched changes (all milestones)
