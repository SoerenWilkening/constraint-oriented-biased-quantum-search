#include <stdio.h>
#include "exec_metal.h"

#define size  1024

static inline void flip_bit(
		uint *state_data,
		uint bit
) {
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)));
	state_data[index] ^= mask;
}

static inline uint get_bit_32(
		const uint *state_data,
		uint bit){
	uint index = bit >> 5;
	uint mask = (1 << (bit - (index << 5)) );
	return (state_data[index] & mask) != 0;
}

static inline uint first_clause_index_32(const uint32_t *con_clause_offset, size_t C) {
	uint c = (C != 0);
	return c * con_clause_offset[C - 1];
}

static inline int32_t constraint_violation_32_bit(
		const int32_t *con_factors,
		const uint32_t *con_num_constraints,
		const uint32_t *con_num_clauses,
		const uint32_t *con_clause_offset,
		const uint32_t *con_clause_length,
		const uint32_t *con_variable_offset,
		const uint32_t *con_variables,
		const int32_t *rhs,
		const uint32_t *state_data,
		uint32_t cnstr
) {
	int total = 0;
	uint clause_offset = first_clause_index_32(con_clause_offset, cnstr);
	for (uint cl = 0; cl < con_num_clauses[cnstr]; ++cl) {
		uint clause_index = clause_offset + cl;

		// check, if every item of a clause is assigned
		uint assigned = 1;
		for (uint k = 0; k < con_clause_length[clause_index]; ++k) {
			uint var = con_variables[variable_index(cl, k, clause_offset)];
			assigned &= get_bit_32(state_data, var);
		}
		int sign = -2 * (con_factors[clause_index] < 0) + 1;
		int ass = (sign < 0) * (1 - assigned) +(sign >= 0) * assigned;
		total += sign * con_factors[clause_index] * ass;
	}
	return rhs[cnstr] - total;
}

move_gpu_t move_list(int d, int n, int *total_count, int *num_moves) {
	int count = 0;
	int32_t *comb = malloc(d * sizeof(int16_t));
	for (int k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int i = 0; i < k; ++i) comb[i] = i;
		while (1) {
			int i = k - 1;
			while (i >= 0 && comb[i] == n - k + i) i--;
			*total_count += k;
			*num_moves += 1;
			if (i < 0) break; // All combinations done
			comb[i]++;
			for (int j = i + 1; j < k; ++j) comb[j] = comb[j - 1] + 1;
		}
	}
	move_gpu_t move;
	move.moves = malloc(*total_count * sizeof(int32_t));
	move.length = malloc(*num_moves * sizeof(int32_t));
	move.offset = malloc(*num_moves * sizeof(int32_t));
	count = 0;
	int index = 0;
	int32_t offset = 0;
	free(comb);
	comb = malloc(d * sizeof(int32_t));

	for (int32_t k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int32_t i = 0; i < k; ++i) comb[i] = i;
		while (1) {
			move.length[index] = k;
			move.offset[index] = offset;
			offset += k;
			for (int i = 0; i < k; ++i) move.moves[count + i] = comb[i];
//			memcpy(&move.moves[count], comb, k * sizeof(int16_t));
			index++;
			count += k;

			int i = k - 1;
			while (i >= 0 && comb[i] == n - k + i) i--;
			if (i < 0) break; // All combinations done
			comb[i]++;
			for (int j = i + 1; j < k; ++j) comb[j] = comb[j - 1] + 1;
		}
	}
	free(comb);
	return move;
}

id <MTLTexture> Make1DTextureFromBuffer(id <MTLBuffer> buffer,
                                        NSUInteger count,
                                        MTLPixelFormat format,
                                        NSUInteger elementSize) {
	if (count == 0) {
		return nil; // nothing to make
	}
	const NSUInteger maxWidth = 16384; // Metal 2D texture limit

	// Choose width and height
	NSUInteger width = (count < maxWidth) ? count : maxWidth;
	NSUInteger height = (count + width - 1) / width; // ceil(count / width)

	MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:format width:width height:height mipmapped:NO];
	desc.usage = MTLTextureUsageShaderRead;
	NSUInteger rowBytes = width * elementSize;
	NSUInteger alignedRowBytes = ((rowBytes + 255) / 256) * 256;
	id <MTLTexture> tex = [buffer newTextureWithDescriptor:desc offset:0 bytesPerRow:alignedRowBytes];
	return tex;
}

gpu_info_t inti_info(int n, int k, new_constraints_t *obj, new_constraints_t *con) {
	gpu_info_t info;

	info.device = MTLCreateSystemDefaultDevice();
	info.queue = [info.device newCommandQueue];

	chdir([@"/Users/sorenwilkening/Desktop/improved_quantum_search/iqs/src/metal_files/" UTF8String]);
	// Step 3: Load the Metal kernel
	NSError *error = nil;
	NSString *metalSource = [NSString stringWithContentsOfFile:@"main.metal"
	                                                  encoding:NSUTF8StringEncoding
	                                                     error:&error];
	info.library = [info.device newLibraryWithSource:metalSource options:nil error:&error];
	info.kernelFunction = [info.library newFunctionWithName:@"add_arrays"];
	NSLog(@"Failed to read Metal source: %@", error);
	info.pipelineState = [info.device newComputePipelineStateWithFunction:info.kernelFunction error:&error];


	int32_t number_integers[1] = {n / 32 + 1};
	state_32_t state[size];
	for (int i = 0; i < size; ++i) {
		state[i].tot_profit = 0;
		state[i].feasible = 0;
		state[i].x_offset = number_integers[0] * i;
	}

	int num_moves = 0;
	int num_entries = 0;
	info.move = move_list(k, n, &num_entries, &num_moves);

	uint32_t moves_per_thread = num_moves / size;
	uint32_t leftover = num_moves % size;        // leftover items to distribute
	uint32_t first_index[size];
	uint32_t last_index[size];
	for (int16_t i = 0; i < size; ++i) {
		if (i < leftover) {
			first_index[i] = i * (moves_per_thread + 1);
			last_index[i] = first_index[i] + (moves_per_thread + 1);
		} else {
			first_index[i] = i * moves_per_thread + leftover;
			last_index[i] = first_index[i] + moves_per_thread;
		}
	}

	printf("lengths = %d %d %d\n", obj->positive_array_length, obj->negative_array_length, obj->array_length);

	info.state = [info.device newBufferWithBytes:state length:size *
	                                                          sizeof(state_32_t) options:MTLResourceStorageModeShared];
	// requires only a single copy of the state data
	info.state_data = [info.device newBufferWithLength:number_integers[0] *
	                                                   sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.num_integers = [info.device newBufferWithBytes:number_integers length:sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.move_length = [info.device newBufferWithBytes:info.move.length length:num_moves *
	                                                                           sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.move_offset = [info.device newBufferWithBytes:info.move.offset length:num_moves *
	                                                                           sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.move_entries = [info.device newBufferWithBytes:info.move.moves length:num_entries *
	                                                                           sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.first_move = [info.device newBufferWithBytes:first_index length:size *
	                                                                     sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.last_move = [info.device newBufferWithBytes:last_index length:size *
	                                                                   sizeof(uint32_t) options:MTLResourceStorageModeShared];

	// create 32 bit factors
	int32_t factors[obj->total_clauses];
	for (int i = 0; i < obj->total_clauses; ++i) factors[i] = (int32_t) obj->factors[i];
	info.factors = [info.device newBufferWithBytes:factors length:obj->total_clauses *
	                                                              sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.num_clauses = [info.device newBufferWithBytes:obj->num_clauses length:obj->num_constraints *
	                                                                           sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.clause_offset = [info.device newBufferWithBytes:obj->clause_offset length:obj->num_constraints *
	                                                                               sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.clause_length = [info.device newBufferWithBytes:obj->clause_length length:obj->total_clauses *
	                                                                               sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.variable_offset = [info.device newBufferWithBytes:obj->variable_offset length:obj->total_clauses *
	                                                                                   sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.variables = [info.device newBufferWithBytes:obj->variables length:obj->total_variables *
	                                                                       sizeof(uint32_t) options:MTLResourceStorageModeShared];

	// do the same for the constraints
	int32_t con_factors[con->total_clauses];
	for (int i = 0; i < con->total_clauses; ++i) con_factors[i] = (int32_t) con->factors[i];
	info.con_factors = [info.device newBufferWithBytes:con_factors length:con->total_clauses *
	                                                                      sizeof(int32_t) options:MTLResourceStorageModeShared];

	uint32_t con_num_constraints[1] = {con->num_constraints};
	info.con_num_constraints = [info.device newBufferWithBytes:con_num_constraints length:sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.con_num_clauses = [info.device newBufferWithBytes:con->num_clauses length:con->num_constraints *
	                                                                               sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.con_clause_offset = [info.device newBufferWithBytes:con->clause_offset length:con->num_constraints *
	                                                                                   sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.con_clause_length = [info.device newBufferWithBytes:con->clause_length length:con->total_clauses *
	                                                                                   sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.con_variable_offset = [info.device newBufferWithBytes:con->variable_offset length:con->total_clauses *
	                                                                                       sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.con_variables = [info.device newBufferWithBytes:con->variables length:con->total_variables *
	                                                                           sizeof(uint32_t) options:MTLResourceStorageModeShared];

	int32_t rhs[con->num_constraints];
	for (int i = 0; i < con->num_constraints; ++i) rhs[i] = (int32_t) con->rhs[i];
	info.rhs = [info.device newBufferWithBytes:rhs length:con->num_constraints *
	                                                      sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.accepted_move = [info.device newBufferWithLength:size * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	uint32_t state_data[number_integers[0]];
	memset(state_data, 0, number_integers[0] * sizeof(uint32_t));
	int32_t cur_violation[con->num_constraints];
	for (int i = 0; i < con->num_constraints; ++i) {
		cur_violation[i] = con->rhs[i];
	}

	info.cur_violation = [info.device newBufferWithBytes:cur_violation length:con->num_constraints * sizeof(int32_t) options:MTLResourceStorageModeShared];

	info.obj_positive_indices = [info.device   newBufferWithBytes:obj->positive_indices length:
			obj->positive_array_length * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.obj_negative_indices = [info.device   newBufferWithBytes:obj->negative_indices length:
			obj->negative_array_length * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.obj_positive_offsets = [info.device newBufferWithBytes:obj->positive_offsets length:obj->array_length *
	                                                                                         sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.obj_negative_offsets = [info.device newBufferWithBytes:obj->negative_offsets length:obj->array_length *
	                                                                                         sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.obj_num_positive_indices = [info.device newBufferWithBytes:obj->num_positive_indices length:obj->array_length *
	                                                                                                 sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.obj_num_negative_indices = [info.device newBufferWithBytes:obj->num_negative_indices length:obj->array_length *
	                                                                                                 sizeof(uint32_t) options:MTLResourceStorageModeShared];

	id <MTLBuffer> con_positive_indices = [info.device newBufferWithBytes:con->positive_indices length:
			con->positive_array_length * sizeof(uint32_t)         options:MTLResourceStorageModeShared];
	id <MTLBuffer> con_negative_indices = [info.device newBufferWithBytes:con->negative_indices length:
			con->negative_array_length * sizeof(uint32_t)         options:MTLResourceStorageModeShared];
	id <MTLBuffer> con_positive_offsets = [info.device newBufferWithBytes:con->positive_offsets length:
			con->array_length * sizeof(uint32_t)                  options:MTLResourceStorageModeShared];
	id <MTLBuffer> con_negative_offsets = [info.device newBufferWithBytes:con->negative_offsets length:
			con->array_length * sizeof(uint32_t)                  options:MTLResourceStorageModeShared];
	id <MTLBuffer> con_num_positive_indices = [info.device newBufferWithBytes:con->num_positive_indices length:
			con->array_length * sizeof(uint32_t)                      options:MTLResourceStorageModeShared];
	id <MTLBuffer> con_num_negative_indices = [info.device newBufferWithBytes:con->num_negative_indices length:
			con->array_length * sizeof(uint32_t)                      options:MTLResourceStorageModeShared];
	info.con_positive_indices = Make1DTextureFromBuffer(con_positive_indices, con->positive_array_length,
	                                                    MTLPixelFormatR32Uint, sizeof(int32_t));
	info.con_negative_indices = Make1DTextureFromBuffer(con_negative_indices, con->negative_array_length,
	                                                    MTLPixelFormatR32Uint, sizeof(int32_t));
	info.con_positive_offsets = Make1DTextureFromBuffer(con_positive_offsets, con->array_length, MTLPixelFormatR32Uint,
	                                                    sizeof(int32_t));
	info.con_negative_offsets = Make1DTextureFromBuffer(con_negative_offsets, con->array_length, MTLPixelFormatR32Uint,
	                                                    sizeof(int32_t));
	info.con_num_positive_indices = Make1DTextureFromBuffer(con_num_positive_indices, con->array_length,
	                                                        MTLPixelFormatR32Uint, sizeof(int32_t));
	info.con_num_negative_indices = Make1DTextureFromBuffer(con_num_negative_indices, con->array_length,
	                                                        MTLPixelFormatR32Uint, sizeof(int32_t));


	printf("%d\n", con->num_positive_indices[10]);

	return info;
}

void reset_buffer(id <MTLBuffer> buffer) {
	int *content = (int *) [buffer contents];
	int items = (int) [buffer length] / sizeof(int);
	for (int i = 0; i < items; ++i) content[i] = 0;
	[buffer didModifyRange:NSMakeRange(0, items * sizeof(int))];
}

void print_buffer(id <MTLBuffer> buffer) {
	int *content = (int *) [buffer contents];
	int items = (int) [buffer length] / sizeof(int);
	for (int i = 0; i < items; ++i) printf("%4d ", content[i]);
	printf("\n");
}

void run_kernel(gpu_info_t *info) {

	CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();

	id <MTLCommandBuffer> commandBuffer = [info->queue commandBuffer];

	id <MTLComputeCommandEncoder> compute_encoder = [commandBuffer computeCommandEncoder];
	[compute_encoder setComputePipelineState:info->pipelineState];

	[compute_encoder setBuffer:info->state offset:0 atIndex:0];
	[compute_encoder setBuffer:info->state_data offset:0 atIndex:1];
	[compute_encoder setBuffer:info->num_integers offset:0 atIndex:2];

	[compute_encoder setBuffer:info->move_length offset:0 atIndex:3];
	[compute_encoder setBuffer:info->move_offset offset:0 atIndex:4];
	[compute_encoder setBuffer:info->move_entries offset:0 atIndex:5];

	[compute_encoder setBuffer:info->first_move offset:0 atIndex:6];
	[compute_encoder setBuffer:info->last_move offset:0 atIndex:7];

	[compute_encoder setBuffer:info->factors offset:0 atIndex:8];
	[compute_encoder setBuffer:info->num_clauses offset:0 atIndex:9];
	[compute_encoder setBuffer:info->clause_offset offset:0 atIndex:10];
	[compute_encoder setBuffer:info->clause_length offset:0 atIndex:11];
	[compute_encoder setBuffer:info->variable_offset offset:0 atIndex:12];
	[compute_encoder setBuffer:info->variables offset:0 atIndex:13];

	[compute_encoder setBuffer:info->con_factors offset:0 atIndex:14];
	[compute_encoder setBuffer:info->con_num_constraints offset:0 atIndex:15];
	[compute_encoder setBuffer:info->con_num_clauses offset:0 atIndex:16];
	[compute_encoder setBuffer:info->con_clause_offset offset:0 atIndex:17];
	[compute_encoder setBuffer:info->con_clause_length offset:0 atIndex:18];
	[compute_encoder setBuffer:info->con_variable_offset offset:0 atIndex:19];
	[compute_encoder setBuffer:info->con_variables offset:0 atIndex:20];
	[compute_encoder setBuffer:info->rhs offset:0 atIndex:21];

	[compute_encoder setBuffer:info->accepted_move offset:0 atIndex:22];

	[compute_encoder setBuffer:info->obj_positive_indices offset:0 atIndex:23];
	[compute_encoder setBuffer:info->obj_negative_indices offset:0 atIndex:24];
	[compute_encoder setBuffer:info->obj_positive_offsets offset:0 atIndex:25];
	[compute_encoder setBuffer:info->obj_negative_offsets offset:0 atIndex:26];
	[compute_encoder setBuffer:info->obj_num_positive_indices offset:0 atIndex:27];
	[compute_encoder setBuffer:info->obj_num_negative_indices offset:0 atIndex:28];

	[compute_encoder setTexture:info->con_positive_indices atIndex:0];
	[compute_encoder setTexture:info->con_negative_indices atIndex:1];
	[compute_encoder setTexture:info->con_positive_offsets atIndex:2];
	[compute_encoder setTexture:info->con_negative_offsets atIndex:3];
	[compute_encoder setTexture:info->con_num_positive_indices atIndex:4];
	[compute_encoder setTexture:info->con_num_negative_indices atIndex:5];

	[compute_encoder setBuffer:info->cur_violation offset:0 atIndex:29];

	CFAbsoluteTime end = CFAbsoluteTimeGetCurrent();
//	printf("time to compute encode %f\n", end - start);

	MTLSize grid_size = MTLSizeMake(size, 1, 1);
	NSUInteger group_size = info->pipelineState.maxTotalThreadsPerThreadgroup;
	group_size = group_size > size ? size : group_size;
	MTLSize thread_group_size = MTLSizeMake(group_size, 1, 1);
	[compute_encoder dispatchThreads:grid_size threadsPerThreadgroup:thread_group_size];

	NSError *error = nil;
	[compute_encoder endEncoding];
	[commandBuffer commit];
	[commandBuffer waitUntilCompleted];

	[compute_encoder release];
	[commandBuffer release];
}

int exec_gpu(int n, new_constraints_t *obj, new_constraints_t *con) {
	int num_integers = n / 32 + 1;
	int k = 2;
	gpu_info_t info = inti_info(n, k, obj, con);

	CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
	for (int reps = 0; reps < 10; ++reps) {
		run_kernel(&info);
		state_32_t *state = (state_32_t *) [info.state contents];
		uint32_t *state_data = (uint32_t *) [info.state_data contents];
		uint32_t *accepted_move = (uint32_t *) [info.accepted_move contents];

		int index = 0;
		CFAbsoluteTime end = CFAbsoluteTimeGetCurrent();
//		printf("%f ", (end - start));
		int32_t initial = INT32_MAX;
		uint tot_feasible = 0;
		for (int i = 0; i < size; ++i) {
//			printf("%d %d\n", i, state[i].tot_profit);
			uint accept = (!tot_feasible & state[i].feasible) |
			              ((tot_feasible & state[i].feasible | !tot_feasible & !state[i].feasible) &
			               (state[i].tot_profit < initial));
			if (accept) {
				initial = state[i].tot_profit;
				tot_feasible |= state[i].feasible;
				index = i;
			}
		}
		end = CFAbsoluteTimeGetCurrent();
		printf("%d %d %d %f\n", reps, state[index].tot_profit, state[index].feasible, (end - start));
		uint move_index = accepted_move[index];
		for (int i = 0; i < info.move.length[move_index]; ++i) {
			flip_bit(state_data, info.move.moves[info.move.offset[move_index] + i]);
		}
		int32_t *fac = (int32_t *) [info.con_factors contents];
		int32_t *rhs = (int32_t *) [info.rhs contents];
		int32_t *cur_violation = (int32_t *) [info.cur_violation contents];
		for (int i = 0; i < con->num_constraints; ++i) {
			cur_violation[i] = constraint_violation_32_bit(
						fac,
						&con->num_constraints,
						con->num_clauses,
						con->clause_offset,
						con->clause_length,
						con->variable_offset,
						con->variables,
						rhs,
						state_data,
						i
					);
		}
		[info.cur_violation didModifyRange:NSMakeRange(0, con->num_constraints * sizeof(state_32_t))];

		state[0].tot_profit = state[index].tot_profit;
		[info.state didModifyRange:NSMakeRange(0, sizeof(state_32_t))];
		[info.state_data didModifyRange:NSMakeRange(0, num_integers * sizeof(int32_t))];

//		printf("\n");
	}


	return 0;
}