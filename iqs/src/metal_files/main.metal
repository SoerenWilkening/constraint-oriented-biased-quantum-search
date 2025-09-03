#include "/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/metal_functions.h"

#define MAXCLAUSESIZE 5 // maximum 4 variables in clause -> maybe overkill
#define MAXINTEGER 10

static inline uint rand(uint seed){
	seed ^= seed << 21;
	seed ^= seed >> 35;
	seed ^= seed << 4;
	return seed;
}

static inline void set_bit( device state_32_t *state,
					 uint state_index,
					 uint state_data[MAXINTEGER],
					 uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	state_data[index] |= mask;
}

static inline uint get_bit(const device state_32_t *state,
					uint state_index,
					const uint state_data[MAXINTEGER],
					uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	return (state_data[index] & mask) != 0;
}

static inline void flip_bit(device state_32_t *state,
							uint state_index,
							uint state_data[MAXINTEGER],
							uint bit
							){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	state_data[index] ^= mask;
}

static inline uint first_clause_index(const device uint *con_clause_offset, size_t C) {
	uint c = (C != 0);
	return c * con_clause_offset[C - 1];
}

static inline uint first_variable_index(uint cls, uint clause_offset) {
	if (cls == 0) return clause_offset * (MAXCLAUSESIZE - 1);
	return clause_offset * (MAXCLAUSESIZE - 1) + (MAXCLAUSESIZE - 1) * cls;
}

static inline uint variable_index(uint cls, uint k, uint clause_offset) {
	return first_variable_index(cls, clause_offset) + k;
}

static inline int objective_value(
                    const device int *obj_factors,
                    const device uint *obj_num_clauses,
                    const device uint *obj_clause_offset,
                    const device uint *obj_clause_length,
                    const device uint *obj_variable_offset,
                    const device uint *obj_variables,
                    const device state_32_t *state,
                    uint state_index,
                    const uint state_data[MAXINTEGER]
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


static inline int constraint_violation(
                    const device int *con_factors,
                    const device uint *con_num_constraints,
                    const device uint *con_num_clauses,
                    const device uint *con_clause_offset,
                    const device uint *con_clause_length,
                    const device uint *con_variable_offset,
                    const device uint *con_variables,
                    const device int *rhs,
                    const device state_32_t *state,
                    uint state_index,
                    const uint state_data[MAXINTEGER],
                    uint cnstr
                    ) {
	int total = 0;
	uint clause_offset = first_clause_index(con_clause_offset, cnstr);
	for (uint cl = 0; cl < con_num_clauses[cnstr]; ++cl) {
		uint clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		uint assigned = 1;
		for (uint k = 0; k < con_clause_length[clause_index]; ++k) {
			uint var = con_variables[variable_index(cl, k, clause_offset)];
			assigned &= get_bit(state, state_index, state_data, var);
		}
		int sign = -2 * (con_factors[clause_index] < 0) + 1;
		int ass = (sign < 0) * (1 - int(assigned)) + (sign >= 0) * int(assigned);
		total += sign * con_factors[clause_index] * ass;
	}
	return rhs[cnstr] - total;
	//return total;
}




kernel void add_arrays(device state_32_t *state [[ buffer(0) ]], // states to store new assignment in
                       device uint *state_data [[ buffer(1) ]],  //
                       const device uint *num_integers [[ buffer(2) ]],  //
                       const device uint *move_length [[ buffer(3) ]],  //
                       const device uint *move_offset [[ buffer(4) ]],  //
                       const device uint *move_entries [[ buffer(5) ]],  //
                       const device uint *first_index [[ buffer(6) ]],  //
                       const device uint *last_index [[ buffer(7) ]],  //
                       const device int *obj_factors [[ buffer(8) ]],
                       const device uint *obj_num_clauses [[ buffer(9) ]],
                       const device uint *obj_clause_offset [[ buffer(10) ]],
                       const device uint *obj_clause_length [[ buffer(11) ]],
                       const device uint *obj_variable_offset [[ buffer(12) ]],
                       const device uint *obj_variables [[ buffer(13) ]],
                       const device int *con_factors [[ buffer(14) ]],
                       const device uint *con_num_constraints [[ buffer(15) ]],
                       const device uint *con_num_clauses [[ buffer(16) ]],
                       const device uint *con_clause_offset [[ buffer(17) ]],
                       const device uint *con_clause_length [[ buffer(18) ]],
                       const device uint *con_variable_offset [[ buffer(19) ]],
                       const device uint *con_variables [[ buffer(20) ]],
                       const device int *rhs [[ buffer(21) ]],
                       device uint *accepted_move [[ buffer(22) ]],
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {
	uint seed = id + 1;

    uint state_copy[MAXINTEGER];
    for (int i = 0; i < num_integers[0]; i++) state_copy[i] = state_data[i];

    int initial = INT_MAX;
    int tot_feasible = 0;

	for (uint index = first_index[id]; index < last_index[id]; index++){
	// for (uint index = first_index[id]; index < first_index[id] + 1; index++){

		// flip bits
		for (int i = 0; i < move_length[index]; i++) flip_bit(state, id, state_copy, move_entries[move_offset[index] + i]);

		// do the computation
		int total_violation = 0;
		for (int cnstr = 0; cnstr < con_num_constraints[0]; cnstr++){
            int violation = constraint_violation(
                con_factors,
                con_num_constraints,
                con_num_clauses,
                con_clause_offset,
                con_clause_length,
                con_variable_offset,
                con_variables,
                rhs,
                state,
                id,
                state_copy,
                cnstr
            );
            total_violation -= (violation < 0) * violation; // add all violations
        }
        uint feasible = (total_violation <= 0);
        uint objective = objective_value(
            obj_factors,
            obj_num_clauses,
            obj_clause_offset,
            obj_clause_length,
            obj_variable_offset,
            obj_variables,
            state,
            id,
            state_copy
        );

        // if feasible: use objective value, otherwise constraint violation
		int obj = feasible * objective + (!feasible) * total_violation;

		// accept if:
		//  1) !tot_feasible & feasible -> obj doesnt matter
		//  2) (tot_feasible & feasible | !tot_feasible & !feasible) & (obj < initial)
		int accept = (!tot_feasible & feasible) | ((tot_feasible & feasible | !tot_feasible & !feasible) & (obj < initial));
		initial = (accept) * obj + (!accept) * initial;

		accepted_move[id] = (accept) * index + (!accept) * accepted_move[id];

        tot_feasible |= feasible;

		// unflip bits
		for (int i = 0; i < move_length[index]; i++) flip_bit(state, id, state_copy, move_entries[move_offset[index] + i]);
	}
    state[id].tot_profit = initial;
    state[id].feasible = tot_feasible;
}

// 0: [-23 0 0 ]
// 1: [-46 1 0 ]
// 2: [-92 2 0 ]
// 3: [-184 3 0 ]
// 4: [-46 0 1 ]
// 5: [-92 1 1 ]
// 6: [-184 2 1 ]