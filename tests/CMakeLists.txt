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
    GIT_REPOSITORY https://git.cryptomilk.org/projects/cmocka.git
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
