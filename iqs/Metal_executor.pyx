from libc.stdint cimport uint32_t
from libc.stdlib cimport calloc

from .Constants import *

cdef extern from "objc/objc.h":
	ctypedef void * id

cdef extern from "src/main.h":
	ctypedef struct gpu_info_t:
		id device
		id commandQueue
		id pipelineState
		id cur_val_Buffer
		id cur_array_Buffer
		id new_val_Buffer
		id arrays_Buffer
		id reps_Buffer
		id bias_Buffer
		id objective_Buffer
		id constraint_Buffer
		id seed_Buffer

	gpu_info_t *init_buffers(int *constraint, int c_terms,
	                         int *objective, int o_terms,
	                         double bias, uint32_t globalSeed,
	                         int num_integers,
	                         char *shader);

	int gpu_qmax_search_c(int n, int M,
	                      int *constraint, int c_terms,
	                      int *objective, int o_terms,
	                      int cur, uint32_t *arr,
	                      gpu_info_t *info
	                      );

cdef class Executor:
	cdef gpu_info_t *info
	cdef int * obj_c
	cdef int * con_c
	cdef int o_terms_c
	cdef int c_terms_c
	# cdef char *shader

	def __cinit__(self, n: int, bias: float, gloabalSeed: int,
	              constraint: list[int],
	              objective: list[int],
	              C, con, obj, solver):

		self.obj_c = <int *> calloc(len(objective), sizeof(int))
		for i in range(len(objective)): self.obj_c[i] = <int> objective[i]

		self.con_c = <int *> calloc(len(constraint), sizeof(int))
		for i in range(len(constraint)): self.con_c[i] = <int> constraint[i]

		self.o_terms_c = len(objective)
		self.c_terms_c = len(constraint)

		if solver == OPTIMIZE:
			shader = self.generate_itl_metal(n, C, con, obj)
		else:
			shader = self.generate_sat_metal(n, C, con)

		self.info = init_buffers(self.con_c, len(constraint), self.obj_c, len(objective),
		                         bias, gloabalSeed, n // 32 + 1, shader.encode("utf-8"))

	def __init__(self, n: int, bias: float, gloabalSeed: int,
	             constraint: list[int],
	             objective: list[int],
	             C, con, obj, solver):
		pass

	def gpu_qmax_search(self, n: int, M: int,
	                    cur: int, arr: list[int]):
		cdef uint32_t * arr_c = <uint32_t *> calloc(len(arr), sizeof(uint32_t))
		for i in range(len(arr)):
			arr_c[i] = <uint32_t> arr[i]

		# print("Method included!")

		gpu_qmax_search_c(n, M,
		                  self.con_c, self.c_terms_c,
		                  self.obj_c, self.o_terms_c,
		                  cur, arr_c, self.info)

	def generate_itl_metal(self, n, C, constraints, obj, sense = ">"):
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
}}"""
		return metal_file
	def generate_sat_metal(self, n, C, constraints):
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
}}"""
		return metal_file