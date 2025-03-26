cmake_minimum_required(VERSION 3.28)
project(improved_quantum_search C)

set(CMAKE_C_STANDARD 11)

include_directories(iqs/src)

add_executable(improved_quantum_search
        iqs/src/Expression.c
        iqs/src/Expression.h
        iqs/src/test.c)
