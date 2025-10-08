cdef class circuit:

	def __cinit__(self):
		self.circ = <circuit_t *> init_circuit()

	def __init__(self):
		pass

	def __str__(self):
		print_circuit(self.circ)
		return ""

	cdef perform_qft(self):
		cdef sequence_t *seq = QFT(NULL, 10)
		cdef unsigned int *qubit_array = <unsigned int *> calloc(100000, sizeof(unsigned int))
		for i in range(100000):
			qubit_array[i] = i
		# qubit_mapping(qubit_array, self.circ)
		printf("%d\n", qubit_array[10])
		run_instruction(seq, qubit_array, 0, self.circ)
		free(qubit_array)
		free(seq)
		# print_sequence(seq)

	def compile(self):
		self.perform_qft()