import os
import subprocess
import ast

def generate_sat_metal(n, C, constraints, lp_factor, lp_opt, new  = True, direction = ""):
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
	if not new: return 0
	# print("generate")
	num_integers = int(n / 32) + 1
	# print("n", n)
	# print("numintegers", num_integers)

	metal_file = f"""
kernel void add_arrays(const device int *cur_val [[ buffer(0) ]],       // Current objective value
                       const device uint *cur_array [[ buffer(1) ]],    // Current array
                       device int *new_val [[ buffer(2) ]],             // New objective value
                       device uint *array [[ buffer(3) ]],              // New array (only stored if good new objective)
                       const device int *num_reps [[ buffer(4) ]],      // Number of samples per thread
                       const device float *bias [[ buffer(5) ]],        // bias
                       const device int *objective [[ buffer(6) ]],
                       const device int *constraint [[ buffer(7) ]],
                       device long *additional_seed [[ buffer(8) ]], // add to thread id
                       uint id [[ thread_position_in_grid ]]            // Thread ID
) {{
    int cur = cur_val[0];
    int sum = 0;

    uint x[{num_integers}];    // copy of old assignment
    for (int i = 0; i < {num_integers}; i++) x[i] = cur_array[i];
    uint y[{num_integers}];    // new assignment
    char P[{C}];    // potentials
    
    bool b_plus;    // booleans
    bool b_minus;   // booleans
    
    bool update = 1;
    
    char step;
    char branch;
    
    uint seed = additional_seed[id]; // Each thread gets a unique seed
    
    float probs[2] = {{ (1. + bias[0]) / (bias[0] + 2), 1. / (bias[0] + 2) }};
		
	for(int reps=0; reps < num_reps[0]; reps++){{
		for (int i = 0; i < {num_integers}; i++) y[i] = 0;
	"""
	for i in range(C):
		metal_file += f"""
		P[{i}] = {int(constraints[i][-1])};"""


	for item in range(n):
		metal_file += f"""
		b_plus = 1;
		b_minus = 1;"""
		S_plus = [constraints.index(i) for i in constraints if [1.0, item] in i]
		S_minus = [constraints.index(i) for i in constraints if [-1.0, item] in i]

		# counter = 0
		for s in S_plus:
			metal_file += f"""
		b_plus = b_plus && (P[{s}] >= 1);"""
			# counter += 1
		for s in S_minus:
			metal_file += f"""
		b_minus = b_minus && (P[{s}] >= 1);"""
			# counter += 1

		metal_file += f"""
		seed ^= seed << 21;
		seed ^= seed >> 35;
		seed ^= seed << 4;
		branch =  (char) (((float) seed / 0xFFFFFFFF) > probs[(x[{int(item / 32)}] & (1 << {item % 32} ) ) != 0]);
		
		step = (char(b_plus) & char(b_minus) & char(branch)) | char(1 - b_minus);
		// step = char(branch);
		y[{int(item / 32)}] |= (step << {item % 32});
	"""
		for s in S_plus:
			metal_file += f"""
		P[{s}] -= step;"""

		for s in S_minus:
			metal_file += f"""
		P[{s}] -= 1 - step;"""

	metal_file += f"""
		sum = 0;
		for (int i = 0; i < {C}; i++) {{ sum += (P[i] >= 0); }}
		for (int i = 0; i < {num_integers}; i++) x[i] = (sum > cur && update) * y[i] + (sum <= cur || !update) * x[i];
		
		cur = (sum > cur && update) * sum + (sum <= cur || !update) * cur;
		update = update && (sum <= cur);
	}}
	for (int i = 0; i < {num_integers}; i++){{
		array[id * {num_integers} + i] = x[i];
	}}
	additional_seed[id] = seed;
	new_val[id] = cur;
}}
	"""
	file = open(f"{direction}/build/shader.metal", "w")
	file.write(metal_file)