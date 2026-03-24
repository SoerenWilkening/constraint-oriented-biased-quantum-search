from generate import location, read_instance
import os
import fcntl
import sys
from time import time

import numpy as np
from cbqs import MAXIMIZE
from cbqs import Model

def bench_quantum(size, index, max_m = -1, stop_val = 1, f = "plots/res.csv", stop_time = 1e9):
	c1, c2, c3 = read_instance(f'{location}/{size}_{index}')

	if max_m == -1:
		max_m = 100 * (size // 4) ** 2

	t1 = time()
	m = Model()
	x = m.add_variables(size)

	# Lower-triangular matrices (i >= j) for objective and constraints
	c1_lower = np.tril(c1).astype(np.int64)
	c2_lower = np.tril(c2).astype(np.int64)
	c3_lower = np.tril(c3).astype(np.int64)

	# Objective: sum(c1[i][j] * x[i] * x[j] for i >= j)
	m.set_objective(x @ (c1_lower @ x), sense=MAXIMIZE)

	# Constraints using matrix ops
	c3_sum = int(np.tril(c3).sum())
	m.add_constraint(x @ (2 * c3_lower @ x) <= c3_sum)

	c2_sum = int(np.tril(c2).sum())
	m.add_constraint(x @ (2 * c2_lower @ x) >= c2_sum)

	m.close()
	modeling_time = time() - t1
	print("Modeling time:", modeling_time)

	def callback(a, b, c, d):
		file = open(f, "a")
		try:
			fcntl.flock(file, fcntl.LOCK_EX)
			file.write(f"{size},{index},{-a},{c:.3f},{b},{d + modeling_time:.3f},iqs\n")
			file.flush()
			os.fsync(file.fileno())
		finally:
			fcntl.flock(file, fcntl.LOCK_UN)
			file.close()

	m.set_param('M', max_m)
	m.set_param('num_workers', 1)
	m.set_param('callback', callback)
	m.set_param('stop_val', -stop_val)
	m.set_param('stopping_time', int(stop_time))
	m.solve()
	sol = m.final_state
	val = -m.objective_value
	m.reset()
	del x, m

	return sol, val


# bench_quantum(500, 0)
