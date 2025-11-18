#include "/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/metal_functions.h"

using namespace metal;

#define MAXCLAUSESIZE 5 // maximum 4 variables in clause -> maybe overkill
#define MAXINTEGER 32
#define maxWidth 16384

static inline uint rand(uint seed){
	seed ^= seed << 21;
	seed ^= seed >> 35;
	seed ^= seed << 4;
	return seed;
}

static inline void set_bit(
					 uint state_data[],
					 uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	state_data[index] |= mask;
}

static inline uint get_bit(
					const uint state_data[],
					uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	return (state_data[index] & mask) != 0;
}

static inline void flip_bit(
							uint state_data[],
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
                    const uint state_data[MAXINTEGER]
                    ) {
	// compute objective value of given solution
	int total = 0;
	for (uint cl = 0; cl < obj_num_clauses[0]; ++cl) {

		// check, if every item of a clause is assigned
	    uint assigned = 1;
	    for (uint k = 0; k < obj_clause_length[cl]; ++k) {
	    	uint var = obj_variables[variable_index(cl, k, 0)];
	    	assigned &= get_bit(state_data, var);
	    }
        total += obj_factors[cl] * assigned;
	}
    return total;
}

#define OVERLAPS 5

static inline uint var_in_array(const device uint *changes, uint length, uint var){
    uint is_contained = 0;
    for(uint i = 0; i < length; i++){
        is_contained |= (changes[i] == var);
    }
    return is_contained;
}

static inline int objective_value_improved(
                    const device int *obj_factors,
                    const device uint *obj_num_clauses,
                    const device uint *obj_clause_offset,
                    const device uint *obj_clause_length,
                    const device uint *obj_variable_offset,
                    const device uint *obj_variables,
                    const uint old_state_data[MAXINTEGER],
                    const uint new_state_data[MAXINTEGER],
                    const device uint *obj_indices,
                    const device uint *obj_offsets,
                    const device uint *obj_num_indices,
                    uint num_changes,
                    const device uint *changes
                    ) {

    int total = 0;

    // compute only the adjusted value
    for(uint i = 0; i < num_changes; i++){
        uint item = changes[i];
        for (uint cls = 0; cls < obj_num_indices[item]; cls++){
            uint old_assigned = 1;
            uint new_assigned = 1;
            uint clause_index = obj_indices[obj_offsets[item] + cls];
            //uint already_investigated = get_bit(assigned, clause_index);
            uint already_investigated = 0;

            // compute if term was satisfied or is satisfied now
            for (uint j = 0; j < obj_clause_length[clause_index]; j++){
                uint var = obj_variables[variable_index(clause_index, j, 0)];
                old_assigned &= get_bit(old_state_data, var);
                new_assigned &= get_bit(new_state_data, var);

                //
                already_investigated |= var_in_array(changes, num_changes, var) & (var != item) & (i > 0);
            }
            uint subtract = old_assigned & !new_assigned;
            uint add = (!old_assigned) & new_assigned;
            total += obj_factors[clause_index] * int(add - subtract) * int(!already_investigated);
            // total += obj_factors[clause_index] * int(add) * int(!already_investigated);
            // set_bit(assigned, clause_index);
        }
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
			assigned &= get_bit(state_data, var);
		}
		int sign = -2 * (con_factors[clause_index] < 0) + 1;
		int ass = (sign < 0) * (1 - int(assigned)) + (sign >= 0) * int(assigned);
		total += sign * con_factors[clause_index] * ass;
	}
	return rhs[cnstr] - total;
	//return total;
}


static inline int constraint_violation_improved(
                    const device int *con_factors,
                    const device uint *con_num_constraints,
                    const device uint *con_num_clauses,
                    const device uint *con_clause_offset,
                    const device uint *con_clause_length,
                    const device uint *con_variable_offset,
                    const device uint *con_variables,
                    const uint old_state_data[MAXINTEGER],
                    const uint new_state_data[MAXINTEGER],
                    texture2d<uint, access::read> con_indices,
                    texture2d<uint, access::read> con_offsets,
                    texture2d<uint, access::read> con_num_indices,
                    uint num_changes,
                    const device uint *changes,
                    uint cnstr
                    ) {

    int total = 0;
    uint C = con_num_constraints[0];
    uint clause_offset = first_clause_index(con_clause_offset, cnstr);
    for(uint i = 0; i < num_changes; i++){
        uint item = changes[i];
        for (uint cls = 0; cls < con_num_indices.read(uint2( (item * C + cnstr) & (maxWidth - 1), (item * C + cnstr) >> 14 )).r; cls++){
            uint off = con_offsets.read(uint2( (item * C + cnstr) & (maxWidth - 1) , (item * C + cnstr) >> 14 )).r;
            uint index = con_indices.read(uint2( (off + cls) & (maxWidth - 1) , (off + cls) >> 14)).r; // index of the clause of constraint cnstr
            uint clause_index = clause_offset + index;

            uint old_assigned = 1;
            uint new_assigned = 1;
            uint already_investigated = 0;

            for (uint j = 0; j < con_clause_length[clause_index]; j++){
                uint var = con_variables[variable_index(index, j, clause_offset)];
                old_assigned &= get_bit(old_state_data, var);
                new_assigned &= get_bit(new_state_data, var);

                already_investigated |= var_in_array(changes, num_changes, var) & (var != item) & (i > 0);
            }
            int sign = -2 * (con_factors[clause_index] < 0) + 1;
            uint subtract = (sign > 0) & old_assigned & !new_assigned | ((sign < 0) & uint((1- new_assigned) == 0) & uint((1 - old_assigned) == 1));
            uint add = (sign > 0) & (!old_assigned) & new_assigned | ((sign < 0) & uint((1 - new_assigned) == 1) & uint((1 - old_assigned) == 0));
            total += abs(con_factors[clause_index]) * int(add - subtract) * int(!already_investigated);
        }
    }
    return total;

    // // compute only the adjusted value
    // for(uint i = 0; i < num_changes; i++){
    //     uint item = changes[i];
    //     for (uint cls = 0; cls < obj_num_indices[item]; cls++){
    //         uint old_assigned = 1;
    //         uint new_assigned = 1;
    //         uint clause_index = obj_indices[obj_offsets[item] + cls];
    //         //uint already_investigated = get_bit(assigned, clause_index);
    //         uint already_investigated = 0;
//
    //         // compute if term was satisfied or is satisfied now
    //         for (uint j = 0; j < obj_clause_length[clause_index]; j++){
    //             uint var = obj_variables[variable_index(clause_index, j, 0)];
    //             old_assigned &= get_bit(old_state_data, var);
    //             new_assigned &= get_bit(new_state_data, var);
//
    //             //
    //             already_investigated |= var_in_array(changes, num_changes, var) & (var != item) & (i > 0);
    //         }
    //         uint subtract = old_assigned & !new_assigned;
    //         uint add = (!old_assigned) & new_assigned;
    //         total += obj_factors[clause_index] * int(add - subtract) * int(!already_investigated);
    //         // total += obj_factors[clause_index] * int(add) * int(!already_investigated);
    //         // set_bit(assigned, clause_index);
    //     }
    // }
    // return total;
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
                       const device uint *obj_positive_indices [[ buffer(23) ]],
                       const device uint *obj_negative_indices [[ buffer(24) ]],
                       const device uint *obj_positive_offsets [[ buffer(25) ]],
                       const device uint *obj_negative_offsets [[ buffer(26) ]],
                       const device uint *obj_num_positive_indices [[ buffer(27) ]],
                       const device uint *obj_num_negative_indices [[ buffer(28) ]],
                       texture2d<uint, access::read> con_positive_indices [[ texture(0) ]],
                       texture2d<uint, access::read> con_negative_indices [[ texture(1) ]],
                       texture2d<uint, access::read> con_positive_offsets [[ texture(2) ]],
                       texture2d<uint, access::read> con_negative_offsets [[ texture(3) ]],
                       texture2d<uint, access::read> con_num_positive_indices [[ texture(4) ]],
                       texture2d<uint, access::read> con_num_negative_indices [[ texture(5) ]],
                       const device int *cur_violation [[ buffer(29) ]],
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {
	uint seed = id + 1;
	uint state_copy[MAXINTEGER];
	uint state_copy_unadjusted[MAXINTEGER];
	for (uint i = 0; i < num_integers[0]; i++) state_copy[i] = state_data[i];
	for (uint i = 0; i < num_integers[0]; i++) state_copy_unadjusted[i] = state_data[i];

	int initial = INT_MAX;
	int tot_feasible = 0;
	int total_violation = 0;

	// for (uint i = 0; i < move_length[first_index[id]]; i++) flip_bit(state_copy, move_entries[move_offset[first_index[id]] + i]);
    //for (int cnstr = 0; cnstr < con_num_constraints[0]; cnstr++){
	//     total_violation += rhs[cnstr] - constraint_violation_improved(
	//         con_factors,
    //         con_num_constraints,
    //         con_num_clauses,
    //         con_clause_offset,
    //         con_clause_length,
    //         con_variable_offset,
    //         con_variables,
    //         state_copy_unadjusted,
    //         state_copy,
    //         con_positive_indices,
    //         con_positive_offsets,
    //         con_num_positive_indices,
    //         move_length[first_index[id]],
    //         &move_entries[move_offset[first_index[id]]],
    //         cnstr
	//     );
	//     //total_violation += constraint_violation(
    //     //            con_factors,
    //     //            con_num_constraints,
    //     //            con_num_clauses,
    //     //            con_clause_offset,
    //     //            con_clause_length,
    //     //            con_variable_offset,
    //     //            con_variables,
    //     //            rhs,
    //     //            state_copy,
    //     //            cnstr
    //     //        );
	//}
	//state[id].tot_profit = total_violation;

	for (uint index = first_index[id]; index < last_index[id]; index++){
	//for (uint index = first_index[id]; index < first_index[id] + 1; index++){

		// flip bits
		for (uint i = 0; i < move_length[index]; i++) flip_bit(state_copy, move_entries[move_offset[index] + i]);

		// do the computation
		int total_violation = 0;
		for (int cnstr = 0; cnstr < con_num_constraints[0]; cnstr++){
            //int violation = constraint_violation(
            //    con_factors,
            //    con_num_constraints,
            //    con_num_clauses,
            //    con_clause_offset,
            //    con_clause_length,
            //    con_variable_offset,
            //    con_variables,
            //    rhs,
            //    state_copy,
            //    cnstr
            //);
            int violation = cur_violation[cnstr] - constraint_violation_improved(
                            	         con_factors,
                                         con_num_constraints,
                                         con_num_clauses,
                                         con_clause_offset,
                                         con_clause_length,
                                         con_variable_offset,
                                         con_variables,
                                         state_copy_unadjusted,
                                         state_copy,
                                         con_positive_indices,
                                         con_positive_offsets,
                                         con_num_positive_indices,
                                         move_length[index],
                                         &move_entries[move_offset[index]],
                                         cnstr
                            	     );
            violation -= constraint_violation_improved(
                                         con_factors,
                                         con_num_constraints,
                                         con_num_clauses,
                                         con_clause_offset,
                                         con_clause_length,
                                         con_variable_offset,
                                         con_variables,
                                         state_copy_unadjusted,
                                         state_copy,
                                         con_negative_indices,
                                         con_negative_offsets,
                                         con_num_negative_indices,
                                         move_length[index],
                                         &move_entries[move_offset[index]],
                                         cnstr
                                     );
            total_violation -= (violation < 0) * violation; // add all violations
        }
        uint feasible = (total_violation <= 0);
        int objective = state[0].tot_profit;
        objective += objective_value_improved(
                                         obj_factors,
                                         obj_num_clauses,
                                         obj_clause_offset,
                                         obj_clause_length,
                                         obj_variable_offset,
                                         obj_variables,
                                         state_copy_unadjusted,
                                         state_copy,
                                         obj_positive_indices,
                                         obj_positive_offsets,
                                         obj_num_positive_indices,
                                         move_length[index],
                                         &move_entries[move_offset[index]]
                                         );
        objective += objective_value_improved(
                                         obj_factors,
                                         obj_num_clauses,
                                         obj_clause_offset,
                                         obj_clause_length,
                                         obj_variable_offset,
                                         obj_variables,
                                         state_copy_unadjusted,
                                         state_copy,
                                         obj_negative_indices,
                                         obj_negative_offsets,
                                         obj_num_negative_indices,
                                         move_length[index],
                                         &move_entries[move_offset[index]]
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
		for (uint i = 0; i < move_length[index]; i++) flip_bit(state_copy, move_entries[move_offset[index] + i]);
	}
    state[id].tot_profit = initial;
    state[id].feasible = tot_feasible;
}

// 0 627360 0 627360
// 1 627347 1 627347
// 2 627297 2 627297
// 3 627101 3 627101
// 4 627353 4 627353
// 5 627319 5 627319
// 6 627185 6 627185
// 7 626653 7 626653
// 8 627292 8 627292
// 9 627075 9 627075
// 10 626209 10 626209
// 11 622749 11 622749
// 12 627313 12 627313
// 13 627159 13 627159
// 14 626545 14 626545
// 15 624093 15 624093
// 16 627303 16 627303
// 17 627119 17 627119
// 18 626385 18 626385
// 19 623453 19 623453
// 20 625355 20 625355
// 21 619327 21 619327
// 22 595217 22 595217
// 23 498781 23 498781
// 24 624261 24 624261
// 25 614951 25 614951
// 26 577713 26 577713
// 27 428765 27 428765
// 28 623555 28 623555
// 29 612127 29 612127
// 30 566417 30 566417
// 31 383581 31 383581
// 32 621906 32 621906
// 33 605531 33 605531
// 34 540033 34 540033
// 35 278045 35 278045
// 36 619641