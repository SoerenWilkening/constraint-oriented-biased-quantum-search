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
