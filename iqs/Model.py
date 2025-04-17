# import os
# import sys
import os
from time import time

import numpy as np

from iqs.Metal_executor import Executor
from .Constants import *
from .Expression import Variable, Expression2
from .SearchLib import state_py, new_constraint, run_ctg, set_seed, set_bias_wrapper
from copy import copy
from warnings import warn

from multiprocessing import shared_memory
import signal
import sys
import atexit


class Model:

	def __init__(self):
		self.gpu_imported: bool = False

		self.gpu_executor: Executor | None = None

		self.calls = 0
		self.met = None
		self.objective: new_constraint = new_constraint()
		self.constraint: new_constraint = new_constraint()

		self.sense = MAXIMIZE

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.solver = SATISFY

		self.runtime: float = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		self.objective_value: list[int] | int = 0
		self.final_state: list[state_py] | state_py | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False
		# set_seed(time())

	def __copy__(self):
		new_m = Model()
		new_m.objective = copy(self.objective)
		new_m.constraint = copy(self.constraint)
		new_m.initial_state = copy(self.initial_state)
		new_m.solver = self.solver
		new_m.sense = self.sense
		return new_m

	def __str__(self):
		if not self.improved:
			return "No better solution found"
		return f"""
Found solution with Objective = {self.objective_value}
using either {self.grover_iterations} grover iterations 
or {self.runtime}s sampling
		"""

	def reset(self):
		self.runtime: float = 0
		self.quantum_cycles: int = 0
		self.objective_value: int = 0
		self.final_state: state_py | None = None
		self.improved: bool = False

	def add_variable(self, index: int = 0, name: str = "x") -> Variable:
		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x") -> dict:
		x = {}
		for i in range(n):
			x[self.n + i] = Variable(self.n + i, f"{name}{self.n + i}")
			self.variables[self.n + i] = x[self.n + i]
		self.n += n

		return x

	def set_objective(self, objective: Expression2 | int | None = None, sense: int = MAXIMIZE) -> None:
		if sense not in [MINIMIZE, MAXIMIZE]:
			raise TypeError

		self.sense = sense
		self.solver = OPTIMIZE
		expr = objective
		expr.merge()
		if sense == MINIMIZE:
			expr = expr <= 0
		else:
			expr = expr >= 0

		self.objective.add_expression(expr)

	def add_constraint(self, constraint: Expression2 | int | None = None) -> None:
		expr = constraint
		expr.merge()
		self.constraint.add_expression(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	def compile(self):
		self.gpu_compiled = True
		self.gpu_executor = Executor(self.n, self.n / 4, int(time()), self.linear_con_form, self.linear_obj_form,
		                             len(self.constraint.liste()), self.constraint.liste(), self.objective.liste(),
		                             self.solver)

	def worker_process(self, shm_name, index, shape,
	                   M, depth_look_ahead, stop_val, callback, max_delta, reset_delta):
		try:
			existing_shm = shared_memory.SharedMemory(shm_name)
			arr = np.ndarray(shape, dtype=np.float64, buffer=existing_shm.buf)
			set_seed(time() + os.getpid() * 1234)

			res = run_ctg(self.initial_state, self.constraint, self.objective, M, depth_look_ahead, self.solver,
			               stop_val, callback, max_delta, reset_delta)
			# print(res)
			arr[index, 0] = res[0].objective_value()
			arr[index, 1] = res[1]
		except KeyboardInterrupt:
			pass

	def kill_children(self):
		for pid in self.child_pid:
			try:
				os.kill(pid, signal.SIGTERM)
			except ProcessLookupError:
				pass
		for _ in range(len(self.child_pid)):
			try:
				os.wait()
			except ChildProcessError:
				pass

	def cleanup(self):
		if os.getpid() == self.parent_pid:
			self.shm.close()
			self.shm.unlink()

	def solve(self, M: int = -1, bias: float | int = -1, stop_val: int = -1, callback = None, arch = "cpu",
	          max_delta = 7, reset_delta = True, depth_look_ahead = 0, num_workers:int=0,
	          results = "min") -> float | None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		assert results in ["min", "average"]

		self.calls += 1
		# set_seed(time() + 10 * self.calls)

		if self.solver == SATISFY:
			if M != -1: warn("Defined M will be ignored when solving SAT")
			if bias != -1: warn("Defined bias will be ignored when solving SAT")
			if stop_val != -1: warn("Defined stop_val will be ignored when solving SAT")

		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		if M == -1: M = self.n ** 2 // 16
		if bias == -1: bias = self.n / 4
		set_bias_wrapper(bias)


		if arch == "gpu":
			raise TypeError("needs some fixing, currently doesnt seems to work properly!")

			if not self.gpu_compiled:
				self.compile()

			initial = self.initial_state.integer_liste()
			initial = initial[: min(len(initial), int(np.ceil(self.n / 32)))]

			res, oracle, t = self.gpu_executor.gpu_qmax_search(self.n, M, 0, initial, callback)
			self.objective_value = res
			self.runtime = t
			self.grover_iterations = oracle
			self.quantum_cycles = oracle
			return

		t1 = time()
		shape = (num_workers, 2)
		self.shm = shared_memory.SharedMemory(create = True, size = np.prod(shape) * np.int64().itemsize)
		arr = np.ndarray(shape, dtype = np.float64, buffer=self.shm.buf)

		atexit.register(self.cleanup)

		self.child_pid = []
		self.parent_pid = os.getpid()

		try:
			for i in range(num_workers):
				pid = os.fork()
				if pid == 0:
					self.worker_process(self.shm.name, i, shape, M, depth_look_ahead, stop_val, callback, max_delta, reset_delta)
					exit(0)  # Terminate child process after work is done
				else:
					self.child_pid.append(pid)

			for _ in range(num_workers):
				os.wait()
		except KeyboardInterrupt:
			self.kill_children()
			self.cleanup()
			sys.exit(1)

		self.runtime = time() - t1 # stores classical runtime of all the complete execution
		if results == "min":
			self.objective_value =  min(i[0] for i in arr)
			self.grover_iterations = min(list(i[1] for i in arr if i[0] == self.objective_value))
		else:
			self.objective_value = np.mean([i[0] for i in arr])
			self.grover_iterations = np.mean([i[1] for i in arr])

		self.cleanup()