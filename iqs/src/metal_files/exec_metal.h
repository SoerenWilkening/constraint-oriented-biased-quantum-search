#ifndef EXEC_METAL_H
#define EXEC_METAL_H

#include <Metal/Metal.h>
#include <stdlib.h>
#include "../constraint.h"

typedef struct {
	int32_t *length;
	int32_t *moves;
	int32_t *offset;
} move_gpu_t;


typedef struct {
	move_gpu_t move;

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
	id <MTLBuffer> num_clauses;
	id <MTLBuffer> clause_offset;
	id <MTLBuffer> clause_length;
	id <MTLBuffer> variable_offset;
	id <MTLBuffer> variables;

	id <MTLBuffer> obj_positive_indices;
	id <MTLBuffer> obj_negative_indices;
	id <MTLBuffer> obj_positive_offsets;
	id <MTLBuffer> obj_negative_offsets;
	id <MTLBuffer> obj_num_positive_indices;
	id <MTLBuffer> obj_num_negative_indices;

	id <MTLBuffer> con_factors;
	id <MTLBuffer> con_num_constraints;
	id <MTLBuffer> con_num_clauses;
	id <MTLBuffer> con_clause_offset;
	id <MTLBuffer> con_clause_length;
	id <MTLBuffer> con_variable_offset;
	id <MTLBuffer> con_variables;
	id <MTLBuffer> rhs;

	id <MTLTexture> con_positive_indices;
	id <MTLTexture> con_negative_indices;
	id <MTLTexture> con_positive_offsets;
	id <MTLTexture> con_negative_offsets;
	id <MTLTexture> con_num_positive_indices;
	id <MTLTexture> con_num_negative_indices;

	id <MTLBuffer> accepted_move;
	id <MTLBuffer> cur_violation;
} gpu_info_t;

typedef struct {
	int32_t tot_profit;
	uint32_t feasible;
	uint32_t n;
	uint32_t bits;
	uint32_t x_offset;
} state_32_t;

int exec_gpu(int n, new_constraints_t *obj, new_constraints_t *con);

#endif