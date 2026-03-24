import gurobipy as gp
import numpy as np
import os
# from iqs import Model, MAXIMIZE
from random import randint
from time import time
from hexaly.optimizer import HexalyOptimizer

location = "instances"

def generate_random_instance():
	# for size, index in product(sizes, indices):
	size = 3000
	index = 0
	t1 = time()
	while size < 3010:
		print(size, index, time() - t1)

		c1 = np.array([[randint(1, 10000) for _ in range(size)] for _ in range(size)])
		c1 = (c1 + c1.T)
		c2 = np.array([[randint(1, 10 * size) for _ in range(size)] for _ in range(size)])
		c2 = (c2 + c2.T)
		c3 = np.array([[randint(1, 10 * size) for _ in range(size)] for _ in range(size)])
		c3 = (c3 + c3.T)

		# if obj.value != 0: # varify feasibility
		os.makedirs(f"{location}/{size}_{index}/", exist_ok=True)
		np.save(f"{location}/{size}_{index}/c1.npy", c1)
		np.save(f"{location}/{size}_{index}/c2.npy", c2)
		np.save(f"{location}/{size}_{index}/c3.npy", c3)
		index += 1

		if index == 10:
			size += 500
			index = 0

def read_instance(name):
	c1 = np.load(f"{name}/c1.npy")
	c2 = np.load(f"{name}/c2.npy")
	c3 = np.load(f"{name}/c3.npy")
	# c4 = np.load(f"{name}/c4.npy")
	efficiency = np.sum(c1, axis = 1) / (np.sum(c2, axis = 1) + np.sum(c3, axis = 1))
	to_sort = sorted(zip(efficiency, range(len(efficiency))), key = lambda x: x[0], reverse = True)
	sorting = np.array([i for _, i in to_sort])
	c1 = c1[np.ix_(sorting, sorting)]
	c2 = c2[np.ix_(sorting, sorting)]
	c3 = c3[np.ix_(sorting, sorting)]

	for i in range(len(c1)):
		for j in range(len(c2)):
			if i < j:
				c1[i, j] = 0
				c2[i, j] = 0
				c3[i, j] = 0
	return c1, c2, c3

if __name__ == "__main__":
	generate_random_instance()