cmake_minimum_required(VERSION 3.28)
project(constraint-oriented-biased-quantum-search C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)  # enforce /std:c17 on MSVC (needed by /experimental:c11atomics, bd 8an.1.10)

find_package(Python3 REQUIRED COMPONENTS Development)

add_executable(constraint-oriented-biased-quantum-search
        cbqs/src/Expression.c
        cbqs/src/Expression.h
        cbqs/src/test.c
        cbqs/src/constraint.h
        cbqs/src/constraint.c
        cbqs/src/intarray.c
        cbqs/src/intarray.h
        cbqs/src/state.c
        cbqs/src/SearchLib.c
        cbqs/src/SearchLib.h
        cbqs/src/Branching.c
        cbqs/src/Branching.h
        cbqs/src/solver_ctx.c
        cbqs/src/solver_ctx.h
        cbqs/src/solver.c
        cbqs/src/solver.h
        cbqs/src/local_search.c
        cbqs/src/local_search.h
        cbqs/src/quantum_search.c
        cbqs/src/quantum_search.h
        cbqs/src/model.c
        cbqs/src/model.h
        cbqs/src/approximate_state_sampler.c
        cbqs/src/approximate_state_sampler.h
        cbqs/src/arena.c
        cbqs/src/arena.h
        cbqs/src/dyn_expr.c
        cbqs/src/dyn_expr.h
        cbqs/src/prng.c
        cbqs/src/prng.h
        cbqs/src/platform.c
        cbqs/src/platform.h
)

target_include_directories(constraint-oriented-biased-quantum-search PRIVATE ${Python3_INCLUDE_DIRS})
target_link_libraries(constraint-oriented-biased-quantum-search PRIVATE ${Python3_LIBRARIES})
if(NOT WIN32)
    target_link_libraries(constraint-oriented-biased-quantum-search PRIVATE m)
endif()
if(NOT MSVC)
    target_compile_options(constraint-oriented-biased-quantum-search PRIVATE
        -Wall -Wextra -Wpedantic -Wvla
    )
else()
    # solver_ctx.c uses C11 <stdatomic.h>; MSVC needs /experimental:c11atomics
    # (paired with the /std:c17 implied by CMAKE_C_STANDARD=17) or it fails with
    # C1189 "C atomic support is not enabled" (bd 8an.1.10).
    target_compile_options(constraint-oriented-biased-quantum-search PRIVATE /experimental:c11atomics)
endif()


if(APPLE)
    add_executable(metal_test EXCLUDE_FROM_ALL
            cbqs/src/metal_files/exec_metal.m
            cbqs/src/metal_files/exec_metal.h
    )
    target_link_libraries(metal_test
            "-framework Metal"
            "-framework Foundation"
    )
endif()
