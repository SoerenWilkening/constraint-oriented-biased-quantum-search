from time import time
import gurobipy as gp
from .SearchLib import read_nodes_wrapper, store
from .Constants import OPTIMIZE, SATISFY
class StateGenerator:
	def __init__(self, model, path = "./"):
		self.model = model
		self.states: list[float, tuple[list[int], list[int]]] | list = []
		self.bfs = None
		self.num_bfs = 0

		self.gur_model = gp.Model()
		self.gur_model.setParam('OutputFlag', 0)
		self.file = f"{path}states_1.txt"


	def generate_gurobi_model(self):
		# generate gurobi model from own model
		self.vars = [self.gur_model.addVar(vtype = gp.GRB.BINARY) for _ in range(self.model.n)]

		def product(clause):
			gr_clause = clause[0]
			for i in clause[1:]:
				gr_clause *= self.vars[i]
			if self.model.solver == SATISFY and clause[0] < 0:
				gr_clause = 1 - gr_clause
			return gr_clause

		# model for optimization problems
		if self.model.solver == OPTIMIZE:
			self.gur_model.setObjective(sum([product(i) for i in self.model.obj_expr[0] if type(i) != int]), sense = gp.GRB.MINIMIZE)

			for i in self.model.con_expr:
				expr = list(i)
				# subtract potential again
				rhs = expr[-1] + sum(i[0] for i in expr[:-2] if i[0] < 0)
				self.gur_model.addConstr(sum([product(i) for i in expr[:-2]]) <= rhs)
		# For satisfiability we require a maxsat solver
		else:
			sat = self.gur_model.addVars(len(self.model.con_expr), vtype = gp.GRB.BINARY)
			# print(len(self.model.con_expr))
			counter = 0
			for i in self.model.con_expr:
				expr = list(i)
				# rhs = expr[-1] + sum(j[0] for j in expr[:-2] if j[0] < 0)
				self.gur_model.addConstr(sum([product(j) for j in expr[:-2]]) >= sat[counter])
				counter += 1
			self.gur_model.setObjective(-sum(sat[i] for i in sat), sense = gp.GRB.MINIMIZE)


	def stategen(self):
		self.counter = 0
		self.explored = 0
		self.reltime = time()
		self.time = time()
		self.prevtime = 0
		# only run stategen, if bfs was not executed

		# self.file = (f"{self.path}states_"
		#              f"{initial}.txt")
		# if all_feasible: self.file = f"{self.path}states_all_feasible.txt"

		if self.bfs is not None:
			return self.num_bfs

		exists = read_nodes_wrapper(self.file, self.model.n)
		if exists != 1:
			self.bfs = exists
			return len(self.bfs)

		self.model.initial_state.get_x()
		initial = self.model.initial_state.objective_value()
		self.store_counter = 0

		self.gur_model.setParam('MIPGap', .0)
		self.gur_model.optimize()
		assignment = [int(i.X) for i in self.gur_model.getVars()]
		opt = self.gur_model.ObjVal
		self.gur_model.reset()

		try:
			self.breadth_first_search(initial, 0, [], assignment, [], opt)
		except KeyboardInterrupt:
			self.file = f"interrupted_"

		# print("\r number states = ", len(self.__states))
		print(
			f"\r{self.explored / (2 ** (self.model.n + 1) - 1) * 100:10f}% | "
			f"{int(self.t / 3600) :4.0f}:{int(self.t / 60) % 60:2.0f}:{self.t % 60:2.0f} | "
			f"{len(self.states)} states "
		)
		store(self.states, self.file.encode())
		self.bfs = read_nodes_wrapper(self.file, self.model.n)
		return len(self.states)

	def breadth_first_search(self, threshold, level, assignment, sol, branch, ObjVal):
		if level == self.model.n:
			self.states.append([ObjVal, assignment, branch])
			if len(self.states) > 500000:
				f = str(self.file)
				f = f.replace("states", f"states_part_{self.store_counter}")
				store(self.states, f.encode())
				self.store_counter += 1
				self.states = []
			return

		self.counter += 1

		self.reltime += time() - self.prevtime
		self.prevtime = time()

		# if not happend:
		# !!! v2:
		#   -> previous solution is known and therefore the next assignment to come
		#   -> -> gurobi only has to be executed on the opposite assignment
		#   -> -> we know, since we arrived in this branch, that one solution exists:
		#   -> -> -> if the other assignment is feasible, we know, the quantum algorithm would branch
		#   -> -> -> even, if the ObjVal might be bad
		# -> add constraint x[level] == 0 ==> x[level] == 1 - self.vars[level].X
		# -> run gurobi
		# -> self.model.reset()
		# -> if threshold > (<) result and feasible
		# -> -> go deeper in recursion : level + 1, assingment <- assignment + [0]
		# -> remove constraint x[level] == 0

		# would the quantum algorithm branch out
		would_branch = self.model.constraint.eval_con_from_array(assignment + [1 - sol[level]])

		# determine if status update should be printed
		if self.reltime > 10:
			self.t = time() - self.time
			print(
				f"\r{self.explored / (2 ** (self.model.n + 1) - 1) * 100:.10f}% | "
				f"{int(self.t / 3600) :4.0f}:{int(self.t / 60) % 60:2.0f}:{self.t % 60:2.0f} | "
				f"{len(self.states)} states ", end = ""
			)
			self.reltime = 0


		x_l0 = self.gur_model.addConstr(self.vars[level] == 1 - sol[level], name = f"x{level}=={1 - sol[level]}")
		self.gur_model.reset()  # remove all stored data from the model
		self.gur_model.optimize()  # calculate the optimal solution

		if self.gur_model.SolCount > 0:  # fesibility check

			# obj = int(round(decimal.Decimal(self.model.ObjVal) * decimal.Decimal(10 ** self.digits)))
			obj = self.gur_model.ObjVal
			# if solver == "sat": obj = self.Con.count()
			if threshold < obj:
				self.breadth_first_search(
					threshold,
					level + 1,
					assignment + [1 - sol[level]],
					[int(i.X) for i in self.gur_model.getVars()],
					branch + [would_branch],
					obj)
				self.explored += 1
			else:
				self.explored += 2 ** (self.model.n - level) - 1
		else:
			self.explored += 2 ** (self.model.n - level) - 1
		self.gur_model.remove(x_l0)  # remove the constraint, since it's no longer required

		# the other branch still has to be examined
		# -> no need to run gurobi, since value is known
		x_l1 = self.gur_model.addConstr(self.vars[level] == sol[level], name = f"x{level}=={sol[level]}")

		self.breadth_first_search(
			threshold,
			level + 1,
			assignment + [sol[level]],
			sol,
			branch + [would_branch],
			ObjVal)
		# self.explored += 1
		self.gur_model.remove(x_l1)  # remove the constraint, since it's no longer required
		return


	# def test_states(self):
	# 	return self.bfs.update(self.model.initial_state, self.model.n / 4, self.sense)
	#
	# def analyse_tree(self):
	# 	updated = self.bfs.update(self.initial_state, self.sense)
	# 	return updated.analyse_tree(self.initial_state)
