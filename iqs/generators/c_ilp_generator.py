import os
import subprocess


def generate_ilp_gpu(n, C, constraints, obj, lp_factor, lp_opt, new, num_integers, sense = ">", direction = "."):
	if os.path.exists("main") and not new: return 0

	# c_file = open(os.path.dirname(os.path.abspath(__file__)) + "/main.m", "r").read()
	ret = n
	if len(obj[0][:-1][0]) == 3:
		ret = n * n

	c_file = f"""	
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// int objective_terms(){{
// 	// printf(\"size 1 = %d\\n\", {ret});
// 	return {ret};
// }}
// 
// int constraint_terms(){{
// 	// printf(\"size 2 = %d\\n\", {n * C});
// 	return {n * C};
// }}
// 
// char *direction(){{
// 	// printf(\"dir = %s\\n\", \"{direction}\");
// 	return \"{direction}\";
// }}

int32_t QSearch(float *probs, int32_t val, uint32_t *x, int total_reps, int *constraint, int *objective) {{
	printf("start function\\n");
	fflush(stdout);
	float random;
	char b_plus;
	char b_minus;
	char sum;
	int64_t obj = 0;
	uint32_t bit;
	int index;

	uint32_t y[{num_integers}];
	memset(y, 0, {num_integers} * sizeof(uint32_t));

	int64_t P[{C}];
	
	for(int reps=0; reps < total_reps; reps++){{"""
	for i in range(C):
		c_file += f"""
		P[{i}] = {int(constraints[i][-1])};"""
	c_file += f"""
		for (int i = 0; i < {num_integers}; i++){{y[i] = 0;}}
		//printf("%ld %ld %ld\\n", obj, P[0], P[1]);
		printf("start loop\\n");
		fflush(stdout);
		"""

	c_file += f"""
		for(int item = 0; item < {n}; item++){{
			printf("%d\\n", item);
			fflush(stdout);
			b_plus = 1;
			b_minus = 1;
			for (int con = 0; con < {C}; con++){{
				if (constraint[con * {n} + item] >= 0) b_plus &= P[con] >= constraint[con * {n} + item];
				else b_minus &= P[con] >= - constraint[con * {n} + item];
			}}
			
			random = ((float) rand()) / RAND_MAX;
			index = (x[item / 32] & (1 << (item % 32))) != 0;
			bit = (random > probs[index]) && b_plus && b_minus || !b_minus;

			y[item / 32] |= (bit << item % 32);

			for (int con = 0; con < {C}; con++){{
				if (constraint[con * {n} + item] >= 0) P[con] -= ((int) bit) * constraint[con * {n} + item];
				else P[con] += (1 - ((int) bit)) * constraint[con * {n} + item];
				//printf("%d %d %ld %ld\\n", bit, constraint[con * {n} + item], P[0], P[1]);
			}}
		}}"""
	# checking if all the constraints are satisfied
	c_file += \
		f"""
		sum = 1;
		for (int i = 0; i < {C}; i++) {{sum = sum && (P[i] >= 0);}}
		obj = 0;"""

	# compute objective value
	if len(obj[0][:-1][0]) == 2:
		c_file += f"""
		for(int i = 0; i < {n}; i++){{ obj += objective[i] * ((y[i / 32] & (1 << i % 32)) != 0); }}
	"""
	if len(obj[0][:-1][0]) == 3:
		c_file += f"""
		for(int i = 0; i < {n}; i++){{
			for(int j = i; j < {n}; j++){{
				obj += objective[i * {n} + j] * ((y[i / 32] & (1 << i % 32)) != 0) * ((y[j / 32] & (1 << j % 32)) != 0);
			}}
		}}
		//printf("%ld %ld %ld\\n", obj, P[0], P[1]);
	"""
	c_file += f"""
		if ((obj {sense} val) && sum){{
			memcpy(x, y, {num_integers} * sizeof(uint32_t));
			return obj;
		}}
	}}
	return -1;
}}
	"""

	file = open("build/cfile.c", "w")
	file.write(c_file)
	file.close()
	# print(c_file)
	# result = subprocess.run(
	# 	["clang", "-objC", "-x", "objective-c", "-", "-framework", "Metal", "-framework", "Foundation", "-o", f"{direction}/build/run_gpu"],  # Compile from stdin
	# 	input = c_file.encode(),  # Pass the C code as bytes
	# 	stdout = subprocess.PIPE,
	# 	stderr = subprocess.PIPE
	# )
	# if result.returncode != 0:
	# 	print(result)
	# 	exit(1)
	# return result