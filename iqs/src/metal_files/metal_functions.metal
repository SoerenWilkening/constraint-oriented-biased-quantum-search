#include "metal_functions.h"

static uint rand(uint seed){
	seed ^= seed << 21;
	seed ^= seed >> 35;
	seed ^= seed << 4;
	return seed;
}

static uint set_bit( device state_32_t *state,
							int state_index,
							device uint *state_data,
							uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - index << 5) );
	state_data[state[state_index].x_offset + index] |= mask;
	return bit;
}