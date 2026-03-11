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

# Helper function to create a CMocka test
# Usage: add_cmocka_test(NAME test_source.c [extra_cbqs_sources...])
function(add_cmocka_test NAME)
    set(SOURCES ${ARGN})
    add_executable(${NAME} ${SOURCES})
    target_include_directories(${NAME} PRIVATE
        "${CBQS_SRC_DIR}"
        "${cmocka_SOURCE_DIR}/include"
    )
    target_link_libraries(${NAME} PRIVATE cmocka-static pthread m)

    if(ASAN)
        target_compile_options(${NAME} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
        target_link_options(${NAME} PRIVATE -fsanitize=address)
    endif()

    # Strict warning flags for C23-forward compatibility
    target_compile_options(${NAME} PRIVATE
        -Wall -Wextra -Wpedantic -Wvla
        -Wno-unused-parameter  # CMocka test helpers have unused params
    )
    if(WERROR)
        target_compile_options(${NAME} PRIVATE -Werror)
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
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- Plan 01-03 tests: solver, searchlib, integration ---

add_cmocka_test(test_solver
    test_solver.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
)

# SearchLib.c includes Python.h -- find Python for include path
find_package(Python3 COMPONENTS Development)
if(Python3_FOUND)
    set(PYTHON_INCLUDE_DIRS "${Python3_INCLUDE_DIRS}")
else()
    execute_process(
        COMMAND python3 -c "import sysconfig; print(sysconfig.get_path('include'))"
        OUTPUT_VARIABLE PYTHON_INCLUDE_DIRS
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()

add_cmocka_test(test_searchlib
    test_searchlib.c
    ${CBQS_SRC_DIR}/SearchLib.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)
target_include_directories(test_searchlib PRIVATE "${PYTHON_INCLUDE_DIRS}")

add_cmocka_test(test_integration
    test_integration.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
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
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
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
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- M5: CSearch ordering iteration tests ---
add_cmocka_test(test_csearch_ordering
    test_csearch_ordering.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/dyn_expr.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
    ${CBQS_SRC_DIR}/prng.c
    ${CBQS_SRC_DIR}/solver_ctx.c
    ${CBQS_SRC_DIR}/arena.c
)
