from generate import location, read_instance
import os
import fcntl
import sys
from time import time

sys.path.append('../Thesis/')
from cbqs import MAXIMIZE
from cbqs import Model

def bench_quantum(size, index, max_m = -1, stop_val = 1, f = "plots/res.csv", stop_time = 1e9):
	c1, c2, c3 = read_instance(f'{location}/{size}_{index}')

	if max_m == -1:
		max_m = 100 * (size // 4) ** 2

	t1 = time()
	m = Model()
	x = m.add_variables(size)
	m.set_objective(sum(int(c1[i][j]) * x[i] * x[j] for i in x for j in x if i >= j), sense = MAXIMIZE)
	m.add_constraint(sum(2 * int(c3[i][j]) * x[i] * x[j] for i in x for j in x if i >= j) <= sum(int(c3[i][j]) for i in x for j in x if i >= j))
	m.add_constraint(sum(2 * int(c2[i][j]) * x[i] * x[j] for i in x for j in x if i >= j) >= sum(int(c2[i][j]) for i in x for j in x if i >= j))
	m.close()
	# print(m.objective)
	modeling_time = time() - t1
	print("Modeling time:", modeling_time)
	# print(m.constraint)

	def callback(a, b, c, d):
		# pass
		file = open(f, "a")
		try:
			fcntl.flock(file, fcntl.LOCK_EX)
			file.write(f"{size},{index},{-a},{c:.3f},{b},{d + modeling_time:.3f},iqs\n")
			file.flush()
			os.fsync(file.fileno())
		finally:
			fcntl.flock(file, fcntl.LOCK_UN)
			file.close()

	br = m.solve(M = max_m, num_workers = 1, results = "min", callback = callback, stop_val = -stop_val, stopping_time = int(stop_time))
	sol = m.final_state
	val = -m.objective_value
	m.reset()
	del x, m

	# print(br)
	# print(2 * 22.5 * int(2 ** (br / 2)))
	# file = open(f, "a")
	# file.write(f"{size},{index},{0},{modeling_time},{45 * int(2 ** (br / 2))},{0},nested-qs\n")
	# file.close()

	return sol, val
