import numpy as np
import os, sys

cdef class state_py:
	def __cinit__(self, int64_t ObjVal, array: list | np.ndarray) -> None:
		self.num_states = 1
		arr = np.array(array, dtype = np.int32)
		self.arr = arr  # easier handling when list it required

		cdef int * ptr = <int *> calloc(arr.shape[0], sizeof(int))
		for i in range(arr.shape[0]): ptr[i] = <int> arr[i]
		self.state = init_state(ObjVal, ptr, arr.shape[0])
		self.state.feasible = 1
		free(<void *> ptr)

	def __init__(self, ObjVal, array):
		pass

	def __len__(self):
		return self.num_states

	def load(self, file):
		f = open(file, "r").read().split()
		return state_py(float(f[0]), list(map(int, f[1:])))

	def get_x(self):
		if self.state is NULL: self.objval = 0
		else: self.objval = self.state[0].tot_profit

	def __copy__(self) -> state_py:
		cop_st = state_py(0, [0])
		free_state(cop_st.state, 1)
		cop_st.state = copy_state(self.state)
		cop_st.get_x()
		return cop_st

	def __str__(self) -> str:
		if self.state is NULL: return "NULL state"
		# print_state(&self.state[])
		for i in range(self.num_states):
			print_state(&self.state[i])
			print()
		return ""

	def __dealloc__(self) -> None:
		if self.state is not NULL:
			free_state(self.state, self.num_states)

	# def __del__(self):
	# 	del self.arr

	@property
	def objective_value(self):
		return self.state[0].tot_profit

	def __iter__(self):
		return [sw_tstbit(self.state[0].vector, i) for i in range(self.state[0].vector.bits)].__iter__()
	# return [self.state[0].vector.part[i] for i in range(self.state[0].vector.n)].__iter__()

	def integer_liste(self):
		step = [[
			self.state[0].vector.part[i] & 0xFFFFFFFF,
			(self.state[0].vector.part[i] >> 32) & 0xFFFFFFFF
		] for i in range(self.state[0].vector.n)]
		return [j for i in step for j in i]

	def assignment(self):
		return list(self.arr)

	def store(self, file):
		f = open(file, "w")
		f.write(f"{self.objval} ")
		for i in self.arr:
			f.write(f"{i} ")
		f.close()

	def update(self, state_py threshold, int sense) -> state_py:
		up = state_py(0, [0])
		free_state(up.state, up.num_states)
		up.state = <state_t *> updated(self.state, self.num_states, &up.num_states, threshold.state, sense)

		return up

	def read(self, str name, int n) -> None:
		# print(name)
		directoy = os.path.dirname(name)
		# print(directoy)
		value = str(name).split("states_")[0].replace(directoy + "/", "")
		# print(value, directoy)
		files = [f"{directoy}/{i}".encode() for i in os.listdir(directoy) if
		         value in i and "test" not in i and "states" in i]
		# print(files)
		# sys.stdout.flush()

		num_files = len(files)
		# print(num_files)
		sys.stdout.flush()
		cdef char** f = <char **> calloc(num_files, sizeof(char *))
		for i in range(num_files):
			# print(i)
			sys.stdout.flush()
			file_bytes = files[i]
			f[i] = <char *> calloc(len(file_bytes) + 1, sizeof(char))
			for j in range(len(file_bytes)):
				f[i][j] = file_bytes[j]

		free_state(self.state, self.num_states)
		self.state = read_states(f, num_files, &self.num_states, n)


def store(states: list[float, tuple[list[int], list[int]]], where: bytes) -> int:
	if os.path.exists(where): return 1

	file = open(where, "a")
	for i in states:
		file.write(f'{int(i[0])} ')
		for j in range(len(i[1])):
			file.write(f'{i[1][j]} {i[2][j]} ')
		file.write("\n")

	file.close()
	return 0

def read_nodes_wrapper(str name, n: int) -> int | state_py:
	if not os.path.exists(name):
		return 1

	res = state_py(0, [0])
	res.read(name, n)
	return res