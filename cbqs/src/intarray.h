#ifndef INTARRAY_H
#define INTARRAY_H

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "definitions.h"

typedef uint64_t part_length_t;

typedef struct {
	size_t n;
	size_t bits;
	part_length_t *part;
} array_t;


array_t sw_init(size_t B);

static inline void sw_setbit(array_t A, size_t B) {
	size_t which_part = B >> 6;
	size_t which_bit = B - (which_part << 6);
	A.part[which_part] |= (1ULL << which_bit);
}

static inline void sw_flpbit(array_t A, size_t B) {
	size_t which_part = B >> 6;
	size_t which_bit = B - (which_part << 6);
	A.part[which_part] ^= (1ULL << which_bit);
}

static inline void sw_clrbit(array_t A, size_t B) {
	size_t which_part = B >> 6;
	size_t which_bit = B - (which_part << 6);
	A.part[which_part] &= (~(1ULL << which_bit));
}

static inline int sw_tstbit(array_t A, size_t B) {
	size_t which_part = B >> 6;
	size_t which_bit = B - (which_part << 6);
	return (A.part[which_part] & (1ULL << which_bit)) >> which_bit;
}

static inline void sw_set_ui_0(array_t A) {
	for (size_t x = 0; x < A.n; ++x) {
		A.part[x] = 0;
	}
}

static inline void sw_print(array_t A) {
	for (size_t z = 0; z < A.bits; ++z) {
		printf("%d", sw_tstbit(A, z));
	}
}

static inline void sw_clear(array_t A) {
	free(A.part);
}

static inline array_t sw_set(array_t B) {
	array_t A = sw_init(B.bits);
	A.n = B.n;
	for (size_t LOOPINDEX = 0; LOOPINDEX < B.n; ++LOOPINDEX) {
		A.part[LOOPINDEX] = B.part[LOOPINDEX];
	}
	return A;
}


static inline void sw_set_inplace(array_t A, array_t B) {
	A.n = B.n;
	for (size_t LOOPINDEX = 0; LOOPINDEX < B.n; ++LOOPINDEX) {
		A.part[LOOPINDEX] = B.part[LOOPINDEX];
	}
}


static inline int sw_cmp(array_t A1, array_t A2) {
	for (size_t i = 0; i < A1.n; ++i) {
		if (A1.part[i] != A2.part[i]) {
			return 0;
		}
	}
	return 1;
}


//void sw_setbit(array_t A, size_t B);
//void sw_clrbit(array_t A, size_t B);
//int sw_tstbit(array_t A, size_t B);
//void sw_flpbit(array_t A, size_t B);
//void sw_set_ui_0(array_t A);
//void sw_print(array_t A);
//void sw_clear(array_t A);
//array_t sw_set(array_t B);
//int sw_cmp(array_t A1, array_t A2);

#endif // INTARRAY_H