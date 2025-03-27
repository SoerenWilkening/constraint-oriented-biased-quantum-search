#include <Metal/Metal.h>
#include <stdio.h>
#include <mach/mach_time.h>
#include <CommonCrypto/CommonCrypto.h>
#include <string.h>
#include <time.h>

typedef struct {
	id <MTLDevice> device;
	id <MTLCommandQueue> commandQueue;
	id <MTLComputePipelineState> pipelineState;
	id <MTLBuffer> cur_val_Buffer;
	id <MTLBuffer> cur_array_Buffer;
	id <MTLBuffer> new_val_Buffer;
	id <MTLBuffer> arrays_Buffer;
	id <MTLBuffer> reps_Buffer;
	id <MTLBuffer> bias_Buffer;
	id <MTLBuffer> objective_Buffer;
	id <MTLBuffer> constraint_Buffer;
	id <MTLBuffer> seed_Buffer;
} gpu_info_t;

// Function to check for Metal errors
#define CHECK_ERROR(cond, msg) if (!(cond)) { printf("%s\n", msg); return -1; }

int32_t QSearch(float *probs, int32_t val, uint32_t *x, int total_reps, int *constraint, int *objective);

int run_kernel(int reps, int size, int num_integers, int total_reps, int32_t val, uint32_t *x, gpu_info_t *info);

int objective_terms();

int constraint_terms();

char *direction();

int main(int argc, char *argv[]) {
	/*
	 * argv[1]: n: number of items
	 * argv[2]: M: number of grover iterations
	 * argv[3]: bias
	 * argv[4]: seed
	 * argv[5]: flag if gpu should be used
	 * argv[6]: current objective value
	 * argv[7+]: solution to bias to
	 * */

	int n = atoi(argv[1]);
	int num_integers = n / 32 + 1;

	// Input data
	const int size = 512;
	float bias[1] = {(float) atoi(argv[3])};

	uint globalSeed = atoi(argv[4]);
	srand(globalSeed);
	uint32_t seed[size];
	for (uint i = 0; i < size; i++) seed[i] = globalSeed +i;

	bool gpu = strcmp(argv[5], "gpu") == 0;

    char name[1024];

	int *objective = calloc(objective_terms(), sizeof(int));
    if (objective_terms() != 0){
        sprintf(name, "build/objective.txt", direction());
	    FILE *obj = fopen(name, "r");
	    for (int i = 0; i < objective_terms(); i++) fscanf(obj, "%d ", &objective[i]);
	    fclose(obj);
	}

	int constraint[constraint_terms()];
	if (constraint_terms() != 0){
	    sprintf(name, "build/constraint.txt", direction());
	    FILE *obj = fopen(name, "r");
	    for (int i = 0; i < constraint_terms(); i++) fscanf(obj, "%d ", &constraint[i]);
	    fclose(obj);
	}

	uint32_t new_array[num_integers];
	memset(new_array, 0, num_integers * sizeof(uint32_t));

	uint32_t cur_array[num_integers];
	int32_t cur_val[1] = {atoi(argv[6])};
	for (int i = 0; i < num_integers; i++) {cur_array[i] = atoi(argv[7 + i]);}

	// Step 1: Create new_val Metal device
	id <MTLDevice> device = MTLCreateSystemDefaultDevice();
	CHECK_ERROR(device, "Failed to create Metal device");

	// Step 2: Create new_val command queue
	id <MTLCommandQueue> commandQueue = [device newCommandQueue];

	// Step 3: Load the Metal kernel
	sprintf(name, "build/shader.metal", direction());

	NSError *error = nil;
	NSString *filePath = [NSString stringWithUTF8String:name];
	NSString *metalSource = [NSString stringWithContentsOfFile:filePath encoding:NSUTF8StringEncoding error:&error];
	CHECK_ERROR(metalSource, "Failed to load Metal shader");
	id <MTLLibrary> library = [device newLibraryWithSource:metalSource options:nil error:&error];
	CHECK_ERROR(library, "Failed to compile Metal library");
	id <MTLFunction> kernelFunction = [library newFunctionWithName:@"add_arrays"];
	CHECK_ERROR(kernelFunction, "Failed to find Metal kernel function");
	id <MTLComputePipelineState> pipelineState = [device newComputePipelineStateWithFunction:kernelFunction error:&error];
	CHECK_ERROR(pipelineState, "Failed to create pipeline state");

	// Step 4: Create buffers
	id <MTLBuffer> cur_val_Buffer = [device newBufferWithBytes:cur_val length:sizeof(int32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> cur_array_Buffer = [device newBufferWithBytes:cur_array length:num_integers *
	                                                                              sizeof(uint32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> new_val_Buffer = [device newBufferWithLength:size * sizeof(int32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> arrays_Buffer = [device newBufferWithLength:size * num_integers * sizeof(uint32_t) options:MTLResourceStorageModeShared];
	id <MTLBuffer> reps_Buffer = [device newBufferWithLength:sizeof(int) options:MTLResourceStorageModeShared];

	id <MTLBuffer> objective_Buffer = [device newBufferWithBytes:objective length:objective_terms() * sizeof(int) options:MTLResourceStorageModeShared];
	id <MTLBuffer> constraint_Buffer = [device newBufferWithBytes:constraint length:constraint_terms() * sizeof(int) options:MTLResourceStorageModeShared];

	id <MTLBuffer> bias_Buffer = [device newBufferWithBytes:bias length:sizeof(float) options:MTLResourceStorageModeShared];
	id <MTLBuffer> seed_Buffer = [device newBufferWithBytes:seed length:size * sizeof(uint32_t) options:MTLResourceStorageModeShared];

	gpu_info_t gpu_info;

	gpu_info.commandQueue = commandQueue;
	gpu_info.pipelineState = pipelineState;
	gpu_info.cur_val_Buffer = cur_val_Buffer;
	gpu_info.cur_array_Buffer = cur_array_Buffer;
	gpu_info.new_val_Buffer = new_val_Buffer;
	gpu_info.arrays_Buffer = arrays_Buffer;
	gpu_info.reps_Buffer = reps_Buffer;
	gpu_info.objective_Buffer = objective_Buffer;
	gpu_info.constraint_Buffer = constraint_Buffer;
	gpu_info.bias_Buffer = bias_Buffer;
	gpu_info.seed_Buffer = seed_Buffer;


	/*
	 * Run QMaxSearch routine:
	 *
	 * */
	unsigned int M = atoi(argv[2]);
	unsigned int qtg_applications = 0;
	unsigned int m_tot = 0;
	unsigned int rounds = 0;
	double lambda = 6. / 5;
	int res;
	float probs[] = {(1. + bias[0]) / (bias[0] + 2), 1. / (bias[0] + 2)};

    sprintf(name, "results.csv", direction());

    clock_t t1 = clock();
	while (m_tot < M) {
// 	for (int i = 0; i < 1; i++){
		int m = ceil(pow(lambda, rounds));
		int j = rand() % (m + 1);
		m_tot += 2 * j + 1;
		qtg_applications += 2 * j + 1;
		rounds++;

		int reps = MAX((int) ceil(4 * j * j / size), 1);
// 		int reps = 1;
// 		res = run_kernel(reps, size, num_integers, 4 * j * j, cur_val[0], cur_array, &gpu_info);
		if (4 * j * j >= 30 && gpu) res = run_kernel(reps, size, num_integers, 4 * j * j, cur_val[0], cur_array, &gpu_info);
		else res = QSearch(probs, cur_val[0], cur_array, 4 * j * j, constraint, objective);
// 		res = QSearch(probs, cur_val[0], cur_array, 4 * j * j, constraint, objective);
		if (res != -1) {
		    FILE *file = fopen(name, "a");
		    fprintf(file, "%d,%d,%s,qtg\n", res, qtg_applications, argv[6]);
	        fclose(file);
			cur_val[0] = res;
			rounds = 0;
			m_tot = 0;
// 			if (res == 218 || res == 430 || res == 325) break;
		}
	}

    clock_t t2 = clock();
    printf("{count: %d, applications: %d, c-time: %f, sol:[", cur_val[0], qtg_applications, ((double) t2 - t1) / CLOCKS_PER_SEC);
    for (int i = 0; i < num_integers; i++) printf("%lu,", cur_array[i]);
    printf("]}");

    free(objective);

	return 0;
}

int run_kernel(int reps,
               int size,
               int num_integers,
               int total_reps,
               int32_t val,
               uint32_t *x,
               gpu_info_t *info) {

    int32_t * new_values = (int *) [info->new_val_Buffer contents];
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

    int32_t *cur_val = (int *) [info->cur_val_Buffer contents];
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

	while (i++, i < size && counter < total_reps) {
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
