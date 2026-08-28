cmake_minimum_required(VERSION 3.14)
project(cbqs-tests C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)

include(FetchContent)

set(WITH_STATIC_LIB ON CACHE BOOL "" FORCE)
set(WITH_EXAMPLES OFF CACHE BOOL "" FORCE)
set(UNIT_TESTING ON CACHE BOOL "" FORCE)

FetchContent_Declare(
    cmocka
    GIT_REPOSITORY https://gitlab.com/cmocka/cmocka.git
    GIT_TAG cmocka-1.1.7
)
FetchContent_MakeAvailable(cmocka)

# Path to cbqs C sources
set(CBQS_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../cbqs/src")

# ASan option
option(ASAN "Enable AddressSanitizer" OFF)
option(WERROR "Enable -Werror for strict warning compliance" OFF)

# --- Sanitizer runtime smoke check (bd aft) ----------------------------------
# Apple clang's compiler-rt SIGILLs at process startup on macOS 26+ (Darwin 25+):
# every instrumented binary exits 132 before main, so the CLAUDE.md §7 local
# sanitizer gate is SILENTLY non-functional (it reads as "all tests crash"). When
# a sanitizer is requested, compile+run a trivial instrumented program at
# configure time and fail LOUDLY with the remedy if the runtime can't start. On
# Linux / a working toolchain (incl. CI) this passes silently.
if(ASAN OR CMAKE_C_FLAGS MATCHES "-fsanitize")
    include(CheckCSourceRuns)
    if(ASAN)
        set(CMAKE_REQUIRED_FLAGS "-fsanitize=address")
        set(CMAKE_REQUIRED_LINK_OPTIONS "-fsanitize=address")
    endif()
    # Any -fsanitize=thread already lives in CMAKE_C_FLAGS, so the check inherits it.
    check_c_source_runs("int main(void){return 0;}" CBQS_SANITIZER_RUNTIME_OK)
    unset(CMAKE_REQUIRED_FLAGS)
    unset(CMAKE_REQUIRED_LINK_OPTIONS)
    if(NOT CBQS_SANITIZER_RUNTIME_OK)
        set(_san_hint "")
        if(APPLE)
            string(CONCAT _san_hint
                "\n  macOS 26+ (Darwin 25+): Apple clang's sanitizer runtime is broken (bd aft)."
                "\n  Use Homebrew LLVM clang (verified working) — reconfigure a fresh build dir with"
                "\n      -DCMAKE_C_COMPILER=$(brew --prefix llvm)/bin/clang"
                "\n  or just run  tests/run_sanitizers.sh  (it selects the right compiler).")
        endif()
        message(FATAL_ERROR
            "Sanitizer runtime fails to start with "
            "${CMAKE_C_COMPILER_ID} ${CMAKE_C_COMPILER_VERSION} (${CMAKE_C_COMPILER}): "
            "a trivial instrumented program exits before main, so the gate would "
            "report a spurious crash for every test.${_san_hint}")
    endif()
endif()

# Helper function to create a CMocka test
# Usage: add_cmocka_test(NAME test_source.c [extra_cbqs_sources...])
function(add_cmocka_test NAME)
    set(SOURCES ${ARGN})
    add_executable(${NAME} ${SOURCES})
    target_include_directories(${NAME} PRIVATE
        "${CBQS_SRC_DIR}"
        "${cmocka_SOURCE_DIR}/include"
    )
    target_link_libraries(${NAME} PRIVATE cmocka-static)
    if(NOT WIN32)
        target_link_libraries(${NAME} PRIVATE pthread m)
    else()
        target_link_libraries(${NAME} PRIVATE bcrypt)
    endif()

    if(ASAN)
        target_compile_options(${NAME} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
        target_link_options(${NAME} PRIVATE -fsanitize=address)
    endif()

    # Strict warning flags for C23-forward compatibility (GCC/Clang vs MSVC).
    # The -W* flags are GCC/Clang-only; passing them to cl.exe yields fatal
    # D8021 "invalid numeric argument '/Wextra'" (bd 8an.1.10).
    if(NOT MSVC)
        target_compile_options(${NAME} PRIVATE
            -Wall -Wextra -Wpedantic -Wvla
            -Wno-unused-parameter  # CMocka test helpers have unused params
        )
        if(WERROR)
            target_compile_options(${NAME} PRIVATE -Werror)
        endif()
    else()
        target_compile_options(${NAME} PRIVATE /W3)
        # solver_ctx.c uses C11 <stdatomic.h> (atomic_bool stop flag). MSVC only
        # enables it under /experimental:c11atomics, which in turn requires a C11/C17
        # mode (supplied here via CMAKE_C_STANDARD=17 -> /std:c17). Without this the
        # build dies with C1189 "C atomic support is not enabled" (bd 8an.1.10).
        target_compile_options(${NAME} PRIVATE /experimental:c11atomics)
        # /WX (warnings-as-errors) deferred: MSVC surfaces C4267 size_t->int
        # warnings (incl. from cmocka) that need triage first (bd 8an.1.10).
    endif()

    add_test(NAME ${NAME} COMMAND ${NAME})
endfunction()

enable_testing()

# Test targets with their specific source dependencies
add_cmocka_test(test_intarray
    test_intarray.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_expression
    test_expression.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
)

add_cmocka_test(test_merge_duplicate_terms
    test_merge_duplicate_terms.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
)

add_cmocka_test(test_state
    test_state.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_constraint
    test_constraint.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_model
    test_model.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_branching
    test_branching.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# bd a0w (M5): angle-precision lever -- Ross-Selinger/gridsynth theta quantization
# inside BranchingFunction. Same source list as test_branching (header-only lever
# + the solver_ctx setters).
add_cmocka_test(test_angle_precision
    test_angle_precision.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- Plan 01-03 tests: solver, searchlib, integration ---

add_cmocka_test(test_solver
    test_solver.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
)

# test_searchlib needs no Python: SearchLib.c no longer includes <Python.h>
# (bd 8an.1.10), so the former find_package(Python3)/include-dir machinery and
# the CMAKE_CROSSCOMPILING guard it required are gone.
add_cmocka_test(test_searchlib
    test_searchlib.c
    ${CBQS_SRC_DIR}/SearchLib.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

add_cmocka_test(test_integration
    test_integration.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
)

# --- Plan 02-01: local_search regression test ---
# Tests thread data lifetime fix (use-after-free bug)
# Updated 05-02: Added prng.c and solver_ctx.c for VLA replacement changes
# Updated 06-03: Added arena.c for hot-path arena allocations
add_cmocka_test(test_local_search
    test_local_search.c
    ${CBQS_SRC_DIR}/local_search.c
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- Plan 03-05: Thread safety test ---
# Tests that solver_ctx_t enables safe concurrent usage:
# - Independent contexts don't interfere
# - Atomic stop flag visibility across threads
# - Timeout mechanism works correctly
# - Debug output doesn't crash
add_cmocka_test(test_thread_safety
    test_thread_safety.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- Plan 04-01: PRNG unit tests ---
# Tests xoshiro256** PRNG implementation:
# - Seeding produces valid non-zero state
# - prng_next_double in [0.0, 1.0)
# - prng_next_int in [0, max)
# - Determinism with same seed
# - Jump function produces distinct streams
add_cmocka_test(test_prng
    test_prng.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
)

# --- Plan 06-01: Arena allocator unit tests ---
# Tests arena bump allocator for hot-path allocation elimination:
# - Create/free lifecycle
# - Basic allocation and alignment
# - Overflow chunk chaining
# - Reset clears without freeing
# - Large allocations
# - NULL safety
add_cmocka_test(test_arena
    test_arena.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- Plan 06-02: Dynamic expression unit tests ---
# Tests dynamic expression with small-object optimization:
# - Inline storage for <=8 terms
# - Inline-to-heap transition at 9 terms
# - 2x capacity growth for heap storage
# - Memory efficiency (small vs large expressions)
# - Copy operations for inline and heap
add_cmocka_test(test_dyn_expr
    test_dyn_expr.c
    ${CBQS_SRC_DIR}/dyn_expr.c
)

# --- M4: Variable ordering unit tests ---
add_cmocka_test(test_variable_ordering
    test_variable_ordering.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- bd h8d: feasibility consistency under variable reordering (quadratic clauses) ---
# Name keeps the "test_variable" prefix so CI's ctest -R filter matches it.
add_cmocka_test(test_variable_order_feasibility
    test_variable_order_feasibility.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- M5: CSearch ordering iteration tests ---
add_cmocka_test(test_csearch_ordering
    test_csearch_ordering.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- bd 0o8.2 (exact win A): incremental evaluation() cross-check ---
add_cmocka_test(test_eval_incremental
    test_eval_incremental.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- bd 0o8: classical Grover-round sample cap (opt_sample_cap) ---
add_cmocka_test(test_opt_sample_cap
    test_opt_sample_cap.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- bd 0o8.3: mid-round wall-clock deadline interrupt (ctx->deadline_ns) ---
add_cmocka_test(test_deadline_interrupt
    test_deadline_interrupt.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- bd w29 (M5 / 71e): continuous oracle-indexed opt-radius DECAY lever ---
# Drives ctg (mirrors test_searchlib's source list) for the bit-for-bit negative
# control + liveness, plus pure-evaluator unit tests.
add_cmocka_test(test_opt_radius_schedule
    test_opt_radius_schedule.c
    ${CBQS_SRC_DIR}/SearchLib.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/incr_eval.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)

# --- M1: Phase-specific BranchingStats in solver_ctx_t ---
add_cmocka_test(test_solver_ctx_phases
    test_solver_ctx_phases.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
)

# --- M2: ctg() stage switching ---
add_cmocka_test(test_stage_switching
    test_stage_switching.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/platform.c
)

# --- C-level variable vector struct and lifecycle ---
add_cmocka_test(test_variable_vector
    test_variable_vector.c
    ${CBQS_SRC_DIR}/variable_vector.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
)

# --- bilinear_reduce / linear_reduce ---
add_cmocka_test(test_reduce_ops
    test_reduce_ops.c
    ${CBQS_SRC_DIR}/variable_vector.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
)
