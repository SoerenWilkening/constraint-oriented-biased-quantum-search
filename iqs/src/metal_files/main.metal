//#include <metal_stdlib>
//using namespace metal;
#include "/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/metal_functions.h"
#include "/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/metal_functions.metal"

kernel void add_arrays(device int *pointer [[ buffer(0) ]],       // Current objective value
                       device state_32_t *state [[ buffer(1) ]],
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {
	uint seed = id + 1;
    state[id].tot_profit += rand(seed) % 100;
}