#ifndef INTARRAY_H
#define INTARRAY_H

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "definitions.h"

#ifdef _WIN32
typedef uint64_t part_length_t;
#else
typedef u_int64_t part_length_t;
#endif

typedef struct {
    size_t n;
    size_t bits;
    part_length_t* part;
} array_t;


array_t sw_init(size_t B);
void sw_setbit(array_t A, size_t B);
void sw_clrbit(array_t A, size_t B);
int sw_tstbit(array_t A, size_t B);
void sw_set_ui_0(array_t A);
void sw_print(array_t A);
void sw_clear(array_t A);
array_t sw_set(array_t B);
int sw_cmp(array_t A1, array_t A2);

#endif // INTARRAY_H