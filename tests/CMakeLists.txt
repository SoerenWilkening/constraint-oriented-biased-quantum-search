cmake_minimum_required(VERSION 3.14)
project(cbqs-tests C)

set(CMAKE_C_STANDARD 11)
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
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_model
    test_model.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

add_cmocka_test(test_branching
    test_branching.c
    ${CBQS_SRC_DIR}/Branching.c
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
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
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
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)
target_include_directories(test_searchlib PRIVATE "${PYTHON_INCLUDE_DIRS}")

add_cmocka_test(test_integration
    test_integration.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)

# --- Plan 02-01: local_search regression test ---
# Tests thread data lifetime fix (use-after-free bug)
add_cmocka_test(test_local_search
    test_local_search.c
    ${CBQS_SRC_DIR}/local_search.c
    ${CBQS_SRC_DIR}/quantum_search.c
    ${CBQS_SRC_DIR}/solver.c
    ${CBQS_SRC_DIR}/Branching.c
    ${CBQS_SRC_DIR}/model.c
    ${CBQS_SRC_DIR}/constraint.c
    ${CBQS_SRC_DIR}/Expression.c
    ${CBQS_SRC_DIR}/state.c
    ${CBQS_SRC_DIR}/intarray.c
)
