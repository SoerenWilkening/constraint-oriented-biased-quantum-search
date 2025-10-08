import os
from time import time
import numpy as np

from .Constants import *
from .Expression import Variable, Expression
from .SearchLib import state_py, new_constraint, run_sampling, set_seed, set_bias_wrapper, run_bfs, run_local_search, run_quantum_local_search, run_general_greedy
from copy import copy
from warnings import warn

from multiprocessing import shared_memory
from .StateGenerator import StateGenerator
from joblib import Parallel, delayed

from .CircuitBackendBinder import circuit

class Model:

	def __init__(self):
		self.gpu_imported: bool = False

		# self.gpu_executor: Executor | None = None

		self.calls = 0
		self.met = None
		self.objective: new_constraint = new_constraint()
		self.constraint: new_constraint = new_constraint()

		self.obj_expr = []
		self.con_expr = []

		self.sense = MAXIMIZE

		self.n: int = 0
		self.variables = {}

		self.initial_state: state_py | None = None

		self.solver = SATISFY

		self.runtime: float = 0
		self.feasible = 0
		self.grover_iterations: list[int] | int = 0
		self.quantum_cycles: list[int] | int = 0
		self.objective_value: list[int] | int = 0
		self.final_state: list[state_py] | state_py | list | None = None
		self.improved: bool = False

		self.gpu_compiled: bool = False

		self.constraints_compiled: bool = False

		self.circuit : circuit | None = None
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

	def add_variable(self, index: int = 0, name: str = "x", bound: int = 1) -> Variable | Expression:
		if bound > 1:
			number = int(np.floor(np.log2(bound))) + 1
			x = self.add_variables(number, name=name)
			expr = sum(2 ** i * x[list(x.keys())[i]] for i in range(number))
			self.add_constraint(expr <= bound)
			return expr

		x = Variable(max(index, self.n), f"{name}{max(index, self.n)})")
		self.variables[max(index, self.n)] = x
		self.n += 1
		return x

	def add_variables(self, n: int = 1, name: str = "x", bound = 1) -> dict:
		x = {}
		if bound > 1:
			for i in range(n):
				# print(i)
				x[i] = self.add_variable(self.n, name=name, bound=bound)
			return x
		for i in range(n):
			x[self.n + i] = Variable(self.n + i, f"{name}{self.n + i}")
			self.variables[self.n + i] = x[self.n + i]
		self.n += n

		return x

	def set_objective(self, objective: Expression | int | None = None, sense: int = MAXIMIZE) -> None:
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

	def add_constraint(self, constraint: Expression | int | None = None) -> None:
		expr = constraint
		expr.merge()
		# self.con_expr.append(expr)
		self.constraint.add_expression(expr)

	def manual_initial(self, P: int, assignment: list) -> None:
		self.initial_state = state_py(P, assignment)

	def compile(self):
		self.gpu_compiled = True
		# self.gpu_executor = Executor(self.n, self.n / 4, int(time()), self.linear_con_form, self.linear_obj_form,
		#                              len(self.constraint.liste()), self.constraint.liste(), self.objective.liste(),
		#                              self.solver)

	def worker_process(self, shm_name, index, shape,
	                   M, stopping_time, depth_look_ahead, stop_val, callback, max_delta, reset_delta):
		try:
			existing_shm = shared_memory.SharedMemory(shm_name)
			arr = np.ndarray(shape, dtype=np.float64, buffer=existing_shm.buf)
			set_seed(int(time() + os.getpid() * 1234) % (int(2 ** 16) - 1))
			res = run_sampling(self.initial_state, self.constraint, self.objective, M, stopping_time, depth_look_ahead, self.solver,
			                   stop_val, callback, max_delta, reset_delta)
			arr[index, 0] = res[0].objective_value()
			arr[index, 1] = res[1]
			arr[index, 2] = res[2]
			counter = 3
			for i in res[3]:
				arr[index, counter] = i
				counter += 1
		except KeyboardInterrupt:
			pass

	def __del__(self):
		if self.final_state is not None: del self.final_state
		if self.initial_state is not None: del self.initial_state
		del self.objective
		del self.constraint
		del self.circuit


	# def kill_children(self):
	# 	for pid in self.child_pid:
	# 		try:
	# 			os.kill(pid, signal.SIGTERM)
	# 		except ProcessLookupError:
	# 			pass
	# 	for pid in self.child_pid:
	# 		try:
	# 			os.waitid(pid, 0, 0)
	# 		except ChildProcessError:
	# 			pass

	def close(self):
		if not self.constraints_compiled:
			self.objective.process(self.n)
			self.constraint.process(self.n)
			# self.circuit = circuit()
			# self.circuit.compile()
			# print(self.circuit)
			self.constraints_compiled = True

	def general_greedy(self):
		if self.initial_state is not None:
			del self.initial_state
		self.manual_initial(0, [0] * self.n)
		run_general_greedy(self.initial_state, self.constraint, self.objective)


	def solve(self, M: int = -1, stopping_time: int = 300, bias: float | int = -1, stop_val: int = -1, callback = None, arch = "cpu",
	          max_delta = 7, reset_delta = True, depth_look_ahead = 0, num_workers:int=12,
	          results = "min", bfs = False) -> float | None:
		"""

		:param M:
		:param bias:
		:return:
			returns True if the Algorithm found a satisfying state
		"""
		if not self.constraints_compiled:
			raise ValueError("No constraints compiled")

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

		if bfs:
			s = StateGenerator(self)
			s.generate_gurobi_model()
			s.stategen()
			print(len(s.bfs))
			run_bfs(self.initial_state, self.constraint, self.objective, M, depth_look_ahead, self.solver,
			           stop_val, callback, max_delta, reset_delta)
			return

		t1 = time()
		global_opt: state_py = copy(self.initial_state)
		res = Parallel(n_jobs = num_workers, backend = "threading")(
		         delayed(run_sampling)(
			         self.initial_state,
			         self.constraint,
			         self.objective,
			         M, stopping_time,
			         depth_look_ahead,
			         self.solver,
                     stop_val, callback, max_delta, reset_delta,
			         global_opt) for _ in range(num_workers)
		         )

		self.objective_value = min([i[0].objective_value() for i in res])
		self.grover_iterations = min([i[1] for i in res])
		self.runtime = time() - t1
		self.final_state = res[0][0]
		return res[0][-1]


	def local_search(self, distance = 2, callback = None, stop_time = 1 << 20, max_worse_acceptances: int = 10, stopping_condition: int = STOPATFIRST):
		assert stopping_condition in [STOPATFIRST, STOPATBEST]
		if not self.initial_state: self.manual_initial(0, [0] * self.n)
		t1 = time()
		self.final_state = run_local_search(self.initial_state, self.constraint, self.objective, distance, stop_time, self.solver, -1,
		                                    callback, max_worse_acceptances, stopping_condition)
		self.runtime = time() - t1
		self.objective_value = self.final_state.objective_value()

	def quantum_local_search(self, distance, callback = None, num_workers = 1):
		Parallel(n_jobs = num_workers, backend="threading")(
			delayed(run_quantum_local_search)(
				self.initial_state,
				self.constraint,
				self.objective,
				distance,
				callback
			) for _ in range(num_workers)
		)
		# run_quantum_local_search(self.initial_state, self.constraint, self.objective, distance, callback)