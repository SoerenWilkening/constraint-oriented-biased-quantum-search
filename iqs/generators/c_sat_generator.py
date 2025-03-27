import os
import subprocess
import ast
import sys


def qsearch(n, C, constraints, lp_factor, lp_opt, num_integers, direction = ""):
	c_file = f"""


int objective_terms(){{
	return 0;
}}

int constraint_terms(){{
	return 0;
}}

char *direction(){{
	return \"{direction}\";
}}	
	
int QSearch(float *probs, int val, uint32_t *x, int total_reps, int *constr, int *obj) {{
	float random;
	char b_plus;
	char b_minus;
	short count;
	uint32_t bit;
	int index;

	uint32_t y[{num_integers}];
	memset(y, 0, {num_integers} * sizeof(uint32_t));

	char P[{C}];
	
	for(int reps=0; reps < total_reps; reps++){{
		//for (int i = 0; i < {C}; i++) P[i] = 2;
		for (int i = 0; i < {num_integers}; i++){{y[i] = 0;}}"""

	for i in range(C):
		c_file += f"""
		P[{i}] = {int(constraints[i][-1])};"""

	for item in range(n):
		S_plus = [constraints.index(i) for i in constraints if [1.0, item] in i]
		S_minus = [constraints.index(i) for i in constraints if [-1.0, item] in i]

		c_file +="""
		b_plus = 1;
		b_minus = 1;"""

		for s in S_plus:
			c_file += f"""          
		b_plus &= P[{s}] >= 1;"""

		for s in S_minus:
			c_file += f"""          
		b_minus &= P[{s}] >= 1;"""

		c_file += \
			f"""
		random = ((float) rand()) / RAND_MAX;
		index = (x[{int(item / 32)}] & (1 << ({item % 32}))) != 0;
		bit = (random > probs[index] + index * {lp_factor * lp_opt[item]}) && b_plus && b_minus || !b_minus;
		// bit = (random > probs[index] + index * {lp_factor * lp_opt[item]});
		y[{int(item / 32)}] |= bit << {item % 32}; 

		if (bit == 1){{"""

		for s in S_plus:
			c_file += f"""                
			P[{s}] -= 1;"""

		c_file += f"""            
		}}
		if (bit == 0){{"""
		for s in S_minus:
			c_file += f"""                
			P[{s}] -= 1;"""

		c_file += f"""            
		}}"""
	c_file += \
		f"""
		count = 0;
		for (int i = 0; i < {C}; i++) {{
			count += (P[i] >= 0);
		}}

		if (count > val){{
			memcpy(x, y, {num_integers} * sizeof(uint32_t));
			if (reps > 0) return count;
		}}
	}}
	return -1;
}}"""
	return c_file

def generate_sat_gpu(n, C, constraints, lp_factor, lp_opt, new, num_integers, direction = ""):
	if os.path.exists("run_gpu") and not new: return 0

	c_file = open(os.path.dirname(os.path.abspath(__file__)) + "/main.m", "r").read()

	c_file += qsearch(n, C, constraints, lp_factor, lp_opt, num_integers, direction)

	result = subprocess.run(
		["clang", "-objC", "-x", "objective-c", "-", "-framework", "Metal", "-framework", "Foundation", "-o", f"{direction}/build/run_gpu"],  # Compile from stdin
		input = c_file.encode(),  # Pass the C code as bytes
		stdout = subprocess.PIPE,
		stderr = subprocess.PIPE
	)
	# print(result)
	return result

def run_hardcode_gpu(n, M, bias, seed, array, arch = "gpu", direction = "."):
	# res = subprocess.run([f"./{direction}/build/run_gpu", f"{n}", f"{M}", f"{bias}", f"{seed}", arch,*array])
	# print(res)
	# os.system("pwd && ./build/run_gpu")
	# print("run")
	# print(f"./build/run_gpu")
	# print(" ".join([f"./build/run_gpu", f"{n}", f"{M}", f"{bias}", f"{seed}", arch, *array]))
	res = subprocess.run([f"./build/run_gpu", f"{n}", f"{M}", f"{int(bias)}", f"{int(seed)}", arch, *list(map(str, array))], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
	# res = subprocess.run([f"./build/run_gpu", f"{n}", f"{M}", f"{int(bias)}", f"{int(seed)}", arch, *list(map(str, array))])
	if res.returncode != 0:
		print(res)
		exit(1)

	res = res.stdout.decode().replace(
		"c-time", "'c-time'").replace(
		"count", "'count'").replace(
		"applications","'applications'").replace(
		"sol", "'sol'")

	sp = res.split("\n")

	intermetiates = [[int(i.split()[0]), int(i.split()[1]), float(i.split()[2])] for i in sp[:-1]]
	res = ast.literal_eval(sp[-1])
	res["sol"] = [str(i) for i in res["sol"]]
	return res, intermetiates
