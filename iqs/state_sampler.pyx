from copy import copy
from .SearchLib import set_bias_wrapper, QSearch_wrapper

cdef class approximate_state:

	def __cinit__(self, int n, bias):
		self.n = n
		self.state = <approximate_state_t *> init_approximete_state(self.n, bias)

	def __init__(self, int n, bias):
		self.n = n

	def __str__(self):
		print_approximate_state(self.state)
		return ""

	def __del__(self):
		free_approximate_state(self.state)

	@property
	def delta(self):
		return self.state.delta


	def opt_sampler(self, new_constraint obj, new_constraint con, state_py cur_sol, samples):
		# print(samples)
		# self.c_opt_sampler(obj, con, cur_sol, samples)
		cdef state_t * st = <state_t *> cur_sol.state;
		cdef new_constraints_t *ob = <new_constraints_t *> &obj.con;
		cdef new_constraints_t *co = <new_constraints_t *> &con.con;
		CSearch_opt_sampler(self.state, st, samples, co, ob, 1)
		# print("number good = ", self.state.num_good)

	# cdef c_opt_sampler(self, new_constraint obj , new_constraint con, state_py cur_sol, int samples):

	def QSearch(self, M):
		st = state_py(0, [0])
		cdef size_t it = 0
		cdef size_t rounds = 0
		cdef size_t index = 0

		cdef state_t *res = QSearch(self.state.good, self.state.num_good, &it, &rounds, M, &index)

		if res is NULL:
			del st
			return None, it, rounds

		st.state = res
		return st, it, rounds


	def exact_QSearch(self, obj, con, M, initial):
		bfs = state_py(0, [])
		bfs.read("/Users/sorenwilkening/Desktop/improved_quantum_search/Projects/Knapsack/KP_instances/n_25_c_8191_g_6_f_0.3_eps_0_s_100/states_0.0.txt", self.state.good[0].vector.bits)
		total_iterations = 0
		threshold: state_py = copy(initial)

		incumbents = []

		while True:
			up = bfs.update(threshold, 0)

			it = 0
			rounds = 0
			index = 0
			st, it, round = QSearch_wrapper(up, M)
			# print(st.objective_value, 2 * it + rounds)
			total_iterations += 2 * it + rounds

			if st is None:
				break
			else:
				del threshold
				threshold = st
				incumbents.append((-threshold.objective_value, total_iterations))

		return incumbents