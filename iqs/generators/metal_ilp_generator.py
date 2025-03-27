import os
import subprocess
import ast


def generate_ilp_metal(n, C, constraints, obj,  sense = ">", direction = ""):
	"""
	arrays are stored in bits rather in bytes:
	slightly slower, but gpu programming requires more compact data
	:param n:
	:param C:
	:param constraints:
	:param lp_factor:
	:param lp_opt:
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
				if (constraint[con * {n} + item] >= 0) P[con] -= int(step) * constraint[con * {n} + item];
				else P[con] += (1 - int(step)) * constraint[con * {n} + item];
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
		bool up = (obj {sense} cur && update && sum);
		for (int i = 0; i < {num_integers}; i++) x[i] = up * y[i] + (!up) * x[i];

		cur = (up) * obj + (!up) * cur;
		update = update && (!up); // if !(obj {sense} cur) or !su^m we still have to update
	}}
	for (int i = 0; i < {num_integers}; i++){{
		array[id * {num_integers} + i] = x[i];
	}}
	additional_seed[id] = seed;
	new_val[id] = cur;
}}
	"""
	file = open(f"{direction}/build/shader.metal", "w+")
	file.write(metal_file)
	file.close()