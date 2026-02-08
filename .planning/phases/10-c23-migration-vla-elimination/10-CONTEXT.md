# Phase 10: C23 Migration & VLA Elimination - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Clean GCC 15 compilation with zero warnings and eliminate all VLAs from C source. Replace deprecated patterns (bool macros, old-style function declarations) with C23-forward-compatible equivalents. No behavioral changes — all existing tests must pass unchanged.

</domain>

<decisions>
## Implementation Decisions

### VLA replacement strategy
- Use arena allocation as the primary replacement for VLAs, matching existing v1.0 patterns
- Exception: VLAs under ~64 bytes in hot paths with provably bounded max size may use fixed-size stack buffers
- Arena lifetime: match whatever pattern v1.0 already uses — do not introduce new lifetime semantics

### Warning suppression policy
- Enable `-Werror` in CI only (not local development builds)
- Add `-Wpedantic` alongside `-Wall -Wextra` for strictest standard compliance
- Cython-generated C files: suppress warnings per-file using `#pragma` (these are outside our control)
- Unused parameters: use `__attribute__((unused))` — wrapped in a portability macro for MSVC (see compiler scope)
- Sign comparison warnings: fix by changing variable types to match signedness (not casts)
- `stdbool.h` migration: include `stdbool.h` first in our headers; remove all `#define true/false` macros
- `callback_t` typedef: update to explicit `(void)` parameter list — only `callback_t`, not all typedefs
- Implicit function declarations: Claude decides per-site whether to add missing includes or forward declarations

### Compiler support scope
- Must support Windows/MSVC in addition to GCC/Clang on Linux/macOS
- Need a portability macro for `__attribute__((unused))` (e.g., `CBQS_UNUSED`) that maps to `__attribute__((unused))` on GCC/Clang and the MSVC equivalent
- Minimum GCC version, C standard version, and Clang support: Claude's discretion based on what the codebase actually needs and what the changes require

### Claude's Discretion
- VLA regression guard (compiler flag like `-Wvla` or CI grep check)
- Minimum GCC version to support
- C language standard to target (`-std=c11`, `-std=c17`, or `-std=c23`)
- Whether to also ensure Clang warning-free compilation
- Per-site choice of include vs forward declaration for implicit function warnings
- Portability macro implementation details

</decisions>

<specifics>
## Specific Ideas

- "Include stdbool.h first" — user wants our headers to establish bool before third-party headers
- MSVC support is required — all GCC-specific attributes need portability wrappers
- `-Wpedantic` explicitly requested for strictest compliance
- `-Werror` in CI only — developers shouldn't be blocked by warnings during active development

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-c23-migration-vla-elimination*
*Context gathered: 2026-02-08*
