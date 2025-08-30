#include <stdio.h>
#include "exec_metal.h"
#include "obj-c_header.h"
#define size  1024

gpu_info_t inti_info(){
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

	// initialize buffers
	info.pointer = [info.device newBufferWithLength:size * sizeof(int) options:MTLResourceStorageModeShared];
	info.state = [info.device newBufferWithLength:size * sizeof(state_32_t) options:MTLResourceStorageModeShared];

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

	[compute_encoder setBuffer:info->pointer offset:0 atIndex:0];
	[compute_encoder setBuffer:info->state offset:0 atIndex:1];

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

int main(){
	gpu_info_t info = inti_info();

	run_kernel(&info);
	state_32_t *state = (state_32_t *) [info.state contents];
	for (int i = 0; i < size; ++i) {
		printf("%ld\n", state[i].tot_profit);
	}

	return 0;
}