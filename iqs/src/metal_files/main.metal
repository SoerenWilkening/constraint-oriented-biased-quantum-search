#include "/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/metal_functions.h"

#define MAXCLAUSESIZE 5 // maximum 4 variables in clause -> maybe overkill

static inline uint rand(uint seed){
	seed ^= seed << 21;
	seed ^= seed >> 35;
	seed ^= seed << 4;
	return seed;
}

static inline void set_bit( device state_32_t *state,
					 uint state_index,
					 device uint *state_data,
					 uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	state_data[state[state_index].x_offset + index] |= mask;
}

static inline uint get_bit(const device state_32_t *state,
					uint state_index,
					const device uint *state_data,
					uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	return (state_data[state[state_index].x_offset + index] & mask) != 0;;
}

static inline void flip_bit(device state_32_t *state,
							uint state_index,
							device uint *state_data,
							uint bit
							){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	state_data[state[state_index].x_offset + index] ^= mask;
}

static inline uint first_variable_index(uint cls, uint clause_offset) {
	if (cls == 0) return clause_offset * (MAXCLAUSESIZE - 1);
	return clause_offset * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}

static inline uint variable_index(uint cls, uint k, uint clause_offset) {
	return first_variable_index(cls, clause_offset) + k;
}

static inline int objective_value(const device int *obj_factors,
                    const device uint *obj_num_constraints,
                    const device uint *obj_num_clauses,
                    const device uint *obj_clause_offset,
                    const device uint *obj_clause_length,
                    const device uint *obj_variable_offset,
                    const device uint *obj_variables,
                    const device state_32_t *state,
                    uint state_index,
                    const device uint *state_data
                    ) {
	// compute objective value of given solution
	int total = 0;
	for (uint cl = 0; cl < obj_num_clauses[0]; ++cl) {

		// check, if every item of a clause is assigned
	    uint assigned = 1;
	    for (uint k = 0; k < obj_clause_length[cl]; ++k) {
	    	uint var = obj_variables[variable_index(cl, k, 0)];
	    	assigned &= get_bit(state, state_index, state_data, var);
	    }
        total += obj_factors[cl] * assigned;
	}
    return total;
}




kernel void add_arrays(device state_32_t *state [[ buffer(0) ]], // states to store new assignment in
                       device uint *state_data [[ buffer(1) ]],  //
                       const device ushort *move_length [[ buffer(2) ]],  //
                       const device ushort *move_offset [[ buffer(3) ]],  //
                       const device ushort *move_entries [[ buffer(4) ]],  //
                       const device ushort *first_index [[ buffer(5) ]],  //
                       const device ushort *last_index [[ buffer(6) ]],  //
                       const device int *obj_factors [[ buffer(7) ]],
                       const device uint *obj_num_constraints [[ buffer(8) ]],
                       const device uint *obj_num_clauses [[ buffer(9) ]],
                       const device uint *obj_clause_offset [[ buffer(10) ]],
                       const device uint *obj_clause_length [[ buffer(11) ]],
                       const device uint *obj_variable_offset [[ buffer(12) ]],
                       const device uint *obj_variables [[ buffer(13) ]],
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {
	uint seed = id + 1;


	//for (ushort index = first_index[id]; index < last_index[id]; index++){
	for (ushort index = first_index[id]; index < first_index[id] + 1; index++){
		// flip bits
		for (int i = 0; i < move_length[index]; i++) flip_bit(state, id, state_data, move_entries[move_offset[index] + i]);

		// do the computation

        state[id].tot_profit = objective_value(
            obj_factors,
            obj_num_constraints,
            obj_num_clauses,
            obj_clause_offset,
            obj_clause_length,
            obj_variable_offset,
            obj_variables,
            state,
            id,
            state_data
        );

		// unflip bits
		//for (int i = 0; i < move_length[index]; i++) flip_bit(state, id, state_data, move_entries[move_offset[index] + i]);
	}
}

// 0: [-23 0 0 ]
// 1: [-46 1 0 ]
// 2: [-92 2 0 ]
// 3: [-184 3 0 ]
// 4: [-46 0 1 ]
// 5: [-92 1 1 ]
// 6: [-184 2 1 ]