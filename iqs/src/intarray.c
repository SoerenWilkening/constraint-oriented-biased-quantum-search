#include "intarray.h"
#include <stdio.h>
#include <stdlib.h>

array_t sw_init(size_t B) {
    array_t A;
    A.bits = B;
    size_t numbits = (B >> 6) + 1;
    A.n = numbits;
    A.part = (part_length_t*)calloc(A.n, sizeof(part_length_t));
    return A;
}

void sw_setbit(array_t A, size_t B) {
    size_t which_part = B >> 6;
    size_t which_bit = B - (which_part << 6);
    A.part[which_part] |= (1ULL << which_bit);
}

void sw_clrbit(array_t A, size_t B) {
    size_t which_part = B >> 6;
    size_t which_bit = B - (which_part << 6);
    A.part[which_part] &= (~(1ULL << which_bit));
}

int sw_tstbit(array_t A, size_t B) {
    size_t which_part = B >> 6;
    size_t which_bit = B - (which_part << 6);
    return (A.part[which_part] & (1ULL << which_bit)) >> which_bit;
}

void sw_set_ui_0(array_t A) {
    for (size_t x = 0; x < A.n; ++x) {
        A.part[x] = 0;
    }
}

void sw_print(array_t A) {
    for (size_t z = 0; z < A.bits; ++z) {
        printf("%d", sw_tstbit(A, z));
    }
}

void sw_clear(array_t A) {
    free(A.part);
}

array_t sw_set(array_t B) {
    array_t A = sw_init(B.bits);
    A.n = B.n;
    for (size_t LOOPINDEX = 0; LOOPINDEX < B.n; ++LOOPINDEX) {
        A.part[LOOPINDEX] = B.part[LOOPINDEX];
    }
    return A;
}

int sw_cmp(array_t A1, array_t A2) {
    for (size_t i = 0; i < A1.n; ++i) {
        if (A1.part[i] != A2.part[i]) {
            return 0;
        }
    }
    return 1;
}
