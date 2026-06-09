#!/usr/bin/env bash
#
# Local sanitizer gate for CBQS (CLAUDE.md §7, bd aft).
#
# Builds and runs the ASan suite (full) and the TSan thread-safety test with a
# sanitizer-capable compiler, then reports PASS/FAIL.
#
# Why this script exists (bd aft): on macOS 26+ (Darwin 25+) Apple clang's
# compiler-rt SIGILLs at process startup, so EVERY instrumented binary exits 132
# before main and the §7 local sanitizer gate is silently non-functional.
# Homebrew LLVM clang's sanitizer runtime is verified working on this OS, so on
# macOS this script uses it (install with `brew install llvm`); on Linux it uses
# the default clang (CI's toolchain, which already runs these gates).
#
# Usage:
#   tests/run_sanitizers.sh            # ASan (full ctest) + TSan (thread_safety)
#   tests/run_sanitizers.sh asan       # ASan only
#   tests/run_sanitizers.sh tsan       # TSan only
set -euo pipefail

cd "$(dirname "$0")/.."

# --- pick a sanitizer-capable C compiler -------------------------------------
pick_sanitizer_cc() {
    if [[ "$(uname)" == "Darwin" ]]; then
        local llvm cc
        llvm="$(brew --prefix llvm 2>/dev/null || true)"
        for cc in "${llvm:+$llvm/bin/clang}" \
                  /usr/local/opt/llvm/bin/clang \
                  /opt/homebrew/opt/llvm/bin/clang; do
            [[ -n "$cc" && -x "$cc" ]] && { echo "$cc"; return 0; }
        done
        echo "ERROR: Homebrew LLVM clang not found. Apple clang's sanitizer" >&2
        echo "       runtime SIGILLs at startup on macOS 26+ (bd aft), so the" >&2
        echo "       sanitizer gate cannot run with the system toolchain." >&2
        echo "       Install a working one:  brew install llvm" >&2
        return 1
    fi
    command -v clang || { echo "ERROR: clang not found on PATH." >&2; return 1; }
}

CC_SAN="$(pick_sanitizer_cc)"
echo ">>> sanitizer compiler: $CC_SAN"
"$CC_SAN" --version | head -1

run_asan() {
    echo ">>> ASan: configure + build + full ctest"
    # Fresh configure: CMake ignores -DCMAKE_C_COMPILER if a stale cache pins a
    # different one, which would silently run the gate on the broken Apple
    # toolchain (bd aft). Wiping the dir guarantees the requested compiler.
    rm -rf build-asan
    cmake -S tests -B build-asan -DASAN=ON -DWERROR=ON \
        -DCMAKE_C_COMPILER="$CC_SAN" >/dev/null
    cmake --build build-asan -j
    ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 \
        ctest --test-dir build-asan --output-on-failure
}

run_tsan() {
    echo ">>> TSan: configure + build + thread-safety test"
    rm -rf build-tsan   # fresh configure — see run_asan (bd aft stale-cache note)
    cmake -S tests -B build-tsan -DCMAKE_C_COMPILER="$CC_SAN" \
        -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_C_FLAGS="-fsanitize=thread -g -O1" \
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=thread" >/dev/null
    cmake --build build-tsan --target test_thread_safety -j
    TSAN_OPTIONS=halt_on_error=1 \
        ctest --test-dir build-tsan -R test_thread_safety --output-on-failure
}

case "${1:-all}" in
    asan) run_asan ;;
    tsan) run_tsan ;;
    all)  run_asan; run_tsan ;;
    *)    echo "usage: $0 [asan|tsan|all]" >&2; exit 2 ;;
esac

echo ">>> sanitizer gate: PASS"
