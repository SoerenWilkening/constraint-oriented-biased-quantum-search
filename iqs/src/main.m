#include <stdio.h>
#include <string.h>
#include <mach/mach_time.h>
#include <CommonCrypto/CommonCrypto.h>
#include <time.h>
#include "main.h"

int run_kernel(int reps, int size, int num_integers, int total_reps, int32_t val, uint32_t *x, gpu_info_t *info);

gpu_info_t *init_buffers(   int *constraint, int c_terms,
                            int *objective, int o_terms,
                            double bias, uint32_t globalSeed,
                            int num_integers,
                            char *shader){

    int size = 512;

    char name[1024];

    uint32_t seed[size];
	for (uint i = 0; i < size; i++) {
// 	    seed[i] = globalSeed + arc4random();
	    seed[i] = globalSeed + 100 * i;
	}

	double b[] = {bias};

    gpu_info_t *info = malloc(sizeof(gpu_info_t));

    // Step 1: Create new_val Metal device
	id <MTLDevice> device = MTLCreateSystemDefaultDevice();

	// Step 2: Create new_val command queue
	id <MTLCommandQueue> commandQueue = [device newCommandQueue];

	// Step 3: Load the Metal kernel
	NSError *error = nil;
    NSString *sourceString = [NSString stringWithUTF8String:shader];
	id <MTLLibrary> library = [device newLibraryWithSource:sourceString options:nil error:&error];
	id <MTLFunction> kernelFunction = [library newFunctionWithName:@"add_arrays"];
	id <MTLComputePipelineState> pipelineState = [device newComputePipelineStateWithFunction:kernelFunction error:&error];

	// Step 4: Create buffers
	id <MTLBuffer> cur_val_Buffer = [device newBufferWithLength:sizeof(int) options:MTLResourceStorageModeShared];
	id <MTLBuffer> cur_array_Buffer = [device newBufferWithLength:num_integers * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> new_val_Buffer = [device newBufferWithLength:size * sizeof(int) options:MTLResourceStorageModeShared];
	id <MTLBuffer> arrays_Buffer = [device newBufferWithLength:size * num_integers * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> reps_Buffer = [device newBufferWithLength:sizeof(int) options:MTLResourceStorageModeShared];

	id <MTLBuffer> objective_Buffer = [device newBufferWithBytes:objective length: o_terms * sizeof(int) options:MTLResourceStorageModeShared];
	id <MTLBuffer> constraint_Buffer = [device newBufferWithBytes:constraint length: c_terms * sizeof(int) options:MTLResourceStorageModeShared];

	id <MTLBuffer> bias_Buffer = [device newBufferWithBytes:b length:sizeof(float) options:MTLResourceStorageModeShared];
	id <MTLBuffer> seed_Buffer = [device newBufferWithBytes:seed length:size * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	info->commandQueue = commandQueue;
	info->pipelineState = pipelineState;
	info->cur_val_Buffer = cur_val_Buffer;
	info->cur_array_Buffer = cur_array_Buffer;
	info->new_val_Buffer = new_val_Buffer;
	info->arrays_Buffer = arrays_Buffer;
	info->reps_Buffer = reps_Buffer;
	info->objective_Buffer = objective_Buffer;
	info->constraint_Buffer = constraint_Buffer;
	info->bias_Buffer = bias_Buffer;
	info->seed_Buffer = seed_Buffer;

    return info;
}

int gpu_qmax_search_c(int n, int M,
                    int *constraint, int c_terms,
                    int *objective, int o_terms,
                    int cur, uint32_t *arr,
                    gpu_info_t *gpu_info,
                    callback_t callback,
                    int *total_applications) {
    uint64_t t1 = mach_absolute_time();
	int num_integers = n / 32 + 1;

    char name[1024];

	const int size = 512;

	uint32_t new_array[num_integers];
	memset(new_array, 0, num_integers * sizeof(uint32_t));

	uint32_t cur_array[num_integers];
	int32_t cur_val[] = {cur};
	for (int i = 0; i < num_integers; i++) {cur_array[i] = arr[i];}

	/*
	 * Run QMaxSearch routine:
	 *
	 * */
	unsigned int qtg_applications = 0;
	unsigned int m_tot = 0;
	unsigned int rounds = 0;
	double lambda = 6. / 5;
	int res;

	while (m_tot < M) {
		int m = ceil(pow(lambda, rounds));
		int j = rand() % (m + 1);
		m_tot += 2 * j + 1;
		qtg_applications += 2 * j + 1;
		rounds++;

		int reps = MAX((int) ceil(4 * j * j / size), 1);
		res = run_kernel(reps, size, num_integers, 4 * j * j, cur_val[0], cur_array, gpu_info);
		if (res != -1) {
		    uint64_t t_step = mach_absolute_time();
		    mach_timebase_info_data_t info;
            mach_timebase_info(&info);
            uint64_t elapsedNano = (t_step - t1) * info.numer / info.denom;
            double elapsedSec = elapsedNano / 1.0e9;

            if (callback){
                callback(res, qtg_applications, elapsedSec);
            }
			cur_val[0] = res;
			rounds = 0;
			m_tot = 0;
		}
	}

    uint64_t t2 = mach_absolute_time();
    mach_timebase_info_data_t info;
    mach_timebase_info(&info);
    uint64_t elapsedNano = (t2 - t1) * info.numer / info.denom;
    double elapsedSec = elapsedNano / 1.0e9;

    *total_applications = qtg_applications;

	return cur_val[0];
}

int run_kernel(int reps,
               int size,
               int num_integers,
               int total_reps,
               int32_t val,
               uint32_t *x,
               gpu_info_t *info) {

    int * new_values = (int *) [info->new_val_Buffer contents];
    for (int i = 0; i < size; i++){new_values[i] = 0;}
    [info->new_val_Buffer didModifyRange:NSMakeRange(0, size)];

	// update number of repetitions per thread
	int *repetitions = (int *) [info->reps_Buffer contents];
	repetitions[0] = reps;
	[info->reps_Buffer didModifyRange:NSMakeRange(0, 1)];

	// 1. Create a command buffer
	id <MTLCommandBuffer> commandBuffer = [info->commandQueue commandBuffer];

	// 2. Create a compute command encoder
	id <MTLComputeCommandEncoder> computeEncoder = [commandBuffer computeCommandEncoder];
	[computeEncoder setComputePipelineState:info->pipelineState];

    int *cur_val = (int *) [info->cur_val_Buffer contents];
    cur_val[0] = val;
	[info->cur_val_Buffer didModifyRange:NSMakeRange(0, 1)];

    uint32_t *cur_array = (uint32_t *) [info->cur_array_Buffer contents];
    for (int j = 0; j < num_integers; ++j) cur_array[j] = x[j];
    [info->cur_array_Buffer didModifyRange:NSMakeRange(0, num_integers)];

	// 3. Set the buffers
	[computeEncoder setBuffer:info->cur_val_Buffer offset:0 atIndex:0];
	[computeEncoder setBuffer:info->cur_array_Buffer offset:0 atIndex:1];
	[computeEncoder setBuffer:info->new_val_Buffer offset:0 atIndex:2];
	[computeEncoder setBuffer:info->arrays_Buffer offset:0 atIndex:3];
	[computeEncoder setBuffer:info->reps_Buffer offset:0 atIndex:4];
	[computeEncoder setBuffer:info->bias_Buffer offset:0 atIndex:5];
	[computeEncoder setBuffer:info->objective_Buffer offset:0 atIndex:6];
	[computeEncoder setBuffer:info->constraint_Buffer offset:0 atIndex:7];
	[computeEncoder setBuffer:info->seed_Buffer offset:0 atIndex:8];

	// Dispatch the compute kernel
	MTLSize gridSize = MTLSizeMake(size, 1, 1);
	NSUInteger threadGroupSize = info->pipelineState.maxTotalThreadsPerThreadgroup;
	threadGroupSize = threadGroupSize > size ? size : threadGroupSize;
	MTLSize threadgroupSize = MTLSizeMake(threadGroupSize, 1, 1);
	[computeEncoder dispatchThreads:gridSize threadsPerThreadgroup:threadgroupSize];

	// Finalize and commit
	NSError *error = nil;
	[computeEncoder endEncoding];
	[commandBuffer commit];
	[commandBuffer waitUntilCompleted];

	// Step 6: Retrieve the new_array

	new_values = (int *) [info->new_val_Buffer contents];
	uint32_t *new_arrays = (uint32_t *) [info->arrays_Buffer contents];

	int i = -1;
	int counter = 0;

	while (i++, i < size && counter <= total_reps) {
		counter += reps;
		if (cur_val[0] < new_values[i]) {
			int value = new_values[i];
			for (int j = 0; j < num_integers; ++j) {
			    x[j] = new_arrays[i * num_integers + j];
// 			    printf("%d %lu %lu\n", value, x[j], new_arrays[i * num_integers + j]);
			}
			[computeEncoder release];
			[commandBuffer release];
			return value;
		}
	}
	[computeEncoder release];
	[commandBuffer release];
	return -1;
}


// clang -ObjC -framework Metal -framework Foundation -o program main.m
