cmake_minimum_required(VERSION 3.28)
project(constraint-oriented-biased-quantum-search C)

set(CMAKE_C_STANDARD 11)

include_directories(iqs/src)

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
)


add_executable(metal_test
        cbqs/src/metal_files/exec_metal.m
        cbqs/src/metal_files/exec_metal.h
)
target_link_libraries(metal_test
        "-framework Metal"
        "-framework Foundation"
)
