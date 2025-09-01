#ifndef EXEC_METAL_H
#define EXEC_METAL_H

#include <Metal/Metal.h>
#include <stdlib.h>
#include "../constraint.h"

typedef struct {
	id <MTLDevice> device;
	id <MTLCommandQueue> queue;
	id <MTLLibrary> library;
	id <MTLFunction> kernelFunction;
	id <MTLComputePipelineState> pipelineState;
	id <MTLBuffer> pointer;

	id <MTLBuffer> state;   //    stores state metadata
	id <MTLBuffer> state_data; // stores state data
	id <MTLBuffer> num_integers; // stores state data

	id <MTLBuffer> move_length;
	id <MTLBuffer> move_offset;
	id <MTLBuffer> move_entries;

	id <MTLBuffer> first_move;
	id <MTLBuffer> last_move;

	id <MTLBuffer> factors;
	id <MTLBuffer> num_constraints;
	id <MTLBuffer> num_clauses;
	id <MTLBuffer> clause_offset;
	id <MTLBuffer> clause_length;
	id <MTLBuffer> variable_offset;
	id <MTLBuffer> variables;

	id <MTLBuffer> con_factors;
	id <MTLBuffer> con_num_constraints;
	id <MTLBuffer> con_num_clauses;
	id <MTLBuffer> con_clause_offset;
	id <MTLBuffer> con_clause_length;
	id <MTLBuffer> con_variable_offset;
	id <MTLBuffer> con_variables;
	id <MTLBuffer> rhs;
} gpu_info_t;


typedef struct {
	int16_t *length;
	int16_t *moves;
	int16_t *offset;
} move_gpu_t;

typedef struct {
	int32_t  tot_profit;
	uint32_t feasible;
	uint32_t n;
	uint32_t bits;
	uint32_t x_offset;
} state_32_t;

int exec_gpu(int n, new_constraints_t *obj, new_constraints_t *con);

#endif