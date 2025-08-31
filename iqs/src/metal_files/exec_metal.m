#include <stdio.h>
#include "exec_metal.h"
#define size  1024

move_gpu_t move_list(int d, int n, int *total_count, int *num_moves) {
	int count = 0;
	int16_t *comb = malloc(d * sizeof(int16_t));
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
	move.moves = malloc(*total_count * sizeof(int16_t));
	move.length = malloc(*num_moves * sizeof(int16_t));
	move.offset = malloc(*num_moves * sizeof(int16_t));
	count = 0;
	int index = 0;
	int16_t offset = 0;
	free(comb);
	comb = malloc(d * sizeof(int16_t));

	for (int16_t k = 1; k <= d; ++k) {
		// Initialize first combination: [0, 1, ..., k-1]
		for (int16_t i = 0; i < k; ++i) comb[i] = i;
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

gpu_info_t inti_info(int n, int k, new_constraints_t *obj){
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


	int number_integers = n / 32 + 1;
	state_32_t state[size];
	for (int i = 0; i < size; ++i) state[i].x_offset = number_integers * i;

	int num_moves = 0;
	int num_entries = 0;
	move_gpu_t move = move_list(k, n, &num_entries, &num_moves);

	uint16_t moves_per_thread = num_moves / size;
	uint leftover  = num_moves % size;        // leftover items to distribute
	uint16_t first_index[size];
	uint16_t last_index[size];
	for (int16_t i = 0; i < size; ++i) {
		if (i < leftover) {
			first_index[i] = i * (moves_per_thread + 1);
			last_index[i]   = first_index[i] + (moves_per_thread + 1);
		} else {
			first_index[i] = i * moves_per_thread + leftover;
			last_index[i]   = first_index[i] + moves_per_thread;
		}
	}

	info.state = [info.device newBufferWithBytes:state length:size * sizeof(state_32_t) options:MTLResourceStorageModeShared];
	info.state_data = [info.device newBufferWithLength:number_integers * size * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.move_length = [info.device newBufferWithBytes:move.length length:num_moves * sizeof(uint16_t) options:MTLResourceStorageModeShared];
	info.move_offset = [info.device newBufferWithBytes:move.offset length:num_moves * sizeof(uint16_t) options:MTLResourceStorageModeShared];
	info.move_entries = [info.device newBufferWithBytes:move.moves length:num_entries * sizeof(uint16_t) options:MTLResourceStorageModeShared];

	info.first_move = [info.device newBufferWithBytes:first_index length:size * sizeof(uint16_t) options:MTLResourceStorageModeShared];
	info.last_move = [info.device newBufferWithBytes:last_index length:size * sizeof(uint16_t) options:MTLResourceStorageModeShared];

	// create 32 bit factors
	int32_t factors[obj->total_clauses];
	for (int i = 0; i < obj->total_clauses; ++i) factors[i] = (int32_t) obj->factors[i];
	info.factors = [info.device newBufferWithBytes:factors length:obj->total_clauses * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	uint32_t num_constraints[1] = {obj->num_constraints};
	info.num_constraints  = [info.device newBufferWithBytes:num_constraints length:sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.num_clauses = [info.device newBufferWithBytes:obj->num_clauses length:obj->num_constraints * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.clause_offset = [info.device newBufferWithBytes:factors length:obj->num_constraints * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info.clause_length = [info.device newBufferWithBytes:obj->clause_length length:obj->total_clauses * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.variable_offset = [info.device newBufferWithBytes:obj->variable_offset length:obj->total_clauses * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	info.variables = [info.device newBufferWithBytes:obj->variables length:obj->total_variables * sizeof(uint32_t) options:MTLResourceStorageModeShared];


	free(move.offset);
	free(move.length);
	free(move.moves);

	return info;
}

void reset_buffer(id <MTLBuffer> buffer){
	int *content = (int *) [buffer contents];
	int items = (int) [buffer length] / sizeof(int);
	for (int i = 0; i < items; ++i) content[i] = 0;
	[buffer didModifyRange:NSMakeRange(0, items * sizeof(int))];
}

void print_buffer(id <MTLBuffer> buffer){
	int *content = (int *) [buffer contents];
	int items = (int) [buffer length] / sizeof(int);
	for (int i = 0; i < items; ++i) printf("%4d " ,content[i]);
	printf("\n");
}

void run_kernel(gpu_info_t *info){

	id <MTLCommandBuffer> commandBuffer = [info->queue commandBuffer];

	id <MTLComputeCommandEncoder> compute_encoder = [commandBuffer computeCommandEncoder];
	[compute_encoder setComputePipelineState:info->pipelineState];

	[compute_encoder setBuffer:info->state offset:0 atIndex:0];
	[compute_encoder setBuffer:info->state_data offset:0 atIndex:1];

	[compute_encoder setBuffer:info->move_length offset:0 atIndex:2];
	[compute_encoder setBuffer:info->move_offset offset:0 atIndex:3];
	[compute_encoder setBuffer:info->move_entries offset:0 atIndex:4];

	[compute_encoder setBuffer:info->first_move offset:0 atIndex:5];
	[compute_encoder setBuffer:info->last_move offset:0 atIndex:6];

	[compute_encoder setBuffer:info->factors offset:0 atIndex:7];
	[compute_encoder setBuffer:info->num_constraints offset:0 atIndex:8];
	[compute_encoder setBuffer:info->num_clauses offset:0 atIndex:9];
	[compute_encoder setBuffer:info->clause_offset offset:0 atIndex:10];
	[compute_encoder setBuffer:info->clause_length offset:0 atIndex:11];
	[compute_encoder setBuffer:info->variable_offset offset:0 atIndex:12];
	[compute_encoder setBuffer:info->variables offset:0 atIndex:13];

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

int exec_gpu(int n, new_constraints_t *obj){
	int num_integers = n / 32 + 1;
	gpu_info_t info = inti_info(n , 3, obj);

	printf("%lld\n", obj->factors[0]);

 	run_kernel(&info);
 	state_32_t *state = (state_32_t *) [info.state contents];
 	uint32_t *state_data = (uint32_t *) [info.state_data contents];
 	for (int i = 0; i < size; ++i) {
 		printf("%d %d ", i, state[i].tot_profit);
 		for (int k = 0; k < num_integers; ++k) {
 			for (int j = 0; j < 32; ++j) {
 				printf("%u", ((1 << j) & state_data[state[i].x_offset + k + j / 32]) != 0);
 			}
 			printf(" ");
 		}
 		printf("\n");
 	}
	return 0;
}

// int main(){
// 	exec_gpu();
//
// 	return 0;
// }