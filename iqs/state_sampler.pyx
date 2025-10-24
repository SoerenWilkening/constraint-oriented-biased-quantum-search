
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

	def opt_sampler(self, obj, con, cur_sol, samples):
		print(samples)
		self.c_opt_sampler(obj, con, cur_sol, samples)

	cdef c_opt_sampler(self, new_constraint obj , new_constraint con, state_py cur_sol, int samples):
		cdef state_t * st = <state_t *> cur_sol.state;
		cdef new_constraints_t *ob = <new_constraints_t *> &obj.con;
		cdef new_constraints_t *co = <new_constraints_t *> &con.con;
		CSearch_opt_sampler(self.state, st, samples, co, ob, 1)
