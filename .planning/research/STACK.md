# Stack Research

**Domain:** C/Cython/Python solver optimization and stabilization
**Researched:** 2026-02-04
**Confidence:** HIGH (most tools verified via official docs and multiple sources)

## Recommended Stack

### Core Technologies (Already In Place)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.13.7 | Top-level API, orchestration, joblib parallelism | Already in use; 3.13 is current stable line |
| Cython | 3.2.x (latest 3.2.4) | Python-to-C bridge, .pyx middleware layer | Already in use; 3.2.4 is latest stable (Jan 2026). Upgrade from "Cython 3" unspecified to pin 3.2.x for free-threading groundwork and bug fixes |
| C11 | gcc/clang | Core solver kernel: local search, branching, constraint evaluation | Already in use; C11 is correct choice for `_Atomic`, VLAs, and `stdint.h` |
| setuptools + Cython.Build | current | Build system for extensions | Already in use; adequate for this project size |

### Memory Debugging Tools

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| AddressSanitizer (ASan) | Built into gcc/clang | Heap/stack buffer overflows, use-after-free, double-free | **Primary memory debugger.** 2-3x slowdown (vs Valgrind's 20-50x). Catches stack overflows Valgrind cannot. Compile with `-fsanitize=address -fno-omit-frame-pointer`. Already partially set up (commented ASan flags in setup.py). |
| Valgrind (memcheck) | 3.26.0 (Oct 2025) | Heap leak detection, uninitialized memory reads | **Secondary leak detector.** No recompilation needed; use `PYTHONMALLOC=malloc` and CPython suppression file to filter interpreter noise. Essential for finding the leaks in `explore_neighbourhood` (calloc/free in hot loop). |
| LeakSanitizer (LSan) | Built into ASan | Focused leak detection | Runs automatically with ASan. Use `ASAN_OPTIONS=detect_leaks=1` to enable standalone leak reports. |

### Thread Safety Analysis

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| ThreadSanitizer (TSan) | Built into gcc/clang | Data race detection on shared memory | **Primary thread safety tool.** Compile with `-fsanitize=thread -g -O1`. 5-15x slowdown. Directly addresses the `stopping_criterion` shared-write race and any BranchingStats global state races. Cannot combine with ASan in same build -- use separate build configs. |
| Helgrind (Valgrind tool) | 3.26.0 | Alternative thread error detector | **Backup option.** Use when TSan is impractical (e.g., cannot recompile all libraries). Detects lock ordering violations TSan may miss. Run with `valgrind --tool=helgrind`. |

### Performance Profiling

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| `perf` | Linux kernel tool | CPU sampling profiler, hardware counters | **Primary profiler.** Zero instrumentation overhead sampling. Use `perf record -g -F 99` then generate flame graphs. Build with `-fno-omit-frame-pointer` for accurate stacks. |
| FlameGraph | Latest from github.com/brendangregg/FlameGraph | Visualization of perf sampling data | **Essential companion to perf.** Converts perf stacks to interactive SVG. Immediately identifies hot C functions (constraint_violation, explore_neighbourhood). |
| `gprof` | Part of binutils | Function-level call counts and timing | **Lightweight alternative** when perf is unavailable (e.g., macOS without root). Compile with `-pg`. Less accurate than perf for multithreaded code. |
| cProfile + py-spy | Python packages | Python-level profiling | **For Python/Cython layer.** py-spy can profile without code changes and shows both Python and C frames. Use to find overhead in joblib dispatch and Cython wrapper calls. |

### C Unit Testing

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| CMocka | 2.0.x (2.0.1, Dec 2025) | C unit test framework with mocking | **Recommended C test framework.** TAP 14 output for CI integration. Type-safe assertions (C99 `intmax_t`). Built-in mock support for isolating functions like `constraint_violation`, `move_list`, `accept_move`. Used by samba, libssh, OpenVPN. CMake and Meson build support. |

### Python/Cython Testing

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| pytest | 8.x | Python test runner | **Standard choice.** Run integration tests that exercise the full Python -> Cython -> C stack. Test the public API (Model, SearchLib, Constraint). |
| pytest-cython | 0.2.x | Doctest support for .pyx files | **Optional.** Useful for testing Cython-only `cdef` functions by writing test wrappers in .pyx files that pytest discovers. |
| hypothesis | 6.x | Property-based testing | **Recommended for solver correctness.** Generate random constraint models and verify invariants (feasibility check consistency, objective monotonicity). Catches edge cases manual tests miss. |

### Static Analysis

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| cppcheck | 2.x | Static analysis of C code | **Lightweight first pass.** Catches uninitialized variables, null pointer dereferences, buffer overflows without running code. Run on `cbqs/src/*.c` before committing. |
| Cython boundscheck/cdivision | Compiler directives | Catch array/division errors in development | Enable `boundscheck=True` and `cdivision=False` in dev builds. Disable for release (`-O3`). |

### Memory Allocation Patterns (No External Dependency)

| Pattern | Purpose | Where to Apply |
|---------|---------|----------------|
| Arena/bump allocator | Eliminate per-iteration malloc/free in hot loops | `explore_neighbourhood`: replace `calloc(MINSIZE, sizeof(int))` for `changed_con` and `changes` with a per-thread arena that resets each iteration. Also for `sw_init` temporary bitvectors. |
| Thread-local arenas | Avoid synchronization overhead | Each pthread gets its own arena (allocated once in `accept_best_routine`, freed after join). No locking needed. |
| Stack allocation | Replace small heap allocations | VLA `int bits[dat->d]` is already on stack (good). Consider converting `int64_t totals[C]` from VLA to arena-backed if C is large. |

## Installation

```bash
# Python dependencies (existing + new)
pip install cython>=3.2.0 numpy pandas pytest hypothesis py-spy

# Dev dependencies
pip install pytest-cython

# System tools (Ubuntu/Debian)
sudo apt install valgrind linux-tools-common linux-tools-generic cppcheck cmake

# FlameGraph (clone once)
git clone https://github.com/brendangregg/FlameGraph.git ~/FlameGraph
```

## Build Configurations

```bash
# === Release build (existing) ===
CFLAGS="-O3 -flto -pthread" pip install -e .

# === ASan debug build ===
CFLAGS="-O1 -g -fsanitize=address -fno-omit-frame-pointer -pthread" \
LDFLAGS="-fsanitize=address" \
pip install -e . --no-build-isolation

# === TSan thread safety build ===
CFLAGS="-O1 -g -fsanitize=thread -fno-omit-frame-pointer -pthread" \
LDFLAGS="-fsanitize=thread" \
pip install -e . --no-build-isolation

# === Profiling build ===
CFLAGS="-O2 -g -fno-omit-frame-pointer -pthread" \
pip install -e . --no-build-isolation

# === Valgrind run ===
PYTHONMALLOC=malloc valgrind --leak-check=full --suppressions=valgrind-python.supp \
  python -c "import cbqs; ..."
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| CMocka 2.0 | Unity (ThrowTheSwitch) | If you need embedded system support or want zero external dependencies (Unity is 2 headers + 1 .c file). Unity lacks built-in mocking -- needs CMock addon. |
| CMocka 2.0 | Check | If you prefer fork-based test isolation (each test runs in a subprocess). Heavier weight than CMocka. |
| ASan | Valgrind only | If you cannot recompile (e.g., testing binary-only libraries). Valgrind works on unmodified binaries. |
| TSan | Helgrind | When you need lock-ordering analysis or cannot recompile all threaded code. Helgrind is Valgrind-based, no recompilation needed. |
| perf + FlameGraph | Instruments (macOS) | On macOS development. perf is Linux-only. Use Instruments.app or `sample` command on macOS. |
| pytest | unittest | Never -- pytest is strictly superior for this use case. |
| Arena allocator (custom) | jemalloc/tcmalloc | If you want a drop-in malloc replacement without rewriting allocation sites. Does not eliminate the overhead of individual free() calls though. Arena is better for batch-allocate/batch-free patterns in the hot loop. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| gprof for multithreaded code | gprof does not handle pthreads correctly; it only profiles the main thread and misses time in spawned threads | perf + FlameGraph |
| `-fsanitize=address` + `-fsanitize=thread` together | ASan and TSan are mutually exclusive; combining them causes false positives and crashes | Separate build configurations |
| `rand()` in threaded code | `rand()` uses global state, creating a data race. Already present in `move_list` shuffle. | `rand_r()` with per-thread seed, or `drand48_r()` |
| VLAs with unbounded size | `int64_t totals[C]` and `int64_t remainings[C]` where C comes from user input can overflow stack for large constraint counts | Arena-allocated buffer or heap with size check |
| `#define false 0` / `#define true 1` in definitions.h | Conflicts with C99 `<stdbool.h>` and C++ `bool` | `#include <stdbool.h>` (C99 standard) |

## Stack Patterns by Variant

**If targeting macOS development (current, based on Metal backend):**
- Use Instruments.app for profiling instead of perf
- ASan and TSan work with Apple Clang
- Valgrind does NOT support Apple Silicon (arm64). Use ASan/TSan exclusively on macOS.

**If scaling to larger problem sizes (>1000 variables):**
- Arena allocator becomes critical (malloc per-iteration at 1000+ vars = measurable overhead)
- Consider SIMD for bitvector operations (sw_tstbit, sw_setbit, sw_clrbit)
- Thread count should be configurable, not hardcoded `#define NUMThreads 6`

**If adding CI/CD pipeline:**
- CMocka TAP 14 output integrates directly with GitHub Actions test reporters
- ASan/TSan builds should be separate CI jobs (different compiler flags)
- Use `cppcheck --xml` for static analysis reporting

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Cython 3.2.x | Python 3.9-3.13 | Python 3.8 support dropped in 3.2.0 |
| Cython 3.2.x | Python 3.13t (free-threaded) | Experimental support since Cython 3.1. Extension modules not yet thread-safe for cdef class attributes. |
| CMocka 2.0.x | C99+ compilers | Requires C99 for `intmax_t`; project already uses C11 |
| Valgrind 3.26.0 | Linux x86_64, aarch64 | Does NOT support macOS arm64 (Apple Silicon) |
| ASan/TSan | gcc 4.8+, clang 3.2+ | Supported on both Linux and macOS |

## Confidence Assessment

| Item | Confidence | Source |
|------|------------|--------|
| ASan/TSan flags and behavior | HIGH | Official Clang docs, Google Sanitizers wiki |
| Valgrind 3.26.0 version | HIGH | valgrind.org official downloads page |
| CMocka 2.0 features | HIGH | Official cmocka.org, LWN.net announcement (Dec 2025) |
| Cython 3.2.4 current version | HIGH | PyPI official page |
| Arena allocator 50-100x speedup claim | MEDIUM | Multiple blog posts, no benchmark on this specific codebase |
| py-spy compatibility with Cython 3.2 | MEDIUM | Generally works but not verified for this specific version combo |
| Free-threaded Python + Cython safety | MEDIUM | Cython docs state "experimental"; not recommended for production yet |
| Helgrind vs TSan tradeoffs | MEDIUM | Based on Valgrind docs and Google Sanitizers wiki; not tested side-by-side on this codebase |

## Sources

- [Valgrind 3.26.0 release](https://valgrind.org/downloads/) -- verified version and platform support
- [ThreadSanitizer manual](https://github.com/google/sanitizers/wiki/threadsanitizercppmanual) -- compilation flags, overhead, pthread support
- [Clang ThreadSanitizer docs](https://clang.llvm.org/docs/ThreadSanitizer.html) -- official compiler documentation
- [Red Hat: Comparing Sanitizers and Valgrind](https://developers.redhat.com/blog/2021/05/05/memory-error-checking-in-c-and-c-comparing-sanitizers-and-valgrind) -- ASan vs Valgrind tradeoffs
- [Using Valgrind with Cython](https://adrianeboyd.github.io/using-valgrind-with-cython/) -- PYTHONMALLOC, suppression files
- [CMocka 2.0 release announcement](https://blog.cryptomilk.org/2025/12/04/cmocka-2-0-released-enhancing-unit-testing-in-c/) -- TAP 14, type-safe assertions
- [cmocka.org](https://cmocka.org/) -- official project page
- [Cython 3.2.4 on PyPI](https://pypi.org/project/Cython/) -- current version verification
- [Cython free threading docs](https://cython.readthedocs.io/en/latest/src/userguide/freethreading.html) -- experimental nogil status
- [Brendan Gregg's FlameGraph](https://github.com/brendangregg/FlameGraph) -- perf visualization
- [Brendan Gregg's perf examples](https://www.brendangregg.com/perf.html) -- profiling workflow
- [Arena allocator patterns](https://nullprogram.com/blog/2023/09/27/) -- implementation tips
- [Arena performance claims](https://medium.com/@ramogh2404/arena-and-memory-pool-allocators-the-50-100x-performance-secret-behind-game-engines-and-browsers-1e491cb40b49) -- MEDIUM confidence
- [joblib parallel docs](https://joblib.readthedocs.io/en/stable/parallel.html) -- threading backend with nogil
- [pytest-cython](https://github.com/lgpage/pytest-cython) -- Cython test integration

---
*Stack research for: CBQS solver optimization and stabilization*
*Researched: 2026-02-04*
