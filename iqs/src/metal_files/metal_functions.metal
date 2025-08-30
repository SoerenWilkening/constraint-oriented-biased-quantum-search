#include "metal_functions.h"

static uint rand(uint seed){
	seed ^= seed << 21;
	seed ^= seed >> 35;
	seed ^= seed << 4;
	return seed;
}