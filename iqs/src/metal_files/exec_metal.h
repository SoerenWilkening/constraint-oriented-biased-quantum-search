#ifndef EXEC_METAL_H
#define EXEC_METAL_H

#include <Metal/Metal.h>

typedef struct {
	id <MTLDevice> device;
	id <MTLCommandQueue> queue;
	id <MTLLibrary> library;
	id <MTLFunction> kernelFunction;
	id <MTLComputePipelineState> pipelineState;
	id <MTLBuffer> pointer;
	id <MTLBuffer> state;
} gpu_info_t;

#endif