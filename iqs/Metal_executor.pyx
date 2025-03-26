import Metal
import random
import ctypes
import os
import objc
import numpy as np
from time import time

class metal_executor:

	def __init__(self, n, objective, constaint, C, Con, Obj):
		O_terms = len(objective)
		C_terms = len(constaint)

		shader_code = self.generate_ilp_metal(n, C, Con, Obj)
		# with open("shader.metal", "r") as f:
		# 	shader_code = f.read()

		# Create a Metal device, library, and kernel function
		self.device = Metal.MTLCreateSystemDefaultDevice()
		self.library = self.device.newLibraryWithSource_options_error_(shader_code, None, None)[0]
		self.kernel_function = self.library.newFunctionWithName_("add_arrays")

		#########################################
		# 2. Setup the input and output buffers.
		#########################################
		self.array_length = 1024
		self.num_integers = int(np.ceil(n / 32))
		# print(self.num_integers)

		# self.buffer_length = self.array_length * 4
		self.cur_val_buffer = self.device.newBufferWithLength_options_(ctypes.sizeof(ctypes.c_int), Metal.MTLResourceStorageModeShared)
		self.cur_array_buffer = self.device.newBufferWithLength_options_(self.num_integers * ctypes.sizeof(ctypes.c_uint32), Metal.MTLResourceStorageModeShared)

		self.new_val_buffer = self.device.newBufferWithLength_options_(self.array_length * ctypes.sizeof(ctypes.c_int), Metal.MTLResourceStorageModeShared)
		self.new_array_buffer = self.device.newBufferWithLength_options_(self.array_length * self.num_integers * ctypes.sizeof(ctypes.c_uint32), Metal.MTLResourceStorageModeShared)

		self.reps_buffer = self.device.newBufferWithLength_options_(ctypes.sizeof(ctypes.c_int), Metal.MTLResourceStorageModeShared)

		self.objective_buffer = self.device.newBufferWithLength_options_(O_terms * ctypes.sizeof(ctypes.c_int), Metal.MTLResourceStorageModeShared)
		self.constraint_buffer = self.device.newBufferWithLength_options_(C_terms * ctypes.sizeof(ctypes.c_int), Metal.MTLResourceStorageModeShared)

		self.bias_buffer = self.device.newBufferWithLength_options_(ctypes.sizeof(ctypes.c_float), Metal.MTLResourceStorageModeShared)
		self.seed_buffer = self.device.newBufferWithLength_options_(self.array_length * ctypes.sizeof(ctypes.c_uint32), Metal.MTLResourceStorageModeShared)

		# populate buffers with constant values
		self.populate_buffer(self.objective_buffer, ctypes.c_int, objective, len(objective))
		self.populate_buffer(self.constraint_buffer, ctypes.c_int, constaint, len(constaint))
		self.populate_buffer(self.bias_buffer, ctypes.c_float, [n / 4], 1)
		self.populate_buffer(self.seed_buffer, ctypes.c_uint32, [3 * i for i in range(self.array_length)], self.array_length)

	def populate_buffer(self, buffer, type, array, length):
		input_array = (type * length).from_buffer(buffer.contents().as_buffer(length * ctypes.sizeof(type)))  # Map the Metal buffer to a Python array
		input_array[:] = array

	def gpu_ctg(self, P, initial, M):
		m_tot = 0
		qtg_applications = 0
		rounds = 0
		lam = 6. / 5
		t1 = time()
		while m_tot < M:
			m = int(np.ceil(lam ** rounds))
			j = random.randint(0, m)
			m_tot += 2 * j + 1
			qtg_applications += 2 * j + 1
			rounds += 1

			res = self.gpu_csearch(P, initial, 4 * j * j)
			if res != -1:
				print(res, qtg_applications, time() - t1)
				P = res
				rounds = 0
				m_tot = 0

		return P, qtg_applications


	def gpu_csearch(self, P, initial, reps):
		if reps == 0: return -1
		#####################################
		# 3. Call the Metal kernel function.
		#####################################
		self.populate_buffer(self.new_val_buffer, ctypes.c_int, [0] * self.array_length, self.array_length)
		self.populate_buffer(self.new_array_buffer, ctypes.c_uint32, [0] * self.array_length * self.num_integers, self.array_length * self.num_integers)

		self.populate_buffer(self.cur_val_buffer, ctypes.c_int, [P], 1)
		self.populate_buffer(self.cur_array_buffer, ctypes.c_uint32, initial, self.num_integers)

		reps_per_thread = int(np.ceil(reps / 1024))
		self.populate_buffer(self.reps_buffer, ctypes.c_int, [reps_per_thread], 1)

		# Create a command queue and command buffer
		commandQueue = self.device.newCommandQueue()
		commandBuffer = commandQueue.commandBuffer()
		# Set the kernel function and buffers

		pso = self.device.newComputePipelineStateWithFunction_error_(self.kernel_function, None)[0]
		computeEncoder = commandBuffer.computeCommandEncoder()
		computeEncoder.setComputePipelineState_(pso)
		computeEncoder.setBuffer_offset_atIndex_(self.cur_val_buffer, 0, 0)
		computeEncoder.setBuffer_offset_atIndex_(self.cur_array_buffer, 0, 1)
		computeEncoder.setBuffer_offset_atIndex_(self.new_val_buffer, 0, 2)
		computeEncoder.setBuffer_offset_atIndex_(self.new_array_buffer, 0, 3)
		computeEncoder.setBuffer_offset_atIndex_(self.reps_buffer, 0, 4)
		computeEncoder.setBuffer_offset_atIndex_(self.bias_buffer, 0, 5)
		computeEncoder.setBuffer_offset_atIndex_(self.objective_buffer, 0, 6)
		computeEncoder.setBuffer_offset_atIndex_(self.constraint_buffer, 0, 7)
		computeEncoder.setBuffer_offset_atIndex_(self.seed_buffer, 0, 8)

		# Define threadgroup size
		threadsPerThreadgroup = Metal.MTLSizeMake(1024, 1, 1)
		threadgroupSize = Metal.MTLSizeMake(pso.maxTotalThreadsPerThreadgroup(), 1, 1)

		# Dispatch the kernel
		computeEncoder.dispatchThreads_threadsPerThreadgroup_(threadsPerThreadgroup, threadgroupSize)
		computeEncoder.endEncoding()

		# Commit the command buffer
		commandBuffer.commit()
		commandBuffer.waitUntilCompleted()

		# print(self.new_val_buffer)
		# # Map the Metal buffer to a Python array
		output_value = (ctypes.c_int * self.array_length).from_buffer(self.new_val_buffer.contents().as_buffer(self.array_length * ctypes.sizeof(ctypes.c_int)))
		output_array = (ctypes.c_uint32 * (self.array_length * self.num_integers)).from_buffer(self.new_array_buffer.contents().as_buffer(self.array_length * self.num_integers * ctypes.sizeof(ctypes.c_uint32)))

		output_value = list(output_value)
		output_array = list(output_array)

		counter = 0

		for i in range(self.array_length):
			counter += reps_per_thread
			# if reps != 0: print(reps, counter)
			if counter > reps: break
			if P < output_value[i]:
				# print(reps, counter)
				for j in range(self.num_integers):
					initial[j] = output_array[i * self.num_integers + j]
				value = output_value[i]
				commandQueue.release()
				commandBuffer.release()
				return value

		commandQueue.release()
		commandBuffer.release()
		return -1

	def generate_ilp_metal(self, n, C, constraints, obj, sense = ">"):
		"""
		arrays are stored in bits rather in bytes:
		slightly slower, but gpu programming requires more compact data
		:param n:
		:param C:
		:param constraints:
		:param new:
		:return:
		"""
		num_integers = int(n / 32) + 1

		metal_file = f"""
kernel void add_arrays(const device int *cur_val [[ buffer(0) ]],       // Current objective value
                       const device uint *cur_array [[ buffer(1) ]],    // Current array
                       device int *new_val [[ buffer(2) ]],             // New objective value
                       device uint *array [[ buffer(3) ]],              // New array (only stored if good new objective)
                       const device int *num_reps [[ buffer(4) ]],          // Number of samples per thread
                       const device float *bias [[ buffer(5) ]],        // bias
                       const device int *objective [[ buffer(6) ]],
                       const device int *constraint [[ buffer(7) ]],
                       device long *additional_seed [[ buffer(8) ]], // add to thread id
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {{
    int cur = cur_val[0];
    bool sum = 0;
	int obj = 0;

    uint x[{num_integers}];    // copy of old assignment
    for (int i = 0; i < {num_integers}; i++) x[i] = cur_array[i];
    uint y[{num_integers}];    // new assignment
    int P[{C}];    // potentials

    bool b_plus;    // booleans
    bool b_minus;   // booleans

    bool update = 1;
    bool single_update;

    uint step;
    uint branch;

    uint seed = additional_seed[id]; // Each thread gets a unique seed

    float probs[2] = {{ (1. + bias[0]) / (bias[0] + 2), 1. / (bias[0] + 2) }};

	for(int reps=0; reps < num_reps[0]; reps++){{
		for (int i = 0; i < {num_integers}; i++) y[i] = 0;
		obj = 0;
		"""
		for i in range(C):
			metal_file += f"""
		P[{i}] = {int(constraints[i][-1])};"""

		metal_file += f"""
		for(int item = 0; item < {n}; item++){{
			b_plus = 1;
			b_minus = 1;
			for (int con = 0; con < {C}; con++){{
				if (constraint[con * {n} + item] >= 0) b_plus &= P[con] >= constraint[con * {n} + item];
				else b_minus &= P[con] >= - constraint[con * {n} + item];
			}}
			seed ^= seed << 21;
			seed ^= seed >> 35;
			seed ^= seed << 4;
			branch =  (uint) (((float) seed / 0xFFFFFFFF) > probs[(x[item / 32] & (1 << item % 32)) != 0]);

			step = (uint(b_plus) & uint(b_minus) & uint(branch)) | uint(1 - b_minus);
			y[item / 32] |= (step << item % 32);

			for (int con = 0; con < {C}; con++){{
				if (constraint[con * {n} + item] >= 0) P[con] -= step * constraint[con * {n} + item];
				else P[con] += (1 - step) * constraint[con * {n} + item];
			}}
		}}"""

		# sum the objective value
		if len(obj[0][:-1][0]) == 2:
			metal_file += f"""
		for(int i = 0; i < {n}; i++){{ obj += objective[i] * ((y[i / 32] & (1 << i % 32)) != 0); }}
		"""
		if len(obj[0][:-1][0]) == 3:
			metal_file += f"""
		for(int i = 0; i < {n}; i++){{
			for(int j = i; j < {n}; j++){{
				obj += objective[i * {n} + j] * ((y[i / 32] & (1 << i % 32)) != 0) * ((y[j / 32] & (1 << j % 32)) != 0);
			}}
		}}
	"""

		metal_file += f"""
		sum = 1;
		
		for (int i = 0; i < {C}; i++) {{ sum = sum && (P[i] >= 0); }}
		single_update = obj {sense} cur && update && sum;
		
		for (int i = 0; i < {num_integers}; i++) x[i] = single_update * y[i] + (!single_update) * x[i];

		cur = single_update * obj + (!single_update) * cur;
		update = update && (!single_update); // if !(obj {sense} cur) or !su^m we still have to update
	}}
	for (int i = 0; i < {num_integers}; i++){{
		array[id * {num_integers} + i] = x[i];
	}}
	additional_seed[id] = seed;
	new_val[id] = cur;
}}
		"""
		return metal_file
