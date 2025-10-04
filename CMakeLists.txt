cmake_minimum_required(VERSION 3.28)
project(improved_quantum_search C)

set(CMAKE_C_STANDARD 11)

include_directories(iqs/src)

add_executable(improved_quantum_search
        iqs/src/Expression.c
        iqs/src/Expression.h
        iqs/src/test.c
        iqs/src/constraint.h
        iqs/src/constraint.c
        iqs/src/intarray.c
        iqs/src/intarray.h
        iqs/src/state.c
        iqs/src/SearchLib.c
        iqs/src/SearchLib.h
        iqs/src/Branching.c
        iqs/src/Branching.h
        iqs/src/solver.c
        iqs/src/solver.h
        iqs/src/local_search.c
        iqs/src/local_search.h
        iqs/src/quantum_search.c
        iqs/src/quantum_search.h
        iqs/src/model.c
        iqs/src/model.h
)


add_executable(metal_test
        iqs/src/metal_files/exec_metal.m
        iqs/src/metal_files/exec_metal.h
)
target_link_libraries(metal_test
        "-framework Metal"
        "-framework Foundation"
)
