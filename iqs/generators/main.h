#ifndef MAIN_H
#define MAIN_H

#include <Metal/Metal.h>

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

#define CHECK_ERROR(cond, msg) if (!(cond)) { printf("%s\n", msg); return -1; }

char *direction();

gpu_info_t *init_buffers(   int *constraint, int c_terms,
                            int *objective, int o_terms,
                            double bias, uint32_t globalSeed,
                            int num_integers);

int gpu_qmax_search_c(int n, int M,
                    int *constraint, int c_terms,
                    int *objective, int o_terms,
                    int cur, uint32_t *arr,
                    gpu_info_t *gpu_info
                    );

#endif // MAIN_H